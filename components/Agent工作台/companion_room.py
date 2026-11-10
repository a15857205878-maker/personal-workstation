"""Bounded local display lease. Never launches a pet or reads account state."""
from pathlib import Path
import base64,json,math,os,re,threading,time,uuid
from companion_adapter import PET

def read(path):
    try:
        if path.stat().st_size>2048:return {}
        value=json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError,UnicodeError):return {}

def write(path,value):
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        tmp.write_text(json.dumps(value,allow_nan=False),encoding='utf-8');os.replace(tmp,path)
    finally:tmp.unlink(missing_ok=True)

def live(value,now):
    expires=value.get('expires')
    return value.get('version')==1 and value.get('mode')=='home' and type(expires) in (float,int) and math.isfinite(expires) and 0<expires-now<=8.1 and isinstance(value.get('token'),str) and re.fullmatch('[a-f0-9]{32}',value['token'])

class RoomPresence:
    def __init__(self,pet_root=PET,clock=time.time):
        self.root=Path(pet_root);self.clock=clock;self.token=None;self.lock=threading.RLock();self._portrait=None
        self.request=self.root/'room-presence.request.json';self.ack=self.root/'room-presence.status.json'
    def enter(self):
        with self.lock:
            if not self.root.is_dir():raise ValueError('桌宠安装位置不可用，请检查原桌宠。')
            if live(read(self.request),self.clock()):raise ValueError('另一个房间仍在使用角色，请先返回桌面。')
            self.token=uuid.uuid4().hex;self._renew();return self.status(self.token)
    def _renew(self):write(self.request,dict(version=1,mode='home',token=self.token,expires=self.clock()+8))
    def heartbeat(self,token):
        with self.lock:
            if not self.token or token!=self.token:raise ValueError('房间已离开，请重新请角色回家。')
            req=read(self.request)
            if req.get('token')!=token or not live(req,self.clock()):self.token=None;raise ValueError('房间连接已过期，请重新请角色回家。')
            ack=read(self.ack)
            if ack.get('token')==token and ack.get('state') in ('revoked','incompatible'):
                self.leave(token);raise ValueError('桌宠已从托盘返回桌面。' if ack['state']=='revoked' else '请先在原桌宠设置中切换为龙娘形象。')
            self._renew();return self.status(token)
    def status(self,token):
        now=self.clock();req=read(self.request);ack=read(self.ack);at=ack.get('at')
        owned=bool(self.token and token==self.token and req.get('token')==token and live(req,now))
        fresh=type(at) in (float,int) and math.isfinite(at) and 0<=now-at<2
        home=bool(owned and fresh and ack.get('token')==token and ack.get('state')=='home' and ack.get('hidden') is True and ack.get('appearance')=='dragon')
        return dict(token=token,home=home,state='home' if home else 'waiting' if owned else 'desktop')
    def leave(self,token=None):
        with self.lock:
            token=token or self.token
            if token and token==self.token:
                req=read(self.request)
                if req.get('token')==token:write(self.request,dict(version=1,mode='desktop',token=token,expires=self.clock()))
                self.token=None
            return dict(home=False,state='desktop')
    def portrait(self):
        file=self.root/'web/appearances/dragon/01-idle.png'
        if not file.is_file() or file.stat().st_size>2_000_000:raise ValueError('原龙娘静态形象不可用。')
        stamp=file.stat().st_mtime_ns
        if not self._portrait or self._portrait[0]!=stamp:
            data=file.read_bytes()
            if not data.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('原角色图片格式不正确。')
            self._portrait=(stamp,'data:image/png;base64,'+base64.b64encode(data).decode('ascii'))
        return self._portrait[1]
