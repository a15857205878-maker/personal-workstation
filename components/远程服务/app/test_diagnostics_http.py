import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from transfer import create_server


class DiagnosticsHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=create_server('127.0.0.1',0,Path(self.tmp.name)/'photos','PRIVATE_PAIRING_TOKEN')
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.worker.join();self.tmp.cleanup()

    def get(self,query):
        connection=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        connection.request('GET','/api/bot/diagnostics'+query)
        response=connection.getresponse()
        code,body=response.status,json.loads(response.read())
        connection.close()
        return code,body

    def test_auth_and_source_are_required(self):
        self.assertEqual(self.get('?source_id=phone')[0],403)
        self.assertEqual(self.get('?token=PRIVATE_PAIRING_TOKEN')[0],400)

    def test_reply_probe_is_scoped_and_never_executes(self):
        with patch.object(self.server.bot.replies,'list',return_value=[{'status':'waiting','text':'PRIVATE_PROMPT','observed_status':'native_writer_busy'}]) as listing:
            code,body=self.get('?token=PRIVATE_PAIRING_TOKEN&source_id=phone&thread_id=target')
        self.assertEqual(code,200)
        listing.assert_called_once_with('web','phone','target')
        self.assertNotIn('PRIVATE_',json.dumps(body,ensure_ascii=False))
        self.assertEqual(self.server.tasks.list(),[])
        self.assertEqual(self.server.desktop_open.requests,{})

    def test_subsystem_failure_is_partial_and_does_not_leak_errors(self):
        with patch.object(self.server,'refresh_network',side_effect=OSError('PRIVATE_TOKEN_AND_PATH')):
            code,body=self.get('?token=PRIVATE_PAIRING_TOKEN&source_id=phone')
        self.assertEqual(code,200)
        checks={item['id']:item for item in body['checks']}
        self.assertEqual(checks['receiver']['status'],'ok')
        self.assertEqual(checks['remote']['status'],'unknown')
        self.assertEqual(checks['tasks']['status'],'ok')
        self.assertNotIn('PRIVATE_',json.dumps(body))
