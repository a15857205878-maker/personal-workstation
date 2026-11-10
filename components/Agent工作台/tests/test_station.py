from pathlib import Path
import hashlib
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from task_station.core import Service


class FakeModels:
    def __init__(self):
        self.calls = []
        self.after_review = None
        self.answers = ['发现两项需要澄清，建议精简第二段。', '这是经审改后的完整正文。']

    def capabilities(self):
        return {role: dict(label=role, mode='test', can_run=True, detail='fake') for role in
                ('text_1', 'text_2', 'frontend', 'backend_and_integration',
                 'presentation','presentation_gemini','text_claude','excel_gemini','image_gemini','animation_gemini','research_kimi', 'excel', 'research_sources')}

    def run(self, role, prompt, cancel, chunk, folder):
        self.calls.append(dict(role=role, prompt=prompt, folder=folder))
        answer = self.answers[len(self.calls) - 1]
        chunk(answer)
        if len(self.calls) == 1 and self.after_review:
            self.after_review()
        return answer


class StationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fake = FakeModels()
        self.gate = threading.Lock()
        self.service = Service(Path(self.tmp.name), self.fake, execution_gate=self.gate)

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def source(self, text='原始初稿，第二段需要完善。'):
        task = self.service.call('create', dict(task_type='text', role='text_1', instruction='测试初稿'))
        return self.service.call('save_text', dict(id=task['id'], text=text))

    def review(self, source, **kw):
        return self.service.call('review_draft', dict(id=source['id'], source='result',
                                 reviewer='backend_and_integration', editor='text_1', **kw))

    def finish(self, task):
        self.service.call('submit', dict(id=task['id']))
        deadline = time.monotonic() + 3
        while self.service.jobs and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(self.service.jobs)
        return self.service.call('get', dict(id=task['id']))

    def test_two_model_review_preserves_source_and_creates_real_versions(self):
        source = self.source()
        task = self.review(source)
        self.assertNotEqual(task['id'], source['id'])
        self.assertEqual(self.fake.calls, [])
        result = self.finish(task)
        self.assertEqual(result['status'], '结果待确认')
        self.assertEqual([c['role'] for c in self.fake.calls], ['backend_and_integration', 'text_1'])
        self.assertIn('原始初稿', self.fake.calls[0]['prompt'])
        self.assertIn(self.fake.answers[0], self.fake.calls[1]['prompt'])
        self.assertEqual(result['result'], self.fake.answers[1])
        versions = result['workflow']['versions']
        self.assertEqual([v['number'] for v in versions], [1, 2])
        for v in versions:
            data = self.service.file_path(task['id'], v['name']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), v['sha256'])
        self.assertEqual(self.service.call('get', {'id': source['id']})['result'], source['result'])
        self.assertFalse(self.gate.locked())

    def test_cancellation_after_review_does_not_call_editor_or_create_v2(self):
        task = self.review(self.source())
        self.fake.after_review = lambda: self.service.call('cancel', {'id': task['id']})
        result = self.finish(task)
        self.assertEqual(result['status'], '已取消')
        self.assertEqual(len(self.fake.calls), 1)
        self.assertFalse(any('v002' in f['name'] for f in result['files']))

    def test_same_role_and_unsupported_source_rejected(self):
        source = self.source()
        with self.assertRaises(ValueError):
            self.service.call('review_draft', dict(id=source['id'], source='result',
                              reviewer='text_1', editor='text_1'))
        with self.assertRaises(ValueError):
            self.service.call('review_draft', dict(id=source['id'], source='file:../x.md',
                              reviewer='backend_and_integration', editor='text_1'))

    def test_large_source_and_large_review_are_not_silently_truncated(self):
        source = self.source('字' * 9001)
        with self.assertRaises(ValueError):
            self.review(source)
        self.fake.answers[0] = '字' * 6001
        task = self.review(self.source())
        result = self.finish(task)
        self.assertEqual(result['status'], '失败')
        self.assertEqual(len(self.fake.calls), 1)
        self.assertFalse(any('v002' in f['name'] for f in result['files']))

    def test_file_snapshot_is_an_independent_byte_exact_copy(self):
        source = self.source()
        file = Path(self.tmp.name) / '稿件.md'
        raw = '\ufeff# 标题\r\n原始内容\r\n'.encode('utf-8')
        file.write_bytes(raw)
        source = self.service.import_file(source['id'], file)
        task = self.service.call('review_draft', dict(id=source['id'], source='file:稿件.md',
                                 reviewer='backend_and_integration', editor='text_1'))
        snapshot = task['workflow']['versions'][0]
        self.assertEqual(self.service.file_path(task['id'], snapshot['name']).read_bytes(), raw)
        file.write_text('外部原件后来改了', encoding='utf-8')
        self.assertEqual(self.service.file_path(task['id'], snapshot['name']).read_bytes(), raw)

    def test_legacy_gate_blocks_station_before_any_model_call(self):
        task = self.source()
        self.gate.acquire()
        try:
            with self.assertRaises(ValueError):
                self.service.call('submit', {'id': task['id']})
            self.assertEqual(self.fake.calls, [])
            self.assertEqual(self.service.call('get', {'id': task['id']})['status'], '结果待确认')
        finally:
            self.gate.release()

    def test_enqueue_write_failure_releases_shared_gate(self):
        task = self.source()
        with patch.object(self.service, '_save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.service.call('submit', {'id': task['id']})
        self.assertFalse(self.gate.locked())
        self.assertEqual(self.fake.calls, [])

    def test_finished_review_is_not_reexecuted_in_place(self):
        task = self.review(self.source())
        self.finish(task)
        review_file = self.service.file_path(task['id'], 'review.md')
        original = review_file.read_bytes()
        with self.assertRaises(ValueError):
            self.service.call('submit', {'id': task['id']})
        self.assertEqual(review_file.read_bytes(), original)
        self.assertEqual(len(self.fake.calls), 2)

    def test_custom_review_requirements_reach_both_models(self):
        task = self.review(self.source(), requirements='检查虚构功能，控制在600字以内。')
        self.assertIn('检查虚构功能', task['requirements'])
        self.finish(task)
        for call in self.fake.calls:
            self.assertIn('检查虚构功能，控制在600字以内。', call['prompt'])
            self.assertIn('不编造数据或引用', call['prompt'])

    def test_review_requirements_validate_before_creating_task(self):
        source = self.source()
        for invalid in [42, '字' * 4001]:
            with self.assertRaises(ValueError):
                self.review(source, requirements=invalid)
        self.assertEqual(len(self.service.call('list')), 1)

    def test_delete_requires_archived_confirmed_idle_task(self):
        task = self.source()
        with self.assertRaises(ValueError):
            self.service.call('delete', dict(id=task['id'], confirm=True))
        self.service.call('archive', dict(id=task['id']))
        for confirm in [None, False, 'true']:
            with self.assertRaises(ValueError):
                self.service.call('delete', dict(id=task['id'], confirm=confirm))
        self.service.jobs[task['id']] = threading.Event()
        try:
            with self.assertRaises(ValueError):
                self.service.call('delete', dict(id=task['id'], confirm=True))
        finally:
            self.service.jobs.pop(task['id'])
        self.assertEqual(len(self.service.call('list', dict(archived=True))), 1)

    def test_delete_removes_history_preserves_files_and_other_review(self):
        source = self.source()
        task = self.review(source)
        folder = self.service.folder(source['id'])
        file = folder / 'response.txt'
        file.write_text('保留文件', encoding='utf-8')
        self.service.call('archive', dict(id=source['id']))
        result = self.service.call('delete', dict(id=source['id'], confirm=True))
        self.assertTrue(result['deleted'])
        self.assertEqual(file.read_text(encoding='utf-8'), '保留文件')
        self.assertEqual(self.service.call('list', dict(archived=True)), [])
        with self.assertRaises(ValueError):
            self.service.call('get', dict(id=source['id']))
        revised = self.finish(task)
        self.assertEqual(revised['status'], '结果待确认')
        self.assertEqual(len(self.service.call('list')), 1)

    def test_ppt_handoff_preserves_full_body_without_execution(self):
        source=self.source('修订正文：样本12人，没有对照组。\r\n \n')
        task=self.service.call('ppt_draft',dict(id=source['id'],instruction='制作6页，青绿色。'))
        self.assertEqual(task['task_type'],'pptx')
        self.assertEqual(task['role'],'presentation_gemini')
        self.assertEqual(task['status'],'草稿')
        self.assertEqual(self.fake.calls,[])
        self.assertIn(source['result'],task['materials'])
        self.assertIn('制作6页，青绿色。',task['prompt'])
        self.assertEqual(task['handoff_source']['task_id'],source['id'])
        self.assertEqual(task['handoff_source']['sha256'],hashlib.sha256(source['result'].encode('utf-8')).hexdigest())
        self.service.call('archive',dict(id=source['id']))
        self.service.call('delete',dict(id=source['id'],confirm=True))
        self.assertIn(source['result'],self.service.call('get',dict(id=task['id']))['materials'])

    def test_ppt_handoff_rejects_unusable_source_and_invalid_requirements(self):
        source=self.source('字'*20001)
        with self.assertRaises(ValueError):self.service.call('ppt_draft',dict(id=source['id']))
        source=self.source()
        for requirement in [22,'字'*2001]:
            with self.assertRaises(ValueError):self.service.call('ppt_draft',dict(id=source['id'],instruction=requirement))
        self.service.call('archive',dict(id=source['id']))
        with self.assertRaises(ValueError):self.service.call('ppt_draft',dict(id=source['id']))
        empty=self.service.call('create',dict(task_type='text',role='text_1',instruction='无正文'))
        with self.assertRaises(ValueError):self.service.call('ppt_draft',dict(id=empty['id']))
        with self.service.lock:
            task=self.service._load(empty['id']);task.update(status='执行中',result='未完成的内容');self.service._save(task)
        with self.assertRaises(ValueError):self.service.call('ppt_draft',dict(id=empty['id']))

    def test_tool_harness_is_not_a_bounded_text_reviewer(self):
        source=self.source()
        caps=self.fake.capabilities()
        caps['frontend']['mode']='deepseek_harness'
        with patch.object(self.fake,'capabilities',return_value=caps):
            with self.assertRaises(ValueError):
                self.service.call('review_draft',dict(id=source['id'],source='result',reviewer='frontend',editor='text_1'))


if __name__ == '__main__':
    unittest.main()
