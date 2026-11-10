"""App-owned hidden WebView2 capture of one prepared local static product."""
from pathlib import Path
import argparse,sys,tempfile,threading,time,json,base64
parser=argparse.ArgumentParser();parser.add_argument('--url',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
from urllib.parse import urlsplit
url=urlsplit(args.url)
if url.scheme!='http' or url.hostname!='127.0.0.1' or not url.path.startswith('/web-product/'):raise SystemExit(2)
# pywebview is installed in the active Python environment.
import webview
webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER']=False
window=webview.create_window('网页成果截图',html='<html></html>',width=1440,height=1000,hidden=False,focus=False,x=-16000,y=-16000,frameless=True)
ok=[]
def capture():
 try:
  print('capture: waiting initial document',flush=True)
  if not window.events.loaded.wait(20):
   print('capture: initial load timeout',flush=True);return
  print('capture: initial ready',flush=True)
  from System import Action
  from System.IO import FileStream,FileMode,FileAccess
  from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
  ready=threading.Event()
  def protect():
   core=window.native.webview.CoreWebView2
   core.Settings.AreDevToolsEnabled=False;core.Settings.IsWebMessageEnabled=False;core.Settings.AreHostObjectsAllowed=False;core.Settings.AreDefaultScriptDialogsEnabled=False
   core.NewWindowRequested-=window.native.browser.on_new_window_request
   def navigate(sender,event):
    if not str(event.Uri).startswith(args.url.rsplit('/',1)[0]+'/'):event.Cancel=True
   def popup(sender,event):event.Handled=True
   def completed(sender,event):
    if event.IsSuccess and str(core.Source).startswith(args.url.rsplit('/',1)[0]+'/'):ready.set()
   core.NavigationStarting+=navigate;core.NewWindowRequested+=popup;core.NavigationCompleted+=completed
  window.native.Invoke(Action(protect))
  window.load_url(args.url)
  if not ready.wait(15):
   print('capture: product navigation timeout',flush=True);return
  print('capture: product ready',flush=True)
  time.sleep(1)
  pending={}
  def start():
   core=window.native.webview.CoreWebView2
   pending['task']=core.CallDevToolsProtocolMethodAsync('Page.captureScreenshot',json.dumps({'format':'png','captureBeyondViewport':True,'fromSurface':True}))
  window.native.Invoke(Action(start))
  if pending['task'].Wait(12000):
   data=json.loads(str(pending['task'].Result));args.output.write_bytes(base64.b64decode(data['data']));ok.append(True)

 finally:window.destroy()
with tempfile.TemporaryDirectory(prefix='web-product-render-') as storage:webview.start(capture,private_mode=True,storage_path=storage)
raise SystemExit(0 if ok else 1)
