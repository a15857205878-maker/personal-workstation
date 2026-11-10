import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from remote_surface import RemoteSurface


class RemoteSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'app').mkdir()
        (self.root/'app/pairing.json').write_text(json.dumps({'token':'fixture-pair-token'}))
        (self.root/'app/transfer.py').write_text('fixture')

    def online(self,url):
        path=urlsplit(url).path
        if path=='/health':return b'{"ok":true}'
        if path=='/qr.svg':return b'<svg xmlns="http://www.w3.org/2000/svg"/>'
        return json.dumps({'ui_mode':'unified-only','urls':[
            'http://192.168.1.5:8765/?token=fixture-pair-token',
            'http://evil.example:8765/?token=fixture-pair-token',
            'http://192.168.1.5:9999/?token=fixture-pair-token',
            'http://192.168.1.5:8765/?token=wrong',
        ],'remote_access':{'state':'not_installed'}}).encode()

    def test_online_reuses_service_and_filters_addresses(self):
        spawn=Mock()
        surface=RemoteSurface(self.root,fetch=self.online,spawn=spawn)
        result=surface.start()
        spawn.assert_not_called()
        self.assertTrue(result['online'])
        self.assertTrue(result['gateway_online'])
        self.assertEqual(len(result['connections']),1)
        self.assertTrue(result['connections'][0]['qr'].startswith('data:image/svg+xml;base64,'))
        self.assertTrue(result['session_url'].startswith('http://127.0.0.1:8765/'))
        self.assertNotIn(str(self.root),json.dumps(result))

    def test_offline_probe_has_no_side_effects_or_credentials(self):
        def offline(url):raise OSError('secret-detail')
        spawn=Mock()
        result=RemoteSurface(self.root,fetch=offline,spawn=spawn).status()
        spawn.assert_not_called()
        self.assertFalse(result['online'])
        self.assertNotIn('fixture-pair-token',json.dumps(result))
        self.assertNotIn('secret-detail',json.dumps(result))

    def test_start_only_fixed_headless_script_and_then_probe(self):
        state={'started':False}
        def fetch(url):
            if not state['started']:raise OSError()
            return self.online(url)
        def spawn(args,**kwargs):
            self.assertEqual(args[1:],[str(self.root/'app/transfer.py'),'--headless'])
            self.assertEqual(kwargs['cwd'],str(self.root))
            self.assertNotIn('shell',kwargs)
            state['started']=True
            return Mock(poll=lambda:None)
        self.assertTrue(RemoteSurface(self.root,fetch=fetch,spawn=spawn).start()['online'])

    def test_reject_unrelated_service(self):
        def other(url):return b'{"urls":[],"ui_mode":"unknown"}'
        self.assertFalse(RemoteSurface(self.root,fetch=other).status()['online'])

    def test_core_rejects_parameters_before_contacting_service(self):
        from workstation_core import WorkstationCore
        core=WorkstationCore(Mock(),tools=Mock(),town=Mock())
        for action in ('workstation_remote_status','workstation_remote_start','workstation_tailscale_open'):
            with self.assertRaises(ValueError):core.call(action,{'url':'http://evil.example'})
        self.assertFalse(hasattr(core,'remote'))

    def test_tailscale_opens_only_the_installed_ui(self):
        executable=self.root/'tailscale-ipn.exe';executable.write_bytes(b'fixture')
        opener=Mock()
        result=RemoteSurface(self.root,tailscale_path=executable,opener=opener).open_tailscale()
        opener.assert_called_once_with(str(executable))
        self.assertIn('Tailscale',result['message'])

    def test_missing_tailscale_does_not_launch_anything(self):
        opener=Mock()
        with self.assertRaisesRegex(ValueError,'Tailscale'):
            RemoteSurface(self.root,tailscale_path=self.root/'missing.exe',opener=opener).open_tailscale()
        opener.assert_not_called()


if __name__=='__main__':unittest.main()


class FileRootsTests(unittest.TestCase):
    def test_local_folder_picker_is_required_and_cannot_receive_a_remote_path(self):
        from types import SimpleNamespace
        service=RemoteSurface();access=Mock();access.local_roots.return_value={'roots':[]};access.add_root.return_value={'roots':[{'id':'a'*32,'label':'chosen','path':'C:/chosen'}]};service._files=access
        window=Mock();window.create_file_dialog.return_value=['C:/chosen']
        with patch.dict(sys.modules,{'webview':SimpleNamespace(FileDialog=SimpleNamespace(FOLDER=20))}):
            result=service.file_roots('add',window,{})
        access.add_root.assert_called_once_with('C:/chosen');self.assertEqual(len(result['roots']),1)
        with self.assertRaises(ValueError):service.file_roots('add',window,{'path':'C:/other'})
        window.create_file_dialog.return_value=None
        with patch.dict(sys.modules,{'webview':SimpleNamespace(FileDialog=SimpleNamespace(FOLDER=20))}):
            self.assertEqual(service.file_roots('add',window,{}),{'roots':[]})


class FixedLibraryTests(unittest.TestCase):
    def test_library_uses_fixed_local_path_and_opens_only_that_folder(self):
        with tempfile.TemporaryDirectory() as raw:
            library=Path(raw)/'手机文件库';access=Mock();access.local_roots.return_value={'roots':[],'library_id':None};opened=[];surface=RemoteSurface(opener=opened.append);surface._files=access
            with patch('remote_surface.LIBRARY_ROOT',library):
                self.assertFalse(surface.file_library()['ready']);self.assertFalse(library.exists())
                access.local_roots.side_effect=[{'roots':[],'library_id':None},{'roots':[],'library_id':None},{'roots':[{'id':'a'*32,'path':str(library)}],'library_id':'a'*32}]
                result=surface.file_library(open_folder=True)
            self.assertTrue(result['ready']);self.assertTrue(library.is_dir());access.set_library.assert_called_once_with(library);self.assertEqual(opened,[str(library)])

    def test_selected_folder_is_preserved_when_opened_and_cancel_does_not_change_it(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as raw:
            chosen=Path(raw)/'实验结果';chosen.mkdir();surface=RemoteSurface(opener=Mock());access=Mock();surface._files=access
            access.local_roots.return_value={'roots':[{'id':'a'*32,'path':str(chosen)}],'library_id':'a'*32}
            self.assertEqual(surface.file_library(open_folder=True)['path'],str(chosen))
            access.set_library.assert_not_called()
            window=Mock();window.create_file_dialog.return_value=None
            with patch.dict(sys.modules,{'webview':SimpleNamespace(FileDialog=SimpleNamespace(FOLDER=20))}):
                self.assertEqual(surface.file_library(choose_folder=True,window=window)['path'],str(chosen))
            access.set_library.assert_not_called()

    def test_library_switch_requires_local_picker(self):
        from types import SimpleNamespace
        surface=RemoteSurface();access=Mock();surface._files=access;access.local_roots.return_value={'roots':[],'library_id':None}
        with self.assertRaises(ValueError):surface.file_library(choose_folder=True)
        window=Mock();window.create_file_dialog.return_value=['C:/selected']
        with patch.dict(sys.modules,{'webview':SimpleNamespace(FileDialog=SimpleNamespace(FOLDER=20))}):
            surface.file_library(choose_folder=True,window=window)
        access.set_library.assert_called_once_with('C:/selected')
