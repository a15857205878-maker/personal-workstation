import unittest,uuid,json
from copy import deepcopy
import test_agent_center as fixtures

class RetryTests(unittest.TestCase):
    setUp=fixtures.CenterTests.setUp
    call=fixtures.CenterTests.call
    create=fixtures.CenterTests.create
    send=fixtures.CenterTests.send
    done=fixtures.CenterTests.done
    def fail_chat(self):
        self.client.fail_at=2
        return self.done(self.send(self.create(),'原始需求'))
    def retry(self,c,t,request=None,item=None):
        return self.call('api_center_retry',dict(id=c['id'],turn_id=t['id'],item=item or t['failures'][0]['item'],request_id=request or uuid.uuid4().hex))
    def test_chat_retry_only_failed_member_and_preserves_original(self):
        c=self.fail_chat();t=c['turns'][0];before=deepcopy(t['run']);rid=uuid.uuid4().hex
        self.assertEqual(t['failures'][0]['item'],'message:'+before['messages'][-1]['id'])
        c=self.done(self.retry(c,t,rid));self.assertEqual(len(self.client.calls),3)
        self.assertEqual(c['call_count'],3);self.assertEqual(c['turns'][0]['run'],before)
        self.assertEqual(c['turns'][-1]['target'],'B');self.assertEqual(c['turns'][-1]['kind'],'discuss')
        self.assertIn('reply-1',json.dumps(self.client.calls[-1]));self.assertFalse(c['turns'][0]['failures'][0]['retryable'])
        self.retry(c,t,rid);self.assertEqual(len(self.client.calls),3)
        self.assertFalse(self.bridge.call('api_center_retry',dict(id=c['id'],turn_id=t['id'],item=t['failures'][0]['item'],request_id=uuid.uuid4().hex))['ok'])
    def test_work_retry_runs_only_selected_job(self):
        c=self.create();jobs=[dict(title='成功项',instruction='',output_format='text',primary_id=self.roles['A']),dict(title='失败项',instruction='保留要求',output_format='text',primary_id=self.roles['B']),dict(title='后续项',instruction='',output_format='text',primary_id=self.roles['A'])]
        self.client.fail_at=2;c=self.send(c,'总目标','execute',jobs=jobs);self.call('api_center_confirm',dict(id=c['id'],request_id=c['turns'][0]['id']));c=self.done(c);t=c['turns'][0]
        self.assertEqual([f['item'] for f in t['failures']],['job:1'])
        old=[j['run_id'] for j in t['jobs']];c=self.done(self.retry(c,t))
        self.assertEqual(len(self.client.calls),3);self.assertEqual(len(c['turns'][-1]['jobs']),1)
        self.assertEqual(c['turns'][-1]['jobs'][0]['title'],'失败项');self.assertEqual([j['run_id'] for j in c['turns'][0]['jobs']],old)
        self.assertEqual(c['turns'][0]['jobs'][2]['state'],'skipped')
    def test_invalid_archived_budget_busy_and_profile_change(self):
        c=self.fail_chat();t=c['turns'][0];p=dict(id=c['id'],turn_id=t['id'],item=t['failures'][0]['item'],request_id=uuid.uuid4().hex)
        for bad in (dict(item='message:missing'),dict(item='job:0'),dict(request_id='bad'),dict(extra=True)):
            self.assertFalse(self.bridge.call('api_center_retry',{**p,**bad})['ok'])
        center=self.bridge._auto.center
        raw=center.sessions.load(c['id']);raw['archived']=True;center.sessions.save(raw)
        self.assertFalse(self.bridge.call('api_center_retry',p)['ok']);raw['archived']=False;raw['call_limit']=2;center.sessions.save(raw)
        self.assertFalse(self.bridge.call('api_center_retry',p)['ok']);raw['call_limit']=30;center.sessions.save(raw)
        self.bridge._command_lock.acquire()
        try:self.assertFalse(self.bridge.call('api_center_retry',p)['ok'])
        finally:self.bridge._command_lock.release()
        profile=self.bridge._auto.profiles.list()[0];self.call('api_profile_save',{**profile,'model':'changed'})
        self.assertFalse(self.bridge.call('api_center_retry',p)['ok']);self.assertEqual(len(self.client.calls),2)
    def test_unknown_interruption_never_offers_retry(self):
        c=self.fail_chat();center=self.bridge._auto.center;center.chat.sessions.delete(c['turns'][0]['run_id']);center.chat.run=None
        c=self.call('api_center_status',{'id':c['id']});self.assertFalse(any(f['retryable'] for f in c['turns'][0]['failures']))
    def test_diagnostics_redacts_secrets_and_paths(self):
        from failure_recovery import diagnose
        d=diagnose('HTTP 401 Bearer abcdefghijkl sk-abcdefghijkl C:/Users/example/private/log.txt https://example.invalid?token=secret')
        self.assertEqual(d['code'],'auth');self.assertNotIn('abcdefghijkl',d['detail']);self.assertNotIn('private',d['detail']);self.assertNotIn('secret',d['detail'])
    def test_negotiated_chat_retry_is_plain_one_member_reply(self):
        self.client.fail_at=2;c=self.done(self.send(self.create(),'仅讨论',kind='chat'))
        t=c['turns'][0];self.assertEqual(t['state'],'failed')
        c=self.done(self.retry(c,t));self.assertEqual(c['turns'][-1]['state'],'completed');self.assertEqual(len(self.client.calls),3)
        self.assertFalse(c['turns'][-1].get('jobs'));self.assertNotIn('agent-center-decision/v1',self.client.calls[-1][0]['content'])
    def test_failed_retry_can_retry_again_but_not_original(self):
        c=self.fail_chat();t=c['turns'][0];self.client.fail_at=3;c=self.done(self.retry(c,t));latest=c['turns'][-1]
        self.assertEqual(latest['state'],'failed');self.assertFalse(c['turns'][0]['failures'][0]['retryable'])
        c=self.done(self.retry(c,latest));self.assertEqual(c['call_count'],4);self.assertEqual(c['turns'][-1]['state'],'completed')
    def test_retry_does_not_take_unrelated_later_instructions_as_context(self):
        c=self.fail_chat();t=c['turns'][0]
        c=self.done(self.send(c,'LATER_UNRELATED_REQUEST'))
        c=self.done(self.retry(c,t))
        self.assertNotIn('LATER_UNRELATED_REQUEST',json.dumps(self.client.calls[-1]))
    def test_retry_chain_keeps_original_context_boundary(self):
        c=self.fail_chat();original=c['turns'][0]
        c=self.done(self.send(c,'UNRELATED_BETWEEN_ATTEMPTS'))
        self.client.fail_at=len(self.client.calls)+1
        c=self.done(self.retry(c,original));failed=c['turns'][-1];self.assertEqual(failed['state'],'failed')
        c=self.done(self.retry(c,failed))
        self.assertNotIn('UNRELATED_BETWEEN_ATTEMPTS',json.dumps(self.client.calls[-1]))

