"""Bounded read-only Harness history; independent of model/credential services."""
import copy
import json
import os
import shutil
from pathlib import Path
import re
import subprocess
import threading
import time


class DeepSeekHistoryReader:
    def __init__(self, root=None, runtime=None, cache_seconds=5):
        self.root = Path(root) if root is not None else Path.home()/'.dsh/sessions'
        self.runtime = Path(runtime) if runtime else self._runtime()
        self.cache_seconds = cache_seconds
        self.cache = {}
        self.lock = threading.Lock()

    @staticmethod
    def _runtime():
        candidates = [Path(os.environ.get('WORKSTATION_NODE') or shutil.which('node') or 'node.exe'),
                      Path(os.environ.get('LOCALAPPDATA',''))/'Programs/DeepSeek Harness/DeepSeek Harness.exe']
        return next((p for p in candidates if p.is_file()),candidates[0])

    def _read(self, mode, session_id='', before=None):
        key = (mode, session_id, before)
        with self.lock:
            cached = self.cache.get(key)
            if cached and time.monotonic()-cached[0] < self.cache_seconds:
                return copy.deepcopy(cached[1])
            if not self.runtime.is_file():
                raise OSError('本机历史读取运行环境不可用，请确认 DeepSeek Harness 已安装。')
            env = dict(os.environ, ELECTRON_RUN_AS_NODE='1')
            try:
                result = subprocess.run([str(self.runtime),str(Path(__file__).with_suffix('.cjs')),mode,
                                         str(self.root),session_id,'' if before is None else str(before)],
                                        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=15,
                                        env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            except (OSError,subprocess.TimeoutExpired) as error:
                raise OSError('本机 DeepSeek 历史暂时无法读取，请稍后刷新。') from error
            if result.returncode or len(result.stdout)>5*1024*1024:
                raise OSError('本机 DeepSeek 历史格式不支持或暂时无法读取。')
            try: value = json.loads(result.stdout)
            except (ValueError,UnicodeError) as error: raise OSError('本机历史读取结果无效。') from error
            if value.get('missing'): raise KeyError(session_id)
            if len(self.cache)>16:self.cache.clear()
            self.cache[key] = (time.monotonic(),value)
            return copy.deepcopy(value)

    def session_page(self, limit=20, offset=0, search=''):
        if type(limit) is not int or not 1<=limit<=50 or type(offset) is not int or offset<0:
            raise ValueError('历史分页无效。')
        if not isinstance(search,str) or len(search)>200:raise ValueError('搜索内容无效。')
        data=self._read('list')
        sessions=[s for s in data['sessions'] if search.casefold() in s['title'].casefold()]
        return {'sessions':sessions[offset:offset+limit],
                'next_offset':offset+limit if offset+limit<len(sessions) else None,
                'warning':data.get('warning','')}

    def resolve(self, identifier):
        if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{64}',identifier):raise ValueError('DeepSeek会话编号无效')
        with self.lock:self.cache.pop(('resolve',identifier,None),None)
        value=self._read('resolve',identifier)
        if not value.get('allowed'):raise ValueError(value.get('reason') or '此会话暂时只读')
        return value

    def conversation(self, session_id, source, before=None, replies=None):
        if not isinstance(session_id,str) or not re.fullmatch('[a-f0-9]{64}',session_id):
            raise ValueError('DeepSeek 会话标识无效。')
        if not isinstance(source,str) or not 1<=len(source)<=120:raise ValueError('网页来源标识无效。')
        if before is not None and (type(before) is not int or not 0<=before<2**53):raise ValueError('历史游标无效。')
        history=self._read('history',session_id,before)
        supported=False;hint='本机Harness历史目前只读；需要执行请新建Flash任务。';jobs=[]
        if replies is not None:
            try:
                self.resolve(session_id);supported=True;hint='可继续原会话；发送时检查占用，使用原工作目录和模型额度。'
            except (ValueError,OSError,KeyError):
                try:hint=self._read('resolve',session_id).get('reason') or '暂时无法检查，保持只读'
                except (ValueError,OSError,KeyError):hint='暂时无法检查，保持只读'
            jobs=replies.list('web',source,session_id)
        pending=replies is not None and replies.has_pending(session_id)
        if pending:hint='续聊已提交，等待原会话返回；请勿重复发送。'
        return {'provider':'deepseek-harness','session_id':session_id,'thread_id':None,'task':None,
                'title':history['title'],'status':'running' if pending else history['status'],'status_hint':hint if replies is not None else history['status_hint'],
                'history':history,'jobs':jobs,'can_reply':supported and not pending,'resume_supported':supported,
                'reply_hint':hint}
