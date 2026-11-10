"""Provider-neutral local task queue and persisted completed work."""
from contextlib import closing
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import sqlite3
import threading
import time

from adapters import RUNNERS, agents, Cancelled, NeedsAttention

TERMINAL = {'completed', 'failed', 'cancelled', 'needs_attention'}
ARTIFACT_WARNING = '成果列表暂时无法读取，已有执行结果保留；请稍后检查工作目录，不要重复执行任务。'


class TaskManager:
    def __init__(self, root, start_worker=True):
        self.root = Path(root)
        self.data = self.root / '任务数据'
        self.uploads = self.root / '任务附件'
        self.data.mkdir(parents=True, exist_ok=True)
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.database = self.root / '任务记录.sqlite3'
        self.lock = threading.RLock()
        self.queue = queue.Queue()
        self.stop_events = {}
        self.closing = threading.Event()
        self.worker = None
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, client_id TEXT UNIQUE NOT NULL, body TEXT NOT NULL)')
        for task in self.list():
            if task['status'] == 'running':
                self.update(task['id'], status='needs_attention', error='电脑接收服务曾中断，任务未自动重新执行。已有成果保留，请检查后重新提交。')
            elif task['status'] == 'queued':
                self.queue.put(task['id'])
        if start_worker:
            self.start()

    def start(self):
        if self.worker is None:
            self.worker = threading.Thread(target=self._work, daemon=True)
            self.worker.start()

    def workspace(self, task_id, agent=None):
        if not isinstance(task_id, str) or not re.fullmatch('[a-f0-9]{32}', task_id):
            raise ValueError('无效的任务编号')
        if agent is None:
            try:agent=self.get(task_id).get('agent')
            except KeyError:pass
        if agent=='codex-deepseek-code':
            from artifact_preview import safe_path
            return safe_path(self.root,self.root/'代码项目'/task_id)
        return self.data/task_id/'workspace'

    def list(self):
        with closing(sqlite3.connect(self.database)) as db:
            rows = db.execute('SELECT body FROM tasks ORDER BY rowid DESC').fetchall()
        return [json.loads(row[0]) for row in rows]

    def get(self, task_id):
        with closing(sqlite3.connect(self.database)) as db:
            row = db.execute('SELECT body FROM tasks WHERE id=?', (task_id,)).fetchone()
        if not row:
            raise KeyError('任务不存在')
        return json.loads(row[0])

    def create(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('任务格式不正确')
        goal, agent, client_id = payload.get('goal'), payload.get('agent'), payload.get('client_id')
        attachments = payload.get('attachments', [])
        mode = payload.get('mode', 'task')
        if mode not in ('task', 'review'):
            raise ValueError('任务模式无效')
        if not isinstance(goal, str) or not goal.strip() or len(goal) > 20000:
            raise ValueError('请填写任务目标，最多 20000 字')
        if not isinstance(agent, str) or agent not in RUNNERS:
            raise ValueError('请选择可用的 Agent')
        if agent=='codex-deepseek-code' and (mode!='task' or attachments or len(goal)>8000):
            raise ValueError('代码协作仅支持8000字以内的新项目目标，不接收附件或已有目录。')
        if agent=='deepseek-flash' and mode!='task':
            raise ValueError('Flash首版仅支持普通新任务。')
        options={}
        if agent=='codex-deepseek-code':
            kind=payload.get('project_kind','web');reference=payload.get('reference_url','')
            if kind not in ('web','local-tool') or not isinstance(reference,str) or len(reference)>2048 or (kind!='web' and reference):raise ValueError('请选择网页设计或电脑本地工具；参考网站仅用于网页设计。')
            if reference:
                from urllib.parse import urlsplit
                parsed=urlsplit(reference)
                if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):raise ValueError('参考网站需要公开HTTPS地址。')
            options={'project_kind':kind,'reference_url':reference}
        if not isinstance(client_id, str) or not 1 <= len(client_id) <= 100:
            raise ValueError('任务请求编号无效')
        if not isinstance(attachments, list) or len(attachments) > 10:
            raise ValueError('每个任务最多 10 个附件')
        for name in attachments:
            if not isinstance(name, str) or Path(name).name != name or '/' in name or '\\' in name:
                raise ValueError('附件名称无效')
            source = self.uploads / name
            if not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(self.uploads.resolve()):
                raise ValueError('附件不存在，请重新上传')
        with self.lock, closing(sqlite3.connect(self.database)) as db, db:
            row = db.execute('SELECT body FROM tasks WHERE client_id=?', (client_id,)).fetchone()
            if row:
                previous = json.loads(row[0])
                if any(previous[key] != value for key, value in [('goal', goal), ('agent', agent), ('attachments', attachments)]) or previous.get('mode', 'task') != mode or any(previous.get(k,'web' if k=='project_kind' else '')!=v for k,v in options.items()):
                    raise ValueError('任务请求冲突，请重新提交')
                return previous
            route=None
            if agent=='codex-deepseek-code':
                from coding_plan import coding_route,stages_for
                route=coding_route({'goal':goal,**options})
            task_id = secrets.token_hex(16)
            workspace = self.workspace(task_id,agent)
            workspace.mkdir(parents=True)
            (workspace / 'inputs').mkdir()
            if agent=='codex-deepseek-code':(self.data/task_id).mkdir(parents=True,exist_ok=True)
            for name in attachments:
                shutil.copy2(self.uploads / name, workspace / 'inputs' / name)
            now = time.time()
            task = {'id': task_id, 'number': time.strftime('T-%m%d-') + task_id[:6].upper(), 'goal': goal,
                    'title': goal.strip().splitlines()[0][:70], 'agent': agent, 'mode': mode, 'status': 'queued',
                    'created': now, 'updated': now, 'attachments': attachments, 'completed_parts': [],
                    'artifacts': [], 'result': '', 'error': '', 'remote_session': ''}
            if agent=='codex-deepseek-code':
                task.update(request_id=client_id,code_stage='queued',code_sessions={},code_route=route,code_plan=list(stages_for(route)),**options)
            db.execute('INSERT INTO tasks VALUES(?,?,?)', (task_id, client_id, json.dumps(task, ensure_ascii=False)))
        self.queue.put(task_id)
        return task

    def update(self, task_id, **changes):
        with self.lock, closing(sqlite3.connect(self.database)) as db, db:
            row = db.execute('SELECT body FROM tasks WHERE id=?', (task_id,)).fetchone()
            if not row:
                raise KeyError('任务不存在')
            task = json.loads(row[0])
            if task['status'] in TERMINAL and 'status' in changes and changes['status'] != task['status']:
                changes.pop('status')
            task.update(changes)
            task['updated'] = time.time()
            db.execute('UPDATE tasks SET body=? WHERE id=?', (json.dumps(task, ensure_ascii=False), task_id))
            return task

    def report(self, task_id, title, detail):
        with self.lock:
            task = self.get(task_id)
            if task['status'] in TERMINAL:
                return
            parts = task['completed_parts']
            if len(parts) < 200:
                parts.append({'title': title, 'detail': detail, 'time': time.time()})
            self.update(task_id, completed_parts=parts)
        self._collect_safely(task_id)

    def _collect_safely(self, task_id):
        try:
            self.collect_artifacts(task_id)
        except (OSError,ValueError):
            task = self.get(task_id)
            if ARTIFACT_WARNING not in task['error']:
                self.update(task_id, error=(task['error'] + '\n' + ARTIFACT_WARNING).strip())
        else:
            task = self.get(task_id)
            if ARTIFACT_WARNING in task['error']:
                self.update(task_id, error=task['error'].replace(ARTIFACT_WARNING, '').strip())

    def collect_artifacts(self, task_id):
        raw_workspace=self.workspace(task_id)
        from artifact_preview import safe_path
        safe_path(self.root,raw_workspace)
        workspace=raw_workspace.resolve()
        files = []
        excluded = {'inputs', 'node_modules', '__pycache__', 'vendor', 'venv'}
        def unreadable(error):
            raise error  # Preserve the last complete listing instead of silently clearing it.
        for directory, dirs, names in os.walk(workspace, topdown=True, followlinks=False, onerror=unreadable):
            dirs[:] = [name for name in dirs if name not in excluded and not name.startswith('.')
                       and not (Path(directory)/name).is_symlink() and not (Path(directory)/name).is_junction()
                       and (Path(directory)/name).resolve().is_relative_to(workspace)]
            for name in names:
                if name.startswith('.'):
                    continue
                path = Path(directory) / name
                if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(workspace):
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if path.is_file() and stat.st_size <= 100*1024*1024:
                    files.append({'path': path.relative_to(workspace).as_posix(), 'name': path.name, 'size': stat.st_size})
                if len(files) >= 200:
                    break
            if len(files) >= 200:
                break
        return self.update(task_id, artifacts=files)

    def artifact_path(self, task_id, name):
        task = self.get(task_id)
        if not isinstance(name, str) or name not in [item['path'] for item in task['artifacts']]:
            raise FileNotFoundError('成果不存在')
        workspace = self.workspace(task_id).resolve()
        raw=workspace/name
        from artifact_preview import safe_path
        safe_path(workspace,raw,file=True)
        path = raw.resolve()
        if not path.is_relative_to(workspace) or not path.is_file():
            raise ValueError('无效的成果路径')
        return path

    def cancel(self, task_id):
        with self.lock:
            task = self.get(task_id)
            if task['status'] not in TERMINAL:
                self.stop_events.setdefault(task_id, threading.Event()).set()
                return self.update(task_id, status='cancelled', error='任务已停止。此前生成的成果会保留。')
            return task

    def record_session(self,task_id,value):
        task=self.get(task_id)
        if task['agent']=='codex-deepseek-code':
            if not isinstance(value,dict):return
            if set(value)=={'code_stage'} and value['code_stage'] in ('backend','frontend','integration','completed'):
                return self.update(task_id,code_stage=value['code_stage'])
            if set(value)=={'code_sessions'} and isinstance(value['code_sessions'],dict) and all(k in ('backend','frontend','integration') and isinstance(v,str) and 0<len(v)<=160 for k,v in value['code_sessions'].items()):
                return self.update(task_id,code_sessions=value['code_sessions'])
            return
        return self.update(task_id,**({'provider_session':value} if task['agent']=='deepseek-flash' else {'remote_session':value}))

    def _work(self):
        while not self.closing.is_set():
            try:
                task_id = self.queue.get(timeout=.2)
            except queue.Empty:
                continue
            try:
                with self.lock:
                    task = self.get(task_id)
                    if task['status'] != 'queued':
                        continue
                    stop = self.stop_events.setdefault(task_id, threading.Event())
                    self.update(task_id, status='running')
                try:
                    from file_review import capture_baseline
                    capture_baseline(self, task_id)
                    result = RUNNERS[task['agent']](task, self.workspace(task_id),
                        lambda title, detail: self.report(task_id, title, detail), stop,
                        lambda remote_id:self.record_session(task_id,remote_id))
                    self._collect_safely(task_id)
                    self.update(task_id, status='completed', result=result)
                except Cancelled:
                    self.update(task_id, status='cancelled', error='执行已停止，已有成果保留。')
                except NeedsAttention as e:
                    self.update(task_id, status='needs_attention', error=str(e))
                except Exception as e:
                    self.update(task_id, status='failed', error=f'执行失败：{str(e)[:2000]}')
                self._collect_safely(task_id)
            finally:
                self.queue.task_done()

    def close(self):
        self.closing.set()
        with self.lock:
            for stop in self.stop_events.values():
                stop.set()
        if self.worker:
            self.worker.join(timeout=15)
