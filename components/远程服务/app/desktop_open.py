"""Explicit, expiring desktop handoff requests. Never launches on timeout."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from uuid import UUID


def canonical_thread(value):
    if not isinstance(value, str):
        raise ValueError('会话尚未建立，请稍后再试。')
    try:
        if str(UUID(value)) != value.lower():
            raise ValueError()
    except ValueError:
        raise ValueError('无效的目标会话。') from None
    return value.lower()


def native_prompt(title, deadline, stop):
    executable = Path(sys.executable)
    if executable.name.lower() == 'python.exe':
        executable = executable.with_name('pythonw.exe')
    process = subprocess.Popen([str(executable), str(Path(__file__).with_name('desktop_prompt.py'))],
                               stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, text=True, encoding='utf-8')
    try:
        process.stdin.write(json.dumps({'title': title, 'expires_at': deadline}, ensure_ascii=False))
        process.stdin.close()
        while process.poll() is None:
            if stop.wait(.1):
                return 2
            if time.time() >= deadline:
                return 3
        return process.returncode
    finally:
        if process.poll() is None:
            process.terminate()  # Only our own confirmation popup, never Codex.
        process.wait(timeout=5)


class DesktopOpenManager:
    def __init__(self, tasks, reader, replies, prompt=None, opener=None, clock=time.time):
        self.tasks, self.reader, self.replies = tasks, reader, replies
        self.prompt = prompt or native_prompt
        self.opener = opener or getattr(os, 'startfile', None)
        self.clock = clock
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.requests = {}
        self.workers = []

    def _busy(self, thread):
        return (any((thread is None or t.get('remote_session') == thread) and t['status'] in ('running', 'queued')
                    for t in self.tasks.list()) or self.replies.has_pending(thread))

    @staticmethod
    def _public(request):
        return {k: v for k, v in request.items() if k != 'task_id'}

    def request(self, task_id=None, thread_id=None, application=False):
        if not isinstance(application, bool) or application and (task_id or thread_id):
            raise ValueError('打开请求格式不正确。')
        task = self.tasks.get(task_id) if task_id else None
        saved = canonical_thread(task.get('remote_session')) if task else None
        thread = canonical_thread(thread_id) if thread_id else saved
        if not application and (not thread or saved and saved != thread):
            raise ValueError('目标会话不一致，请重新选择。')
        session = {} if application else self.reader.get(thread)
        title = str(session.get('title') or (task or {}).get('goal') or 'Codex 会话')[:160]
        with self.lock, self.tasks.lock, self.replies.lock:
            if self.stop.is_set():
                raise ValueError('工作台正在关闭，请稍后重试。')
            for item in self.requests.values():
                if item['status'] == 'pending':
                    if item['thread_id'] == thread:
                        return self._public(item)
                    raise ValueError('电脑上已有打开确认，请先处理或等待倒计时结束。')
            # Bounded in-memory receipts; no delayed launches recovered on restart.
            while len(self.requests) >= 100:
                del self.requests[next(iter(self.requests))]
            request = {'request_id': secrets.token_hex(16), 'task_id': task_id,
                       'thread_id': thread, 'expires_at': self.clock() + 15,
                       'status': 'pending', 'message': '请在电脑确认，15秒后取消本次打开请求；已打开的会话不会自动关闭。'}
            self.requests[request['request_id']] = request
            if self._busy(thread):
                request.update(status='blocked', message=('后台有待发送或执行中的任务，请等待完成；也可以从工作台选择其他空闲会话打开。' if application else '目标会话有待发送或执行中的指令，暂不打开桌面；请等待完成，或在队列里明确取消不需要的待发送指令。'))
            else:
                worker = threading.Thread(target=self._confirm, args=(request, title), daemon=True)
                self.workers = [w for w in self.workers if w.is_alive()]
                self.workers.append(worker)
                worker.start()
            return self._public(request)

    def get(self, request_id):
        with self.lock:
            return self._public(self.requests[request_id])

    def _confirm(self, request, title):
        try:
            code = self.prompt(title, request['expires_at'], self.stop)
            # Queue claims and task updates use these same locks. A target that
            # starts during the popup cannot pass this final busy check.
            with self.lock, self.tasks.lock, self.replies.lock:
                if self.stop.is_set():
                    request.update(status='cancelled', message='工作台已关闭，保持后台。')
                elif self.clock() >= request['expires_at'] or code == 3:
                    request.update(status='expired', message='确认已超时，未打开新会话。已打开的 Codex 会话不会自动关闭；若手机指令仍等待占用，请先退出该会话或桌面应用。')
                elif code == 2:
                    request.update(status='background', message='已取消本次打开请求。已打开的 Codex 会话不会自动关闭；后台是否可执行请以指令队列状态为准。')
                elif code != 0:
                    request.update(status='failed', message='电脑确认窗口未能完成，保持后台。')
                elif (self._busy(request['thread_id']) or
                      request['task_id'] and canonical_thread(self.tasks.get(request['task_id']).get('remote_session')) != request['thread_id']):
                    request.update(status='blocked', message='目标会话状态已变化或正在执行，保持后台，请稍后重试。')
                else:
                    if request['thread_id']:
                        self.reader.get(request['thread_id'])  # Removed/archived targets cannot open.
                    if self.opener is None:
                        raise OSError('Windows opener unavailable')
                    if self.stop.is_set():
                        request.update(status='cancelled', message='工作台已关闭，保持后台。')
                        return
                    if self.clock() >= request['expires_at']:
                        request.update(status='expired', message='确认已超时，未打开新会话；已打开的会话不会自动关闭。')
                        return
                    self.opener('codex://threads/' + request['thread_id'] if request['thread_id'] else
                                'shell:AppsFolder\\OpenAI.Codex_2p2nqsd0c76g0!App')
                    request.update(status='opened', message='已请求在电脑打开此会话。手机后续指令可能等待桌面释放占用；离开会话后若仍等待，请退出 Codex 桌面应用，保持接收服务运行。')
        except Exception:
            with self.lock:
                request.update(status='failed', message='打开未完成，保持后台，请检查电脑端 Codex。')

    def close(self):
        with self.lock:
            self.stop.set()
            for item in self.requests.values():
                if item['status'] == 'pending':
                    item.update(status='cancelled', message='工作台已关闭，保持后台。')
        for worker in self.workers:
            worker.join(timeout=.5)
