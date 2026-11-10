import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock
from transfer import create_server


class UsageHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=create_server('127.0.0.1',0,Path(self.tmp.name)/'photos','PRIVATE_PAIRING')
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.worker.join();self.tmp.cleanup()

    def get(self,auth=True,path='/api/bot/usage'):
        connection=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        connection.request('GET',path+('?token=PRIVATE_PAIRING' if auth else ''))
        response=connection.getresponse();body=response.read();code=response.status
        connection.close();return code,json.loads(body)

    def test_auth_cache_and_no_model_task_side_effects(self):
        probe=Mock(return_value={'rateLimits':{'primary':{'usedPercent':25,'windowDurationMins':300,'resetsAt':2000000000}}})
        self.server.usage.probe=probe
        self.assertEqual(self.get(False)[0],403);probe.assert_not_called()
        code,body=self.get();self.assertEqual(code,200)
        self.assertEqual(body['pools'][0]['windows'][0]['remaining_percent'],75)
        self.assertTrue(self.get()[1]['cached']);probe.assert_called_once()
        self.assertEqual(self.server.tasks.list(),[])
        self.assertEqual(self.server.desktop_open.requests,{})
        self.assertNotIn('PRIVATE',str(body))

    def test_deepseek_balance_auth_cache_and_no_task_side_effects(self):
        probe=Mock(return_value={'is_available':True,'balance_infos':[{'currency':'CNY','total_balance':'4.50'}],'secret':'PRIVATE_KEY'})
        self.server.deepseek_balance.probe=probe
        route='/api/bot/deepseek/balance'
        self.assertEqual(self.get(False,route)[0],403);probe.assert_not_called()
        code,body=self.get(path=route)
        self.assertEqual(code,200);self.assertEqual(body['balances'][0]['total'],'4.50')
        self.assertNotIn('PRIVATE',str(body));self.assertTrue(self.get(path=route)[1]['cached']);probe.assert_called_once()
        self.assertEqual(self.server.tasks.list(),[]);self.assertEqual(self.server.desktop_open.requests,{})
