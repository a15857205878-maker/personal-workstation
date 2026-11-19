import sys,json,tempfile,unittest,uuid
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from backend import Bridge
from remote_gateway import RemoteGateway
from test_api import FakeClient

class CenterRemoteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.client=FakeClient();self.b=Bridge(self.root/'missing',data_dir=self.root/'data',api_client=self.client)
        self.profiles=[self.b.call('api_profile_save',dict(name=s,kind='compatible',base_url='https://private.invalid',model=s,api_key='fake-secret'))['data'] for s in 'ABC']
        self.g=RemoteGateway(self.b,self.root/'data',port=0)
    def rpc(self,a,p=None,rid=None):return self.g.rpc(dict(action=a,payload=p or {},**({'request_id':rid} if rid else {})))
    def test_bootstrap_is_shared_and_never_exports_connection_or_secrets(self):
        boot=self.rpc('center_bootstrap');self.assertTrue(boot['ok'],boot)
        self.assertEqual(len(boot['data']['profiles']),3)
        raw=json.dumps(boot);self.assertNotIn('private.invalid',raw);self.assertNotIn('fake-secret',raw);self.assertNotIn('base_url',raw)
        self.assertEqual(self.client.calls,[])
    def test_create_receipt_duplicate_and_pc_history_visible(self):
        p=dict(primary_id=self.profiles[0]['id'],reviewer_id=self.profiles[1]['id'],third_id=self.profiles[2]['id'])
        rid=uuid.uuid4().hex;a=self.rpc('center_create',p,rid);self.assertTrue(a['ok'],a)
        self.assertEqual(self.rpc('center_create',p,rid),a)
        self.assertEqual(len(self.b._auto.center.sessions.list()),1)
        pc=self.b.call('api_center_create',p)['data']
        self.assertIn(pc['id'],[s['id'] for s in self.rpc('center_bootstrap')['data']['sessions']])
        self.assertTrue(self.rpc('center_get',{'id':pc['id']})['ok'])
    def test_phone_cannot_write_settings_or_inject_unbounded_payload(self):
        for a,p in [('center_create',dict(primary_id='x',reviewer_id='y',api_key='bad')),('center_send',dict(id=uuid.uuid4().hex,text='x',path='C:/secret')),('center_identity_save',{}),('center_get',{'id':'../secret'})]:
            self.assertFalse(self.rpc(a,p,uuid.uuid4().hex)['ok'])
        self.assertEqual(self.client.calls,[])
    def test_projection_strips_nested_control_config_and_paths(self):
        from center_remote import public_session
        session=dict(id='a'*32,roles={'A':dict(id='b'*32,name='A',model='m',base_url='https://secret')},turns=[dict(id='c'*32,run=dict(roles={},messages=[dict(seat='A',content='hello',control={'secret':'bad'},encrypted_key='bad')],reference_context=['bad']),decision={'reply':'PRIVATE'})],seat_styles={'A':{'text':'PRIVATE'}})
        raw=json.dumps(public_session(session));self.assertNotIn('PRIVATE',raw);self.assertNotIn('secret',raw);self.assertNotIn('reference_context',raw)
    def test_artifact_requires_membership_in_selected_center_session(self):
        result=self.rpc('center_artifact',dict(id='a'*32,run_id='b'*32,name='unrelated.docx'))
        self.assertFalse(result['ok'])
    def complete(self,mode='reply',jobs=None):
        import time
        from test_negotiated_chat import Negotiator
        c=self.b.call('api_center_create',dict(primary_id=self.profiles[0]['id'],reviewer_id=self.profiles[1]['id'],third_id=self.profiles[2]['id']))['data']
        client=Negotiator(dict(schema='agent-center-decision/v1',mode=mode,reply='公开回复',jobs=jobs or []))
        self.b._auto.center.agent.chat.client=client;self.b._auto.center.agent.workflow.engine.client=client
        p=dict(id=c['id'],text='明确测试资料，整理成文档。' if jobs else '三位聊聊',target='ABC',rounds=1);rid=uuid.uuid4().hex
        result=self.rpc('center_send',p,rid);self.assertTrue(result['ok'],result)
        end=time.monotonic()+5
        while self.b._auto.center.busy() and time.monotonic()<end:time.sleep(.02)
        self.assertFalse(self.b._auto.center.busy())
        self.assertEqual(self.rpc('center_send',p,rid),result)
        return self.rpc('center_get',{'id':c['id']})['data'],client
    def test_send_duplicate_three_replies_and_no_control_projection(self):
        c,client=self.complete()
        self.assertEqual(len(client.calls),3);self.assertEqual(c['turns'][-1]['state'],'completed')
        self.assertEqual([m['seat'] for m in c['turns'][-1]['run']['messages']],list('UABC'))
        self.assertNotIn('agent-center-decision/v1',json.dumps(c))
    def test_dragon_draft_edits_on_pc_confirms_on_phone_and_stays_in_today(self):
        import time
        from test_negotiated_chat import Negotiator
        a,b,_=self.profiles
        session=self.b.call('api_center_create',dict(primary_id=a['id'],reviewer_id=b['id']))['data']
        center=self.b._auto.center
        client=Negotiator(dict(schema='agent-center-decision/v1',mode='work',reply='建议先整理成册。',
                              jobs=[dict(title='周计划',instruction='用已给出的三条记录',output_format='docx',executor='B')]))
        center.agent.chat.client=client;center.workflow.engine.client=client

        def wait():
            end=time.monotonic()+5
            while center.busy() and time.monotonic()<end:time.sleep(.02)
            self.assertFalse(center.busy())
            return self.rpc('center_get',{'id':session['id']})['data']['turns'][-1]

        def request(action,payload):
            result=self.rpc(action,payload,uuid.uuid4().hex)
            self.assertTrue(result['ok'],result)
            return result['data']

        draft=dict(id=session['id'],text='请把甲、乙、丙三项整理成一份周计划。只拟分工，等我确认后再执行。')
        nonce=uuid.uuid4().hex
        sent=self.rpc('center_draft',draft,nonce)
        self.assertTrue(sent['ok'],sent)
        turn=wait();key=dict(id=session['id'],turn_id=turn['id'])
        self.assertEqual(self.rpc('center_draft',draft,nonce),sent)
        self.assertEqual((turn['state'],turn['plan_revision'],turn['draft_model']),('prepared',1,a['model']))
        self.assertEqual(client.profiles,[a['id']])
        self.assertIsNone(turn['jobs'][0]['run'])
        self.assertEqual(self.rpc('center_today')['data']['today']['prepared']['items'][0]['turn_id'],turn['id'])

        edited={**turn['job_plan'][0],'title':'修订后的行动清单','primary_id':a['id']}
        pc=self.b.call('api_center_edit_plan',dict(**key,plan_revision=1,jobs=[edited]))
        self.assertTrue(pc['ok'],pc)
        self.assertEqual(wait()['plan_revision'],2)
        self.assertFalse(self.rpc('center_confirm',dict(**key,plan_revision=1),uuid.uuid4().hex)['ok'])
        self.assertFalse(self.rpc('center_confirm',key,uuid.uuid4().hex)['ok'])
        final_job={**edited,'primary_id':b['id'],'instruction':'把三项各写成一行。'}
        request('center_edit_plan',dict(**key,plan_revision=2,jobs=[final_job]))
        self.assertEqual(client.profiles,[a['id']])
        request('center_confirm',dict(**key,plan_revision=3))
        turn=wait()
        self.assertEqual(turn['state'],'completed')
        self.assertEqual(turn['phase'],'finished')
        self.assertEqual(client.profiles,[a['id'],b['id']])
        self.assertIn('用户已确认分工',client.calls[-1][0]['content'])
        self.assertIn('勿把工作站的审批状态写入交付',client.calls[-1][0]['content'])
        self.assertIn(draft['text'],client.calls[-1][1]['content'])
        stored=center.sessions.load(session['id'])
        self.assertEqual(stored['turns'][-1]['phase'],'finished')
        stored['turns'][-1]['phase']='awaiting_confirmation'
        center.sessions.save(stored)
        self.assertEqual(wait()['phase'],'finished')
        self.assertEqual(turn['jobs'][0]['title'],final_job['title'])
        artifact=self.rpc('center_results')['data']['items'][0]
        self.assertEqual(artifact['turn_id'],key['turn_id'])
        self.assertTrue(self.rpc('center_artifact',dict(id=key['id'],run_id=artifact['run_id'],name=artifact['name']))['ok'])
        self.assertEqual(self.rpc('center_today')['data']['today']['review']['items'][0]['turn_id'],key['turn_id'])
        request('center_accept',key)
        today=self.rpc('center_today')['data']['today']
        self.assertEqual(today['review']['count'],0)
        self.assertEqual(today['accepted']['items'][0]['turn_id'],key['turn_id'])
    def test_file_can_be_downloaded_only_through_its_center(self):
        c,client=self.complete('work',[dict(title='测试文档',instruction='只用测试资料',output_format='docx',executor='C')])
        run=c['turns'][-1]['jobs'][0]['run'];name=run['files'][0]['name']
        data=self.rpc('center_artifact',dict(id=c['id'],run_id=run['id'],name=name))
        self.assertTrue(data['ok'],data);self.assertTrue(__import__('base64').b64decode(data['data']['content_base64']).startswith(b'PK'))
        self.assertFalse(self.rpc('center_artifact',dict(id=c['id'],run_id=uuid.uuid4().hex,name=name))['ok'])
    def test_results_read_download_membership_and_unknown_fields(self):
        c,client=self.complete('work',[dict(title='测试文档',instruction='只用测试资料',output_format='docx',executor='C')])
        before=len(client.calls);result=self.rpc('center_results');self.assertTrue(result['ok'],result)
        item=result['data']['items'][0];self.assertEqual(item['conversation_id'],c['id']);self.assertEqual(item['turn_id'],c['turns'][-1]['id']);self.assertEqual(item['owner'],self.profiles[2]['name'])
        self.assertTrue(self.rpc('center_artifact',dict(id=item['conversation_id'],run_id=item['run_id'],name=item['name']))['ok'])
        self.assertEqual(len(client.calls),before)
        self.assertFalse(self.rpc('center_results',{'path':'C:/private'})['ok'])
        self.assertFalse(self.rpc('center_results',{'limit':100000})['ok'])
        self.assertNotIn('base_url',json.dumps(result));self.assertNotIn('content_base64',json.dumps(result))

    def test_uncertain_gateway_receipt_never_dispatches(self):
        rid=uuid.uuid4().hex;p=dict(primary_id=self.profiles[0]['id'],reviewer_id=self.profiles[1]['id'])
        import hashlib
        digest=hashlib.sha256(json.dumps({'action':'center_create','payload':p},sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        with self.g._db() as db:db.execute('INSERT INTO receipts VALUES(?,?,NULL)',(rid,digest))
        self.assertFalse(self.rpc('center_create',p,rid)['ok']);self.assertEqual(self.b._auto.center.sessions.list(),[])

    def test_phone_plan_requires_exact_round_and_confirmation(self):
        import time
        a,b,c=self.profiles
        session=self.b.call('api_center_create',dict(primary_id=a['id'],reviewer_id=b['id']))['data']
        job=dict(title='草案',instruction='保留原材料',output_format='text',primary_id=a['id'])
        plan=dict(id=session['id'],text='交办测试',jobs=[job])
        send_id=uuid.uuid4().hex
        self.assertFalse(self.rpc('center_prepare',{**plan,'jobs':[{**job,'primary_id':c['id']}]},uuid.uuid4().hex)['ok'])
        self.assertFalse(self.rpc('center_prepare',{**plan,'jobs':[{**job,'path':'C:/private'}]},uuid.uuid4().hex)['ok'])
        response=self.rpc('center_prepare',plan,send_id)
        self.assertTrue(response['ok'],response)
        self.assertEqual(self.rpc('center_prepare',plan,send_id),response)
        prepared=response['data']['turns'][-1]
        self.assertEqual(prepared['state'],'prepared')
        self.assertEqual(prepared['jobs'][0]['instruction'],'保留原材料')
        self.assertEqual(self.client.calls,[])
        wrong=dict(id=session['id'],turn_id=uuid.uuid4().hex)
        self.assertFalse(self.rpc('center_confirm',wrong,uuid.uuid4().hex)['ok'])
        unchanged=self.rpc('center_cancel_plan',wrong,uuid.uuid4().hex)
        self.assertEqual(unchanged['data']['turns'][-1]['state'],'prepared')
        exact=dict(id=session['id'],turn_id=prepared['id'])
        request=uuid.uuid4().hex
        confirmed=self.rpc('center_confirm',exact,request)
        self.assertTrue(confirmed['ok'],confirmed)
        self.assertEqual(self.rpc('center_confirm',exact,request),confirmed)
        deadline=time.monotonic()+8
        while self.b._auto.center.busy() and time.monotonic()<deadline:time.sleep(.02)
        self.assertEqual(len(self.client.calls),1)
        self.assertTrue(self.rpc('center_confirm',exact,uuid.uuid4().hex)['ok'])
        next_plan=self.rpc('center_prepare',plan,uuid.uuid4().hex)['data']['turns'][-1]
        stale=self.rpc('center_stop',exact,uuid.uuid4().hex)
        self.assertEqual(stale['data']['turns'][-1]['state'],'prepared')
        cancelled=self.rpc('center_cancel_plan',dict(id=session['id'],turn_id=next_plan['id']),uuid.uuid4().hex)
        self.assertTrue(cancelled['ok'],cancelled)
        self.assertEqual(cancelled['data']['turns'][-1]['state'],'cancelled')
        self.assertEqual(len(self.client.calls),1)
    def test_busy_is_explicit_rejection_before_mutation(self):
        p=dict(primary_id=self.profiles[0]['id'],reviewer_id=self.profiles[1]['id'])
        self.b._command_lock.acquire()
        try:
            result=self.rpc('center_create',p,uuid.uuid4().hex);self.assertEqual(result['error'],'center_busy')
            self.assertEqual(self.b._auto.center.sessions.list(),[])
        finally:self.b._command_lock.release()
        self.assertTrue(self.rpc('center_create',p,uuid.uuid4().hex)['ok'])

if __name__=='__main__':unittest.main()
