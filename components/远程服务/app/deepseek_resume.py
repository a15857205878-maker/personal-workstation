"""Exact-session continuation; reuse durable replies without Codex's busy retry policy."""
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import threading
import time
from contextlib import closing
from reply_queue import ReplyQueue
from deepseek_runner import harness_paths
from owned_process import OwnedProcessGroup
from permission_notices import PERMISSION_INSTRUCTIONS, permission_error, permission_notice


def resume(reader, job, stop):
    if stop.is_set():raise RuntimeError('服务正在关闭，未继续发送。')
    meta = reader.resolve(job['thread_id'])
    if meta['cwd'] != job['cwd']:
        raise ValueError('原工作目录已改变，未发送，请重新打开记录核对。')
    paths = harness_paths()
    if not paths:
        raise ValueError('未找到本机Harness，未发送。')
    patch = Path(job['output']).with_name('resume.patch.yml')
    patch.write_text(json.dumps([
        {'id': 'credentials', 'disabled': False},
        {'id': 'agent-default-model', 'config': meta['model']}
    ]), encoding='utf-8')
    command = [str(paths[0]), '--expose-internals', str(paths[1]), 'headless',
               '--patch', str(patch), '--json', '--session-id', meta['native_id'], '-']
    process = subprocess.Popen(command, cwd=meta['cwd'], env=dict(os.environ, ELECTRON_RUN_AS_NODE='1'),
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               text=True, encoding='utf-8', errors='replace',
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), start_new_session=os.name!='nt')
    try:
        group = OwnedProcessGroup(process)
    except Exception:
        process.kill();process.wait()
        process.stdin.close();process.stdout.close()
        raise RuntimeError('执行进程无法管理，未继续发送。') from None
    done = threading.Event()
    def terminate():
        try:group.terminate()
        except OSError:
            if process.poll() is None:process.kill()
    def watch():
        until = time.monotonic()+900
        while not done.wait(.25):
            if stop.is_set() or time.monotonic()>until:
                terminate();return
    watcher = threading.Thread(target=watch, daemon=True)
    matched=False;final=None;terminal=None;failed=False;permission_blocked=False
    try:
        watcher.start()
        if stop.is_set():raise RuntimeError('服务正在关闭，未继续发送。')
        process.stdin.write(PERMISSION_INSTRUCTIONS+'\n继续用户当前会话，只处理以下明确指令，不更改审批设置或派生代理。\n'+job['text'])
        process.stdin.close()
        for line in process.stdout:
            try:event=json.loads(line)
            except ValueError:continue
            if not isinstance(event,dict):continue
            if event.get('type')=='session':
                if event.get('sessionId')!=meta['native_id']:
                    raise RuntimeError('返回的会话编号不一致，已停止，请核对历史。')
                matched=True
            elif event.get('type')=='error':
                failed=True;permission_blocked=permission_blocked or permission_error(str(event.get('message','')))
            elif event.get('type')=='final':
                final=event.get('text');terminal=event.get('reason')
            elif event.get('type')=='status' and event.get('phase')=='turn_end':terminal=event.get('reason')
        code=process.wait()
        if permission_blocked:raise RuntimeError(permission_notice())
        if stop.is_set() or code or failed or not matched or not isinstance(terminal,dict) or terminal.get('kind')!='completed' or not isinstance(final,str) or not final.strip():
            raise RuntimeError('未确认续聊完成。可能会话被占用，或登录、额度、权限有问题；请在电脑核对原会话，不会自动重发。')
        return final[:60000]
    finally:
        done.set();terminate()
        try:
            process.wait(timeout=10);watcher.join(timeout=2)
            if not process.stdin.closed:process.stdin.close()
            process.stdout.close()
        finally:group.close()


class DeepSeekReplies(ReplyQueue):
    def __init__(self, root, reader, runner=None, start_worker=True):
        self.history = reader
        class SessionReader:
            def get(_, identifier):return reader.resolve(identifier)
        def run(job,stop):
            try:return resume(reader,job,stop)
            except OSError:raise RuntimeError('本机续聊暂不可用，请检查权限、原目录和Harness；未自动重发。') from None
        super().__init__(Path(root)/'DeepSeek续聊', SessionReader(),
                         runner=runner or run,start_worker=start_worker)

    def create(self, channel, source, request_id, thread_id, text, attachments=None):
        if channel!='web' or not isinstance(source,str) or not 1<=len(source)<=120 or not isinstance(thread_id,str) or not re.fullmatch('[a-f0-9]{64}',thread_id):
            raise ValueError('续聊来源或会话编号无效')
        if attachments:raise ValueError('DeepSeek历史续聊本版仅支持文字，请勿添加附件')
        with self.lock:
            with closing(sqlite3.connect(self.database)) as db:
                old=db.execute('SELECT 1 FROM replies WHERE channel=? AND source=? AND request_id=?',(channel,source,request_id)).fetchone()
            if not old and self.has_pending(thread_id):
                raise ValueError('此会话已有续聊等待或执行中，请先等待结果')
            return super().create(channel,source,request_id,thread_id,text,attachments)
