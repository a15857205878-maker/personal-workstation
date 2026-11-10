"""Phone-owned packing receipts; execution remains in the original tool worker.

Private input snapshots never leave this store. A durable task consumes a preview
before contacting the worker, including when the worker acknowledgement is lost.
"""
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid

MAX_FILE = 10 * 1024 * 1024
MAX_INPUT = 256 * 1024 * 1024
SOURCE = '电脑上次选定文件'
STATUSES = {'queued': '排队中', 'running': '执行中', 'completed': '已完成', 'failed': '失败'}


def plain_path(path):
    """Reject symlinks and Windows junction/reparse ancestors before resolving."""
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            if part.is_symlink() or getattr(part.lstat(), 'st_file_attributes', 0) & 0x400:
                raise ValueError('artifact_size_or_path_limit')
    return path.resolve()


def fingerprint(value, max_bytes=MAX_INPUT):
    path = plain_path(value)
    if not path.is_file():
        raise ValueError('pack_inputs_changed')
    stat = path.stat()
    if stat.st_size > max_bytes:
        raise ValueError('pack_inputs_too_large')
    digest = hashlib.sha256()
    read = 0
    with path.open('rb') as stream:
        while True:
            # Read at most the declared file length plus one byte, even if a
            # concurrently growing file never reaches EOF.
            chunk = stream.read(min(1024 * 1024, stat.st_size - read + 1))
            if not chunk:
                break
            read += len(chunk)
            if read > max_bytes:
                raise ValueError('pack_inputs_too_large')
            if read > stat.st_size:
                raise ValueError('pack_inputs_changed')
            digest.update(chunk)
    after = path.stat()
    if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('pack_inputs_changed')
    return {'path': str(path), 'name': path.name, 'size': stat.st_size,
            'mtime': stat.st_mtime_ns, 'inode': stat.st_ino, 'sha256': digest.hexdigest()}


def fingerprints(files):
    # Stat every input before opening any file for hashing. This applies both to
    # preview and confirmation; selections are never silently truncated.
    paths = [plain_path(f['path']) for f in files]
    if any(not path.is_file() for path in paths):
        raise ValueError('pack_inputs_changed')
    if sum(path.stat().st_size for path in paths) > MAX_INPUT:
        raise ValueError('pack_inputs_too_large')
    result = []
    remaining = MAX_INPUT
    for path in paths:
        item = fingerprint(path, max_bytes=remaining)
        result.append(item)
        remaining -= item['size']
    return result


