from pathlib import Path
import unittest,tempfile,json,sys
W=Path(__file__).resolve().parents[1];sys.path.insert(0,str(W))
from butler_center import ButlerCenter

class CenterTests(unittest.TestCase):
    def test_independent_of_pet_and_only_returns_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'data').mkdir();(root/'data/pet-notices.json').write_text(json.dumps({'version':1,'events':[dict(id='a'*32,source='task',task_id='b'*32,status='已完成',kind='done',title='PRIVATE',body='SECRET',at=123)]}),encoding='utf-8')
            value=ButlerCenter(root).snapshot({'counts':{'tasks':2,'collaborations':1,'active':1,'attention':0},'tasks':[{'title':'PRIVATE'}],'credentials':'SECRET'})
            self.assertEqual(value['counts']['tasks'],2);self.assertEqual(len(value['notices']),1)
            self.assertNotIn('PRIVATE',json.dumps(value));self.assertNotIn('SECRET',json.dumps(value))
            self.assertEqual(value['notices'][0]['page'],'tasks')
    def test_corrupt_feed_is_reported_without_touching_data(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'data').mkdir();p=root/'data/pet-notices.json';p.write_text('bad',encoding='utf-8')
            result=ButlerCenter(root).snapshot({'counts':{}})
            self.assertEqual(result['feed_state'],'unavailable');self.assertEqual(p.read_text(),'bad')
    def test_missing_pet_and_missing_feed_are_supported(self):
        with tempfile.TemporaryDirectory() as d:
            value=ButlerCenter(d).snapshot({'counts':{}})
            self.assertEqual(value['notices'],[]);self.assertEqual(value['feed_state'],'empty')
            self.assertTrue(value['independent_of_pet'])
    def test_bad_event_is_not_accepted_as_navigation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'data').mkdir();(root/'data/pet-notices.json').write_text(json.dumps({'version':1,'events':[dict(id='a'*32,source='shell',task_id='b'*32,status='已完成',at=123)]}),encoding='utf-8')
            self.assertEqual(ButlerCenter(d).snapshot({'counts':{}})['notices'],[])
    def test_core_uses_current_data_root_and_rejects_custom_payload(self):
        from workstation_core import WorkstationCore
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'custom-data').mkdir();(root/'custom-data/pet-notices.json').write_text(json.dumps({'version':1,'events':[]}),encoding='utf-8')
            from town_adapter import TownAdapter
            from unittest.mock import Mock
            core=WorkstationCore(SimpleNamespace(_data_dir=root/'custom-data'),tools=Mock(),town=TownAdapter(base=root/'town-fixture'));core.overview=lambda:{'counts':{'active':4}}
            value=core.call('workstation_butler_status',{})
            self.assertEqual(value['counts']['active'],4);self.assertEqual(value['feed_state'],'ready')
            with self.assertRaises(ValueError):core.call('workstation_butler_status',{'path':'arbitrary'})
    def test_partial_overview_is_unknown_and_does_not_leak_errors(self):
        with tempfile.TemporaryDirectory() as d:
            value=ButlerCenter(d).snapshot({'counts':{'tasks':0},'warnings':['PRIVATE PATH OR CONTENT']})
            self.assertIsNone(value['counts']['tasks']);self.assertEqual(value['overview_state'],'unavailable')
            self.assertTrue(value['warnings']);self.assertNotIn('PRIVATE',json.dumps(value))
if __name__=='__main__':unittest.main()
