from pathlib import Path
import sys, tempfile, unittest
from unittest.mock import Mock
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE));sys.path.insert(0,str(BASE/'vendor'))
from bridge_boundary import install_boundary
import webview.util

class BoundaryTests(unittest.TestCase):
    def test_drag_only_for_explicit_window_with_two_bounded_coordinates(self):
        install_boundary()
        window=Mock();window._functions={};window._callbacks={};window._js_api=None
        webview.util.js_bridge_call(window,'pywebviewMoveWindow',[10,20],'move')
        window.move.assert_not_called()
        window._workstation_native_drag=True
        for payload in ([True,2],[1],['1',2],[float('nan'),2],[float('inf'),2],[100001,2],{'x':1,'y':2}):
            webview.util.js_bridge_call(window,'pywebviewMoveWindow',payload,'move')
        window.move.assert_not_called()
        webview.util.js_bridge_call(window,'pywebviewMoveWindow',[-1500,35],'move')
        window.move.assert_called_once_with(-1500,35)

    def test_native_dispatch_rejects_private_and_nested_names(self):
        install_boundary()
        secret=Mock();window=Mock();window._js_api=secret
        window._functions={'call':Mock(return_value={'ok':True})}
        for name in ('_opener','_manager.spawn','call.__globals__.clear','__class__','pywebviewStateUpdate'):
            webview.util.js_bridge_call(window,name,[], 'test')
        secret._opener.assert_not_called();secret._manager.spawn.assert_not_called()
        window._functions['call'].assert_not_called();window.evaluate_js.assert_not_called()
    def test_only_registered_call_and_known_callbacks_allowed(self):
        install_boundary()
        import threading
        done=threading.Event();window=Mock();window._js_api=None
        window._functions={'call':Mock(return_value={'ok':True})}
        window.evaluate_js.side_effect=lambda value:done.set()
        webview.util.js_bridge_call(window,'call',['bootstrap',{}],'test')
        self.assertTrue(done.wait(2));window._functions['call'].assert_called_once_with('bootstrap',{})
        callback=Mock();window._callbacks={'expected':callback}
        webview.util.js_bridge_call(window,'pywebviewAsyncCallback','{"ok":true}','missing')
        callback.assert_not_called()
        webview.util.js_bridge_call(window,'pywebviewAsyncCallback','{"ok":true}','expected')
        callback.assert_called_once_with({'ok':True})

