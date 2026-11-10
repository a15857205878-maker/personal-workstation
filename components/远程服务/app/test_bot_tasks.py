import tempfile
import unittest
from pathlib import Path
from bot_tasks import create_bot_task
from tasks import TaskManager
from adapters import codex_command


class BotTaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.manager = TaskManager(Path(self.tmp.name), start_worker=False)
        (self.manager.uploads / 'sample.png').write_bytes(b'\x89PNG\r\n\x1a\nfixture')

    def tearDown(self):
        self.manager.close()
        self.tmp.cleanup()

    def test_image_only_default_and_retry(self):
        payload = {'text': '', 'attachments': ['sample.png'], 'request_id': 'one'}
        task = create_bot_task(self.manager, payload)
        self.assertEqual(task['goal'], '请查看并说明所附图片内容')
        self.assertEqual(task['agent'], 'codex')
        self.assertEqual(task['attachments'], ['sample.png'])
        self.assertEqual(create_bot_task(self.manager, payload)['id'], task['id'])
        self.assertEqual(len(self.manager.list()), 1)

    def test_text_and_image_same_task_and_new_requests_are_independent(self):
        payload = {'text': '请解释截图', 'attachments': ['sample.png'], 'request_id': 'first'}
        first = create_bot_task(self.manager, payload)
        second = create_bot_task(self.manager, dict(payload, request_id='second'))
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(first['goal'], '请解释截图')
        self.assertTrue((self.manager.workspace(first['id']) / 'inputs/sample.png').exists())

    def test_review_mode_readonly_and_idempotency_conflict(self):
        payload = {'text': '检查错误', 'attachments': ['sample.png'], 'request_id': 'one', 'mode': 'review'}
        task = create_bot_task(self.manager, payload)
        self.assertEqual(task['mode'], 'review')
        command = codex_command('codex', task, self.manager.workspace(task['id']), Path('final.txt'))
        self.assertEqual(command[command.index('--sandbox') + 1], 'read-only')
        self.assertIn('--image', command)
        self.assertNotIn('resume', command)
        with self.assertRaises(ValueError):
            create_bot_task(self.manager, dict(payload, mode='task'))

    def test_invalid_empty_review_and_unsupported_images(self):
        (self.manager.uploads / 'photo.heic').write_bytes(b'heic')
        for payload in [{}, {'text': '审查', 'mode': 'review', 'request_id': 'r'},
                        {'attachments': ['photo.heic'], 'request_id': 'h'},
                        {'text': 'x', 'mode': 'bad', 'request_id': 'b'},
                        {'text': 'x', 'attachments': ['../outside.png'], 'request_id': 'p'}]:
            with self.assertRaises(ValueError):
                create_bot_task(self.manager, payload)
