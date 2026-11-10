"""Small optional adapter copied into native apps. Missing hub never blocks startup."""
from pathlib import Path
import atexit
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error

_inbox_lock = threading.RLock()


def settings(base):
    config = Path(base) / 'app_link.json'
    if not config.is_file():
        raise ValueError('尚未配置应用联动入口。')
    value = json.loads(config.read_text(encoding='utf-8'))
    root = Path(value['hub_root'])
    if not root.is_absolute() or not (root / 'launcher.pyw').is_file():
        raise ValueError('应用联动目录已移动，请更新 app_link.json。')
    return root, value['app_id']


def open_hub(base):
    root, _ = settings(base)
    runtime = Path(sys.executable)
    if not runtime.is_file():
        runtime = Path(sys.executable)
    # No caller-controlled command, path or arguments are accepted through the UI bridge.
    subprocess.Popen([str(runtime), str(root / 'launcher.pyw')], cwd=root,
                     creationflags=0x00000008 | 0x00000200 if os.name == 'nt' else 0,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {'message': '已打开应用联动。'}


def _request(base, action, payload=None):
    root, _ = settings(base)
    if action not in ('pending', 'claim'):
        raise ValueError('不支持的联动操作。')
    registry = json.loads((root / 'registry.json').read_text(encoding='utf-8'))
    key = (root / 'data/access.key').read_text(encoding='ascii').strip()
    url = 'http://127.0.0.1:' + str(registry['port']) + '/api/' + action
    headers = {'X-App-Link-Key': key}
    data = None
    if payload is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=3) as response:
            result = json.load(response)
        if not result.get('ok'):
            raise ValueError(result.get('error', '联动操作失败。'))
        return result['data']
    except (OSError, urllib.error.URLError) as exc:
        raise ValueError('联动服务未就绪，请先打开“应用联动”后重试。') from exc


def received(base):
    path = Path(base) / 'data/app_link_inbox.json'
    if not path.exists():
        return []
    try:
        if path.stat().st_size > 40 * 1024 * 1024:
            raise ValueError('接收记录过大。')
        rows = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(rows, list) or any(not isinstance(t, dict) or not isinstance(t.get('id'), str) or not isinstance(t.get('text'), str) for t in rows):
            raise ValueError('接收记录格式无效。')
        return rows
    except (OSError, ValueError) as exc:
        raise ValueError('工作台联动收件箱无法读取，原文件已保留，请先修复。') from exc


def _write_received(base, rows):
    path = Path(base) / 'data/app_link_inbox.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


def _save_received(base, task, acknowledged=False):
    with _inbox_lock:
        rows = received(base)
        existing = next((t for t in rows if t['id'] == task['id']), None)
        if existing is not None:
            if acknowledged:
                existing['acknowledged'] = True
                _write_received(base, rows)
            return
        if len(rows) >= 1000:
            raise ValueError('联动收件箱已达 1000 条，请先归档已接收记录。')
        _write_received(base, [dict(task, received=True, acknowledged=acknowledged)] + rows)


def archive_received(base, identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}', identifier):
        raise ValueError('任务编号无效。')
    with _inbox_lock:
        rows = received(base)
        task = next((t for t in rows if t['id'] == identifier), None)
        if task is None:
            raise ValueError('接收记录不存在。')
        folder = Path(base) / 'data/app_link_archive'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (identifier + '.json')
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, path)
        _write_received(base, [t for t in rows if t['id'] != identifier])
    return {'id': identifier, 'archived': True}


def api(base, action, payload=None):
    if action == 'pending':
        saved = received(base)
        try:
            pending = _request(base, 'pending')
        except ValueError:
            if saved:
                return saved
            raise
        identifiers = {t['id'] for t in pending}
        return pending + [t for t in saved if t['id'] not in identifiers]
    if action == 'claim':
        identifier = (payload or {}).get('id')
        saved = next((t for t in received(base) if t['id'] == identifier), None)
        if saved is not None and saved.get('acknowledged'):
            return saved
        if saved is None:
            task = next((t for t in _request(base, 'pending') if t['id'] == identifier), None)
            if task is None:
                raise ValueError('任务已变化，请刷新收件箱。')
            # Commit a local durable copy before acknowledging the central queue.
            _save_received(base, task)
        try:
            result = _request(base, 'claim', {'id': identifier})
        except ValueError:
            # A durable local import remains useful offline or after central archival.
            return dict(next(t for t in received(base) if t['id'] == identifier), sync_pending=True)
        _save_received(base, result, acknowledged=True)
        return result
    if action == 'archive':
        return archive_received(base, (payload or {}).get('id'))
    raise ValueError('不支持的联动操作。')


def start_heartbeat(base):
    try:
        root, identifier = settings(base)
        if identifier not in ('tools', 'workbench', 'pet'):
            return
        folder = root / 'data/heartbeats'
        folder.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError, KeyError):
        return
    path = folder / (identifier + '-' + str(os.getpid()) + '.json')
    stop = threading.Event()
    def write():
        while not stop.is_set():
            try:
                temp = path.with_suffix('.tmp')
                temp.write_text(json.dumps({'app_id': identifier, 'pid': os.getpid(), 'time': time.time()}), encoding='utf-8')
                os.replace(temp, path)
            except OSError:
                pass
            stop.wait(5)
    def cleanup():
        stop.set()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    atexit.register(cleanup)
    threading.Thread(target=write, name='app-link-presence', daemon=True).start()
