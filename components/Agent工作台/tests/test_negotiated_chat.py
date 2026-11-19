import json,threading,uuid,unittest
import test_agent_center as fixtures
from test_api import FakeClient

class Negotiator(FakeClient):
    def __init__(self,decision):super().__init__();self.decision=decision;self.profiles=[]
    def complete(self,profile,key,messages,max_tokens,cancel,on_chunk,deadline):
        self.calls.append(messages);self.profiles.append(profile['id'])
        if 'agent-center-decision/v1' in messages[0]['content']:
            text=self.decision if isinstance(self.decision,str) else json.dumps(self.decision,ensure_ascii=False)
        elif 'SVG真实文件' in messages[0]['content'] and '独立审查' not in messages[0]['content']:
            text='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 80"><text x="5" y="40">本周方案</text></svg>'
        else:text='公开回应：先明确资料范围，再制作交付内容。'
        on_chunk(text);return dict(content=text,model=profile['model'],finish_reason='stop')

class NegotiatedTests(unittest.TestCase):
    setUp=fixtures.CenterTests.setUp
    call=fixtures.CenterTests.call
    create=fixtures.CenterTests.create
    send=fixtures.CenterTests.send
    done=fixtures.CenterTests.done
    def configure_client(self,mode='reply',jobs=None):
        value=dict(schema='agent-center-decision/v1',mode=mode,reply='我们先按已有资料继续。' if mode!='clarify' else '这周项目的目标、资料和截止时间是什么？',jobs=jobs or [])
        client=Negotiator(value);self.bridge._auto.center.agent.chat.client=client;self.bridge._auto.center.agent.workflow.engine.client=client
        return client
    def jobs(self):return [dict(title='项目总览文档',instruction='整理本次用户提供的材料，不编造进度。',output_format='docx',executor='B',reviewer='A')]
    def draft(self,chat):
        return self.done(self.call('api_center_draft',dict(id=chat['id'],request_id=uuid.uuid4().hex,text='请根据这些资料拟一项文档分工。')))
    def test_draft_requests_json_transport_with_an_example(self):
        chat=self.create();client=self.configure_client('work',self.jobs());structured=[]
        def complete_json(*args):
            structured.append(args[2])
            return client.complete(*args)
        client.complete_json=complete_json
        turn=self.draft(chat)['turns'][0]
        self.assertEqual(turn['state'],'prepared')
        self.assertEqual(len(structured),1)
        self.assertIn('"mode":"work"',structured[0][0]['content'])
        self.assertEqual(len(client.calls),1)
    def test_enclosed_json_draft_stays_awaiting_confirmation(self):
        chat=self.create();client=self.configure_client('work',self.jobs())
        client.decision='```json\n'+json.dumps(client.decision,ensure_ascii=False)+'\n```'
        turn=self.draft(chat)['turns'][0]
        self.assertEqual(turn['state'],'prepared')
        self.assertEqual(len(client.calls),1)
        self.assertIsNone(turn['jobs'][0]['run_id'])
    def test_invalid_draft_reports_specific_reason_without_dispatching(self):
        chat=self.create();client=self.configure_client('work',self.jobs())
        client.decision['jobs'][0]['output_format']='exe'
        turn=self.draft(chat)['turns'][0]
        self.assertEqual(turn['state'],'failed')
        self.assertFalse(turn.get('jobs'))
        self.assertEqual(len(client.calls),1)
        failure=turn['failures'][0]
        self.assertEqual(failure['code'],'plan_rejected')
        self.assertIn('交付格式',failure['detail'])
        self.assertNotIn('单独重试',failure['hint'])
        self.assertFalse(failure['retryable'])
    def test_legacy_draft_fails_with_recovery_hint(self):
        from failure_recovery import failure_targets
        error='协商方案格式、能力或剩余预算不符合限制，未执行任何子任务；可调整需求后再聊。'
        turn=dict(id='example',kind='execute',state='failed',drafted=True,error=error)
        failure=failure_targets(dict(turns=[turn]),turn)[0]
        self.assertEqual(failure['code'],'plan_rejected')
        self.assertIn('旧记录',failure['detail'])
        self.assertNotIn('单独重试',failure['hint'])
    def test_casual_chat_and_clarification_do_not_dispatch(self):
        chat=self.create();client=self.configure_client();chat=self.done(self.send(chat,'今天想和你们随便聊聊','chat'))
        self.assertEqual(chat['turns'][0]['state'],'completed');self.assertEqual(len(client.calls),2)
        self.assertEqual(chat['turns'][0]['decision']['mode'],'reply');self.assertFalse(chat['turns'][0].get('jobs'))
        self.assertNotIn('"schema"',chat['turns'][0]['run']['messages'][-1]['content'])
        client.decision.update(mode='clarify',reply='请提供本周项目目标和已有资料。')
        chat=self.done(self.send(chat,'完成我这周的项目','chat'))
        self.assertEqual(chat['turns'][-1]['decision']['mode'],'clarify');self.assertEqual(chat['call_count'],4)
    def test_negotiate_document_without_manual_assignment_and_followup(self):
        chat=self.create();client=self.configure_client('work',self.jobs())
        chat=self.done(self.send(chat,'你们自己协商，把我上面的材料整理成一份文档','chat'))
        turn=chat['turns'][0];self.assertEqual(turn['state'],'completed');self.assertEqual(turn['call_count'],3)
        self.assertEqual(len(turn['jobs'][0]['run']['files']),1);self.assertEqual(client.profiles[2],self.roles['B'])
        self.assertIn('已完成',turn['report']);self.assertIn('.docx',turn['report'])
        client.decision.update(mode='reply',jobs=[])
        chat=self.done(self.send(chat,'再解释下这份文档','chat'))
        self.assertEqual(chat['call_count'],5);self.assertIn('项目总览',json.dumps(client.calls[-2],ensure_ascii=False))
    def test_multiple_sections_report_only_actual_files(self):
        chat=self.create();jobs=self.jobs()+[dict(title='流程图',instruction='把项目流程画成SVG。',output_format='svg',executor='A',reviewer='B')]
        client=self.configure_client('work',jobs);chat=self.done(self.send(chat,'用这些已给出的材料做本周项目总览和配图','chat'))
        self.assertEqual(chat['turns'][0]['state'],'completed');self.assertEqual(chat['call_count'],4)
        self.assertEqual([j['run']['files'][0]['format'] for j in chat['turns'][0]['jobs']],['docx','svg'])
        self.assertIn('流程图',chat['turns'][0]['report'])
    def test_invalid_decision_and_budget_never_dispatch(self):
        chat=self.create();client=self.configure_client('work',[dict(title='x',instruction='x',output_format='exe',executor='A',reviewer='B')])
        chat=self.done(self.send(chat,'hello','chat'));self.assertEqual(chat['turns'][0]['state'],'failed');self.assertEqual(len(client.calls),2)
        client.decision.update(jobs=self.jobs());raw=self.bridge._auto.center.sessions.load(chat['id']);raw['call_limit']=4;self.bridge._auto.center.sessions.save(raw)
        chat=self.done(self.send(chat,'再整理文档','chat'))
        self.assertEqual(chat['turns'][-1]['state'],'failed');self.assertEqual(chat['call_count'],4)
    def test_stop_between_decision_and_work_prevents_dispatch(self):
        chat=self.create();client=self.configure_client('work',self.jobs());runner=self.bridge._auto.center.agent
        reached=threading.Event();release=threading.Event();original=runner.on_update
        def hold(*args):
            original(*args)
            if args[2].get('decision'):reached.set();release.wait(3)
        runner.on_update=hold
        self.send(chat,'自己协商写文档','chat');self.assertTrue(reached.wait(2))
        try:self.call('api_center_stop',{'id':chat['id']})
        finally:release.set()
        chat=self.done(chat);self.assertEqual(len(client.calls),2);self.assertEqual(chat['turns'][0]['state'],'cancelled')
    def test_lab_styles_memory_and_source_are_shared(self):
        chat=self.call('api_center_create',dict(primary_id=self.roles['A'],reviewer_id=self.roles['B'],seat_styles={'A':{'preset':'custom','text':'A_STYLE'},'B':{'preset':'custom','text':'B_STYLE'}}))
        self.call('api_chat_memory_save',dict(scope='A',kind='preference',text='A_PRIVATE'))
        self.call('api_chat_memory_save',dict(scope='shared',kind='note',text='SHARED_INFO'))
        client=self.configure_client();chat=self.done(self.send(chat,'聊一下','chat'))
        self.assertIn('A_STYLE',json.dumps(client.calls[0]));self.assertIn('A_PRIVATE',json.dumps(client.calls[0]));self.assertNotIn('A_PRIVATE',json.dumps(client.calls[1]))
        run=chat['turns'][0]['run'];m=run['messages'][-1]
        self.call('api_center_memory_save',dict(scope='shared',kind='preference',text='简洁些',source=dict(chat_id=run['id'],message_id=m['id'],seat=m['seat'],excerpt=m['content'],title='test')))
        self.assertEqual(self.call('api_chat_memory')['count'],3)
    def test_small_context_keeps_latest_input(self):
        chat=self.create();service=self.bridge._auto.center.chat
        run=service.create(dict(primary_id=self.roles['A'],reviewer_id=self.roles['B'],seat_styles={'A':{'preset':'lele','resolved_text':'风'*12000},'B':{'preset':'conductor'}}))
        for i in range(14):self.call('api_chat_memory_save',dict(scope='A',kind='note',text=str(i)+'资料'*240))
        self.call('api_chat_memory_save',dict(scope='shared',kind='note',text='保留当前问题'))
        service.memory.relevant=lambda seat,query:[dict(id=str(i),text='资料'*240) for i in range(12)]
        service.send(dict(id=run['id'],text='LATEST_INPUT_MARKER'+'问'*3800),reference_context=['旧参考'*500]*4)
        self.done(chat)
        self.assertIn('LATEST_INPUT_MARKER',json.dumps(self.client.calls[0]))
        self.assertLessEqual(sum(len(m['content']) for m in self.client.calls[0]),24000)
    def test_large_catalog_and_style_never_drop_current_user_input(self):
        for i in range(30):self.call('api_profile_save',dict(name=str(i)+'名'*77,kind='compatible',base_url='https://mock.invalid',model='m'*200,api_key='fake-secret'))
        chat=self.call('api_center_create',dict(primary_id=self.roles['A'],reviewer_id=self.roles['B'],seat_styles={'A':{'preset':'conductor'},'B':{'preset':'lele','resolved_text':'风'*12000}}))
        jobs=[dict(title=str(i)+'文档',instruction='要求'*490,output_format='docx',primary_id=self.roles['A'],reviewer_id=self.roles['B']) for i in range(4)]
        self.call('api_center_preset_save',dict(name='long',jobs=jobs));client=self.configure_client()
        chat=self.done(self.send(chat,'LATEST_INPUT_MARKER'+'问'*3800,'chat'))
        self.assertEqual(chat['turns'][0]['state'],'completed')
        self.assertTrue(all('LATEST_INPUT_MARKER' in json.dumps(messages) for messages in client.calls),'每个模型都必须看到当前用户输入')
        self.assertTrue(all(sum(len(m['content']) for m in messages)<=24000 for messages in client.calls))
    def test_duplicate_and_restart_never_resubmit_negotiated_work(self):
        from backend import Bridge
        chat=self.create();client=self.configure_client('work',self.jobs())
        payload=dict(id=chat['id'],request_id=uuid.uuid4().hex,text='你们自己协商整理文档',kind='chat')
        self.call('api_center_send',payload);self.call('api_center_send',payload);chat=self.done(chat)
        self.call('api_center_send',payload);self.assertEqual(len(client.calls),3)
        other=Bridge(self.base/'missing',data_dir=self.base/'data',api_client=FakeClient())
        restored=other.call('api_center_status',dict(id=chat['id']))['data']
        self.assertEqual(restored['call_count'],3);self.assertEqual(restored['turns'][0]['state'],'completed');self.assertIn('.docx',restored['turns'][0]['report'])
    def test_failed_section_stops_later_work_and_reports_failure(self):
        from provider_client import ProviderError
        chat=self.create();client=self.configure_client('work',self.jobs()+[dict(title='后续汇总',instruction='汇总',output_format='text',executor='A',reviewer='B')])
        complete=client.complete
        def fail(*args):
            result=complete(*args)
            if len(client.calls)==3:raise ProviderError('模拟负责人交付失败')
            return result
        client.complete=fail;chat=self.done(self.send(chat,'根据材料写方案并汇总','chat'))
        turn=chat['turns'][0];self.assertEqual(turn['state'],'failed');self.assertEqual(turn['call_count'],3)
        self.assertEqual(turn['jobs'][1]['state'],'skipped');self.assertIn('失败',turn['report']);self.assertNotIn('.docx',turn['report'])
    def test_close_during_chat_cancels_and_keeps_shared_gate(self):
        from provider_client import Cancelled
        chat=self.create();client=self.configure_client();entered=threading.Event()
        def pause(profile,key,messages,max_tokens,cancel,on_chunk,deadline):
            client.calls.append(messages);entered.set();cancel.wait(3);raise Cancelled('用户关闭')
        client.complete=pause;self.send(chat,'hello','chat');self.assertTrue(entered.wait(2));self.assertTrue(self.bridge._api_active())
        self.assertFalse(self.bridge.call('api_profile_delete',dict(id=self.roles['A']))['ok'])
        self.bridge._stop_api();chat=self.done(chat)
        self.assertEqual(chat['turns'][0]['state'],'cancelled');self.assertEqual(chat['call_count'],1)

if __name__=='__main__':unittest.main()
