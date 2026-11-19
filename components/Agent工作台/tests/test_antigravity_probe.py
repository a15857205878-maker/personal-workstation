import unittest,tempfile,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

class ProbeTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def test_desktop_alone_is_not_a_model_channel(self):
        from antigravity_probe import snapshot
        path=self.root/'AppData/Local/Programs/antigravity/Antigravity.exe';path.parent.mkdir(parents=True);path.write_bytes(b'fake')
        result=snapshot(home=self.root,path_lookup=lambda _:None)
        self.assertEqual(result['state'],'desktop_only');self.assertFalse(result['can_generate']);self.assertTrue(result['desktop_installed'])
    def test_native_cli_discovery_is_still_unverified(self):
        from antigravity_probe import snapshot
        path=self.root/'AppData/Local/agy/bin/agy.exe';path.parent.mkdir(parents=True);path.write_bytes(b'not executed')
        result=snapshot(home=self.root,path_lookup=lambda _:None)
        self.assertEqual(result['state'],'cli_found_unverified');self.assertFalse(result['can_generate']);self.assertTrue(result['cli_found'])
    def test_missing_and_script_shim_do_not_claim_ready(self):
        from antigravity_probe import snapshot
        script=self.root/'agy.cmd';script.write_text('not executed')
        result=snapshot(home=self.root,path_lookup=lambda _:str(script))
        self.assertEqual(result['state'],'missing');self.assertFalse(result['can_generate'])
    def test_bridge_probe_does_not_initialize_models_and_rejects_arguments(self):
        from backend import Bridge
        bridge=Bridge(self.root/'missing',data_dir=self.root/'data')
        with patch('antigravity_probe.snapshot',return_value={'state':'desktop_only','can_generate':False}):
            result=bridge.call('api_antigravity_status',{})
        self.assertTrue(result['ok']);self.assertIsNone(bridge._auto)
        self.assertFalse(bridge.call('api_antigravity_status',{'executable':'unexpected.exe'})['ok']);self.assertIsNone(bridge._auto)

if __name__=='__main__':unittest.main()
