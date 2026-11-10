import sys,tempfile,unittest
from pathlib import Path
B=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(B/'个人工具中心新版/vendor'));sys.path.insert(0,str(B/'个人工具中心'))
from icon_studio_fixture import make_api

class InlineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.api=make_api(self.root);self.data=self.api.call({'action':'load'})
    def tearDown(self):self.temp.cleanup()
    def payload(self,action,**extra):return dict(action=action,revision=self.data['revision'],**extra)
    def test_apply_restore_uses_original_backup_and_keeps_other_properties(self):
        item=self.data['targets'][0];asset=next(x for x in self.data['assets'] if x['name']=='green');original=self.api.service.backend.read('unused')
        self.data=self.api.call(self.payload('apply',target=item['id'],asset=asset['id']))
        changed=self.api.service.backend.read('unused');self.assertNotEqual(changed['icon'],original['icon'])
        self.assertEqual({k:v for k,v in changed.items() if k!='icon'},{k:v for k,v in original.items() if k!='icon'})
        self.api.call(self.payload('restore',target=item['id']));self.assertEqual(self.api.service.backend.read('unused'),original)
    def test_unknown_ids_extra_paths_and_stale_revisions_are_rejected(self):
        target=self.data['targets'][0]['id'];asset=self.data['assets'][0]['id'];rev=self.data['revision']
        with self.assertRaises(ValueError):self.api.call(self.payload('apply',target='unknown',asset=asset))
        with self.assertRaises(ValueError):self.api.call({'action':'import','paths':['C:/anything']})
        self.api.call({'action':'load'})
        with self.assertRaises(ValueError):self.api.call(dict(action='apply',revision=rev,target=target,asset=asset))
    def test_import_uses_picker_and_preserves_original_library(self):
        originals={p.name:p.read_bytes() for p in (self.root/'assets/pokemon').iterdir()}
        data=self.api.call({'action':'import'});self.assertEqual(len(data['assets']),3)
        self.assertEqual({p.name:p.read_bytes() for p in (self.root/'assets/pokemon').iterdir()},originals)
        self.assertTrue(any(x['source']=='新增' for x in data['assets']))
    def test_cancel_does_not_create_import_folder(self):
        self.api.picker=lambda **kwargs:None
        self.api.call({'action':'import'});self.assertFalse(self.api.added.exists())
    def test_preview_and_public_dto_do_not_export_shortcut_arguments(self):
        self.assertNotIn('arguments',self.data['targets'][0]);self.assertNotIn('target',self.data['targets'][0])
        value=self.api.call(self.payload('preview',target=self.data['targets'][0]['id'],asset=self.data['assets'][0]['id']))
        self.assertTrue(value['current'].startswith('data:image/png;base64,'));self.assertTrue(value['proposed'].startswith('data:image/png;base64,'))
    def test_external_icon_popup_is_no_longer_a_workstation_module(self):
        sys.path.insert(0,str(B/'Agent工作台'));from workstation_zones import validate_module
        with self.assertRaises(ValueError):validate_module({'id':'icons'})
    def test_successful_write_is_not_reported_failed_when_refresh_fails(self):
        item=self.data['targets'][0];asset=self.data['assets'][0]
        self.api.service.scan=lambda:(_ for _ in ()).throw(OSError('fixture scan failure'))
        result=self.api.call(self.payload('apply',target=item['id'],asset=asset['id']))
        self.assertTrue(result['refresh_required']);self.assertIsNone(result['revision']);self.assertIn('已应用',result['message'])
        self.assertTrue(result['warnings']);self.assertNotIn('fixture scan failure',str(result))
if __name__=='__main__':unittest.main()
