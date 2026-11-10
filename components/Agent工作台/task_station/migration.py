"""Idempotent local import; source records and files remain in place."""
from contextlib import closing
import json
from pathlib import Path
import re
import shutil
import sqlite3
import uuid


def import_station(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError('来源与目标目录必须不同')
    if not (source / 'tasks.sqlite3').is_file():
        return dict(imported=0, skipped=0, source_missing=True)
    moved = []
    with closing(sqlite3.connect(source / 'tasks.sqlite3', timeout=5)) as src:
        src.execute('BEGIN IMMEDIATE')
        rows = src.execute('SELECT id,status,archived,updated,payload FROM tasks').fetchall()
        if any(row[1] in ('排队中', '执行中') for row in rows):
            raise ValueError('原独立任务仍在执行，请先正常结束后再导入')
        destination.mkdir(parents=True, exist_ok=True)
        marker = destination / 'import-origin.json'
        origin = json.loads(marker.read_text(encoding='utf-8')) if marker.exists() else dict(source=str(source), ids=[])
        known = set(origin.get('ids', [])) if origin.get('source') == str(source) else set()
        with closing(sqlite3.connect(destination / 'tasks.sqlite3', timeout=5)) as dst:
            dst.execute('BEGIN IMMEDIATE')
            dst.execute('CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,status TEXT,archived INTEGER,updated TEXT,payload TEXT)')
            if dst.execute("SELECT count(*) FROM tasks WHERE status IN ('排队中','执行中')").fetchone()[0]:
                raise ValueError('融合任务正在执行，请空闲后再导入')
            added, skipped = [], 0
            try:
                for row in rows:
                    identifier = row[0]
                    if not re.fullmatch('[a-f0-9]{32}', identifier):
                        raise ValueError('来源含无效任务编号，未切换入口')
                    existing = dst.execute('SELECT payload FROM tasks WHERE id=?', (identifier,)).fetchone()
                    if existing:
                        if identifier not in known and json.loads(existing[0]) != json.loads(row[4]):
                            raise ValueError('发现同编号的不同任务，已保留两边数据并停止导入')
                        skipped += 1
                        continue
                    folder = source / 'tasks' / identifier
                    target = destination / 'tasks' / identifier
                    if target.exists():
                        raise ValueError('目标存在未登记的同名任务目录，未覆盖')
                    if folder.exists():
                        if folder.is_symlink() or any(p.is_symlink() for p in folder.rglob('*')):
                            raise ValueError('任务目录含链接文件，未自动复制')
                        temporary = destination / 'tasks' / ('.import-' + uuid.uuid4().hex)
                        temporary.parent.mkdir(exist_ok=True)
                        shutil.copytree(folder, temporary)
                        temporary.replace(target)
                        moved.append(target)
                    dst.execute('INSERT INTO tasks VALUES(?,?,?,?,?)', row)
                    added.append(identifier)
                dst.commit()
            except Exception:
                dst.rollback()
                # Keep incomplete copies for diagnosis rather than deleting unknown content.
                for path in moved:
                    path.resolve().relative_to(destination)
                    preserved = destination / 'incomplete-import'
                    preserved.mkdir(exist_ok=True)
                    path.replace(preserved / (path.name + '-' + uuid.uuid4().hex[:8]))
                raise
        for name in ('connections.json', 'templates.json'):
            target = destination / name
            if (source / name).is_file() and not target.exists():
                temporary = destination / ('.config-' + uuid.uuid4().hex + '.tmp')
                shutil.copy2(source / name, temporary)
                temporary.replace(target)
        origin = dict(source=str(source), ids=sorted(known | {r[0] for r in rows}), imported_last=len(added))
        temporary = marker.with_suffix('.tmp')
        temporary.write_text(json.dumps(origin, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(marker)
        return dict(imported=len(added), skipped=skipped)
