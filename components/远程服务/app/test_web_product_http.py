import http.client,json,threading,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from transfer import create_server
class WebProductHTTPTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  with patch('transfer.TaskManager.start'),patch('transfer.ReplyQueue.start'),patch('transfer.CodexSessionReader',return_value=Mock()):self.server=create_server('127.0.0.1',0,Path(self.tmp.name)/'photos','web-test')
  task=self.server.tasks.create({'agent':'codex-deepseek-code','goal':'website','client_id':'one'});self.id=task['id'];self.server.tasks.update(self.id,status='completed');workspace=self.server.tasks.workspace(self.id);(workspace/'frontend').mkdir();(workspace/'frontend/index.html').write_text('<main>Web result</main>');(workspace/'frontend/style.css').write_text('main{color:blue}');self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
 def request(self,path,payload=None,headers=None):
  c=http.client.HTTPConnection(*self.server.server_address,timeout=5);c.request('POST' if payload is not None else 'GET',path,json.dumps(payload) if payload is not None else None,headers or {});r=c.getresponse();result=r.status,dict(r.getheaders()),r.read();c.close();return result
 def test_paired_preparation_and_opaque_sandbox_asset_ticket(self):
  self.assertEqual(self.request('/api/web-product?id='+self.id)[0],403)
  code,headers,raw=self.request('/api/web-product?id='+self.id+'&token=web-test');self.assertEqual(code,200);ticket=json.loads(raw)['url'];self.assertNotIn('web-test',ticket)
  code,headers,raw=self.request(ticket);self.assertEqual(code,200);self.assertIn(b'Web result',raw);self.assertIn('sandbox allow-scripts',headers['Content-Security-Policy']);self.assertNotIn('allow-same-origin',headers['Content-Security-Policy']);self.assertEqual(headers['Referrer-Policy'],'no-referrer')
  self.assertEqual(self.request(ticket.rsplit('/',1)[0]+'/style.css')[0],200)
  self.assertEqual(self.request(ticket.rsplit('/',1)[0]+'/%2e%2e/secret')[0],404)
 def test_screenshot_rejects_foreign_origin_and_arbitrary_url_before_process(self):
  with patch.object(self.server.web_products,'screenshot') as capture:
   self.assertEqual(self.request('/api/web-product/screenshot?token=web-test',{'id':self.id},{'Origin':'https://external.test','Content-Type':'application/json'})[0],403)
   self.assertEqual(self.request('/api/web-product/screenshot?token=web-test',{'id':self.id,'url':'http://evil'},{'Content-Type':'application/json'})[0],400);capture.assert_not_called()
 def test_screenshot_is_available_even_when_source_artifacts_hit_limit(self):
  metadata=self.server.tasks.data/self.id;metadata.mkdir(parents=True,exist_ok=True);image=metadata/'web-screenshot.png';image.write_bytes(b'\x89PNG\r\n\x1a\nTEST');self.server.tasks.update(self.id,web_screenshot=True,artifacts=[{'path':str(i)+'.js','name':str(i)+'.js','size':1} for i in range(200)])
  self.assertEqual(self.request('/api/web-product/screenshot?id='+self.id)[0],403)
  code,headers,raw=self.request('/api/web-product/screenshot?id='+self.id+'&token=web-test');self.assertEqual(code,200);self.assertEqual(headers['Content-Type'],'image/png');self.assertTrue(raw.startswith(b'\x89PNG'))
if __name__=='__main__':unittest.main()
