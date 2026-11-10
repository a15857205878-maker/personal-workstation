"""One lightweight window sharing the workbench bridge; show-only authenticated IPC."""
import ctypes,ctypes.wintypes as wt,hmac,json,os,secrets,socket,threading,time
from pathlib import Path
from credential_store import atomic_json
from quick_commands import QuickCommands

def request_quick(base):
    try:
        p=Path(base)/'data/quick-window.json'
        if p.stat().st_size>4096:return False
        row=json.loads(p.read_text(encoding='utf-8'))
        with socket.create_connection(('127.0.0.1',int(row['port'])),timeout=.5) as s:
            s.settimeout(1);s.sendall(json.dumps(dict(action='quick',token=row['token'])).encode()+b'\n')
            return json.loads(s.recv(1024)).get('ok') is True
    except (OSError,ValueError,KeyError,TypeError):return False

class QuickWindow:
    def __init__(self,base,bridge,main,ready,enable_signal=True):
        self.base=Path(base);self.bridge=bridge;self.main=main;self.ready=ready;self.window=None;self.closed=False;self.lock=threading.RLock();self.signal=None;self.hotkey=False;self.hotkey_thread_id=None
        self.commands=QuickCommands(bridge,self.dispatch)
        bridge.ui_actions.update(api_quick_submit=self.commands.submit,api_quick_open=lambda p:self.open(),api_quick_hide=lambda p:self.hide(),api_main_open=lambda p:self.show_main(),api_quick_info=lambda p:dict(hotkey=self.hotkey))
        if enable_signal:self._signal();self._hotkey()
    def show_main(self):self.main.restore();self.main.show();return dict(opened=True)
    def open(self):
        if self.closed:return dict(opened=False)
        if not self.ready.wait(12):raise ValueError('工作台仍在启动，请稍候再试。')
        with self.lock:
            if self.window is None:
                import webview
                self.window=webview.create_window('Agent 快捷指令',str(self.base/'frontend/dist/quick.html'),width=620,height=300,min_size=(520,240),frameless=True,easy_drag=False,on_top=True,resizable=True,background_color='#fcfaf5',text_select=True)
                self.bridge.quick_window=self.window;self.window.expose(self.bridge.call)
                def closing():
                    if self.closed:return True
                    self.window.hide();return False
                self.window.events.closing+=closing
                self.window.events.loaded+=lambda:self.sync_appearance(force=True)
            else:
                self.window.restore();self.window.show()
                self.sync_appearance()
                self.window.evaluate_js("document.querySelector('[aria-label=快捷指令]')?.focus()")
        return dict(opened=True)
    def sync_appearance(self,force=False):
        if not self.window or (not force and not self.window.events.loaded.is_set()):return
        values=self.bridge.appearance.get()
        script="(()=>{const v="+json.dumps(values)+";const r=document.documentElement;r.dataset.palette=v.theme;r.dataset.colorScheme=v.color_scheme;r.style.colorScheme=v.color_scheme;})()"
        try:self.window.evaluate_js(script)
        except Exception:pass # It can be in the middle of closing.
    def hide(self):
        if self.window:self.window.hide()
        return dict(hidden=True)
    def dispatch(self,event):
        self.show_main();deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            done=threading.Event();box={}
            def receive(v):box['ok']=v;done.set()
            self.main.evaluate_js('(async()=>typeof window.workbenchReceive==="function" ? window.workbenchReceive('+json.dumps(event,ensure_ascii=False)+') : false)()',callback=receive)
            if done.wait(1) and box.get('ok') is True:return
            time.sleep(.1)
        raise ValueError('主窗口尚未接收任务。')
    def _signal(self):
        self.token=secrets.token_urlsafe(32);self.signal=socket.socket();self.signal.bind(('127.0.0.1',0));self.signal.listen(4);self.signal.settimeout(1)
        self.signalpath=self.base/'data/quick-window.json';atomic_json(self.signalpath,dict(port=self.signal.getsockname()[1],token=self.token))
        def listen():
            while not self.closed:
                try:conn,_=self.signal.accept()
                except socket.timeout:continue
                except OSError:break
                with conn:
                    try:
                        conn.settimeout(1);row=json.loads(conn.recv(1024))
                        if not isinstance(row,dict) or row.get('action')!='quick' or not isinstance(row.get('token'),str) or not hmac.compare_digest(row['token'],self.token):continue
                        conn.sendall(b'{"ok":true}');threading.Thread(target=self.open,daemon=True).start()
                    except (OSError,ValueError,TypeError):continue
        threading.Thread(target=listen,name='quick-show-signal',daemon=True).start()
    def _hotkey(self):
        if os.name!='nt':return
        def loop():
            user=ctypes.WinDLL('user32',use_last_error=True);self.hotkey_thread_id=ctypes.windll.kernel32.GetCurrentThreadId()
            self.hotkey=bool(user.RegisterHotKey(None,0x4A61,0x4003,0x20))
            if not self.hotkey:return
            msg=wt.MSG()
            try:
                while not self.closed and user.GetMessageW(ctypes.byref(msg),None,0,0)>0:
                    if msg.message==0x0312:threading.Thread(target=self.open,daemon=True).start()
            finally:user.UnregisterHotKey(None,0x4A61);self.hotkey=False
        threading.Thread(target=loop,name='quick-hotkey',daemon=True).start()
    def close(self):
        self.closed=True
        if self.signal:self.signal.close()
        if self.hotkey_thread_id:ctypes.windll.user32.PostThreadMessageW(self.hotkey_thread_id,0x0012,0,0)
        if self.window:
            try:self.window.destroy()
            except Exception:pass
        if getattr(self,'signalpath',None):
            try:
                if json.loads(self.signalpath.read_text(encoding='utf-8')).get('token')==self.token:self.signalpath.unlink()
            except (OSError,ValueError):pass
