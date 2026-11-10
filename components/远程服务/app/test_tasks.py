import json
import tempfile
import time
import unittest
import os
from unittest.mock import patch
from pathlib import Path

from tasks import TaskManager


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.manager = TaskManager(self.root, start_worker=False)

    def tearDown(self):
        self.manager.close()
        self.tmp.cleanup()

    def create(self, **changes):
        payload = {'goal': '把资料整理成报告 👋', 'agent': 'demo', 'client_id': 'request-1', 'attachments': []}
        payload.update(changes)
        return self.manager.create(payload)

    def wait(self, task_id):
        for _ in range(150):
            task = self.manager.get(task_id)
            if task['status'] not in ('queued', 'running'):
                return task
            time.sleep(.02)
        self.fail('task did not finish')

    def test_coding_root_junction_is_rejected_before_creation(self):
        with patch('pathlib.Path.is_junction',lambda path:path.name=='代码项目'),self.assertRaises(ValueError):
            self.create(agent='codex-deepseek-code')

    def test_demo_lifecycle_artifacts_and_idempotency(self):
        first = self.create()
        self.assertEqual(self.create()['id'], first['id'])
        self.assertEqual(len(self.manager.list()), 1)
        self.manager.start()
        task = self.wait(first['id'])
        self.assertEqual(task['status'], 'completed')
        self.assertGreaterEqual(len(task['completed_parts']), 2)
        self.assertGreaterEqual(len(task['artifacts']), 1)
        self.assertEqual(len(task['artifacts']), 2)
        report = next(item for item in task['artifacts'] if item['path'].endswith('.md'))
        artifact = self.manager.artifact_path(task['id'], report['path'])
        self.assertTrue(artifact.is_file())
        self.assertIn('演示', artifact.read_text(encoding='utf-8'))
        self.assertTrue(task['number'].startswith('T-'))

    def test_cancel_queued_task_and_restart(self):
        task = self.create()
        self.manager.cancel(task['id'])
        self.manager.start()
        self.assertEqual(self.wait(task['id'])['status'], 'cancelled')
        self.manager.close()
        self.manager = TaskManager(self.root, start_worker=False)
        self.assertEqual(self.manager.get(task['id'])['status'], 'cancelled')

    def test_restart_marks_running_as_needing_attention(self):
        task = self.create()
        self.manager.update(task['id'], status='running')
        self.manager.close()
        self.manager = TaskManager(self.root, start_worker=False)
        self.assertEqual(self.manager.get(task['id'])['status'], 'needs_attention')

    def test_artifact_scan_failure_preserves_result_and_worker_continues(self):
        first=self.create(client_id='first')
        second=self.create(client_id='second')
        original=self.manager.collect_artifacts
        calls=[]
        def scan(task_id):
            if task_id==first['id']:raise PermissionError('temporary file access')
            return original(task_id)
        def runner(task,workspace,report,*args):
            calls.append(task['id'])
            report('工作完成','阶段成果已记录')
            return '执行成果已完成'
        with patch.object(self.manager,'collect_artifacts',side_effect=scan),patch('tasks.RUNNERS',{'demo':runner}):
            self.manager.start()
            self.wait(first['id'])
            self.assertEqual(self.wait(second['id'])['status'],'completed')
            saved=self.manager.get(first['id'])
            self.assertEqual(saved['status'],'completed')
            self.assertEqual(saved['result'],'执行成果已完成')
            self.assertIn('成果',saved['error'])
            self.assertEqual(calls,[first['id'],second['id']])

    def test_artifact_warning_does_not_replace_execution_failure(self):
        task=self.create()
        def fail(*args):raise RuntimeError('actual execution failure')
        with patch.object(self.manager,'collect_artifacts',side_effect=PermissionError('locked file')),patch('tasks.RUNNERS',{'demo':fail}):
            self.manager.start()
            self.manager.queue.join()
        saved=self.manager.get(task['id'])
        self.assertEqual(saved['status'],'failed')
        self.assertIn('actual execution failure',saved['error'])
        self.assertIn('成果',saved['error'])

    def test_unreadable_directory_preserves_previous_artifact_list(self):
        task=self.create()
        workspace=self.manager.workspace(task['id'])
        (workspace/'report.txt').write_text('already generated',encoding='utf-8')
        before=self.manager.collect_artifacts(task['id'])['artifacts']
        original=os.scandir
        def deny(path):
            if Path(path)==workspace:raise PermissionError('directory temporarily unavailable')
            return original(path)
        with patch('tasks.os.scandir',side_effect=deny):
            self.manager._collect_safely(task['id'])
        saved=self.manager.get(task['id'])
        self.assertEqual(saved['artifacts'],before)
        self.assertIn('成果',saved['error'])

    def test_bad_input_and_artifact_path_escape(self):
        for changes in [{'goal': ' '}, {'agent': 'unknown'}, {'agent': []}, {'goal': 'x'*20001}, {'attachments': ['../secret']}, {'client_id': ''}]:
            with self.assertRaises(ValueError):
                self.create(**changes)
        task = self.create()
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.manager.artifact_path(task['id'], '../../secret.txt')

    def test_attachment_snapshot_and_missing_file(self):
        upload = self.manager.uploads / 'sample.txt'
        upload.write_text('输入资料', encoding='utf-8')
        task = self.create(attachments=['sample.txt'])
        copied = self.manager.workspace(task['id']) / 'inputs' / 'sample.txt'
        self.assertEqual(copied.read_text(encoding='utf-8'), '输入资料')
        self.assertEqual(task['attachments'], ['sample.txt'])
        with self.assertRaises(ValueError):
            self.create(client_id='missing', attachments=['missing.txt'])

    def test_cancel_running_preserves_real_completed_parts(self):
        task = self.create()
        self.manager.start()
        for _ in range(100):
            current = self.manager.get(task['id'])
            if current['completed_parts']:
                break
            time.sleep(.02)
        self.assertGreaterEqual(len(current['completed_parts']), 1)
        cancelled = self.manager.cancel(task['id'])
        self.assertEqual(cancelled['status'], 'cancelled')
        self.manager.close()
        after = self.manager.get(task['id'])
        self.assertEqual(after['status'], 'cancelled')
        self.assertGreaterEqual(len(after['completed_parts']), 1)

    def test_artifacts_do_not_descend_into_inputs_or_dependencies(self):
        task = self.create()
        workspace = self.manager.workspace(task['id'])
        (workspace / 'node_modules' / 'package').mkdir(parents=True)
        (workspace / 'node_modules' / 'package' / 'dependency.txt').write_text('excluded')
        (workspace / 'output.md').write_text('actual result')
        original = os.scandir
        def checked_scandir(path):
            if Path(path).name in {'node_modules', 'inputs'}:
                raise AssertionError('Artifact scan descended into an excluded directory')
            return original(path)
        with patch('os.scandir', checked_scandir):
            task = self.manager.collect_artifacts(task['id'])
        self.assertEqual([item['path'] for item in task['artifacts']], ['output.md'])


if __name__ == '__main__':
    unittest.main()
