import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from tasks import TaskManager
from artifact_preview import PreviewService


PNG=bytes.fromhex('89504e470d0a1a0a')+b'fake'


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.tasks=TaskManager(Path(self.tmp.name),start_worker=False)
        self.task=self.tasks.create({'goal':'预览测试','agent':'demo','client_id':'preview'})
        self.source=self.tasks.workspace(self.task['id'])/'中文 报告.txt'
        self.source.write_text('原文',encoding='utf-8')
        self.tasks.collect_artifacts(self.task['id'])
        self.calls=[]
        def convert(source,out,stop):
            self.calls.append(source.read_text(encoding='utf-8'))
            (out/'document.pdf').write_bytes(b'%PDF-1.4\nstatic')
            (out/'page-1.png').write_bytes(PNG)
            return {'pages':1}
        self.service=PreviewService(self.tasks,converter=convert)

    def tearDown(self):
        self.service.close();self.tasks.close();self.tmp.cleanup()

    def create(self):return self.service.create(self.task['id'],self.source.name)

    def wait(self,key):
        for _ in range(200):
            state=self.service.get(key)
            if state['status'] in ('ready','failed'):return state
            time.sleep(.01)
        self.fail('preview did not settle')

    def test_workbench_bytes_reuse_converter_and_viewer_without_touching_native_tasks(self):
        before=self.tasks.get(self.task['id'])
        native=self.create();self.wait(native['id'])
        receipt=self.service.create_bytes(self.task['id'],self.source.name,b'workbench content')
        ready=self.wait(receipt['id']);self.assertEqual(ready['status'],'ready')
        self.assertTrue(ready['viewer_url'].startswith('/preview-viewer?preview_id='))
        self.assertTrue(ready['original_url'].startswith('/api/workbench-artifact?id='))
        self.assertNotEqual(native['id'],ready['id'])
        self.assertEqual(self.service.create_bytes(self.task['id'],self.source.name,b'workbench content')['id'],ready['id'])
        self.assertEqual(self.tasks.get(self.task['id']),before);self.assertEqual(self.source.read_text(encoding='utf-8'),'原文')
        self.assertEqual(self.service.asset(ready['id'],'document.pdf').read_bytes()[:4],b'%PDF')
        self.assertNotIn(self.tmp.name,json.dumps(ready))

    def test_collaboration_pdf_keeps_original_source_and_separate_cache(self):
        task=self.service.create_bytes(self.task['id'],'report.pptx',b'fixture')
        collaboration=self.service.create_bytes(self.task['id'],'report.pptx',b'fixture',kind='collaboration')
        ready=self.wait(collaboration['id']);self.assertEqual(ready['status'],'ready')
        self.assertIn('&kind=collaboration',ready['original_url']);self.assertNotEqual(task['id'],collaboration['id'])
        self.assertEqual(self.tasks.get(self.task['id'])['artifacts'][0]['name'],self.source.name)
        with self.assertRaises(ValueError):self.service.create_bytes(self.task['id'],'report.pptx',b'fixture',kind='invalid')

    def test_workbench_conversion_failure_still_returns_original_download(self):
        def fail(source,out,stop):raise RuntimeError('test conversion failure')
        self.service.converter=fail
        receipt=self.service.create_bytes(self.task['id'],'report.docx',b'fixture')
        result=self.wait(receipt['id']);self.assertEqual(result['status'],'failed')
        self.assertTrue(result['original_url'].startswith('/api/workbench-artifact?id='))
        self.assertNotIn('test conversion failure',result['message'])

    def test_workbench_snapshot_rejects_paths_unsupported_formats_and_oversize(self):
        for identifier,name,raw in [('bad','a.txt',b'x'),(self.task['id'],'../a.txt',b'x'),(self.task['id'],'a.zip',b'x'),(self.task['id'],'a.txt',b''),(self.task['id'],'a.txt',b'x'*(10*1024*1024+1))]:
            with self.assertRaises(ValueError):self.service.create_bytes(identifier,name,raw)

    def test_ready_cache_original_and_task_unchanged(self):
        before=self.tasks.get(self.task['id'])
        job=self.create();result=self.wait(job['id'])
        self.assertEqual(result['status'],'ready');self.assertEqual(result['pages'],1)
        self.assertEqual(self.service.asset(job['id'],'document.pdf').read_bytes()[:4],b'%PDF')
        self.assertEqual(self.create()['id'],job['id']);self.assertEqual(self.calls,['原文'])
        self.assertEqual(self.tasks.get(self.task['id']),before)
        self.assertEqual(self.source.read_text(encoding='utf-8'),'原文')
        self.assertNotIn(self.tmp.name,json.dumps(result))
        self.assertEqual(len(self.tasks.get(self.task['id'])['artifacts']),1)

    def test_changed_source_gets_new_preview_and_keeps_old_snapshot(self):
        first=self.create();self.wait(first['id'])
        self.source.write_text('新版',encoding='utf-8')
        second=self.create();self.wait(second['id'])
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(self.calls,['原文','新版'])

    def test_missing_cached_page_is_rebuilt_on_explicit_preview(self):
        first=self.create();self.wait(first['id'])
        self.service.asset(first['id'],'page-1.png').unlink()
        again=self.create();self.assertEqual(again['id'],first['id'])
        self.assertEqual(self.wait(again['id'])['status'],'ready')
        self.assertEqual(self.calls,['原文','原文'])

    def test_missing_cached_pdf_is_rebuilt_on_explicit_preview(self):
        first=self.create();self.wait(first['id'])
        self.service.asset(first['id'],'document.pdf').unlink()
        again=self.create();self.assertEqual(again['id'],first['id'])
        self.assertEqual(self.wait(again['id'])['status'],'ready')
        self.assertEqual(self.calls,['原文','原文'])

    def test_invalid_and_unregistered_paths_fail_closed(self):
        for value in ('../secret','x.txt','/etc/passwd','a\\b.txt'):
            with self.assertRaises((ValueError,FileNotFoundError)):
                self.service.create(self.task['id'],value)
        with self.assertRaises(ValueError):self.service.get('../state')
        job=self.create();self.wait(job['id'])
        for name in ('source.txt','../document.pdf','page-2.png','state.json'):
            with self.assertRaises((ValueError,FileNotFoundError)):
                self.service.asset(job['id'],name)

    def test_failure_and_explicit_retry_no_auto_replay(self):
        def fail(*args):raise RuntimeError('PRIVATE_COMMAND_SECRET')
        self.service.converter=fail
        job=self.create();result=self.wait(job['id'])
        self.assertEqual(result['status'],'failed')
        self.assertNotIn('PRIVATE_COMMAND_SECRET',json.dumps(result))
        self.assertEqual(self.service.get(job['id'])['status'],'failed')
        self.service.converter=lambda source,out,stop: {'pages':0}
        retry=self.create();self.assertEqual(retry['id'],job['id'])
        self.assertEqual(self.wait(retry['id'])['status'],'failed')

    def test_dedup_pending_and_restart_ready_cache(self):
        self.service.close()
        self.service=PreviewService(self.tasks,start_worker=False,converter=lambda *args:None)
        job=self.create();self.assertEqual(self.create()['id'],job['id'])
        self.service.close()
        self.service=PreviewService(self.tasks,start_worker=False)
        self.assertEqual(self.service.get(job['id'])['status'],'failed')

    def test_unsupported_format_remains_downloadable(self):
        z=self.source.with_suffix('.zip');z.write_bytes(b'PK')
        self.tasks.collect_artifacts(self.task['id'])
        with self.assertRaises(ValueError):self.service.create(self.task['id'],z.name)
        self.assertTrue(self.tasks.artifact_path(self.task['id'],z.name).is_file())


if __name__=='__main__':unittest.main()
