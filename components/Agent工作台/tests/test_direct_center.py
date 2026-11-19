import json,unittest,threading,time
import test_agent_center as fixtures
from test_negotiated_chat import Negotiator

class DirectTests(unittest.TestCase):
    setUp=fixtures.CenterTests.setUp
    call=fixtures.CenterTests.call
    create=fixtures.CenterTests.create
    send=fixtures.CenterTests.send
    done=fixtures.CenterTests.done
    def test_owner_only_no_reviewer_profile_and_one_call(self):
        chat=self.create();job=dict(title='文档',instruction='只输出正文',output_format='docx',primary_id=self.roles['A'])
        chat=self.send(chat,'制作文档','execute',jobs=[job]);self.call('api_center_confirm',dict(id=chat['id'],request_id=chat['turns'][0]['id']));chat=self.done(chat)
        turn=chat['turns'][0];run=turn['jobs'][0]['run']
        self.assertEqual(turn['call_count'],1);self.assertEqual(len(self.client.calls),1)
        self.assertEqual(set(run['roles']),{'A'});self.assertEqual([s['stage'] for s in run['steps']],['交付']);self.assertEqual(run['call_limit'],1)
        self.assertEqual(run['files'][0]['format'],'docx');self.assertNotIn('独立审查',self.client.calls[0][0]['content'])
    def test_negotiated_jobs_only_require_executor_and_cost_one_each(self):
        chat=self.create();jobs=[dict(title='正文',instruction='制作正文',output_format='docx',executor='A'),dict(title='图示',instruction='绘图',output_format='svg',executor='B')]
        client=Negotiator(dict(schema='agent-center-decision/v1',mode='work',reply='分别制作正文和图示。',jobs=jobs))
        self.bridge._auto.center.agent.chat.client=client;self.bridge._auto.center.agent.workflow.engine.client=client
        chat=self.done(self.send(chat,'自行协商整理文档与配图','chat'))
        self.assertEqual(chat['turns'][0]['state'],'completed');self.assertEqual(chat['call_count'],4)
        self.assertEqual([len(j['run']['steps']) for j in chat['turns'][0]['jobs']],[1,1])
        self.assertTrue(all('B' not in j['run']['roles'] for j in chat['turns'][0]['jobs']))
    def test_old_preset_reviewer_is_ignored_without_rewriting(self):
        chat=self.create();path=self.bridge._auto.center.preset.path;path.parent.mkdir(parents=True,exist_ok=True)
        old=dict(name='旧预设',jobs=[dict(title='文档',instruction='',output_format='text',primary_id=self.roles['A'],reviewer_id='missing')])
        raw=json.dumps(old);path.write_text(raw,encoding='utf-8')
        preset=self.call('api_center_bootstrap')['preset'];self.assertNotIn('reviewer_id',preset['jobs'][0]);self.assertEqual(path.read_text(encoding='utf-8'),raw)
        self.call('api_center_preset_save',preset)
    def test_direct_text_has_concise_instruction(self):
        chat=self.create();chat=self.send(chat,'给我简洁的结论','execute',jobs=[dict(title='结论',instruction='',output_format='text',primary_id=self.roles['A'])])
        self.call('api_center_confirm',dict(id=chat['id'],request_id=chat['turns'][0]['id']));chat=self.done(chat)
        self.assertEqual(chat['turns'][0]['state'],'completed');self.assertIn('先给结论',self.client.calls[0][0]['content'])
    def test_legacy_api_payload_cannot_enable_direct_mode(self):
        self.create();run=self.call('api_start',dict(task='旧版流程',primary_id=self.roles['A'],reviewer_id=self.roles['B'],call_limit=3,direct=True,execution_mode='direct'))
        end=time.monotonic()+3
        while self.bridge.busy() and time.monotonic()<end:time.sleep(.01)
        run=self.call('api_status',dict(id=run['id']))
        self.assertEqual(run['execution_mode'],'review');self.assertEqual(run['call_count'],3);self.assertEqual(set(run['roles']),{'A','B'})
    def test_stop_during_direct_owner_does_not_call_another_model(self):
        from provider_client import Cancelled
        chat=self.create();entered=threading.Event()
        def pause(profile,key,messages,max_tokens,cancel,on_chunk,deadline):
            self.client.calls.append(messages);entered.set();cancel.wait(3);raise Cancelled('已停止')
        self.bridge._auto.center.workflow.engine.client.complete=pause
        chat=self.send(chat,'任务','execute',jobs=[dict(title='负责部分',instruction='',output_format='text',primary_id=self.roles['A'])])
        self.call('api_center_confirm',dict(id=chat['id'],request_id=chat['turns'][0]['id']));self.assertTrue(entered.wait(2));self.assertTrue(self.bridge._api_active())
        self.call('api_center_stop',dict(id=chat['id']));chat=self.done(chat)
        self.assertEqual(chat['turns'][0]['state'],'cancelled');self.assertEqual(len(self.client.calls),1)

if __name__=='__main__':unittest.main()
