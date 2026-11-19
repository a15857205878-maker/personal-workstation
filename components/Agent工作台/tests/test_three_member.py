import json,unittest,uuid,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_agent_center as fixtures
import test_negotiated_chat as negotiated

class ThreeTests(unittest.TestCase):
    setUp=fixtures.CenterTests.setUp
    call=fixtures.CenterTests.call
    send=fixtures.CenterTests.send
    done=fixtures.CenterTests.done
    configure_client=negotiated.NegotiatedTests.configure_client
    def create3(self):
        self.roles['C']=self.call('api_profile_save',dict(name='Gemini',kind='antigravity_local',model='gemini-test'))['id']
        return self.call('api_center_create',dict(primary_id=self.roles['A'],reviewer_id=self.roles['B'],third_id=self.roles['C'],seat_styles={'C':{'preset':'custom','text':'C独有风格'}}))
    def test_three_order_and_final_control_and_context(self):
        c=self.create3();client=self.configure_client()
        c=self.done(self.send(c,'三位先聊聊，不执行','chat',target='CBA',rounds=2))
        t=c['turns'][0];self.assertEqual(t['state'],'completed');self.assertEqual(t['call_count'],6)
        self.assertEqual([m['seat'] for m in t['run']['messages']],list('UCBACBA'))
        self.assertEqual(['agent-center-decision/v1' in m[0]['content'] for m in client.calls],[False]*5+[True])
        self.assertIn('C独有风格',client.calls[0][0]['content'])
        from agent_center import bounded_context
        self.assertIn('C席',''.join(bounded_context(c['turns'])[0]))
    def test_c_executes_own_job_once_and_remembers_private_source(self):
        c=self.create3();client=self.configure_client('work',[dict(title='文档',instruction='整理已给资料',output_format='docx',executor='C')])
        c=self.done(self.send(c,'把这些明确材料整理成文档','chat',target='ABC'))
        t=c['turns'][0];self.assertEqual(t['state'],'completed');self.assertEqual(client.profiles,[self.roles[s] for s in 'ABCC'])
        self.assertIn('C独有风格',client.calls[-1][0]['content']);self.assertTrue(t['jobs'][0]['run']['files'])
        run=t['run'];m=next(x for x in run['messages'] if x['seat']=='C')
        self.call('api_center_memory_save',dict(scope='C',kind='preference',text='C私有偏好',source=dict(chat_id=run['id'],message_id=m['id'],excerpt=m['content'][:50])))
        mem=self.bridge._auto.chat.memory
        self.assertTrue(mem.relevant('C',''));self.assertFalse(mem.relevant('A',''));self.assertFalse(mem.relevant('B',''))
    def test_invalid_targets_and_budget_do_not_dispatch(self):
        c=self.create3();client=self.configure_client()
        for target in ('D','AAC','ABCD','',True):
            self.assertFalse(self.bridge.call('api_center_send',dict(id=c['id'],request_id=uuid.uuid4().hex,text='hi',kind='chat',target=target))['ok'])
        raw=self.bridge._auto.center.sessions.load(c['id']);raw['call_limit']=2;self.bridge._auto.center.sessions.save(raw)
        self.assertFalse(self.bridge.call('api_center_send',dict(id=c['id'],request_id=uuid.uuid4().hex,text='hi',kind='chat',target='ABC'))['ok'])
        self.assertEqual(client.calls,[])
    def test_pair_and_single_c_and_legacy_two(self):
        c=self.create3();client=self.configure_client()
        c=self.done(self.send(c,'点名','chat',target='C'));c=self.done(self.send(c,'两位','chat',target='AC'))
        self.assertEqual(client.profiles,[self.roles[s] for s in 'CAC'])
        old=fixtures.CenterTests.create(self)
        self.assertNotIn('C',old['roles'])
        self.assertFalse(self.bridge.call('api_center_send',dict(id=old['id'],request_id=uuid.uuid4().hex,text='hi',kind='chat',target='C'))['ok'])
    def test_three_member_legacy_single_execution_remains_supported(self):
        c=self.create3();c=self.send(c,'直接制作正文','execute')
        self.call('api_center_confirm',dict(id=c['id'],request_id=c['turns'][-1]['id']))
        c=self.done(c);self.assertEqual(c['turns'][-1]['state'],'completed')

if __name__=='__main__':unittest.main()
