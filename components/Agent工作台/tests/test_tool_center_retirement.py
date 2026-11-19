import sys,tempfile,unittest,runpy
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[2];NEW=ROOT/'个人工具中心新版';OLD=ROOT/'个人工具中心'
sys.path.insert(0,str(NEW));sys.path.insert(1,str(OLD))
import workstation_redirect
class RetirementTests(unittest.TestCase):
 def test_fixed_destination_and_no_inherited_old_arguments(self):
  spawn=Mock();workstation_redirect.launch(base=NEW,spawn=spawn,executable='fixture-pythonw.exe')
  args,kwargs=spawn.call_args;self.assertEqual(args[0],['fixture-pythonw.exe',str(ROOT/'Agent工作台/launch.pyw')]);self.assertEqual(Path(kwargs['cwd']),ROOT/'Agent工作台')
 def test_missing_workstation_stops_without_launching_legacy(self):
  with tempfile.TemporaryDirectory() as folder:
   spawn=Mock()
   with self.assertRaises(FileNotFoundError):workstation_redirect.launch(base=Path(folder)/'tools',spawn=spawn)
   spawn.assert_not_called()
 def test_legacy_launch_and_normal_apps_forward_without_old_window(self):
  for entry in [NEW/'launch.pyw',NEW/'app.py',OLD/'app.py']:
   with self.subTest(entry=entry),patch.object(workstation_redirect,'launch') as forward,patch.object(sys,'argv',[str(entry)]):
    runpy.run_path(str(entry),run_name='__main__');forward.assert_called_once()
if __name__=='__main__':unittest.main()
