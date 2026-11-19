import tempfile,unittest,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workbench_notices import publish_notice
class NoticeTests(unittest.TestCase):
 def test_terminal_only_bounded_no_user_content(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'events.json'
   publish_notice(p,'task','a'*32,'草稿');self.assertFalse(p.exists())
   publish_notice(p,'task','a'*32,'结果待确认');publish_notice(p,'task','a'*32,'结果待确认')
   data=json.loads(p.read_text(encoding='utf-8'));self.assertEqual(len(data['events']),1);self.assertEqual(data['events'][0]['kind'],'waiting')
   for n in range(110):publish_notice(p,'task',format(n,'032x'),'已完成')
   self.assertEqual(len(json.loads(p.read_text(encoding='utf-8'))['events']),100)
 def test_corrupt_feed_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'events.json';p.write_text('bad');self.assertFalse(publish_notice(p,'task','a'*32,'失败'));self.assertEqual(p.read_text(encoding='utf-8'),'bad')

class RecoveryNoticeTests(unittest.TestCase):
 def test_independent_recovery_notifies_once(self):
  from task_station.core import Service
  from test_station import FakeModels
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);a=Service(root/'station',FakeModels());task=a.call('create',dict(task_type='text',role='text_1',instruction='test'))
   task['status']='执行中';a._save(task);a.pool.shutdown()
   b=Service(root/'station',FakeModels());b.pool.shutdown();events=json.loads((root/'pet-notices.json').read_text(encoding='utf-8'))['events'];self.assertEqual(len(events),1);self.assertEqual(events[0]['status'],'需要检查')
 def test_collaboration_recovery_notifies(self):
  from session_store import SessionStore
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);s=SessionStore(root/'sessions');s.save(dict(id='b'*32,title='test',status='running',call_count=0,call_limit=9,steps=[]));s.recover_interrupted()
   event=json.loads((root/'pet-notices.json').read_text(encoding='utf-8'))['events'][0];self.assertEqual(event['source'],'collaboration');self.assertEqual(event['kind'],'waiting')


class CenterNoticeTests(unittest.TestCase):
    from test_agent_center import CenterTests as fixtures
    setUp = fixtures.setUp
    call = fixtures.call
    create = fixtures.create
    send = fixtures.send
    done = fixtures.done

    def events(self):
        path = self.base/'data/pet-notices.json'
        return json.loads(path.read_text(encoding='utf-8'))['events']

    def test_direct_plan_notices_follow_original_turn_and_ignore_duplicate_confirmation(self):
        session = self.send(self.create(), '只在成果页展示这段测试任务内容', 'execute')
        turn = session['turns'][0]['id']
        self.assertEqual(self.client.calls, [])
        self.assertEqual([(row['task_id'], row['status']) for row in self.events()], [(turn, 'prepared')])
        self.assertIn('待确认',self.events()[0]['title'])
        self.assertNotIn('测试任务内容', json.dumps(self.events(), ensure_ascii=False))
        args = dict(id=session['id'],request_id=turn)
        self.call('api_center_confirm',args)
        self.done(session)
        self.call('api_center_confirm',args)
        self.assertEqual([(row['source'], row['task_id'], row['status']) for row in self.events()],
                         [('center', turn, 'completed')])
        self.assertIn('可验收',self.events()[0]['title'])
        self.assertEqual(len(self.client.calls), 1)

    def test_cancelled_plan_removes_only_its_pending_notice(self):
        legacy = self.base/'data/pet-notices.json'
        self.assertTrue(publish_notice(legacy, 'task', 'a'*32, '结果待确认'))
        session = self.send(self.create(), '查看后取消的计划', 'execute')
        turn = session['turns'][0]['id']
        self.call('api_center_stop', dict(id=session['id'], prepared_id=turn))
        self.assertEqual([(row['source'], row['status']) for row in self.events()], [('task', '结果待确认')])
        self.assertEqual(self.client.calls, [])

    def test_accept_is_idempotent_and_preserves_the_original_turn(self):
        session=self.send(self.create(),'验收记录', 'execute',jobs=[
            dict(title='文字交付',instruction='',output_format='text',primary_id=self.roles['A'])])
        turn=session['turns'][0]['id']
        payload=dict(id=session['id'],turn_id=turn)
        self.assertFalse(self.bridge.call('api_center_accept',payload)['ok'])
        self.call('api_center_confirm',dict(id=session['id'],request_id=turn))
        self.done(session)
        first=self.call('api_center_accept',payload)
        self.assertEqual(self.call('api_center_accept',payload),first)
        details=self.call('api_center_status',dict(id=session['id']))['turns'][0]
        self.assertEqual((details['id'],details['state'],details['accepted_at']),(turn,'completed',first['accepted_at']))
        self.assertFalse(self.events())
        today=self.call('workstation_butler_status',{})['today']
        self.assertEqual(today['review']['count'],0)
        self.assertEqual(today['accepted']['items'][0]['turn_id'],turn)
        self.assertEqual(len(self.client.calls),1)

    def test_failed_subtask_reports_its_owner_turn_instead_of_a_completion(self):
        self.client.fail_at = 1
        session = self.send(self.create(), '失败回执测试', 'execute',
                            jobs=[dict(title='模拟任务', instruction='', output_format='text', primary_id=self.roles['A'])])
        turn = session['turns'][0]['id']
        self.call('api_center_confirm', dict(id=session['id'], request_id=turn))
        self.done(session)
        self.assertEqual([(row['task_id'], row['status'], row['kind']) for row in self.events()], [(turn, 'failed', 'waiting')])