class RemoteRetryTests(unittest.TestCase):
    def test_phone_receipt_failure_projection_and_no_replay(self):
        import test_center_remote as fixtures,time
        f=fixtures.CenterRemoteTests();f.setUp();self.addCleanup(f.doCleanups)
        c=f.b.call('api_center_create',dict(primary_id=f.profiles[0]['id'],reviewer_id=f.profiles[1]['id']))['data']
        f.client.fail_at=2;f.b.call('api_center_send',dict(id=c['id'],request_id=uuid.uuid4().hex,text='测试',kind='discuss'))
        end=time.monotonic()+4
        while f.b.busy() and time.monotonic()<end:time.sleep(.01)
        c=f.rpc('center_get',{'id':c['id']})['data'];failure=c['turns'][0]['failures'][0]
        p=dict(id=c['id'],turn_id=c['turns'][0]['id'],item=failure['item']);rid=uuid.uuid4().hex
        for bad in ({**p,'turn_id':'../x'},{**p,'item':True},{**p,'path':'no'}):self.assertFalse(f.rpc('center_retry',bad,uuid.uuid4().hex)['ok'])
        r=f.rpc('center_retry',p,rid);self.assertTrue(r['ok'],r)
        while f.b.busy() and time.monotonic()<end:time.sleep(.01)
        self.assertEqual(f.rpc('center_retry',p,rid),r);self.assertEqual(len(f.client.calls),3)
        public=f.rpc('center_get',{'id':c['id']})['data'];self.assertEqual(public['turns'][-1]['retry_of'],dict(turn_id=p['turn_id'],item=p['item']))
        self.assertNotIn('base_url',json.dumps(public));self.assertNotIn('fake-secret',json.dumps(public))

if __name__=='__main__':unittest.main()
