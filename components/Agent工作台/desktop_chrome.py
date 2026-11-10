"""Fixed native window controls; close retains the app's existing close guard."""
import ctypes,json,logging,threading

class WindowControls:
    def __init__(self,window):
        self.window=window;self.maximized=False;self.lock=threading.RLock();self.scheme='light';self.tray=None
    def changed(self,maximized):
        with self.lock:self.maximized=bool(maximized)
        try:self.window.evaluate_js("window.dispatchEvent(new CustomEvent('window-workstation-state',{detail:"+json.dumps(self.state())+"}))")
        except Exception:pass # Page may be loading or already closing.
    def state(self):
        with self.lock:return dict(maximized=self.maximized)
    def action(self,payload):
        if not isinstance(payload,dict) or set(payload)!={'action'} or payload.get('action') not in ('state','minimize','toggle_maximize','close','tray'):raise ValueError('窗口操作参数无效')
        action=payload['action']
        if action=='tray':
            if self.tray is None:raise RuntimeError('托盘服务尚未就绪，请稍后重试。')
            self.tray.hide()
        elif action=='minimize':self.window.minimize()
        elif action=='toggle_maximize':
            target=not self.state()['maximized']
            if target:self.window.maximize()
            else:self.window.restore()
            with self.lock:self.maximized=target
        elif action=='close':self.window.destroy()
        return dict(self.state(),requested=action)
    def apply_native_frame(self,*_):
        # Retain the OS sizing frame/system menu, while removing only its caption.
        # No subclassed WndProc or global mouse hook is needed.
        try:
            from System import Action
            def apply():
                if hasattr(self,'_room_visibility') and not getattr(self,'_room_visibility_installed',False):
                    def visible_changed(*_):
                        visible=bool(self.window.native.Visible)
                        threading.Thread(target=self._room_visibility,args=(visible,),daemon=True).start()
                    self.window.native.VisibleChanged+=visible_changed
                    self._room_visibility_installed=True
                hwnd=int(self.window.native.Handle.ToInt64());user=ctypes.windll.user32
                get=user.GetWindowLongPtrW;get.argtypes=[ctypes.c_void_p,ctypes.c_int];get.restype=ctypes.c_ssize_t
                put=user.SetWindowLongPtrW;put.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_ssize_t];put.restype=ctypes.c_ssize_t
                style=get(hwnd,-16);style=(style & ~0x00C00000)|0x00040000|0x00080000|0x00020000|0x00010000
                put(hwnd,-16,style)
                # A local prototype avoids changing pywebview's shared ctypes function;
                # its move() supplies None for the ignored SWP_NOSIZE dimensions.
                pos=ctypes.WINFUNCTYPE(ctypes.c_bool,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_uint)(('SetWindowPos',user))
                pos(hwnd,None,0,0,0,0,0x37)
                dark=ctypes.c_int(self.scheme=='dark')
                ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd),20,ctypes.byref(dark),ctypes.sizeof(dark))
                # WS_THICKFRAME is retained for OS resize/Snap, so its non-client
                # surface needs native theme colors as well as the WebView CSS.
                ctypes.windll.uxtheme.SetWindowTheme(ctypes.c_void_p(hwnd),ctypes.c_wchar_p('DarkMode_Explorer' if self.scheme=='dark' else 'Explorer'),None)
                color=ctypes.c_uint32(0x211710 if self.scheme=='dark' else 0xF9F3ED)
                for attribute in (34,35): # DWMWA_BORDER_COLOR, DWMWA_CAPTION_COLOR (Win11).
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd),attribute,ctypes.byref(color),ctypes.sizeof(color))
                user.RedrawWindow(ctypes.c_void_p(hwnd),None,None,0x481)

            self.window.native.Invoke(Action(apply))
        except Exception:logging.warning('Custom frame system border unavailable',exc_info=True)
    def theme_changed(self,values):
        self.scheme=values.get('color_scheme','light');self.apply_native_frame()
    def install(self,bridge):
        self.window._workstation_native_drag=True
        self.scheme=bridge.appearance.get()['color_scheme']
        bridge.ui_actions.update(api_window_action=self.action,appearance_changed=self.theme_changed)
        self.window.events.shown+=self.apply_native_frame
        self.window.events.maximized+=lambda *_:self.changed(True)
        self.window.events.restored+=lambda *_:self.changed(False)
        def room_visibility(visible):
            visible=bool(visible and self.window.native.Visible)
            bridge._room_surface_visible=visible
            core=getattr(bridge,'_workstation',None)
            if not visible and core is not None and getattr(core,'_room',None) is not None:core._room.leave()
            try:self.window.evaluate_js("window.dispatchEvent(new CustomEvent('workstation-room-visibility',{detail:{visible:"+('true' if visible else 'false')+"}}))")
            except Exception:pass
        self.window.events.minimized+=lambda *_:room_visibility(False)
        self._room_visibility=room_visibility
        self.window.events.restored+=lambda *_:room_visibility(True)
        self.window.events.shown+=lambda *_:room_visibility(True)
        return self
