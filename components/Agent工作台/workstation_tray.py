"""Windows tray for the existing WebView; hiding never stops its services."""
from pathlib import Path

class WorkstationTray:
    def __init__(self,window,icon_path):
        self.window=window;self.icon_path=Path(icon_path)
        self.notify=None;self.menu=None;self.icon=None
    def _ui(self,callback):
        from System import Action
        native=self.window.native
        if native.InvokeRequired:native.Invoke(Action(callback))
        else:callback()
    def _ensure(self):
        if self.notify is not None:return
        from System.Drawing import Icon
        from System.Windows.Forms import NotifyIcon,ContextMenuStrip,MouseButtons
        icon=Icon(str(self.icon_path));menu=ContextMenuStrip();notify=NotifyIcon()
        try:
            menu.Items.Add('打开工作站').Click+=lambda *_:self.restore()
            menu.Items.Add('关闭工作站').Click+=lambda *_:self.window.destroy()
            notify.Icon=icon;notify.Text='个人工作站 · 后台运行';notify.ContextMenuStrip=menu
            def clicked(sender,event):
                if event.Button==MouseButtons.Left:self.restore()
            notify.MouseClick+=clicked
            notify.Visible=True
        except Exception:
            notify.Dispose();menu.Dispose();icon.Dispose();raise
        self.notify=notify;self.menu=menu;self.icon=icon
    def hide(self):
        # Only hide after a recoverable tray entry has been created successfully.
        def apply():
            self._ensure();self.window.native.Hide()
        try:self._ui(apply)
        except Exception as exc:raise RuntimeError('无法创建托盘入口，窗口已保留。请重试。') from exc
    def restore(self):
        def apply():
            self.window.native.Show()
            from System.Windows.Forms import FormWindowState
            if self.window.native.WindowState==FormWindowState.Minimized:
                self.window.native.WindowState=FormWindowState.Normal
            self.window.native.Activate()
        self._ui(apply)
    def dispose(self,*_):
        # closed is emitted after WinForms closes; Dispose is safe at shutdown.
        if self.notify is not None:
            self.notify.Visible=False;self.notify.Dispose();self.notify=None
        if self.menu is not None:self.menu.Dispose();self.menu=None
        if self.icon is not None:self.icon.Dispose();self.icon=None
