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
