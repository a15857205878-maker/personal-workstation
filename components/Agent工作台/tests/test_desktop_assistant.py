from pathlib import Path
import sys,tempfile,json,unittest,http.client
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desktop_assistant import DesktopAssistant

class AssistantTests(unittest.TestCase):
 def test_status_exports_counts_only(self):
  bridge=Mock();bridge.call.return_value={'ok':True,'data':{'counts':{'tasks':3,'collaborations':1,'active':1,'attention':2},'tasks':[{'instruction':'private','title':'private'}]}}
  data=DesktopAssistant(bridge).status()
  self.assertEqual(data['counts']['active'],1)
  self.assertNotIn('tasks',data['pages']);self.assertIn('partner',data['pages']);self.assertNotIn('private',json.dumps(data));self.assertEqual(bridge.call.call_args_list,[unittest.mock.call('workstation_overview',{}),unittest.mock.call('workstation_focus_status',{})])
 def test_fixed_page_navigation_never_submits_tasks(self):
  bridge=Mock();bridge.station_window.evaluate_js.return_value=True
  self.assertEqual(DesktopAssistant(bridge).open({'page':'tasks'})['page'],'artifacts')
  bridge.call.assert_not_called();bridge.station_window.show.assert_called_once()
  for payload in ({'page':'cmd.exe'},{'page':'tasks','instruction':'run'},{'page':[]},{}):
   with self.assertRaises(ValueError):DesktopAssistant(bridge).open(payload)
 def test_turn_navigation_uses_exact_id_and_uses_current_task_state(self):
  from session_store import SessionStore
  with tempfile.TemporaryDirectory() as tmp:
   bridge=Mock();bridge._data_dir=Path(tmp);bridge.station_window.evaluate_js.return_value=True
   store=SessionStore(bridge._data_dir/'agent-center/conversations')
   for i in ('a','b'):
    store.save({'id':i*32,'title':'同名任务','status':'idle','steps':[],'call_count':0,'call_limit':3,
                'turns':[{'id':(i+'c')*16,'kind':'execute','state':'completed' if i=='a' else 'prepared'}]})
   assistant=DesktopAssistant(bridge)
   for i,section in [('a','delivery'),('b','progress')]:
    turn=(i+'c')*16
    self.assertEqual(assistant.open({'turn_id':turn})['turn_id'],turn)
    event=json.loads(bridge.station_window.evaluate_js.call_args.args[0].removeprefix('window.workbenchReceive?.(')[:-1])
    self.assertEqual(event,dict(kind='center_turn',conversation_id=i*32,turn_id=turn,section=section))
   for payload in ({'turn_id':'f'*32},{'turn_id':'../a'},{'turn_id':'ac'*16,'section':'progress'}):
    with self.assertRaises(ValueError):assistant.open(payload)
   bridge.call.assert_not_called()

 def test_local_endpoint_requires_key_and_rejects_browser_origin(self):
  from remote_gateway import RemoteGateway
  with tempfile.TemporaryDirectory() as tmp:
   bridge=Mock();bridge.call.return_value={'ok':True,'data':{'counts':{'active':0}}}
   gateway=RemoteGateway(bridge,Path(tmp),port=0).start()
   try:
    def request(method,body=None,headers=None):
     c=http.client.HTTPConnection('127.0.0.1',gateway.port,timeout=3);c.request(method,'/assistant',body=json.dumps(body) if body is not None else None,headers=headers or {});r=c.getresponse();value=(r.status,json.loads(r.read()));c.close();return value
    self.assertEqual(request('GET')[0],401)
    self.assertEqual(request('GET',headers={'X-Workbench-Key':gateway.key,'Origin':'http://external.example'})[0],401)
    self.assertEqual(request('POST',{'page':'tasks'},headers={'X-Workbench-Key':gateway.key,'Sec-Fetch-Site':'cross-site'})[0],401)
    code,result=request('GET',headers={'X-Workbench-Key':gateway.key});self.assertEqual(code,200);self.assertEqual(result['data']['version'],1)
    self.assertEqual(request('POST',{'page':'api_start'},headers={'X-Workbench-Key':gateway.key})[0],400)
   finally:gateway.close()

if __name__=='__main__':unittest.main()
