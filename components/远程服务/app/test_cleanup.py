import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from transfer import create_server


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=create_server('127.0.0.1',0,Path(self.tmp.name)/'photos','cleanup-token')
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.worker.join();self.tmp.cleanup()

    def request(self,method,path,auth=True):
        connection=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        target=path+('?token=cleanup-token' if auth else '')
        connection.request(method,target,body=b'{}' if method=='POST' else None)
        response=connection.getresponse();body=response.read();code=response.status
        connection.close();return code,body

    def test_old_page_bookmarks_use_the_unified_page(self):
        code,current=self.request('GET','/')
        self.assertEqual(code,200)
        # The root now hosts the session-first shell. Explicit legacy session
        # bookmarks still return the original native session implementation.
        self.assertIn(b'id="mobile-controller-script"',current)
        self.assertIn(b"'/sessions'",current)
        native=None
        for path in ['/workbench','/sessions','/bot']:
            code,page=self.request('GET',path)
            self.assertEqual(code,200)
            self.assertIn(b'conversation.js',page)
            if native is None:native=page
            else:self.assertEqual(page,native)

    def test_legacy_launch_removed_and_new_open_requires_exact_target(self):
        self.assertEqual(self.request('POST','/api/bot/desktop-open',auth=False)[0],403)
        self.assertEqual(self.request('POST','/api/bot/desktop-open')[0],400)
        self.assertEqual(self.request('POST','/api/bot/tasks/anything/open-codex')[0],410)
        self.assertEqual(self.request('GET','/api/bot/desktop-open/old-request')[0],404)
        self.assertEqual(self.server.tasks.list(),[])
        self.assertTrue(hasattr(self.server,'desktop_open'))

    def test_photo_text_transfer_and_pairing_remain_available(self):
        code,page=self.request('GET','/transfer')
        self.assertEqual(code,200)
        self.assertIn(b'messageForm',page)
        self.assertIn(b'fileInput',page)
        self.assertEqual(self.request('GET','/api/files')[0],200)
        self.assertEqual(self.request('GET','/api/messages')[0],200)
        self.assertEqual(self.request('GET','/qr.svg')[0],200)
        code,info=self.request('GET','/api/info')
        self.assertEqual(code,200)
        self.assertNotIn('desktop_open_mode',json.loads(info))
