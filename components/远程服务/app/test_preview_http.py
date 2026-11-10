import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from transfer import create_server


class PreviewHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        with patch('transfer.TaskManager.start'),patch('transfer.ReplyQueue.start'):
            self.server=create_server('127.0.0.1',0,Path(self.tmp.name)/'photos','preview-http')
        def convert(source,out,stop):
            (out/'document.pdf').write_bytes(b'%PDF-1.4\nfixture')
            (out/'page-1.png').write_bytes(bytes.fromhex('89504e470d0a1a0a'))
            return {'pages':1}
        self.server.previews.converter=convert
        self.task=self.server.tasks.create({'goal':'预览','agent':'demo','client_id':'preview-http'})
        file=self.server.tasks.workspace(self.task['id'])/'中文.txt';file.write_text('测试',encoding='utf-8')
        self.server.tasks.collect_artifacts(self.task['id'])
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.worker.join();self.tmp.cleanup()

    def request(self,path,method='GET',body=None,auth=True):
        c=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        c.request(method,path+('&' if '?' in path else '?')+'token='+('preview-http' if auth else 'bad'),
                  body=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        r=c.getresponse();result=(r.status,dict(r.getheaders()),r.read());c.close();return result

    def test_authenticated_lifecycle_inline_download_and_no_task_mutation(self):
        payload={'task_id':self.task['id'],'path':'中文.txt'}
        before=self.server.tasks.get(self.task['id'])
        self.assertEqual(self.request('/api/bot/preview','POST',payload,False)[0],403)
        code,_,body=self.request('/api/bot/preview','POST',payload)
        self.assertIn(code,(200,202));job=json.loads(body)
        for _ in range(100):
            state=json.loads(self.request('/api/bot/preview/'+job['id'])[2])
            if state['status']=='ready':break
            time.sleep(.01)
        self.assertEqual(state['status'],'ready')
        pdf='/preview/'+job['id']+'/document.pdf';page='/preview/'+job['id']+'/page/1.png'
        for target in (pdf,page,'/preview-viewer?preview_id='+job['id'],'/api/bot/preview/'+job['id']):
            self.assertEqual(self.request(target,auth=False)[0],403)
        code,headers,body=self.request(pdf)
        self.assertEqual(code,200);self.assertEqual(headers['Content-Type'],'application/pdf')
        self.assertTrue(headers['Content-Disposition'].startswith('inline;'));self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertTrue(body.startswith(b'%PDF-'))
        self.assertTrue(self.request(pdf+'?download=1')[1]['Content-Disposition'].startswith('attachment;'))
        self.assertEqual(self.request(page)[1]['Content-Type'],'image/png')
        self.assertEqual(self.request('/preview/'+job['id']+'/page/2.png')[0],404)
        self.assertEqual(self.request('/preview/'+job['id']+'/source.txt')[0],404)
        self.assertEqual(self.server.tasks.get(self.task['id']),before)

    def test_unknown_source_and_extra_payload_rejected(self):
        self.assertEqual(self.request('/api/bot/preview','POST',{'task_id':self.task['id'],'path':'../secret'})[0],404)
        self.assertEqual(self.request('/api/bot/preview','POST',{'task_id':self.task['id'],'path':'中文.txt','filename':'secret'})[0],400)


if __name__=='__main__':unittest.main()
