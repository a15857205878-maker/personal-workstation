import json,sys,tempfile,time,threading,unittest,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import Bridge
from test_api import FakeClient

class CenterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.client=FakeClient();self.bridge=Bridge(self.base/'missing',data_dir=self.base/'data',api_client=self.client)
        self.roles={}
        for seat in ('A','B'):
            self.roles[seat]=self.call('api_profile_save',dict(name=seat,kind='compatible',base_url='https://mock.invalid',model=seat,api_key='fake-secret'))['id']
    def call(self,action,payload=None):
        r=self.bridge.call(action,payload);self.assertTrue(r['ok'],r);return r['data']
    def create(self):return self.call('api_center_create',dict(primary_id=self.roles['A'],reviewer_id=self.roles['B']))
    def send(self,chat,text,kind='discuss',**options):
        return self.call('api_center_send',dict(id=chat['id'],request_id=uuid.uuid4().hex,text=text,kind=kind,**options))
    def done(self,chat):
        end=time.monotonic()+4
        while self.bridge.busy() and time.monotonic()<end:time.sleep(.01)
        self.assertFalse(self.bridge.busy());return self.call('api_center_status',{'id':chat['id']})
    def test_discuss_execute_followup_same_timeline_and_context(self):
        chat=self.create();chat=self.done(self.send(chat,'讨论素材：海边观测'))
        self.assertEqual(len(self.client.calls),2)
        chat=self.send(chat,'根据讨论整理方案','execute')
        self.assertEqual(chat['turns'][-1]['state'],'prepared');self.assertEqual(len(self.client.calls),2)
        request=chat['turns'][-1]['id']
        self.call('api_center_confirm',dict(id=chat['id'],request_id=request));chat=self.done(chat)
        self.assertEqual(len(self.client.calls),3)
        self.assertIn('海边观测',json.dumps(self.client.calls[2],ensure_ascii=False))
        chat=self.done(self.send(chat,'继续修改，把上面的方案精简'))
        self.assertEqual(len(chat['turns']),3);self.assertEqual(chat['call_count'],5)
        self.assertIn('reply-3',json.dumps(self.client.calls[3]))
        self.assertEqual([t['kind'] for t in chat['turns']],['discuss','execute','discuss'])
        self.assertNotIn('fake-secret',json.dumps(chat));self.assertFalse((self.base/'data/chats').exists())
        again=Bridge(self.base/'missing',data_dir=self.base/'data',api_client=FakeClient())
        restored=again.call('api_center_status',{'id':chat['id']})['data']
        self.assertEqual(restored['call_count'],5);self.assertEqual(len(restored['turns']),3)
    def test_duplicate_send_and_confirm_never_repeat(self):
        chat=self.create();payload=dict(id=chat['id'],request_id=uuid.uuid4().hex,kind='execute',text='写方案')
        self.call('api_center_send',payload);self.call('api_center_send',payload)
        self.assertFalse(self.bridge.call('api_center_send',{**payload,'text':'changed'})['ok'])
        confirm={k:payload[k] for k in ('id','request_id')}
        self.call('api_center_confirm',confirm);chat=self.done(chat);self.call('api_center_confirm',confirm)
        self.assertEqual(len(self.client.calls),1);self.assertEqual(len(chat['turns']),1)
    def test_failure_and_missing_reference_no_automatic_retry(self):
        self.client.fail_at=1;chat=self.done(self.send(self.create(),'hello'))
        self.assertEqual(chat['turns'][0]['state'],'failed');self.assertEqual(chat['call_count'],1)
        self.call('api_center_status',{'id':chat['id']});self.assertEqual(len(self.client.calls),1)
        run=chat['turns'][0]['run_id'];self.bridge._auto.center.chat.sessions.delete(run)
        chat=self.call('api_center_status',{'id':chat['id']})
        self.assertEqual(chat['turns'][0]['state'],'interrupted');self.assertEqual(chat['call_count'],1)
    def test_cancel_uses_close_protection_and_shared_gate(self):
        class Slow(FakeClient):
            def complete(self,profile,key,messages,max_tokens,cancel,on_chunk,deadline):
                cancel.wait(3);return super().complete(profile,key,messages,max_tokens,cancel,on_chunk,deadline)
        chat=self.create();self.bridge._auto.center.chat.client=Slow();self.send(chat,'hello')
        self.assertTrue(self.bridge._api_active())
        self.assertFalse(self.bridge.call('api_start',dict(task='busy',primary_id=self.roles['A'],reviewer_id=self.roles['B']))['ok'])
        self.bridge._stop_api();chat=self.done(chat)
        self.assertEqual(chat['turns'][0]['state'],'cancelled');self.assertEqual(chat['call_count'],1)
    def test_budget_changed_profile_and_pending_turn_blocked(self):
        chat=self.create();chat=self.send(chat,'任务','execute')
        self.assertFalse(self.bridge.call('api_center_send',dict(id=chat['id'],request_id=uuid.uuid4().hex,text='next',kind='discuss'))['ok'])
        self.call('api_center_stop',{'id':chat['id']})
        raw=self.bridge._auto.center.sessions.load(chat['id']);raw['call_limit']=0;self.bridge._auto.center.sessions.save(raw)
        result=self.bridge.call('api_center_send',dict(id=chat['id'],request_id=uuid.uuid4().hex,text='task',kind='execute'))
        self.assertFalse(result['ok']);self.assertEqual(len(self.client.calls),0)
        p=self.bridge._auto.profiles.list()[0];self.call('api_profile_save',{**p,'model':'changed'})
        self.assertFalse(self.bridge.call('api_center_send',dict(id=chat['id'],request_id=uuid.uuid4().hex,text='hi',kind='discuss'))['ok'])
    def test_context_bounded_and_excludes_partial_reply(self):
        from agent_center import bounded_context
        turns=[dict(text='u'*8000,kind='execute',state='failed',run={'steps':[dict(seat='A',model='m',stage='提案',state='completed',content='x'*20000),dict(seat='B',model='m',stage='审查',state='failed',content='PARTIAL_MARKER')]}) for _ in range(30)]
        context,omitted=bounded_context(turns)
        self.assertLessEqual(sum(map(len,context)),12000);self.assertLessEqual(len(context),20);self.assertGreater(omitted,0)
        self.assertNotIn('PARTIAL_MARKER',''.join(context))
    def test_editable_preset_and_compound_task_real_documents_and_svg(self):
        class Files(FakeClient):
            def complete(self,profile,key,messages,max_tokens,cancel,on_chunk,deadline):
                self.calls.append(messages)
                text='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><rect width="200" height="100" fill="purple"/></svg>' if 'SVG真实文件' in messages[0]['content'] and '独立审查' not in messages[0]['content'] else '文档正文：海边观测报告'
                on_chunk(text);return dict(content=text,model=profile['model'],finish_reason='stop')
        self.client=Files();self.bridge=Bridge(self.base/'missing',data_dir=self.base/'data',api_client=self.client)
        jobs=[dict(title='文档',instruction='整理正文',output_format='docx',primary_id=self.roles['A'],reviewer_id=self.roles['B']),dict(title='示意图',instruction='画观测流程图',output_format='svg',primary_id=self.roles['B'],reviewer_id=self.roles['A'])]
        self.call('api_center_preset_save',dict(name='研究材料',jobs=jobs))
        self.assertEqual(self.call('api_center_bootstrap')['preset']['jobs'],[{k:v for k,v in j.items() if k!='reviewer_id'} for j in jobs])
        chat=self.create();chat=self.send(chat,'整理观测总览','execute',jobs=jobs)
        self.assertEqual(len(self.client.calls),0)
        self.call('api_center_confirm',dict(id=chat['id'],request_id=chat['turns'][0]['id']));chat=self.done(chat)
        turn=chat['turns'][0];self.assertEqual(turn['state'],'completed');self.assertEqual(turn['call_count'],2)
        self.assertEqual([j['run']['roles']['A']['id'] for j in turn['jobs']],[self.roles['A'],self.roles['B']])
        self.assertIn('海边观测报告',json.dumps(self.client.calls[1],ensure_ascii=False))
        self.assertEqual([j['run']['files'][0]['format'] for j in turn['jobs']],['docx','svg'])
        self.assertTrue(self.call('api_collaboration_file',dict(id=turn['jobs'][1]['run_id'],name=turn['jobs'][1]['run']['files'][0]['name']))['content_base64'])
    def test_compound_failure_stops_later_jobs(self):
        chat=self.create();jobs=[dict(title='第一步',instruction='',output_format='text',primary_id=self.roles['A'],reviewer_id=self.roles['B']),dict(title='第二步',instruction='',output_format='text',primary_id=self.roles['B'],reviewer_id=self.roles['A'])]
        self.client.fail_at=1;chat=self.send(chat,'任务','execute',jobs=jobs)
        self.call('api_center_confirm',dict(id=chat['id'],request_id=chat['turns'][0]['id']));chat=self.done(chat)
        self.assertEqual(chat['turns'][0]['state'],'failed');self.assertEqual(len(self.client.calls),1)
        self.assertEqual(chat['turns'][0]['jobs'][1]['state'],'skipped')
    def test_stop_before_dispatch_never_starts_another_request(self):
        chat=self.create();jobs=[dict(title='一步',instruction='',output_format='text',primary_id=self.roles['A'],reviewer_id=self.roles['B'])]
        chat=self.send(chat,'task','execute',jobs=jobs);runner=self.bridge._auto.center.workflow
        reached=threading.Event();release=threading.Event();original=runner.on_update
        def hold(*args):
            original(*args)
            if args[3] and args[3].get('state')=='starting':reached.set();release.wait(3)
        runner.on_update=hold
        self.call('api_center_confirm',dict(id=chat['id'],request_id=chat['turns'][0]['id']))
        self.assertTrue(reached.wait(2))
        try:self.call('api_center_stop',{'id':chat['id']})
        finally:release.set()
        chat=self.done(chat)
        self.assertEqual(len(self.client.calls),0);self.assertEqual(chat['turns'][0]['state'],'cancelled')
    def test_svg_rejects_namespaced_script_and_escaped_css(self):
        from collaboration_files import create_artifact
        for svg in ['<svg xmlns="http://www.w3.org/2000/svg" xmlns:s="http://www.w3.org/2000/svg"><s:script>alert(1)</s:script></svg>',r'<svg xmlns="http://www.w3.org/2000/svg"><style>rect{fill:u\72l(https://example.invalid/a)}</style></svg>']:
            with self.assertRaises(ValueError):create_artifact(self.base,dict(id=uuid.uuid4().hex,output_format='svg',steps=[dict(seat='A',stage='修订',state='completed',content=svg)]))
    def test_corrupt_preset_keeps_new_conversation_available(self):
        path=self.base/'data/agent-center/preset.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text('{bad',encoding='utf-8')
        data=self.call('api_center_bootstrap');self.assertIsNone(data['preset']);self.assertTrue(data['preset_error'])
        self.create();self.assertEqual(path.read_text(encoding='utf-8'),'{bad')
    def test_missing_workflow_result_does_not_report_completed(self):
        chat=self.create();jobs=[dict(title='一步',instruction='',output_format='text',primary_id=self.roles['A'],reviewer_id=self.roles['B'])]
        chat=self.send(chat,'task','execute',jobs=jobs)
        self.call('api_center_confirm',dict(id=chat['id'],request_id=chat['turns'][0]['id']));chat=self.done(chat)
        self.bridge._auto.sessions.delete(chat['turns'][0]['jobs'][0]['run_id'])
        chat=self.call('api_center_status',{'id':chat['id']})
        self.assertEqual(chat['turns'][0]['state'],'interrupted');self.assertEqual(chat['call_count'],1)

if __name__=='__main__':unittest.main()
