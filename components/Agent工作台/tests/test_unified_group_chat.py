import json,unittest,uuid,time,threading
import test_agent_center as fixtures
import test_negotiated_chat as negotiated

class GroupTests(unittest.TestCase):
    def setUp(self):
        fixtures.CenterTests.setUp(self);self.addCleanup(self.stop_workers)
    def stop_workers(self):
        self.bridge._stop_api();end=time.monotonic()+4
        while self.bridge.busy() and time.monotonic()<end:time.sleep(.01)
    call=fixtures.CenterTests.call
    create=fixtures.CenterTests.create
    send=fixtures.CenterTests.send
    done=fixtures.CenterTests.done
    configure_client=negotiated.NegotiatedTests.configure_client
    def test_group_order_and_multiple_rounds_decode_only_final_message(self):
        chat=self.create();client=self.configure_client()
        chat=self.done(self.send(chat,'大家先交流看法，不需要制作文件。','chat',target='BA',rounds=2))
        turn=chat['turns'][0];self.assertEqual(turn['state'],'completed');self.assertEqual(turn['call_count'],4)
        self.assertEqual([m['seat'] for m in turn['run']['messages']],['U','B','A','B','A'])
        self.assertEqual([('agent-center-decision/v1' in messages[0]['content']) for messages in client.calls],[False,False,False,True])
        self.assertEqual(client.profiles,[self.roles['B'],self.roles['A'],self.roles['B'],self.roles['A']])
        self.assertEqual(sum('control' in m for m in turn['run']['messages']),1);self.assertFalse(turn.get('jobs'))
    def test_address_single_member_can_chat_then_deliver_without_mode_switch(self):
        for seat in ('A','B'):
            chat=self.create();client=self.configure_client('work',[dict(title='文档',instruction='按已给资料整理。',output_format='docx',executor=seat)])
            chat=self.done(self.send(chat,'请把这些已给材料整理成文档。','chat',target=seat))
            turn=chat['turns'][0];self.assertEqual(turn['state'],'completed');self.assertEqual(turn['call_count'],2)
            self.assertEqual([m['seat'] for m in turn['run']['messages']],['U',seat]);self.assertEqual(client.profiles,[self.roles[seat],self.roles[seat]])
            self.assertEqual(turn['jobs'][0]['run']['files'][0]['format'],'docx')
    def test_round_budget_and_invalid_single_member_rounds_rejected_before_send(self):
        chat=self.create();client=self.configure_client();raw=self.bridge._auto.center.sessions.load(chat['id']);raw['call_limit']=3;self.bridge._auto.center.sessions.save(raw)
        for options in (dict(target='AB',rounds=2),dict(target='B',rounds=2),dict(target='AB',rounds=True)):
            result=self.bridge.call('api_center_send',dict(id=chat['id'],request_id=uuid.uuid4().hex,text='聊聊',kind='chat',**options));self.assertFalse(result['ok'])
        self.assertEqual(client.calls,[]);self.assertEqual(self.call('api_center_status',dict(id=chat['id']))['turns'],[])
    def test_delivery_after_final_round_and_duplicate_do_not_repeat(self):
        chat=self.create();client=self.configure_client('work',[dict(title='文档',instruction='制作正文',output_format='docx',executor='A')])
        payload=dict(id=chat['id'],request_id=uuid.uuid4().hex,text='你们交流两轮再协商整理文档。',kind='chat',target='AB',rounds=2)
        self.call('api_center_send',payload);chat=self.done(chat);self.call('api_center_send',payload)
        self.assertEqual(chat['turns'][0]['state'],'completed');self.assertEqual(chat['call_count'],5);self.assertEqual(len(client.calls),5)
        self.assertIn('公开回应',json.dumps(client.calls[3],ensure_ascii=False))
    def test_final_decision_cannot_overrun_budget_after_longer_discussion(self):
        chat=self.create();client=self.configure_client('work',[dict(title='文档',instruction='',output_format='docx',executor='A')])
        raw=self.bridge._auto.center.sessions.load(chat['id']);raw['call_limit']=4;self.bridge._auto.center.sessions.save(raw)
        chat=self.done(self.send(chat,'讨论后整理文件','chat',target='BA',rounds=2))
        self.assertEqual(chat['turns'][0]['state'],'failed');self.assertEqual(chat['call_count'],4);self.assertEqual(len(client.calls),4)
        self.assertFalse(chat['turns'][0].get('jobs'))
    def test_stop_in_middle_of_group_rounds_never_starts_work(self):
        from provider_client import Cancelled
        chat=self.create();client=self.configure_client('work',[dict(title='文档',instruction='',output_format='docx',executor='A')]);entered=threading.Event();complete=client.complete
        def pause(profile,key,messages,max_tokens,cancel,on_chunk,deadline):
            result=complete(profile,key,messages,max_tokens,cancel,on_chunk,deadline)
            if len(client.calls)==2:entered.set();cancel.wait(3);raise Cancelled('已停止')
            return result
        client.complete=pause
        self.send(chat,'讨论后制作文档','chat',target='BA',rounds=2);self.assertTrue(entered.wait(2))
        self.call('api_center_stop',dict(id=chat['id']));chat=self.done(chat)
        self.assertEqual(chat['turns'][0]['state'],'cancelled');self.assertEqual(chat['call_count'],2);self.assertFalse(chat['turns'][0].get('jobs'))

if __name__=='__main__':unittest.main()
