"""Best-effort local client fill. Never sends Enter, replaces a draft, or types globally."""
import json,os,re,subprocess,sys,time
from pathlib import Path

MANUAL='客户端入口已打开，指令已复制；未能确认可自动填入的空白输入框，请手动粘贴后自行提交。'
def paste_editor(editor,text):
 try:
  if not editor['guard']():return {'pasted':False,'message':MANUAL}
  if editor['read']().strip():return {'pasted':False,'message':'客户端已有输入，未覆盖；指令已复制，请自行选择位置粘贴。尚未自动提交。'}
  if not editor['guard']():return {'pasted':False,'message':MANUAL}
  editor['write'](text)
  if editor['read']().rstrip('\r\n')==text.rstrip('\r\n'):return {'pasted':True,'message':'已打开客户端并填入指令，请核对后自行点击发送；尚未自动提交。'}
  return {'pasted':False,'uncertain':True,'message':'已尝试填入，但无法确认完整内容；请检查客户端，不会自动重贴或发送。'}
 except Exception:return {'pasted':False,'uncertain':True,'message':'填入状态未确认，指令仍在剪贴板；请核对客户端，不会自动重贴或发送。'}

def paste_client(kind,target,text):
 if kind not in ('exe','app'):return {'pasted':False,'message':MANUAL}
 if not isinstance(text,str) or not 0<len(text)<=40000:raise ValueError('交接指令长度无效')
 python=Path(sys.executable)
 if python.name.lower()=='pythonw.exe' and python.with_name('python.exe').is_file():python=python.with_name('python.exe')
 try:
  result=subprocess.run([str(python),'-B',str(Path(__file__).resolve())],input=json.dumps({'kind':kind,'target':target,'text':text},ensure_ascii=False).encode('utf-8'),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=12,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  value=json.loads(result.stdout.decode('utf-8'))
  if result.returncode==0 and type(value.get('pasted')) is bool and isinstance(value.get('message'),str):return value
 except subprocess.TimeoutExpired:return {'pasted':False,'uncertain':True,'message':'客户端填入状态未确认，请先检查窗口；不会自动重贴或发送。指令已保留在剪贴板。'}
 except Exception:pass
 return {'pasted':False,'uncertain':True,'message':'无法确认自动填入结果，请先核对客户端；指令已复制，不会自动重贴或发送。'}

def _probe(kind,target):
 import ctypes
 from ctypes import wintypes
 import clr
 from System.Runtime.InteropServices import RuntimeEnvironment
 assemblies=Path(RuntimeEnvironment.GetRuntimeDirectory())/'WPF'
 for name in ('WindowsBase','UIAutomationTypes','UIAutomationClient'):
  path=assemblies/(name+'.dll')
  clr.AddReference(str(path) if path.is_file() else name)
 from System.Windows.Automation import AutomationElement,TreeScope,PropertyCondition,OrCondition,ControlType,ValuePattern,TextPattern
 user=ctypes.windll.user32;kernel=ctypes.windll.kernel32
 user.GetForegroundWindow.restype=wintypes.HWND
 user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
 kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
 kernel.CloseHandle.argtypes=[wintypes.HANDLE]
 kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
 kernel.GetApplicationUserModelId.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.UINT),wintypes.LPWSTR]
 from System import IntPtr
 def trusted(pid):
  handle=kernel.OpenProcess(0x1000,False,pid)
  if not handle:return False
  try:
   if kind=='exe':
    buffer=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(32768)
    return bool(kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size))) and os.path.normcase(os.path.abspath(buffer.value))==os.path.normcase(os.path.abspath(target))
   size=wintypes.UINT(0);kernel.GetApplicationUserModelId(handle,ctypes.byref(size),None)
   if not 0<size.value<4096:return False
   buffer=ctypes.create_unicode_buffer(size.value)
   return kernel.GetApplicationUserModelId(handle,ctypes.byref(size),buffer)==0 and buffer.value==target
  finally:kernel.CloseHandle(handle)
 hwnd=user.GetForegroundWindow()
 if not hwnd:return None
 pid=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
 if kind=='exe' and not trusted(pid.value):return None
 root=AutomationElement.FromHandle(IntPtr(int(hwnd)))
 positive=re.compile(r'消息|提问|指令|问题|任务输入|尽管问|prompt|message|chat input|ask (?:gemini|kimi|claude|qwen)',re.I)
 negative=re.compile(r'搜索|search|地址|address|邮箱|email|账号|account|密码|password|验证码',re.I)
 def candidate(element):
  try:
   c=element.Current
   if not trusted(c.ProcessId) or not c.IsEnabled or c.IsOffscreen or c.IsPassword:return None
   name=(c.Name or '')+' '+(c.AutomationId or '')
   if not positive.search(name) or negative.search(name):return None
   reader=writer=None
   try:
    pattern=element.GetCurrentPattern(ValuePattern.Pattern)
    if pattern.Current.IsReadOnly:return None
    reader=lambda:pattern.Current.Value or ''
    writer=lambda value:pattern.SetValue(value)
   except Exception:
    text_pattern=element.GetCurrentPattern(TextPattern.Pattern)
    reader=lambda:text_pattern.DocumentRange.GetText(-1) or ''
    handle=int(c.NativeWindowHandle);name_buffer=ctypes.create_unicode_buffer(256)
    user.GetClassNameW(ctypes.c_void_p(handle),name_buffer,256)
    if handle and re.fullmatch(r'Edit|RichEdit\w*|WindowsForms10\.(?:EDIT|RICHEDIT)\..*',name_buffer.value,re.I):
     if user.GetWindowLongW(ctypes.c_void_p(handle),-16)&0x800:return None
     send=user.SendMessageTimeoutW
     send.argtypes=[wintypes.HWND,wintypes.UINT,ctypes.c_size_t,ctypes.c_void_p,wintypes.UINT,wintypes.UINT,ctypes.POINTER(ctypes.c_size_t)];send.restype=ctypes.c_size_t
     def writer(value):
      result=ctypes.c_size_t();buffer=ctypes.create_unicode_buffer(value)
      if not send(handle,0x000C,0,ctypes.cast(buffer,ctypes.c_void_p),2,1000,ctypes.byref(result)):raise RuntimeError('输入控件未确认写入')
    else:return None
   identity=tuple(element.GetRuntimeId())
   def guard():
    return user.GetForegroundWindow()==hwnd and not element.Current.IsOffscreen and not element.Current.IsPassword and trusted(element.Current.ProcessId) and tuple(AutomationElement.FocusedElement.GetRuntimeId())==identity
   return {'element':element,'read':reader,'write':writer,'guard':guard}
  except Exception:return None
 focused=candidate(AutomationElement.FocusedElement)
 if focused:return focused
 found=[]
 for e in list(root.FindAll(TreeScope.Descendants,OrCondition(PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit),PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Document))))[:200]:
  value=candidate(e)
  if value is not None:found.append(value)
 if len(found)!=1:return None
 found[0]['element'].SetFocus()
 return found[0]

def _main():
 # Use the same shared pythonnet runtime as the existing WebView host.
 sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'个人工具中心新版/vendor'))
 value=json.loads(sys.stdin.buffer.read(200000).decode('utf-8'))
 if value.get('kind') not in ('exe','app') or not isinstance(value.get('text'),str) or not 0<len(value['text'])<=40000:raise ValueError('无效交接')
 until=time.monotonic()+8
 while time.monotonic()<until:
  editor=_probe(value['kind'],value['target'])
  if editor:return paste_editor(editor,value['text'])
  time.sleep(.2)
 return {'pasted':False,'message':MANUAL}
if __name__=='__main__':
 try:result=_main()
 except Exception:result={'pasted':False,'message':MANUAL}
 sys.stdout.buffer.write(json.dumps(result,ensure_ascii=False).encode('utf-8'))
