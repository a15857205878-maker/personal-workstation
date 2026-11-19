from pathlib import Path
import importlib.util,os,sys,unittest
from unittest.mock import Mock,patch
PET=Path(os.environ.get('AGENT_PET_ROOT', str(Path(__file__).resolve().parents[2] / 'agent-desktop-pet')))
if not (PET/'pet_workstation.py').is_file():
    raise unittest.SkipTest('Requires the optional desktop pet')
sys.path.insert(0,str(PET))
from pet_workstation import WorkstationClient

class ClientTests(unittest.TestCase):
 def test_status_poll_never_starts_workstation_and_filters_private_fields(self):
  starts=[]
  client=WorkstationClient(transport=lambda method,payload:{'version':1,'navigation_ready':True,'counts':{'tasks':2,'active':1},'private':'hidden'},opener=lambda:starts.append(True))
  client.snapshot();client.status_thread.join(2)
  result=client.snapshot();self.assertEqual(result['state'],'online');self.assertEqual(result['counts']['tasks'],2)
  self.assertNotIn('private',result);self.assertFalse(starts)
 def test_offline_open_starts_existing_entry_then_navigates_only_once(self):
  state={'online':False};calls=[]
  def transport(method,payload):
   if not state['online']:raise OSError()
   calls.append((method,payload));return {'version':1,'navigation_ready':True,'counts':{}}
  client=WorkstationClient(transport=transport,opener=lambda:state.update(online=True))
  self.assertTrue(client.open('tasks'));client.action_thread.join(2)
  self.assertEqual([x for x in calls if x[0]=='POST'],[('POST',{'page':'tasks'})])
  self.assertEqual(client.snapshot()['last_action']['state'],'opened')
 def test_unknown_command_is_rejected_before_transport(self):
  calls=[];client=WorkstationClient(transport=lambda *a:calls.append(a))
  with self.assertRaises(ValueError):client.open('powershell.exe')
  self.assertFalse(calls)
 def test_turn_click_starts_hidden_workstation_once_then_posts_exact_id(self):
  started=[];posts=[];results=[];turn='a'*32
  def transport(method,payload):
   if method=='POST':
    posts.append(payload);return {'opened':True,'turn_id':payload['turn_id']}
   return {'version':1,'navigation_ready':bool(started),'counts':{}}
  client=WorkstationClient(transport=transport,opener=lambda:started.append(True))
  self.assertTrue(client.open_turn(turn,results.append));client.action_thread.join(2)
  self.assertEqual((started,posts,results),([True],[{'turn_id':turn}],[True]))
  with self.assertRaises(ValueError):client.open_turn('../anywhere')
 def test_uncertain_navigation_post_is_not_replayed(self):
  posts=[]
  def transport(method,payload):
   if method=='POST':posts.append(payload);raise OSError('lost receipt')
   return {'version':1,'navigation_ready':True,'counts':{}}
  client=WorkstationClient(transport=transport);client.open('tasks');client.action_thread.join(2)
  self.assertEqual(posts,[{'page':'tasks'}]);self.assertEqual(client.snapshot()['last_action']['state'],'error')
 def test_offline_status_never_starts_or_returns_false_zero_counts(self):
  opener=Mock()
  def offline(*args):raise OSError()
  client=WorkstationClient(transport=offline,opener=opener);client.snapshot();client.status_thread.join(2)
  self.assertEqual(client.snapshot()['state'],'offline');self.assertIsNone(client.snapshot()['counts']);opener.assert_not_called()
 def test_panel_navigation_validates_envelope(self):
  from pet_panel_actions import apply_action
  client=Mock()
  with patch('pet_workstation.client_for',return_value=client):
   apply_action(Mock(),{'action':'workstation-open','page':'tasks'})
   client.open.assert_called_once_with('tasks')
   with self.assertRaises(ValueError):apply_action(Mock(),{'action':'workstation-open','page':'tasks','command':'run'})

if __name__=='__main__':unittest.main()
