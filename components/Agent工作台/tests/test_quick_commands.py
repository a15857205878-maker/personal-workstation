import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from quick_commands import QuickCommands
class Store:
 def bundle(self,ids):return dict(text='资料内容' if ids else '')
class Bridge:
 def __init__(self):self.calls=[];self.attachments=Store()
 def call(self,action,payload):self.calls.append((action,payload));return dict(ok=True,data={'id':'draft'})
class QuickTests(unittest.TestCase):
 def test_work_brief_idempotent_without_task_creation(self):
  bridge=Bridge();received=[];q=QuickCommands(bridge,received.append);p=dict(request_id='one',mode='work',text='任务',attachments=[])
  q.submit(p);q.submit(p);self.assertEqual(bridge.calls,[]);self.assertEqual(received[-1],{'kind':'advanced','text':'任务','request_id':'one'})
 def test_advanced_includes_text_without_model_call(self):
  b=Bridge();events=[];q=QuickCommands(b,events.append);q.submit(dict(request_id='a',mode='work',text='检查',attachments=['a']))
  self.assertIn('资料内容',events[0]['text']);self.assertEqual(b.calls,[])
 def test_length_and_unknown_mode_rejected(self):
  q=QuickCommands(Bridge(),lambda e:None)
  for p in [dict(mode='work',text='x'*8001),dict(mode='shell',text='hi'),dict(mode='work',text=' ')]:
   with self.assertRaises(ValueError):q.submit({'request_id':'bad',**p})
 def test_retry_after_failed_delivery_does_not_duplicate_draft(self):
  b=Bridge();q=QuickCommands(b,lambda e:(_ for _ in ()).throw(ValueError('busy')));p=dict(request_id='retry',mode='work',text='hi')
  with self.assertRaises(ValueError):q.submit(p)
  q.dispatch=lambda e:None;q.submit(p);self.assertEqual(b.calls,[])

 def test_retired_task_mode_never_creates_record(self):
  b=Bridge();q=QuickCommands(b,lambda e:None)
  with self.assertRaisesRegex(ValueError,'独立任务已停用'):q.submit(dict(request_id='old',mode='tasks',text='hi'))
  self.assertEqual(b.calls,[])
