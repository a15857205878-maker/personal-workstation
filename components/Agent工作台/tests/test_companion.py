from pathlib import Path
import importlib.util
import ast
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from companion_adapter import CompanionAdapter

PET=Path(os.environ.get('AGENT_PET_ROOT', str(Path(__file__).resolve().parents[2] / 'agent-desktop-pet')))

class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.pet=root/'pet';self.work=root/'work'
        self.pet.mkdir();(self.work/'data').mkdir(parents=True)
        self.entry=root/'pet.lnk';self.entry.write_bytes(b'fixture')
        self.launcher=Mock();self.launcher.entry.return_value=self.entry
        self.launcher.launch.return_value={'action':'requested','message':'requested'}
        (self.pet/'workbench_link.json').write_text(json.dumps({'workbench_root':str(self.work)}),encoding='utf-8')
        self.adapter=CompanionAdapter(self.pet,self.work,launcher=self.launcher)

    def test_status_is_readonly_and_reports_config_without_claiming_online(self):
        result=self.adapter.status()
        self.assertTrue(result['launch_ready']);self.assertTrue(result['workbench_linked'])
        self.assertNotIn('running',result);self.launcher.launch.assert_not_called()

    def test_launch_reuses_registered_launcher(self):
        self.assertEqual(self.adapter.launch()['action'],'requested')
        self.launcher.launch.assert_called_once_with()

    def test_missing_entry_and_mismatched_link_remain_visible(self):
        self.entry.unlink();(self.pet/'workbench_link.json').write_text('{}',encoding='utf-8')
        result=self.adapter.status()
        self.assertFalse(result['launch_ready']);self.assertFalse(result['workbench_linked'])

    @unittest.skipUnless((PET/'pet_workbench.py').is_file(), 'Requires the optional desktop pet')
    def test_notice_pipeline_uses_existing_feed_and_persistent_deduplication(self):
        from workbench_notices import publish_notice
        spec=importlib.util.spec_from_file_location('companion_feed_fixture',PET/'pet_workbench.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        feed=self.work/'data/pet-notices.json'
        self.assertTrue(publish_notice(feed,'task','a'*32,'结果待确认'))
        reader=module.WorkbenchFeed(self.pet/'fixture-data',feed=feed)
        events=reader.pending(force=True);self.assertEqual(len(events),1)
        self.assertEqual(events[0]['kind'],'waiting')
        self.assertNotIn('instruction',events[0]);reader.finish(events[0]['id'],True)
        self.assertFalse(module.WorkbenchFeed(self.pet/'fixture-data',feed=feed).pending(force=True))
        self.assertEqual(self.adapter.status()['event_count'],1)

    def test_core_does_not_accept_custom_pet_paths(self):
        from workstation_core import WorkstationCore
        core=WorkstationCore(Mock(),tools=Mock(),town=Mock())
        for action in ('workstation_companion_status','workstation_companion_launch'):
            with self.assertRaises(ValueError):core.call(action,{'path':'elsewhere.exe'})

    @unittest.skipUnless((PET/'pet_banner.py').is_file(), 'Requires the optional desktop pet')
    def test_pet_primary_entry_returns_to_the_workstation(self):
        source=ast.parse((PET/'pet_banner.py').read_text(encoding='utf-8-sig'))
        function=next(n for n in ast.walk(source) if isinstance(n,ast.FunctionDef) and n.name=='activate')
        compiled=ast.Module(body=[function],type_ignores=[])
        workbench=Mock();namespace={'__import__':lambda name:workbench}
        exec(compile(compiled,'pet_banner_fixture','exec'),namespace)
        host=Mock();banner=Mock(host=host)
        namespace['activate'](banner,'tools')
        workbench.open_entry.assert_called_once_with('main')
        host.open_assistant_panel.assert_not_called()

if __name__=='__main__':unittest.main()
