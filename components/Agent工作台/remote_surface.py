"""Fixed local entry to the existing remote receiver; no task execution here."""
from pathlib import Path
import base64
import ipaddress
import json
import os
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import build_opener, ProxyHandler

REMOTE_ROOT=Path(__file__).resolve().parent.parent/'远程服务'
LOCAL='http://127.0.0.1:8765'
LIBRARY_ROOT=Path(__file__).resolve().parent/'手机文件库'


class RemoteSurface:
    def __init__(self,root=REMOTE_ROOT,fetch=None,spawn=None,tailscale_path=None,opener=None):
        self.root=Path(root)
        self.fetch=fetch or self._fetch
        self.spawn=spawn or subprocess.Popen
        self.lock=threading.RLock()
        self.process=None
        self.tailscale_path=Path(tailscale_path) if tailscale_path is not None else Path(os.environ.get('ProgramFiles',r'C:\Program Files'))/'Tailscale/tailscale-ipn.exe'
        self.opener=opener or os.startfile

    def file_roots(self,operation,window=None,payload=None):
        payload=payload or {}
        if operation not in ('list','add','remove') or set(payload)-({'id'} if operation=='remove' else set()):raise ValueError('文件目录参数无效。')
        with self.lock:
            if not hasattr(self,'_files'):
                import importlib.util
                spec=importlib.util.spec_from_file_location('personal_remote_pc_files',self.root/'app/pc_files.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);self._files=module.ComputerFiles(self.root)
            if operation=='list':return self._files.local_roots()
            if operation=='remove':
                if not isinstance(payload.get('id'),str):raise ValueError('目录编号无效。')
                return self._files.remove_root(payload['id'])
            if window is None:raise ValueError('请在电脑个人工作站中选择目录。')
            import webview
            paths=window.create_file_dialog(webview.FileDialog.FOLDER,allow_multiple=False)
            return self._files.add_root(paths[0]) if paths else self._files.local_roots()

    def file_library(self,open_folder=False,choose_folder=False,window=None):
        with self.lock:
            self.file_roots('list')
            if choose_folder:
                if window is None:raise ValueError('请在电脑个人工作站中选择共享文件夹。')
                import webview
                paths=window.create_file_dialog(webview.FileDialog.FOLDER,allow_multiple=False)
                if paths:self._files.set_library(paths[0])
            data=self._files.local_roots()
            selected=next((row for row in data['roots'] if row['id']==data.get('library_id')),None)
            library=Path(selected['path']) if selected else LIBRARY_ROOT
            if open_folder:
                if selected is None:
                    library.mkdir(exist_ok=True)
                    self._files.set_library(library)
                if not library.is_dir():raise ValueError('共享文件夹暂不可用，请重新选择。')
                self.opener(str(library))
            data=self._files.local_roots()
            ready=library.is_dir() and any(row['id']==data.get('library_id') and os.path.normcase(row['path'])==os.path.normcase(str(library)) for row in data['roots'])
            return {'path':str(library),'ready':ready,'message':'手机只读访问此文件夹；可在电脑端更换。'}

    def open_tailscale(self):
        if not self.tailscale_path.is_file():raise ValueError('未找到已安装的 Tailscale，请检查电脑端安装。')
        try:self.opener(str(self.tailscale_path))
        except OSError:raise ValueError('Tailscale 暂未打开，请稍后重试或从开始菜单打开。') from None
        return {'message':'已请求打开 Tailscale，可从任务栏右下角的托盘图标查看或连接。'}

    @staticmethod
    def _fetch(url):
        with build_opener(ProxyHandler({})).open(url,timeout=6) as response:
            data=response.read(2*1024*1024+1)
            if len(data)>2*1024*1024:raise ValueError('response too large')
            return data

    @staticmethod
    def _address(url,token):
        try:
            parsed=urlsplit(url)
            address=ipaddress.ip_address(parsed.hostname)
            return (parsed.scheme=='http' and parsed.port==8765 and parsed.path=='/'
                    and not parsed.username and not parsed.password and not parsed.fragment
                    and not address.is_loopback and not address.is_unspecified and not address.is_multicast
                    and (address.is_private or address in ipaddress.ip_network('100.64.0.0/10'))
                    and parse_qs(parsed.query)=={'token':[token]})
        except (ValueError,TypeError):return False

    def _probe(self):
        token=json.loads((self.root/'app/pairing.json').read_text(encoding='utf-8'))['token']
        if not isinstance(token,str) or not 8<=len(token)<=256:raise ValueError('invalid pairing')
        query=urlencode({'token':token})
        info=json.loads(self.fetch(LOCAL+'/api/info?'+query))
        if info.get('ui_mode')!='unified-only' or not isinstance(info.get('urls'),list):raise ValueError('unrecognized receiver')
        return token,query,info

    def status(self):
        result={'online':False,'gateway_online':False,'connections':[],'message':'远程接收器未连接，点击启动后可在这里配对手机。'}
        try:
            result['gateway_online']=json.loads(self.fetch('http://127.0.0.1:47633/health')).get('ok') is True
        except (OSError,ValueError,TypeError,AttributeError):pass
        try:
            token,query,info=self._probe()
            result.update(online=True,message='远程接收器已连接',session_url=LOCAL+'/?'+query,collaboration_url=LOCAL+'/collaboration?'+query,transfer_url=LOCAL+'/transfer?'+query)
            for url in info['urls'][:16]:
                if not isinstance(url,str) or not self._address(url,token):continue
                connection={'url':url,'address':urlsplit(url).hostname,'qr':None}
                try:
                    raw=self.fetch(LOCAL+'/qr.svg?'+query+'&address='+quote(url,safe=''))
                    connection['qr']='data:image/svg+xml;base64,'+base64.b64encode(raw).decode('ascii')
                except (OSError,ValueError,TypeError):pass
                result['connections'].append(connection)
            remote=info.get('remote_access',{})
            result['network_state']=remote.get('state','unknown') if isinstance(remote,dict) else 'unknown'
        except (OSError,ValueError,KeyError,TypeError,AttributeError):pass
        return result

    def start(self):
        with self.lock:
            current=self.status()
            if current['online']:return current
            script=self.root/'app/transfer.py'
            if not script.is_file():raise ValueError('远程会话台入口不存在，请先检查安装目录。')
            if self.process is None or self.process.poll() is not None:
                executable=Path(sys.executable)
                pythonw=executable.with_name('pythonw.exe')
                if pythonw.is_file():executable=pythonw
                self.process=self.spawn([str(executable),str(script),'--headless'],cwd=str(self.root),
                                        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                current=self.status()
                if current['online']:return current
                if self.process.poll() is not None:break
                time.sleep(.25)
            raise ValueError('接收器尚未连接，请稍后刷新；若仍失败，请检查端口 8765 和原远程会话台。')
