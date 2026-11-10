"""Desktop-only actions, separated from storage and provider execution."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import threading
import webbrowser

from .core import Service, ACTIVE
from .quota import QuotaStore
from .adapters import Settings, Adapters, BASE


def copy_text(text):
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalFree.argtypes = [wintypes.HGLOBAL]
    user.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user.SetClipboardData.restype = wintypes.HANDLE
    raw = (text + '\0').encode('utf-16-le')
    memory = kernel.GlobalAlloc(0x42, len(raw))
    if not memory:
        raise ValueError('剪贴板内存分配失败')
    transferred = False
    opened = False
    try:
        address = kernel.GlobalLock(memory)
        if not address:
            raise ValueError('无法准备剪贴板内容')
        ctypes.memmove(address, raw, len(raw))
        kernel.GlobalUnlock(memory)
        opened = bool(user.OpenClipboard(None))
        if not opened:
            raise ValueError('剪贴板暂被占用，请重试复制')
        if not user.EmptyClipboard() or not user.SetClipboardData(13, memory):
            raise ValueError('复制失败，请重试')
        transferred = True
    finally:
        if opened:
            user.CloseClipboard()
        if not transferred:
            kernel.GlobalFree(memory)


def launch_plan(role):
    role={'presentation_gemini':'research_sources','excel_gemini':'research_sources','image_gemini':'research_sources','animation_gemini':'research_sources','text_claude':'presentation','research_kimi':'excel'}.get(role,role)
    local = Path(os.environ.get('LOCALAPPDATA', ''))
    paths = {
        'text_2': local / 'Programs/QianwenApp/qianwen.exe',
        'excel': local / 'Programs/Kimi/Kimi.exe',
        'research_sources': local / 'Google/Gemini/Gemini.exe',
        'frontend': local / 'Programs/DeepSeek Harness/DeepSeek Harness.exe',
    }
    urls = dict(text_1='https://chatgpt.com/', backend_and_integration='https://chatgpt.com/',
                text_2='https://www.qianwen.com/', excel='https://www.kimi.ai/',
                research_sources='https://gemini.google.com/app', frontend='https://chat.deepseek.com/',
                presentation='https://claude.ai/new')
    if role == 'presentation':
        return ('app', 'Claude_pzs8sxrjxfjjc!Claude')
    if role in ('text_1', 'backend_and_integration'):
        return ('app', 'OpenAI.Codex_2p2nqsd0c76g0!App')
    target = paths.get(role)
    if target and target.is_file():
        return ('exe', str(target))
    return ('url', urls[role])


class Bridge:
    def __init__(self, data, execution_gate=None):
        self.settings = Settings(data)
        self.adapters = Adapters(self.settings)
        self.service = Service(data, self.adapters, execution_gate=execution_gate)
        self.window = None
        self.desktop_lock = threading.Lock()

    def call(self, method, params=None):
        params = params or {}
        try:
            if not isinstance(params, dict):
                raise ValueError('参数格式无效')
            if method == 'quota':
                data = QuotaStore(self.service.data / 'claude-quota.json').read()
            elif method == 'quota_open':
                if not webbrowser.open('https://claude.ai/new'):
                    raise ValueError('未能打开Claude官网，请检查默认浏览器')
                data = dict(opened=True)
            elif method=='preview_animation':
                path=self.service.file_path(params.get('id'),params.get('name'))
                parent=path.parent
                if parent.is_symlink() or getattr(parent,'is_junction',lambda:False)() or path.resolve().parent!=parent.absolute():raise ValueError('成果目录不能为链接')
                if path.suffix.lower()!='.html' or path.stat().st_size>400000:raise ValueError('请选择任务内的小动画HTML文件')
                from .generation_channels import animation_html
                data={'name':path.name,'html':animation_html(path.read_text(encoding='utf-8'))}
            elif method == 'settings':
                data = self.settings.public()
            elif method == 'save_settings':
                if not self.service.execution_gate.acquire(blocking=False):
                    raise ValueError('模型任务运行中，请等待或停止后修改接入配置。')
                try:
                    data = self.settings.save(params)
                finally:
                    self.service.execution_gate.release()
            elif method in ('copy_prompt', 'handoff', 'import_result', 'open_folder', 'open_file'):
                data = self._desktop(method, params)
            else:
                data = self.service.call(method, params)
            return dict(ok=True, data=data)
        except ValueError as exc:
            return dict(ok=False, error=str(exc)[:600])
        except Exception:
            return dict(ok=False, error='操作未完成，请检查文件权限、窗口状态或接入配置。')

    def _desktop(self, method, p):
        task = self.service.call('get', p)
        if method == 'copy_prompt':
            with self.desktop_lock:
                copy_text(task['prompt'])
            return dict(copied=True)
        if method == 'handoff':
            if task['status'] in ACTIVE:
                raise ValueError('请先取消后台任务，再打开客户端交接')
            if task.get('execution_mode')=='api':raise ValueError('本任务选择API执行，请先在草稿中切换外部方式')
            if task.get('execution_mode')=='external':self.service.begin_external_handoff(task['id'])
            kind, target = launch_plan(task['role'])
            with self.desktop_lock:
                copy_text(task['prompt'])
                if kind == 'exe':
                    subprocess.Popen([target], creationflags=subprocess.CREATE_NO_WINDOW)
                elif kind == 'app':
                    # Existing verified Windows AppUserModelID; no user command strings.
                    subprocess.Popen(['explorer.exe', 'shell:AppsFolder\\' + target],
                                     creationflags=subprocess.CREATE_NO_WINDOW)
                elif not webbrowser.open(target):
                    raise ValueError('未能打开浏览器，请检查默认浏览器设置')
                result=None
                if task.get('execution_mode')=='external':
                    from .client_handoff import paste_client
                    result=paste_client(kind,target,task['prompt'])
            return self.service.mark_handoff(task['id'],dict(opened=True,copied=True,**result) if result is not None else None)
        if method == 'import_result':
            import webview
            with self.desktop_lock:
                paths = self.window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False)
            return self.service.import_file(task['id'], paths[0]) if paths else task
        if method == 'open_folder':
            os.startfile(task['folder'])
        elif method == 'open_file':
            path = self.service.file_path(task['id'], p.get('name'))
            if path.suffix.lower() not in ('.pptx', '.xlsx', '.docx', '.pdf', '.txt', '.md', '.csv',
                                           '.png', '.jpg', '.jpeg', '.webp'):
                raise ValueError('此文件类型请在成果文件夹中自行检查后打开')
            os.startfile(str(path))
        return dict(opened=True)