class RemotePrograms:
    def __init__(self, bridge, data_dir):
        self.bridge = bridge
        self.database = Path(data_dir) / 'remote_programs.sqlite3'
        self.live_jobs = set()
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS previews(id TEXT PRIMARY KEY, expires REAL, snapshot TEXT, task_id TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, record TEXT, private TEXT)')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.database, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def tool(self, action, payload):
        value = self.bridge.call('workstation_tool_call', {'action': action, 'payload': payload})
        if not isinstance(value, dict) or not value.get('ok') or not isinstance(value.get('data'), dict):
            raise ValueError('desktop_operation_failed')
        return value['data']

    def preview(self):
        previous = self.tool('pack_previous', {})
        files = previous.get('files')
        if not isinstance(files, list) or not 1 <= len(files) <= 500:
            raise ValueError('pack_no_previous_files')
        try:
            snapshot = {'files': fingerprints(files),
                        'output': str(plain_path(previous['output_dir']))}
        except ValueError as error:
            if str(error) == 'pack_inputs_too_large':
                raise
            raise ValueError('pack_inputs_changed') from None
        except (OSError, KeyError, TypeError):
            raise ValueError('pack_inputs_changed') from None
        identifier = uuid.uuid4().hex
        expires = time.time() + 900
        with self.db() as db:
            db.execute('INSERT INTO previews VALUES(?,?,?,NULL)', (identifier, expires, json.dumps(snapshot)))
        public = [{k: f[k] for k in ('name', 'size')} for f in snapshot['files']]
        return {'preview_id': identifier, 'files': public, 'count': len(public),
                'total_size': sum(f['size'] for f in public), 'source': SOURCE, 'expires_at': expires}

    def owns(self, identifier):
        with self.db() as db:
            return db.execute('SELECT 1 FROM tasks WHERE id=?', (identifier,)).fetchone() is not None

    def save(self, task, private):
        with self.db() as db:
            db.execute('UPDATE tasks SET record=?,private=? WHERE id=?', (json.dumps(task, ensure_ascii=False), json.dumps(private), task['id']))

    def start(self, identifier):
        with self.db() as db:
            row = db.execute('SELECT expires,snapshot,task_id FROM previews WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise ValueError('pack_preview_invalid')
        if row[2]:
            return self.get(row[2])
        if time.time() > row[0]:
            raise ValueError('pack_preview_expired')
        snapshot = json.loads(row[1])
        try:
            if fingerprints(snapshot['files']) != snapshot['files'] or str(plain_path(snapshot['output'])) != snapshot['output']:
                raise ValueError()
        except ValueError as error:
            if str(error) == 'pack_inputs_too_large':
                raise
            raise ValueError('pack_inputs_changed') from None
        except OSError:
            raise ValueError('pack_inputs_changed') from None
        now = datetime.now(timezone.utc).isoformat()
        task = {'id': uuid.uuid4().hex, 'title': '文件打包', 'instruction': '打包电脑上次选定文件',
                'task_type': 'program_pack', 'role': 'tools_pack', 'mode': 'program',
                'status': '需要检查', 'result': '', 'error': '打包启动回执尚未确认，请在电脑检查；未自动重发。',
                'files': [], 'created_at': now, 'updated_at': now, 'events': []}
        private = {'output': snapshot['output'], 'job_id': None, 'result_path': ''}
        # Atomic one-shot consumption and durable pending before the original start.
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT task_id FROM previews WHERE id=?', (identifier,)).fetchone()[0]
            if not old:
                db.execute('INSERT INTO tasks VALUES(?,?,?)', (task['id'], json.dumps(task, ensure_ascii=False), json.dumps(private)))
                db.execute('UPDATE previews SET task_id=? WHERE id=?', (task['id'], identifier))
        if old:
            return self.get(old)
        try:
            job = self.tool('pack_start', {'files': [f['path'] for f in snapshot['files']], 'output_dir': snapshot['output']})['job']
            private['job_id'] = job['id']
            self.live_jobs.add(job['id'])
            self.update(task, private, job)
        except Exception:
            # Any uncertain outcome consumes the preview; never call start again.
            self.save(task, private)
        return task

    def update(self, task, private, job):
        if job.get('id') != private['job_id']:
            raise ValueError('pack_job_unavailable')
        status = job.get('status')
        task['status'] = STATUSES.get(status, '需要检查')
        task['error'] = ('打包未完成，请在电脑检查。' if status == 'failed' else
                         '工具回执未确定，请在电脑检查；未自动重发。' if status not in STATUSES else '')
        if status == 'completed':
            private['result_path'] = job.get('result_path', '')
            try:
                path = self.result_path(private)
                task['files'] = [{'name': path.name, 'size': path.stat().st_size}]
                task['result'] = '压缩包已生成并校验：' + path.name
                if path.stat().st_size > MAX_FILE:
                    task['result'] += '（超过手机 10 MiB 下载上限，请在电脑查看。）'
            except (OSError, ValueError):
                task.update(status='需要检查', error='压缩包位置无法验证，请在电脑检查。', files=[], result='')
        task['updated_at'] = datetime.now(timezone.utc).isoformat()
        self.save(task, private)

    def get(self, identifier):
        with self.db() as db:
            row = db.execute('SELECT record,private FROM tasks WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise ValueError('target_not_remote_owned')
        task, private = map(json.loads, row)
        if task['status'] in ('排队中', '执行中'):
            try:
                # A restarted gateway never launches a new worker to recover old jobs.
                if private['job_id'] not in self.live_jobs:
                    raise ValueError('pack_job_unavailable')
                job = self.tool('job_status', {'id': private['job_id']})['job']
                self.update(task, private, job)
            except Exception:
                task.update(status='需要检查', error='工具任务状态无法确认，请在电脑检查；未自动重发。')
                self.save(task, private)
        return task

    def summaries(self):
        with self.db() as db:
            ids = [row[0] for row in db.execute('SELECT id FROM tasks ORDER BY rowid DESC LIMIT 200')]
        return [{k: v for k, v in self.get(identifier).items() if k in
                 ('id', 'title', 'status', 'updated_at', 'task_type', 'role', 'mode')} for identifier in ids]

    @staticmethod
    def result_path(private):
        if not private.get('result_path'):
            raise ValueError('artifact_size_or_path_limit')
        path = plain_path(private['result_path'])
        output = plain_path(private['output'])
        if path.parent != output or str(output) != private['output'] or path.suffix.lower() != '.zip' or not path.is_file():
            raise ValueError('artifact_size_or_path_limit')
        return path

    def artifact(self, identifier, name):
        task = self.get(identifier)
        if task['status'] != '已完成' or not isinstance(name, str) or not task['files'] or name != task['files'][0]['name'] or Path(name).name != name or any(c in name for c in '/\\:'):
            raise ValueError('artifact_size_or_path_limit')
        with self.db() as db:
            private = json.loads(db.execute('SELECT private FROM tasks WHERE id=?', (identifier,)).fetchone()[0])
        path = self.result_path(private)
        if path.name != name:
            raise ValueError('artifact_size_or_path_limit')
        if path.stat().st_size > MAX_FILE:
            raise ValueError('artifact_size_limit')
        with path.open('rb') as stream:
            raw = stream.read(MAX_FILE + 1)
        if len(raw) > MAX_FILE:
            raise ValueError('artifact_size_limit')
        return {'name': name, 'size': len(raw), 'content_base64': base64.b64encode(raw).decode('ascii')}
