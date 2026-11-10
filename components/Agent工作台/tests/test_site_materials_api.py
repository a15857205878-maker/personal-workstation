from pathlib import Path
from types import SimpleNamespace
import tempfile,unittest
from workstation_core import WorkstationCore

class MaterialsAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.core=WorkstationCore(SimpleNamespace(_data_dir=self.root,station_window=None,opener=lambda _:None),town=object())
    def tearDown(self):self.tmp.cleanup()
    def test_workflow_and_reject_extra_path(self):
        state=self.core.call('workstation_materials_list',{})
        state=self.core.call('workstation_materials_create',dict(title='站点',revision=state['revision']))
        p=state['projects'][0]
        state=self.core.call('workstation_materials_add',dict(id=p['id'],revision=state['revision']))
        p=state['projects'][0];p['entries'][0].update(public=True,title='新版素材')
        state=self.core.call('workstation_materials_save',dict(project=p,revision=state['revision']))
        out=self.core.call('workstation_materials_export',dict(id=p['id'],selected=[p['entries'][0]['id']],revision=state['revision']))
        self.assertTrue(Path(out['path']).is_file())
        for action,payload in [('list',{'path':'C:/secret'}),('add',{'id':p['id'],'revision':state['revision'],'path':'C:/secret'}),('open_export',{'id':p['id'],'export_id':'../secret'})]:
            with self.assertRaises(ValueError):self.core.call('workstation_materials_'+action,payload)
    def test_artifact_reference_reuses_owner_validation(self):
        from artifact_browser import ArtifactBrowser
        file=self.root/'screenshot.png';file.write_bytes(b'\x89PNG\r\n\x1a\noriginal')
        browser=ArtifactBrowser(self.root);browser.add([file]);row=browser.list([])['items'][0]
        self.core._artifact_browser=browser
        state=self.core.call('workstation_materials_list',{})
        state=self.core.call('workstation_materials_create',dict(title='test',revision=state['revision']))
        state=self.core.call('workstation_materials_add_artifact',dict(id=state['projects'][0]['id'],revision=state['revision'],artifact_id=row['id']))
        self.assertEqual(state['projects'][0]['entries'][0]['file_name'],'screenshot.png')
    def test_library_query_and_provenance_from_real_ticket(self):
        import importlib.util
        from remote_surface import REMOTE_ROOT
        spec=importlib.util.spec_from_file_location('materials_test_files',REMOTE_ROOT/'app/pc_files.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        folder=self.root/'shared';folder.mkdir();(folder/'notes.md').write_text('一行\n网站取材',encoding='utf-8')
        files=mod.ComputerFiles(self.root/'remote');files.set_library(folder)
        self.core.remote=SimpleNamespace(file_roots=lambda *args:files.local_roots(),_files=files)
        state=self.core.call('workstation_materials_list',{});state=self.core.call('workstation_materials_create',dict(title='test',revision=state['revision']))
        row=self.core.call('workstation_materials_search',dict(query='取材',mode='content'))['files'][0]
        state=self.core.call('workstation_materials_add_library',dict(id=state['projects'][0]['id'],revision=state['revision'],file_id=row['id']))
        entry=state['projects'][0]['entries'][0]
        self.assertEqual(entry['source'],'notes.md · 第2行');self.assertIn('网站取材',entry['excerpt']);self.assertFalse(entry['public'])
    def test_changed_library_file_after_ticket_close_is_not_added_with_old_excerpt(self):
        import contextlib,importlib.util
        from remote_surface import REMOTE_ROOT
        spec=importlib.util.spec_from_file_location('materials_changed_files',REMOTE_ROOT/'app/pc_files.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        folder=self.root/'shared';folder.mkdir();path=folder/'notes.md';path.write_text('原文取材',encoding='utf-8')
        files=mod.ComputerFiles(self.root/'remote');files.set_library(folder)
        self.core.remote=SimpleNamespace(file_roots=lambda *args:files.local_roots(),_files=files)
        state=self.core.call('workstation_materials_list',{});state=self.core.call('workstation_materials_create',dict(title='test',revision=state['revision']))
        row=self.core.call('workstation_materials_search',dict(query='取材',mode='content'))['files'][0]
        original=files.open_file
        @contextlib.contextmanager
        def changed(identifier):
            with original(identifier) as stream:yield stream
            path.write_text('已被替换的内容',encoding='utf-8')
        files.open_file=changed
        with self.assertRaisesRegex(ValueError,'变化'):
            self.core.call('workstation_materials_add_library',dict(id=state['projects'][0]['id'],revision=state['revision'],file_id=row['id']))
        self.assertEqual(self.core.call('workstation_materials_list',{})['projects'][0]['entries'],[])

if __name__=='__main__':unittest.main()
