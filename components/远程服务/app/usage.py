"""Read Codex account limits via the official stdio API, without loading a thread."""
import json
import math
import os
import queue
import subprocess
import threading
import time
from adapters import codex_path


def stop_process(process):
    try:process.stdin.close()
    except (OSError,ValueError):pass
    try:process.wait(timeout=.3)
    except subprocess.TimeoutExpired:
        try:process.terminate()
        except OSError:pass
        try:process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:process.kill()
            except OSError:pass
            process.wait(timeout=1)


def read_limits(executable=None, timeout=10, spawn=None):
    executable=executable or codex_path()
    if not executable:
        raise RuntimeError('Codex unavailable')
    process=(spawn or subprocess.Popen)([executable,'app-server'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,text=True,encoding='utf-8',errors='replace',
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    inbox=queue.Queue(maxsize=128)
    def receive():
        try:
            while True:
                line=process.stdout.readline(1024*1024)
                if not line:break
                try:inbox.put(json.loads(line),timeout=.1)
                except (ValueError,queue.Full):continue
        finally:
            try:inbox.put(None,timeout=.1)
            except queue.Full:pass
    reader=threading.Thread(target=receive,daemon=True)
    deadline=time.monotonic()+timeout
    def send(value):
        process.stdin.write(json.dumps(value)+'\n');process.stdin.flush()
    def response(identifier):
        while True:
            left=deadline-time.monotonic()
            if left<=0:raise TimeoutError('Limits read timeout')
            value=inbox.get(timeout=left)
            if value is None:raise RuntimeError('Codex disconnected')
            if isinstance(value,dict) and value.get('id')==identifier:
                if 'error' in value:raise RuntimeError('Limits unavailable')
                result=value.get('result')
                if not isinstance(result,dict):raise ValueError('Invalid limits response')
                return result
    try:
        reader.start()
        send({'method':'initialize','id':1,'params':{'clientInfo':{'name':'personal_workbench_usage','version':'1.0.0'}}})
        response(1)
        send({'method':'initialized','params':{}})
        send({'method':'account/rateLimits/read','id':2})
        return response(2)
    finally:
        stop_process(process)
        if reader.ident is not None:reader.join(timeout=1)
        process.stdout.close()


def number(value):
    return float(value) if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) else None


def normalize_limits(value):
    pools=[]
    multiple=value.get('rateLimitsByLimitId')
    buckets=multiple if isinstance(multiple,dict) and multiple else {'codex':value.get('rateLimits')}
    for key,bucket in buckets.items():
        if not isinstance(bucket,dict):continue
        windows=[]
        for slot in ('primary','secondary'):
            window=bucket.get(slot)
            if not isinstance(window,dict):continue
            used=number(window.get('usedPercent'))
            used=max(0,min(100,used)) if used is not None else None
            minutes=number(window.get('windowDurationMins'))
            minutes=minutes if minutes is not None and minutes>0 else None
            reset=number(window.get('resetsAt'))
            reset=reset if reset is not None and 0<reset<253402300800 else None
            windows.append(dict(used_percent=used,remaining_percent=100-used if used is not None else None,
                                window_minutes=minutes,resets_at=reset))
        if windows:
            pools.append(dict(label='Codex' if key=='codex' else '其他额度池 '+str(len(pools)+1),windows=windows))
    return pools


class UsageService:
    def __init__(self,probe=None,clock=time.monotonic):
        self.probe=probe;self.clock=clock;self.lock=threading.Lock();self.expires=0;self.cached=None
        self.process_lock=threading.Lock();self.active=None;self.closed=False

    def _spawn(self,*args,**kwargs):
        # Spawn and ownership registration are atomic with respect to close().
        with self.process_lock:
            if self.closed:raise RuntimeError('Usage service closed')
            self.active=subprocess.Popen(*args,**kwargs)
            return self.active

    def close(self):
        with self.process_lock:
            self.closed=True
            process=self.active
        if process is not None:stop_process(process)
        # The query has a deadline; killing its owned child releases stdout and
        # lets the request's finally finish before daemon HTTP threads exit.
        with self.lock:pass

    def read(self):
        with self.lock:
            if not self.closed and self.cached is not None and self.clock()<self.expires:
                return dict(self.cached,cached=True)
            try:
                pools=[] if self.closed else normalize_limits(self.probe() if self.probe is not None else read_limits(spawn=self._spawn))
            except Exception:
                pools=[]
            finally:
                with self.process_lock:self.active=None
            self.cached=dict(provider='codex',status='available' if pools else 'unavailable',
                pools=pools,checked_at=time.time(),cached=False,
                message='电脑当前 Codex 登录账号的共享额度；不是本会话单独额度，也不是现金余额。' if pools else
                '暂时无法读取额度。请确认电脑 Codex 已用 ChatGPT 账号登录；仅 API Key 登录可能不支持。未读取到不代表额度为零。')
            self.expires=self.clock()+30
            return dict(self.cached)
