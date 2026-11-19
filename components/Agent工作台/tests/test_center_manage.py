import unittest,sys,uuid,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_agent_center as fixtures
import test_center_remote as remote_fixtures

class ManagementTests(unittest.TestCase):
    setUp=fixtures.CenterTests.setUp
    call=fixtures.CenterTests.call
    create=fixtures.CenterTests.create
    send=fixtures.CenterTests.send
    done=fixtures.CenterTests.done
    def test_rename_archive_restore_preserves_turns_and_models(self):
        c=self.done(self.send(self.create(),'这条原记录要保留'))
        original=json.dumps(c['roles'],sort_keys=True);count=c['call_count'];turns=[t['id'] for t in c['turns']]
        c=self.call('api_center_manage',dict(id=c['id'],title='我的项目',archived=True))
        self.assertEqual(c['title'],'我的项目');self.assertTrue(c['archived'])
        rows=self.call('api_center_bootstrap')['sessions'];self.assertTrue(next(r for r in rows if r['id']==c['id'])['archived'])
        self.assertFalse(self.bridge.call('api_center_send',dict(id=c['id'],request_id=uuid.uuid4().hex,kind='chat',text='不可发送'))['ok'])
        c=self.call('api_center_manage',dict(id=c['id'],archived=False))
        self.assertEqual([t['id'] for t in c['turns']],turns);self.assertEqual(c['call_count'],count);self.assertEqual(json.dumps(c['roles'],sort_keys=True),original)
    def test_invalid_busy_and_prepared_management_does_not_write(self):
        c=self.create();path=self.bridge._auto.center.sessions._directory(c['id'])/'session.json';before=path.read_bytes()
        for data in (dict(title=' '),dict(title='x'*61),dict(archived='true'),dict(path='anything'),{}):
            self.assertFalse(self.bridge.call('api_center_manage',dict(id=c['id'],**data))['ok'])
        self.assertEqual(path.read_bytes(),before)
        self.bridge._command_lock.acquire()
        try:self.assertFalse(self.bridge.call('api_center_manage',dict(id=c['id'],title='busy'))['ok'])
        finally:self.bridge._command_lock.release()
        c=self.send(c,'准备的任务','execute')
        self.assertFalse(self.bridge.call('api_center_manage',dict(id=c['id'],archived=True))['ok'])
    def test_manual_title_survives_first_message(self):
        c=self.create();self.call('api_center_manage',dict(id=c['id'],title='新的协作'))
        c=self.done(self.send(c,'不能覆盖我手动命名的标题'))
        self.assertEqual(c['title'],'新的协作')

class PhoneManagementTests(unittest.TestCase):
    setUp=remote_fixtures.CenterRemoteTests.setUp
    rpc=remote_fixtures.CenterRemoteTests.rpc
    def test_phone_manage_receipt_and_history_limit(self):
        c=self.b.call('api_center_create',dict(primary_id=self.profiles[0]['id'],reviewer_id=self.profiles[1]['id']))['data']
        raw=self.b._auto.center.sessions.load(c['id'])
        raw['turns']=[dict(id=uuid.uuid4().hex,kind='chat',text=str(i),state='cancelled',call_count=0,error='',run_id=None) for i in range(25)]
        self.b._auto.center.sessions.save(raw)
        data=self.rpc('center_get',dict(id=c['id']))['data'];self.assertEqual(len(data['turns']),12);self.assertEqual(data['history_omitted'],13)
        data=self.rpc('center_get',dict(id=c['id'],history_limit=60))['data'];self.assertEqual(len(data['turns']),25);self.assertEqual(data['history_omitted'],0)
        for limit in (0,61,True,'60'):
            self.assertFalse(self.rpc('center_get',dict(id=c['id'],history_limit=limit))['ok'])
        rid=uuid.uuid4().hex;p=dict(id=c['id'],title='手机命名',archived=True)
        r=self.rpc('center_manage',p,rid);self.assertTrue(r['ok'],r);self.assertEqual(self.rpc('center_manage',p,rid),r)
        self.assertTrue(self.b.call('api_center_status',{'id':c['id']})['data']['archived'])

if __name__=='__main__':unittest.main()
