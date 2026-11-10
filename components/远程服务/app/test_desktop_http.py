import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from transfer import create_server

THREAD = '01a17e10-8434-76c2-ad83-b9141d1232a8'


class DesktopHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        reader = Mock()
        reader.get.return_value = {'id': THREAD, 'title': '手机新任务'}
        with patch('transfer.CodexSessionReader', return_value=reader):
            self.server = create_server('127.0.0.1', 0, Path(self.tmp.name)/'photos', 'desktop-test')
        self.release = threading.Event()
        self.manager = self.server.desktop_open
        self.manager.prompt = lambda *args: 0 if self.release.wait(2) else 3
        self.manager.opener = Mock()
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()
        self.tmp.cleanup()

    def request(self, method, path, payload=None, auth=True):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        connection.request(method, path + ('?token=desktop-test' if auth else ''),
                           body=json.dumps(payload).encode() if payload is not None else None,
                           headers={'Content-Type':'application/json'})
        response = connection.getresponse()
        status, body = response.status, json.loads(response.read())
        connection.close()
        return status, body

    def test_auth_target_and_no_automatic_launch(self):
        endpoint = '/api/bot/desktop-open'
        self.assertEqual(self.request('POST', endpoint, {'thread_id':THREAD}, False)[0],403)
        code, receipt = self.request('POST', endpoint, {'thread_id':THREAD})
        self.assertEqual(code,200)
        self.assertEqual(receipt['status'],'pending')
        self.manager.opener.assert_not_called()
        self.assertEqual(self.request('POST',endpoint,{'thread_id':THREAD})[1]['request_id'],receipt['request_id'])
        path = endpoint + '/' + receipt['request_id']
        self.assertEqual(self.request('GET',path,auth=False)[0],403)
        self.release.set()
        for _ in range(100):
            code, result = self.request('GET',path)
            if result['status'] != 'pending':break
            time.sleep(.01)
        self.assertEqual(result['status'],'opened')
        self.manager.opener.assert_called_once_with('codex://threads/'+THREAD)
        self.assertEqual(self.server.tasks.list(),[])

    def test_invalid_payloads_and_unknown_receipts(self):
        for payload in ({}, [], {'thread_id':'bad?command=execute'}, {'application':True}, {'task_id':[]}):
            self.assertEqual(self.request('POST','/api/bot/desktop-open',payload)[0],400)
        self.assertEqual(self.request('GET','/api/bot/desktop-open/missing')[0],404)
        self.manager.opener.assert_not_called()

    def test_pending_phone_command_blocks_open(self):
        with patch.object(self.manager.replies,'has_pending',return_value=True):
            code, receipt = self.request('POST','/api/bot/desktop-open',{'thread_id':THREAD})
        self.assertEqual(code,200)
        self.assertEqual(receipt['status'],'blocked')
        self.manager.opener.assert_not_called()
