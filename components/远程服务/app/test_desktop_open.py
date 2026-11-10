import threading
import time
import unittest
from unittest.mock import Mock
from desktop_open import DesktopOpenManager

THREAD = '01a17e10-8434-76c2-ad83-b9141d1232a8'
OTHER = '01a17e09-26f6-7c43-beef-1c1f59058625'


class DesktopOpenTests(unittest.TestCase):
    def setUp(self):
        self.tasks = Mock(lock=threading.RLock())
        self.tasks.list.return_value = []
        self.tasks.get.return_value = {'remote_session': THREAD, 'goal': '目标任务'}
        self.reader = Mock()
        self.reader.get.return_value = {'title': '目标会话'}
        self.replies = Mock(lock=threading.RLock())
        self.replies.is_sending.return_value = False
        self.replies.has_pending.return_value = False
        self.release = threading.Event()
        self.result = 0
        self.opener = Mock()
        self.now = time.time()
        self.manager = DesktopOpenManager(self.tasks, self.reader, self.replies,
            prompt=self.prompt, opener=self.opener, clock=lambda: self.now)

    def prompt(self, title, deadline, stop):
        self.release.wait(2)
        return self.result

    def tearDown(self):
        self.release.set()
        self.manager.close()

    def finish(self, request):
        self.release.set()
        for _ in range(100):
            data = self.manager.get(request['request_id'])
            if data['status'] != 'pending':
                return data
            time.sleep(.01)
        self.fail('确认未结束')

    def test_confirmation_opens_exact_saved_target_and_deduplicates(self):
        first = self.manager.request(task_id='task')
        self.assertEqual(first['status'], 'pending')
        self.opener.assert_not_called()
        self.assertEqual(first['request_id'], self.manager.request(thread_id=THREAD)['request_id'])
        self.assertEqual(self.finish(first)['status'], 'opened')
        self.opener.assert_called_once_with('codex://threads/' + THREAD)

    def test_timeout_decline_and_error_never_open(self):
        for code, status in [(2, 'background'), (3, 'expired'), (1, 'failed')]:
            self.release.clear()
            self.result = code
            request = self.manager.request(thread_id=THREAD)
            self.assertEqual(self.finish(request)['status'], status)
        self.opener.assert_not_called()

    def test_late_confirmation_never_opens(self):
        request = self.manager.request(thread_id=THREAD)
        self.now += 16
        self.assertEqual(self.finish(request)['status'], 'expired')
        self.opener.assert_not_called()

    def test_same_target_busy_blocks_but_other_task_does_not(self):
        self.tasks.list.return_value = [{'remote_session': OTHER, 'status': 'running'}]
        request = self.manager.request(thread_id=THREAD)
        self.replies.is_sending.return_value = True
        self.replies.has_pending.return_value = True
        self.assertEqual(self.finish(request)['status'], 'blocked')
        self.opener.assert_not_called()
        self.assertEqual(self.manager.request(thread_id=THREAD)['status'], 'blocked')

    def test_task_target_change_during_confirmation_blocks(self):
        request = self.manager.request(task_id='task')
        self.tasks.get.return_value = {'remote_session': OTHER}
        self.assertEqual(self.finish(request)['status'], 'blocked')
        self.opener.assert_not_called()

    def test_invalid_or_mismatched_target_rejected(self):
        for payload in [{}, {'thread_id': 'bad'}, {'task_id': 'task', 'thread_id': OTHER}]:
            with self.assertRaises(ValueError):
                self.manager.request(**payload)
        self.opener.assert_not_called()

    def test_close_prevents_confirmed_open(self):
        request = self.manager.request(thread_id=THREAD)
        self.manager.close()
        self.assertEqual(self.finish(request)['status'], 'cancelled')
        self.opener.assert_not_called()

    def test_opener_failure_is_reported(self):
        self.opener.side_effect = OSError('protocol unavailable')
        self.assertEqual(self.finish(self.manager.request(thread_id=THREAD))['status'], 'failed')

    def test_generic_launch_checks_all_background_work(self):
        self.tasks.list.return_value = [{'remote_session': OTHER, 'status': 'running'}]
        self.assertEqual(self.manager.request(application=True)['status'], 'blocked')
        self.tasks.list.return_value = []
        request = self.manager.request(application=True)
        self.assertEqual(self.finish(request)['status'], 'opened')
        self.opener.assert_called_once_with('shell:AppsFolder\\OpenAI.Codex_2p2nqsd0c76g0!App')

    def test_expiry_during_final_index_read_never_opens(self):
        def read(thread):
            self.now += 16
            return {'title': '目标会话'}
        request = self.manager.request(thread_id=THREAD)
        self.reader.get.side_effect = read
        self.assertEqual(self.finish(request)['status'], 'expired')
        self.opener.assert_not_called()

    def test_waiting_phone_instruction_blocks_desktop_open_between_retries(self):
        self.replies.has_pending.return_value = True
        self.replies.is_sending.return_value = False
        request=self.manager.request(thread_id=THREAD)
        self.assertEqual(request['status'],'blocked')
        self.opener.assert_not_called()
