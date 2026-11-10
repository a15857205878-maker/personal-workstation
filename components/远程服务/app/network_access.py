"""Discover this PC's Tailscale address; never export login or peer details."""
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from urllib.parse import quote, urlsplit

TAILNET_V4=ipaddress.ip_network('100.64.0.0/10')


def is_tailnet_url(url):
    try:
        address=ipaddress.ip_address(urlsplit(url).hostname)
        return isinstance(address,ipaddress.IPv4Address) and address in TAILNET_V4
    except (ValueError,TypeError):return False


def read_tailscale(executable=None,runner=None):
    executable=Path(executable) if executable else Path(os.environ.get('ProgramFiles',r'C:\Program Files'))/'Tailscale'/'tailscale.exe'
    result={'provider':'tailscale','state':'not_installed','ipv4':[], 'message':'Tailscale 未安装，局域网功能可正常使用。'}
    if not executable.is_file():return result
    result.update(state='unavailable',message='Tailscale 状态暂不可用，局域网功能可正常使用。')
    try:
        process=(runner or subprocess.run)([str(executable),'status','--json'],capture_output=True,text=True,
            encoding='utf-8',errors='replace',timeout=2,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        data=json.loads(process.stdout)
        if not isinstance(data,dict):return result
        state=data.get('BackendState')
        if state=='NeedsLogin':
            result.update(state='needs_login',message='Tailscale 等待账号登录或网络批准。')
        elif state=='NeedsMachineAuth':
            result.update(state='needs_approval',message='Tailscale 等待网络管理员批准此电脑。')
        elif state=='Stopped' or isinstance(data.get('Self'),dict) and data['Self'].get('Online') is False:
            result.update(state='offline',message='Tailscale 未连接，局域网功能可正常使用。')
        elif state=='Running':
            addresses=data.get('TailscaleIPs')
            for value in addresses if isinstance(addresses,list) else []:
                try:
                    address=ipaddress.ip_address(value) if isinstance(value,str) else None
                except ValueError:continue
                if isinstance(address,ipaddress.IPv4Address) and address in TAILNET_V4 and str(address) not in result['ipv4']:
                    result['ipv4'].append(str(address))
            if result['ipv4']:
                result.update(state='connected',message='Tailscale 已连接；跨网络连接请选择 '+result['ipv4'][0])
            else:
                result.update(state='starting',message='Tailscale 正在连接，等待分配私有地址。')
    except (OSError,ValueError,subprocess.TimeoutExpired):pass
    return result


class NetworkAccess:
    def __init__(self,lan_urls,port,token,probe=None,clock=time.monotonic):
        self.lan_urls=[url for url in lan_urls if not is_tailnet_url(url)]
        self.port=port;self.token=token
        self.probe=probe or read_tailscale;self.clock=clock
        self.lock=threading.Lock();self.expires=0;self.cached=None

    def snapshot(self):
        with self.lock:
            if self.cached is None or self.clock()>=self.expires:
                self.cached=self.probe();self.expires=self.clock()+5
            remote=dict(self.cached);remote['ipv4']=list(remote['ipv4'])
        urls=list(self.lan_urls)
        for ip in remote['ipv4']:
            url=f'http://{ip}:{self.port}/?token={quote(self.token,safe="")}'
            if url not in urls:urls.append(url)
        return {'urls':urls,'remote_access':remote}
