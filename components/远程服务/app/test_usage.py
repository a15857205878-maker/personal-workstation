import io
import json
import subprocess
import threading
import unittest
from unittest.mock import Mock, patch
from usage import normalize_limits, UsageService, read_limits


class UsageTests(unittest.TestCase):
    def test_multiple_buckets_and_real_window_lengths(self):
        value=normalize_limits({'rateLimits':{'primary':{'usedPercent':99}},'rateLimitsByLimitId':{
            'codex':{'primary':{'usedPercent':25,'windowDurationMins':300,'resetsAt':2000000000},'secondary':{'usedPercent':60,'windowDurationMins':10080,'resetsAt':2000000500}},
            'other':{'primary':{'usedPercent':10,'windowDurationMins':60}}}})
        self.assertEqual(len(value),2)
        self.assertEqual(value[0]['windows'][0]['remaining_percent'],75)
        self.assertEqual(value[0]['windows'][1]['remaining_percent'],40)
        self.assertEqual(value[1]['windows'][0]['window_minutes'],60)

    def test_legacy_and_missing_are_not_zero(self):
        value=normalize_limits({'rateLimits':{'primary':{'usedPercent':None,'windowDurationMins':None,'resetsAt':None}}})
        self.assertIsNone(value[0]['windows'][0]['remaining_percent'])
        self.assertIsNone(value[0]['windows'][0]['resets_at'])
        self.assertEqual(normalize_limits({}),[])

    def test_clamps_and_never_exports_raw_account_fields(self):
        value=normalize_limits({'email':'PRIVATE_EMAIL','credits':{'balance':'PRIVATE_BALANCE'},'rateLimits':{'accountId':'PRIVATE_ID','limitName':'PRIVATE_NAME','primary':{'usedPercent':120,'resetsAt':True}}})
        self.assertEqual(value[0]['windows'][0]['remaining_percent'],0)
        self.assertIsNone(value[0]['windows'][0]['resets_at'])
        self.assertNotIn('PRIVATE',str(value))

    def test_cache_and_failure_do_not_relabel_stale_success(self):
        now=[0];calls=[]
        def probe():
            calls.append(1)
            if len(calls)>1:raise RuntimeError('PRIVATE_ERROR_TOKEN')
            return {'rateLimits':{'primary':{'usedPercent':20}}}
        service=UsageService(probe=probe,clock=lambda:now[0])
        first=service.read();self.assertEqual(first['status'],'available')
        self.assertTrue(service.read()['cached']);self.assertEqual(len(calls),1)
        now[0]=31
        failure=service.read()
        self.assertEqual(failure['status'],'unavailable');self.assertEqual(failure['pools'],[])
        self.assertNotIn('PRIVATE',str(failure))

    def test_wire_protocol_only_initializes_and_reads_limits(self):
        process=Mock()
        process.stdout=io.StringIO('\n'.join(json.dumps(x) for x in (
            {'id':1,'result':{}},{'method':'ignoredNotification','params':{'secret':'PRIVATE'}},
            {'id':2,'result':{'rateLimits':{'primary':{'usedPercent':10}}}}))+'\n')
        writes=[];process.stdin.write.side_effect=writes.append
        with patch('usage.subprocess.Popen',return_value=process) as popen:
            result=read_limits('test-codex')
        self.assertEqual([json.loads(line)['method'] for line in writes],['initialize','initialized','account/rateLimits/read'])
        self.assertEqual(result['rateLimits']['primary']['usedPercent'],10)
        self.assertEqual(popen.call_args.args[0],['test-codex','app-server'])
        process.stdin.close.assert_called_once()

    def test_api_auth_error_is_sanitized(self):
        process=Mock()
        process.stdout=io.StringIO(json.dumps({'id':1,'result':{}})+'\n'+json.dumps({'id':2,'error':{'message':'PRIVATE_TOKEN_EMAIL'}})+'\n')
        with patch('usage.subprocess.Popen',return_value=process):
            value=UsageService(probe=lambda:read_limits('test-codex')).read()
        self.assertEqual(value['status'],'unavailable')
        self.assertNotIn('PRIVATE',str(value))

    def test_closing_service_stops_its_active_query_process(self):
        service=UsageService();started=threading.Event();stopped=threading.Event()
        process=Mock()
        process.terminate.side_effect=stopped.set
        def wait(timeout):
            if not stopped.is_set():raise subprocess.TimeoutExpired('fake',timeout)
            return 0
        process.wait.side_effect=wait
        def query(*,spawn):
            spawn(['fake-codex','app-server']);started.set()
            self.assertTrue(stopped.wait(2))
            return {}
        with patch('usage.subprocess.Popen',return_value=process),patch('usage.read_limits',side_effect=query):
            worker=threading.Thread(target=service.read)
            worker.start();self.assertTrue(started.wait(1))
            service.close();worker.join(1)
            self.assertFalse(worker.is_alive())
            process.terminate.assert_called_once()
        service.probe=Mock();service.read();service.probe.assert_not_called()
