import unittest
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from town_adapter import TownAdapter, load_backend
from workstation_core import WorkstationCore

class TownAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="town-adapter-", dir=Path(__file__).resolve().parent)
        self.base = Path(self.temp.name)
        self.tick = [100.0]
        self.adapter = TownAdapter(self.base, clock=lambda: self.tick[0])
    def tearDown(self):
        self.temp.cleanup()
    def test_lazy_state_and_isolated_imports(self):
        self.assertIsNone(self.adapter._bridge)
        before = {k: sys.modules.get(k) for k in ('town_backend','town_state','town_store')}
        state = self.adapter.call('bootstrap')
        self.assertIn('town',state)
        self.assertTrue((self.base/'data/town.json').is_file())
        self.assertTrue(self.adapter._bridge.__class__.__module__.startswith('_workstation_town_'))
        self.assertEqual(before,{k: sys.modules.get(k) for k in before})
        state = self.adapter.call('town_action',{'action':'buy','args':{'kind':'plant'}})
        self.assertTrue(state['town']['inventory'])
    def test_focus_close_pauses_own_instance(self):
        state = self.adapter.call('focus_start',{'task':'test','minutes':25})
        self.assertTrue(state['focus']['running'])
        self.tick[0] += 10
        self.adapter.close()
        self.assertFalse(self.adapter._bridge._focus.running)
        self.adapter.close()
        resumed = TownAdapter(self.base).call('bootstrap')
        self.assertTrue(resumed['focus']['active'])
        self.assertFalse(resumed['focus']['running'])
        self.assertEqual(resumed['focus']['remaining'],1490)
        with self.assertRaises(ValueError): self.adapter.call('bootstrap')
    def test_rejects_unknown_paths_and_oversized_before_initializing(self):
        for action,payload in [('launch_tool',{}),('bootstrap',{'path':'x'}),('focus_start',{'task':'x'*8193}),('town_action',{'action':'buy','args':{'path':'x'}})]:
            with self.subTest(action=action,payload_keys=list(payload)):
                with self.assertRaises(ValueError): self.adapter.call(action,payload)
        self.assertIsNone(self.adapter._bridge)
        self.assertFalse((self.base/'data').exists())
    def test_original_revision_conflict_is_preserved_and_close_retryable(self):
        self.adapter.call('bootstrap')
        other = TownAdapter(self.base)
        other.call('settings_save',{'theme':'dark','motion':True})
        saved = (self.base/'data/town.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'其他窗口'): self.adapter.call('set_mode',{'mode':'focus'})
        with self.assertRaisesRegex(ValueError,'其他窗口'): self.adapter.close()
        self.assertFalse(self.adapter._closed)
        self.assertEqual(saved,(self.base/'data/town.json').read_bytes())
    def test_core_routes_snapshot_and_only_closes_own_town(self):
        tools = Mock()
        core = WorkstationCore(Mock(),tools=tools,town=self.adapter)
        result = core.call('workstation_town_call',{'action':'bootstrap','payload':{}})
        self.assertIn('town',result)
        tools.call.assert_not_called()
        with self.assertRaises(ValueError):core.call('workstation_town_call',{'action':'bootstrap','path':'elsewhere'})
        core.close()
        tools.close.assert_called_once()
    def test_unused_close_does_not_create_data(self):
        self.adapter.close()
        self.assertFalse((self.base/'data').exists())

if __name__ == '__main__': unittest.main()

