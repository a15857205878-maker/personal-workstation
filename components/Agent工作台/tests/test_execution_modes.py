from pathlib import Path
import sys,tempfile,unittest,threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).resolve().parent))
from task_station.core import Service
from test_station import FakeModels
class ModeTests(unittest.TestCase):
 def test_external_prompt_and_no_api_execution(self):
  with tempfile.TemporaryDirectory() as d:
   s=Service(Path(d),FakeModels())
   try:
    task=s.call('create',dict(task_type='pptx',role='presentation_gemini',instruction='两页旅行介绍',execution_mode='external'))
    self.assertEqual(task['execution_mode'],'external');self.assertNotIn('version=2协议',task['prompt'])
    with self.assertRaises(ValueError):s.call('submit',dict(id=task['id']))
    changed=s.call('set_execution_mode',dict(id=task['id'],execution_mode='api'))
    self.assertIn('version=2协议',changed['prompt']);self.assertEqual(changed['instruction'],task['instruction']);self.assertEqual(changed['status'],'草稿')
   finally:s.close()
 def test_handoff_attempt_locks_mode_and_prevents_implicit_retry(self):
  with tempfile.TemporaryDirectory() as d:
   s=Service(Path(d),FakeModels())
   try:
    task=s.call('create',dict(task_type='pptx',role='presentation_gemini',instruction='两页',execution_mode='external'))
    s.begin_external_handoff(task['id'])
    with self.assertRaises(ValueError):s.call('set_execution_mode',dict(id=task['id'],execution_mode='api'))
    with self.assertRaises(ValueError):s.begin_external_handoff(task['id'])
    self.assertEqual(s.call('get',dict(id=task['id']))['status'],'需要检查')
   finally:s.close()
 def test_code_and_old_tasks_keep_original_route(self):
  with tempfile.TemporaryDirectory() as d:
   s=Service(Path(d),FakeModels())
   try:
    task=s.call('create',dict(task_type='software_error',role='backend_and_integration',instruction='分析报错'))
    self.assertEqual(task.get('execution_mode','legacy'),'legacy')
    with self.assertRaises(ValueError):s.call('set_execution_mode',dict(id=task['id'],execution_mode='external'))
   finally:s.close()
 def test_no_overwrite_no_wrong_window_and_no_retry_after_uncertain_write(self):
  from task_station.client_handoff import paste_editor
  for initial,trusted in [('已有草稿',True),('',False)]:
   writes=[];e={'read':lambda:initial,'write':writes.append,'guard':lambda:trusted}
   self.assertFalse(paste_editor(e,'新任务')['pasted']);self.assertEqual(writes,[])
  value=[''];writes=[]
  def write(text):writes.append(text);value[0]=text
  self.assertTrue(paste_editor({'read':lambda:value[0],'write':write,'guard':lambda:True},'新任务')['pasted']);self.assertEqual(writes,['新任务'])
 def test_uncertain_write_is_not_retried(self):
  from task_station.client_handoff import paste_editor
  calls=[]
  def read():
   if calls:raise RuntimeError('read-back unavailable')
   return ''
  result=paste_editor({'read':read,'write':calls.append,'guard':lambda:True},'只写一次')
  self.assertTrue(result['uncertain']);self.assertFalse(result['pasted']);self.assertEqual(calls,['只写一次'])
 def test_local_gemini_and_kimi_startup_preferred(self):
  from unittest.mock import patch
  from task_station.host import launch_plan
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   for f in ['Google/Gemini/Gemini.exe','Programs/Kimi/Kimi.exe']:
    p=root/f;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'fixture-not-executable')
   with patch.dict('os.environ',{'LOCALAPPDATA':d}):
    self.assertEqual(launch_plan('presentation_gemini'),('exe',str(root/'Google/Gemini/Gemini.exe')))
    self.assertEqual(launch_plan('research_kimi'),('exe',str(root/'Programs/Kimi/Kimi.exe')))
    self.assertEqual(launch_plan('text_claude'),('app','Claude_pzs8sxrjxfjjc!Claude'))
 def test_host_external_handoff_no_provider_and_no_real_clipboard(self):
  from unittest.mock import patch
  from task_station.host import Bridge
  with tempfile.TemporaryDirectory() as d:
   host=Bridge(Path(d));host.service.adapter=FakeModels()
   try:
    task=host.call('create',dict(task_type='pptx',role='presentation_gemini',instruction='两页演示',execution_mode='external'))['data']
    with patch('task_station.host.copy_text') as copy,patch('task_station.host.launch_plan',return_value=('exe','fixture.exe')),patch('task_station.host.subprocess.Popen') as launch,patch('task_station.client_handoff.paste_client',return_value={'pasted':True,'message':'已填入，未发送'}) as paste:
     result=host.call('handoff',dict(id=task['id']));self.assertTrue(result['ok'],result);self.assertTrue(result['data']['handoff']['pasted']);self.assertEqual(result['data']['status'],'等待交接');copy.assert_called_once();launch.assert_called_once();paste.assert_called_once()
     self.assertEqual(host.service.adapter.calls,[])
   finally:host.service.close()
if __name__=='__main__':unittest.main()

