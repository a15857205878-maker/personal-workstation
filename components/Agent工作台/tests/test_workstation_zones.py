import unittest
from unittest.mock import Mock
from workstation_zones import catalog, split_tools, validate_module
from workstation_core import WorkstationCore

class ZoneTests(unittest.TestCase):
    def test_catalog_does_not_start_engines_or_tools(self):
        bridge=Mock();tools=Mock()
        result=WorkstationCore(bridge,tools).call('workstation_zones',{})
        self.assertEqual([z['id'] for z in result['zones']],['work','leisure','shared'])
        self.assertFalse(any(m['id']=='pet' for z in result['zones'] for m in z['modules']))
        bridge.call.assert_not_called();tools.call.assert_not_called()
    def test_work_view_omits_games_and_leisure_recent(self):
        source={'tools':[{'id':'delivery'},{'id':'games'},{'id':'town'},{'id':'new'}], 'games':[{'id':'g'}], 'wheel':{'entries':[1]},'pack':{'files':[1]},'materials':{'thesis':{}},'jobs':[1],'recent':[{'id':'game:g'},{'id':'pack'},{'id':'wheel'}]}
        result=split_tools(source,'work')
        self.assertEqual([t['id'] for t in result['tools']],['delivery'])
        self.assertNotIn('games',result);self.assertNotIn('wheel',result)
        self.assertEqual(result['recent'],[{'id':'pack'}])
        self.assertIn('games',source)
        leisure=split_tools(source,'leisure')
        self.assertNotIn('pack',leisure);self.assertNotIn('materials',leisure)
        self.assertEqual(leisure['jobs'],[])
    def test_fixed_module_launch_cannot_start_agent_pet_or_command(self):
        for p in ({'id':'agent'},{'id':'pet'},{'id':'town','command':'cmd'},{'id':'unknown'}):
            with self.assertRaises(ValueError):validate_module(p)
        self.assertEqual(validate_module({'id':'town'}),'town')
    def test_scoped_tools_use_existing_adapter(self):
        tools=Mock();tools.call.return_value={'tools':[{'id':'games'}],'games':[]}
        result=WorkstationCore(Mock(),tools).call('workstation_tools',{'zone':'leisure'})
        self.assertEqual(result['zone'],'leisure');tools.call.assert_called_once_with('bootstrap',{})
        with self.assertRaises(ValueError):split_tools({},'other')
    def test_module_open_checks_expected_zone(self):
        tools=Mock();core=WorkstationCore(Mock(),tools)
        with self.assertRaises(ValueError):core.call('workstation_open_module',{'id':'town','zone':'work'})
        tools.call.assert_not_called()
        core.call('workstation_open_module',{'id':'town','zone':'leisure'})
        tools.call.assert_called_once_with('open_module',{'id':'town'})

if __name__=='__main__':unittest.main()
