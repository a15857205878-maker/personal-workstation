from pathlib import Path
import sys, tempfile, threading, time, unittest, zipfile
from xml.etree import ElementTree as ET
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from task_station.core import Service

class Fake:
    def __init__(self): self.calls=0
    def capabilities(self): return {'text_1': {'mode':'test','can_run':True}}
    def run(self, role, prompt, cancel, chunk, folder):
        self.calls+=1
        return '# 项目说明\n\n中文正文 & <测试>\n- 需要核对的数据'

class DocumentExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.fake=Fake();self.s=Service(Path(self.tmp.name),self.fake)
    def tearDown(self): self.s.close();self.tmp.cleanup()
    def create(self): return self.s.call('create',{'task_type':'text','role':'text_1','instruction':'写项目说明文档'})
    def check_doc(self,task):
        files=[f for f in task['files'] if f['name'].endswith('.docx')];self.assertEqual(len(files),1)
        path=self.s.file_path(task['id'],files[0]['name'])
        with zipfile.ZipFile(path) as z:
            self.assertIsNone(z.testzip())
            for name in z.namelist(): ET.fromstring(z.read(name))
            xml=z.read('word/document.xml').decode();self.assertIn('中文正文',xml);self.assertIn('&amp;',xml)
        return path.read_bytes()
    def test_model_text_automatically_has_real_word_artifact(self):
        t=self.create();self.s.call('submit',{'id':t['id']})
        until=time.monotonic()+5
        while self.s.jobs and time.monotonic()<until: time.sleep(.01)
        t=self.s.call('get',{'id':t['id']});self.assertEqual(t['status'],'结果待确认');self.check_doc(t);self.assertEqual(self.fake.calls,1)
    def test_existing_result_can_export_without_model_or_completion_and_is_idempotent(self):
        t=self.create()
        with self.s.lock:
            raw=self.s._load(t['id']);raw.update(result='# 标题\n中文正文 & <测试>',status='结果待确认');self.s._save(raw)
        a=self.s.call('export_document',{'id':t['id']});content=self.check_doc(a)
        b=self.s.call('export_document',{'id':t['id']});self.assertEqual(self.check_doc(b),content)
        self.assertEqual(b['status'],'结果待确认');self.assertEqual(self.fake.calls,0)
    def test_empty_or_running_results_cannot_be_exported(self):
        t=self.create()
        with self.assertRaises(ValueError):self.s.call('export_document',{'id':t['id']})
        with self.s.lock:
            raw=self.s._load(t['id']);raw.update(result='未完正文',status='执行中');self.s._save(raw)
        with self.assertRaises(ValueError):self.s.call('export_document',{'id':t['id']})
    def test_file_failure_preserves_returned_text(self):
        t=self.create()
        with patch('task_station.core.write_document',side_effect=OSError('disk unavailable')):
            self.s.call('submit',{'id':t['id']})
            until=time.monotonic()+5
            while self.s.jobs and time.monotonic()<until:time.sleep(.01)
        t=self.s.call('get',{'id':t['id']});self.assertEqual(t['status'],'结果待确认');self.assertIn('中文正文',t['result']);self.assertIn('Word',t['events'][-1]['message'])

if __name__=='__main__':unittest.main()
