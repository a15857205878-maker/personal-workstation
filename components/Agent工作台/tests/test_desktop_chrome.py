import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
W=Path(__file__).resolve().parents[1];sys.path.insert(0,str(W))
from backend import Bridge
from desktop_chrome import WindowControls

class ChromeTests(unittest.TestCase):
    def test_scheme_persists_and_partial_changes_keep_palette(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);b=Bridge(root/'room',data_dir=root/'data')
            self.assertTrue(b.call('api_appearance_save',{'theme':'lavender','color_scheme':'dark'})['ok'])
            self.assertEqual(b.call('api_appearance_save',{'theme':'blue'})['data']['color_scheme'],'dark')
            other=Bridge(root/'room',data_dir=root/'data')
            self.assertEqual(other.call('api_appearance_get')['data'],{'theme':'blue','color_scheme':'dark'})
            self.assertIsNone(other._auto)
            self.assertFalse(other.call('api_appearance_save',{'color_scheme':'bad'})['ok'])
            self.assertFalse(other.call('api_appearance_save',{'color_scheme':'light','path':'x'})['ok'])
    def test_old_preference_defaults_to_light_without_rewrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);root.joinpath('appearance.json').write_text('{"theme":"apricot"}',encoding='utf-8')
            b=Bridge(root/'room',data_dir=root)
            self.assertEqual(b.call('api_appearance_get')['data'],{'theme':'apricot','color_scheme':'light'})
            self.assertEqual(root.joinpath('appearance.json').read_text(),'{"theme":"apricot"}')
    def test_fixed_window_actions_and_close_uses_native_guard(self):
        window=Mock();controls=WindowControls(window)
        controls.action({'action':'minimize'});window.minimize.assert_called_once()
        controls.action({'action':'toggle_maximize'});window.maximize.assert_called_once()
        controls.changed(True);controls.action({'action':'toggle_maximize'});window.restore.assert_called_once()
        controls.action({'action':'close'});window.destroy.assert_called_once()
        for data in ({'action':'exec'},{'action':'close','force':True},{}):
            with self.assertRaises(ValueError):controls.action(data)
    def test_first_quick_load_applies_saved_theme_before_loaded_flag_is_set(self):
        import importlib.util,threading
        from types import SimpleNamespace
        from quick_window import QuickWindow
        import webview.event
        path=Path(webview.event.__file__)
        sys.path.insert(0,str(path.parents[1]))
        spec=importlib.util.spec_from_file_location('quick_event_fixture',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        window=Mock();loaded=module.Event(window);window.events=SimpleNamespace(loaded=loaded)
        done=threading.Event();window.evaluate_js.side_effect=lambda value:done.set()
        quick=QuickWindow.__new__(QuickWindow);quick.window=window;quick.bridge=SimpleNamespace(appearance=SimpleNamespace(get=lambda:{'theme':'blue','color_scheme':'dark'}))
        loaded+=lambda:quick.sync_appearance(force=True)
        loaded.set();self.assertTrue(done.wait(1))
        self.assertIn('dark',window.evaluate_js.call_args.args[0])
if __name__=='__main__':unittest.main()
