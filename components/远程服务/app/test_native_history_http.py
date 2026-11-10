import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from transfer import create_server


class NativeHistoryHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        with patch('transfer.TaskManager.start'),patch('transfer.ReplyQueue.start'):
            self.server=create_server('127.0.0.1',0,Path(self.tmp.name)/'photos','native-test')
        self.native=self.server.deepseek_history=Mock()
        self.native.session_page.return_value={'sessions':[],'next_offset':None}
        self.native.conversation.return_value={'provider':'deepseek-harness','thread_id':None,'can_reply':False}
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.worker.join();self.tmp.cleanup()

    def get(self,path,auth=True):
        c=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        c.request('GET',path+('&' if '?' in path else '?')+'token='+('native-test' if auth else 'bad'))
        r=c.getresponse();result=r.status,json.loads(r.read());c.close();return result

    def test_paired_get_only_and_independent_route(self):
        self.assertEqual(self.get('/api/bot/deepseek/sessions',False)[0],403)
        self.native.session_page.assert_not_called()
        code,data=self.get('/api/bot/deepseek/sessions?q=hello&offset=20')
        self.assertEqual(code,200)
        self.native.session_page.assert_called_once_with(limit=20,offset=20,search='hello')
        with patch.object(self.server.bot.reader,'history',side_effect=AssertionError('must never read Codex')):
            code,data=self.get('/api/bot/deepseek/conversation?source_id=phone&session_id='+'a'*64+'&before=12')
        self.assertEqual(code,200);self.assertFalse(data['can_reply']);self.assertIsNone(data['thread_id'])
        self.native.conversation.assert_called_once_with('a'*64,'phone',before=12,replies=self.server.deepseek_replies)

    def test_not_found_errors_and_bad_cursor(self):
        self.native.conversation.side_effect=KeyError('missing')
        self.assertEqual(self.get('/api/bot/deepseek/conversation?source_id=phone&session_id='+'b'*64)[0],404)
        self.assertEqual(self.get('/api/bot/deepseek/conversation?source_id=phone&session_id='+'b'*64+'&before=oops')[0],400)


if __name__=='__main__':unittest.main()
