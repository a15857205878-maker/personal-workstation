from pathlib import Path
import importlib.util,json,sys,tempfile,unittest
W=Path(__file__).resolve().parents[1];sys.path.insert(0,str(W))
P=Path(__file__).resolve().parents[2]/'agent-desktop-pet'

class RoomTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  from companion_room import RoomPresence
  spec=importlib.util.spec_from_file_location('room_pet_fixture',P/'pet_room_presence.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
  self.now=100.;self.host=RoomPresence(self.root,clock=lambda:self.now);self.pet=mod.RoomPresence(self.root,clock=lambda:self.now)
 def test_character_waits_for_native_hidden_ack(self):
  token=self.host.enter()['token'];self.assertFalse(self.host.heartbeat(token)['home'])
  self.assertTrue(self.pet.requested());self.pet.publish(False,'dragon');self.assertFalse(self.host.heartbeat(token)['home'])
  self.pet.publish(True,'dragon');self.assertTrue(self.host.heartbeat(token)['home'])
 def test_expiry_returns_native_and_hides_room_after_crash(self):
  token=self.host.enter()['token'];self.pet.requested();self.pet.publish(True,'dragon');self.now+=9
  self.assertFalse(self.pet.requested());self.assertFalse(self.host.status(token)['home'])
 def test_release_and_late_heartbeat_cannot_rehide_native(self):
  token=self.host.enter()['token'];self.host.leave(token);self.assertFalse(self.pet.requested())
  with self.assertRaises(ValueError):self.host.heartbeat(token)
 def test_tray_override_revokes_current_token(self):
  token=self.host.enter()['token'];self.pet.requested();self.pet.revoke()
  with self.assertRaises(ValueError):self.host.heartbeat(token)
  self.assertFalse(self.pet.requested())
 def test_stale_ack_and_other_character_do_not_render_dragon(self):
  token=self.host.enter()['token'];self.pet.requested();self.pet.publish(True,'legacy')
  self.assertFalse(self.host.status(token)['home'])
  with self.assertRaisesRegex(ValueError,'龙娘'):self.host.heartbeat(token)
  token=self.host.enter()['token'];self.pet.requested();self.pet.publish(True,'dragon');self.now+=3
  self.assertFalse(self.host.heartbeat(token)['home'])
 def test_core_rejects_extra_paths_and_hidden_surface_requests(self):
  from workstation_core import WorkstationCore
  from types import SimpleNamespace
  from unittest.mock import Mock
  core=WorkstationCore(SimpleNamespace(_room_surface_visible=False),tools=Mock(),town=Mock());core._room=self.host
  for action,payload in [('workstation_room_view',{'path':'x'}),('workstation_room_enter',{'command':'x'}),('workstation_room_heartbeat',{'token':'x'})]:
   with self.assertRaises(ValueError):core.call(action,payload)
  with self.assertRaisesRegex(ValueError,'隐藏'):core.call('workstation_room_enter',{})
 def test_room_layout_does_not_create_or_rewrite_town_saves(self):
  from town_adapter import TownAdapter,load_backend
  town=TownAdapter(base=self.root)
  self.assertEqual(town.room_layout()['inventory'],{});self.assertFalse((self.root/'data').exists())
  backend=load_backend();data=backend.new_town();(self.root/'data').mkdir();save=self.root/'data/town.json'
  raw=json.dumps(data).encode();save.write_bytes(raw)
  self.assertEqual(town.room_layout()['inventory'],data['inventory']);self.assertEqual(save.read_bytes(),raw)
  save.write_bytes(b'bad');self.assertEqual(town.room_layout()['inventory'],{});self.assertEqual(save.read_bytes(),b'bad')
 def test_other_window_cannot_steal_live_lease(self):
  from companion_room import RoomPresence
  self.host.enter();other=RoomPresence(self.root,clock=lambda:self.now)
  with self.assertRaises(ValueError):other.enter()
 def test_malformed_request_is_ignored(self):
  for value in [dict(version=1,token='a'*32,mode='home',expires=float('nan')),dict(version=1,token='a'*32,mode='home',expires=99999),dict(version=1,token='../../x',mode='home',expires=105)]:
   (self.root/'room-presence.request.json').write_text(json.dumps(value))
   self.assertFalse(self.pet.requested())
 def test_quiet_room_does_not_cancel_existing_user_hide_or_game(self):
  spec=importlib.util.spec_from_file_location('quiet_room_fixture',P/'pet_quiet.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  q=m.QuietState();self.assertEqual(q.update(False,False,True,False,room=True),'enter')
  q.user_hide();self.assertEqual(q.update(False,False,False,False,room=False),'exit');self.assertFalse(q.restore_pet)
  q=m.QuietState();q.update(True,True,True,False);self.assertIsNone(q.update(True,True,False,False,room=True));self.assertIsNone(q.update(True,True,False,False,room=False))

if __name__=='__main__':unittest.main()
