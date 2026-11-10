import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from transfer import create_server
from tasks import TaskManager


class FileReviewHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        with patch('transfer.TaskManager.start'),patch('transfer.ReplyQueue.start'):
            self.server=create_server('127.0.0.1',0,Path(self.tmp.name)/'photos','file-test')
        self.task=self.server.tasks.create({'goal':'只读预览','agent':'demo','client_id':'file-http'})
        self.id=self.task['id'];self.ws=self.server.tasks.workspace(self.id)
        (self.ws/'hello.py').write_text('print("hello")\n',encoding='utf-8')
        (self.ws/'table.csv').write_text('名称,数量\n苹果,0\n',encoding='utf-8')
        (self.ws/'shot.png').write_bytes(bytes.fromhex('89504e470d0a1a0a')+b'test')
        self.server.tasks.collect_artifacts(self.id)
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.worker.join();self.tmp.cleanup()

    def request(self,path,auth=True):
        c=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        c.request('GET',path+('&' if '?' in path else '?')+'token='+('file-test' if auth else 'bad'))
        r=c.getresponse();result=r.status,dict(r.getheaders()),r.read();c.close();return result

    def test_auth_no_store_and_read_only(self):
        before=self.server.tasks.get(self.id)
        for route in ['/file-viewer?task_id='+self.id,'/api/bot/files?task_id='+self.id,'/api/bot/file?task_id='+self.id+'&path=hello.py','/file-image?task_id='+self.id+'&path=shot.png']:
            self.assertEqual(self.request(route,False)[0],403)
            code,headers,body=self.request(route)
            self.assertEqual(code,200);self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(headers['Referrer-Policy'],'no-referrer')
        data=json.loads(self.request('/api/bot/file?task_id='+self.id+'&path=table.csv')[2])
        self.assertEqual(data['sheets'][0]['rows'][1],['苹果','0'])
        self.assertEqual(self.server.tasks.get(self.id),before)
        self.assertFalse((self.server.tasks.data/self.id/'review-baseline.json').exists())
        self.assertEqual(self.request('/artifact/'+self.id+'/hello.py')[0],200)

    def test_missing_and_unsafe_paths_have_safe_errors(self):
        for query in ['path=../pairing.json','path=.env','path=no.py','path=hello.py%3Astream']:
            code,_,body=self.request('/api/bot/file?task_id='+self.id+'&'+query)
            self.assertIn(code,(400,404));self.assertNotIn(self.tmp.name.encode(),body)
        self.assertIn(self.request('/api/bot/files?task_id=bad')[0],(400,404))
        self.assertIn(self.request('/file-image?task_id='+self.id+'&path=hello.py')[0],(400,404))


class BaselineExecutionTests(unittest.TestCase):
    def test_worker_captures_before_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            manager=TaskManager(directory,start_worker=False)
            task=manager.create({'goal':'snapshot','agent':'demo','client_id':'snapshot'})
            observed=[]
            def run(task,workspace,*args):
                observed.append((workspace.parent/'review-baseline.json').is_file())
                (workspace/'new.py').write_text('print(1)');return 'done'
            with patch.dict('tasks.RUNNERS',{'demo':run}):
                manager.start()
                deadline=time.monotonic()+5
                while manager.get(task['id'])['status'] in ('queued','running') and time.monotonic()<deadline:time.sleep(.01)
                manager.close()
            self.assertEqual(observed,[True]);self.assertEqual(manager.get(task['id'])['status'],'completed')


if __name__=='__main__':unittest.main()
