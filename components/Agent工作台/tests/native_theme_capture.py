"""Capture the app's own WebView surface for visual QA (no external browser)."""
from pathlib import Path

def capture(window,path):
    from System import Action
    from System.IO import FileStream,FileMode,FileAccess
    from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    stream=FileStream(str(path),FileMode.Create,FileAccess.Write)
    pending={}
    try:
        def start():
            pending['task']=window.native.webview.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png,stream)
        window.native.Invoke(Action(start))
        if not pending['task'].Wait(15000):raise RuntimeError('WebView screenshot timeout')
    finally:stream.Close()
    return str(path)
