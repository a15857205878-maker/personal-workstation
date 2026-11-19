"""Loopback-only, narrowly scoped access to the running desktop Bridge.

The SQLite receipt is committed BEFORE a mutation. Interrupted receipts are
deliberately never replayed: the caller must inspect the desktop before retrying.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from contextlib import contextmanager
import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import uuid

from center_remote import FIELDS as CENTER_FIELDS,READS as CENTER_READS,REQUIRED as CENTER_REQUIRED,validate_jobs as validate_center_jobs
MAX_BODY = 262144
MAX_UPLOAD_BODY = 14 * 1024 * 1024
MAX_FILE = 10 * 1024 * 1024
READS = {'room_status', 'catalog', 'list', 'collaboration_get', 'task_get', 'attachment_get', 'task_artifact', 'collaboration_artifact', 'pack_preview'}
FIELDS = {
    'room_status': set(), 'catalog': set(), 'list': set(),
    'collaboration_start': {'task', 'primary_id', 'reviewer_id', 'rounds', 'call_limit', 'max_tokens', 'persona', 'context_count', 'attachment_ids', 'output_format'},
    'collaboration_get': {'id'}, 'collaboration_stop': {'id'}, 'collaboration_note': {'id', 'text'},
    'task_create': {'task_type', 'role', 'instruction', 'materials', 'requirements', 'attachments'},
    'task_get': {'id'}, 'task_submit': {'id'}, 'task_cancel': {'id'},
    'task_note': {'id', 'text'}, 'task_complete': {'id'}, 'task_export_document': {'id'}, 'task_export_spreadsheet': {'id'},
    'attachment_import': {'name', 'content_base64', 'purpose'}, 'attachment_get': {'id'},
    'task_artifact': {'id', 'name'},
    'collaboration_artifact': {'id', 'name'},
    'pack_preview': set(), 'pack_start': {'preview_id'},
}
FIELDS.update(CENTER_FIELDS)
READS.update(CENTER_READS)
COLLAB_FIELDS = set('id title task status rounds planned_calls call_limit call_count max_tokens started updated deadline seconds_left steps notes error stage usage persona context_count output_format files artifact_preview'.split())
TASK_FIELDS = set('id title task_type role instruction materials requirements status result error created_at updated_at events archived mode files remote_notes'.split())
STEP_FIELDS = set('id seat model provider stage round state content error started completed at usage duration seconds'.split())


def clean(value):
    """Defense in depth for public text; never export raw profile/settings maps."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()
                if not re.search(r'key|secret|token$|password|base_url|path|folder|executable|credential', k, re.I)
                or k in ('prompt_tokens', 'completion_tokens', 'max_tokens', 'has_key', 'requires_key')}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r'(?i)\b(?:sk-|Bearer\s+)[A-Za-z0-9_.-]{8,}', '[redacted]', value)
        value = re.sub(r'(?i)\b[A-Z]:[\\/][^<>"\r\n|]+|\\\\[^<>"\r\n|]+', '[local path]', value)
        value = re.sub(r'(?<![\w:])/(?:Users|home|tmp|var|mnt|etc)/[^\s<>"\n]+', '[local path]', value)
        return value
    return value


class RemoteGateway:
    def __init__(self, bridge, data_dir, port=47633):
        self.bridge = bridge
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        key_file = self.data_dir / 'remote_gateway.key'
        try:
            with key_file.open('x', encoding='ascii') as stream:
                stream.write(secrets.token_urlsafe(48))
        except FileExistsError:
            pass
        self.key = key_file.read_text(encoding='ascii').strip()
        if len(self.key) < 32 or not self.key.isascii():
            raise ValueError('远程网关本机密钥无效')
        self.db_path = self.data_dir / 'remote_gateway.sqlite3'
        self.lock = threading.RLock()
        self.port = port
        self.server = None
        self.thread = None
        from remote_programs import RemotePrograms
        self.programs = RemotePrograms(bridge, self.data_dir)
        from desktop_assistant import DesktopAssistant
        self.assistant = DesktopAssistant(bridge)
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY,digest TEXT NOT NULL,response TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS owned(kind TEXT,id TEXT,PRIMARY KEY(kind,id))')
            db.execute('CREATE TABLE IF NOT EXISTS notes(id TEXT,text TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP)')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def start(self):
        if self.server:
            return self
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def _reply(self, status, value):
                body = json.dumps(value, ensure_ascii=False).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == '/assistant':
                    if not self._assistant_authorized():return
                    try:return self._reply(200,{'ok':True,'data':gateway.assistant.status()})
                    except Exception:return self._reply(503,{'ok':False,'error':'工作站状态暂不可读，请在电脑端检查。'})
                self._reply(200 if self.path == '/health' else 404,
                            {'ok': True, 'data': {'service': 'workbench-gateway', 'version': 1}} if self.path == '/health'
                            else {'ok': False, 'data': None, 'error': 'unknown_route'})

            def _assistant_authorized(self):
                if self.headers.get('Origin') or self.headers.get('Sec-Fetch-Site')=='cross-site' or not hmac.compare_digest(self.headers.get('X-Workbench-Key','').encode('utf-8'),gateway.key.encode('ascii')):
                    self._reply(401,{'ok':False,'error':'unauthorized'});return False
                return True

            def do_POST(self):
                self.connection.settimeout(10)
                if self.path not in ('/rpc','/assistant','/room-town'):
                    return self._reply(404, {'ok': False, 'data': None, 'error': 'unknown_route'})
                if self.path in ('/assistant','/room-town') and not self._assistant_authorized():return
                # Reject browser cross-origin requests even if a local key leaks into a page.
                if self.headers.get('Origin') or not hmac.compare_digest(self.headers.get('X-Workbench-Key', '').encode('utf-8'), gateway.key.encode('ascii')):
                    return self._reply(401, {'ok': False, 'data': None, 'error': 'unauthorized'})
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 1 <= length <= (8192 if self.path=='/assistant' else MAX_UPLOAD_BODY) or self.headers.get('Transfer-Encoding'):
                        raise ValueError()
                    body = self.rfile.read(length)
                    if len(body) != length:
                        raise ValueError()
                    request = json.loads(body)
                except (ValueError, OSError, UnicodeError):
                    return self._reply(400, {'ok': False, 'data': None, 'error': 'invalid_request'})
                if self.path=='/room-town':
                    try:
                        from room_town import call_room_town
                        return self._reply(200,{'ok':True,'data':call_room_town(gateway.bridge,request)})
                    except ValueError as error:return self._reply(400,{'ok':False,'error':str(error)})
                    except Exception:return self._reply(503,{'ok':False,'error':'小镇请求未确认，请在电脑端检查。'})
                if self.path=='/assistant':
                    try:return self._reply(200,{'ok':True,'data':gateway.assistant.open(request)})
                    except ValueError as error:return self._reply(400,{'ok':False,'error':str(error)})
                    except Exception:return self._reply(503,{'ok':False,'error':'页面请求未确认，请在电脑端查看。'})
                self._reply(200, gateway.rpc(request))

        self.server = ThreadingHTTPServer(('127.0.0.1', self.port), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, name='workbench-remote-gateway', daemon=True)
        self.thread.start()
        return self

    def close(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=5)
            self.server = None

    def _call(self, action, payload):
        result = self.bridge.call(action, payload)
        if not result.get('ok'):
            # Desktop exceptions can contain provider URLs, executable paths, or credentials.
            raise ValueError('desktop_operation_failed')
        return result.get('data')

    def _owned(self, kind, identifier):
        if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{32}', identifier):
            raise ValueError('invalid_target')
        with self._db() as db:
            if not db.execute('SELECT 1 FROM owned WHERE kind=? AND id=?', (kind, identifier)).fetchone():
                raise ValueError('target_not_remote_owned')

    def _public(self, kind, data):
        fields = COLLAB_FIELDS if kind == 'collaboration' else TASK_FIELDS
        result = {k: v for k, v in data.items() if k in fields}
        if 'steps' in result:
            result['steps'] = [{k: v for k, v in step.items() if k in STEP_FIELDS} for step in result['steps']]
        if kind == 'task':
            with self._db() as db:
                result['remote_notes'] = [dict(text=t, at=at) for t, at in db.execute('SELECT text,created FROM notes WHERE id=? ORDER BY rowid', (data['id'],))]
            result['files'] = [{k: f[k] for k in ('name', 'size') if k in f} for f in data.get('files', [])]
        if kind=='collaboration':result['files']=[{k:f[k] for k in ('name','size','format') if k in f} for f in data.get('files',[])]
        return clean(result)

    def _dispatch(self, action, p):
        if action in CENTER_FIELDS:
            from center_remote import dispatch
            return clean(dispatch(self,action,p))
        if action == 'room_status':
            from mobile_room_status import public_room_status,read_public_pet_activity
            return public_room_status(self._call('workstation_butler_status', {}),pet_activity=read_public_pet_activity())
        if action == 'pack_preview':
            return clean(self.programs.preview())
        if action == 'pack_start':
            return clean(self.programs.start(p['preview_id']))
        if action in ('task_get', 'task_artifact') and self.programs.owns(p.get('id')):
            return clean(self.programs.get(p['id']) if action == 'task_get' else self.programs.artifact(p['id'], p['name']))
        if action == 'attachment_import':
            name = p.get('name', '')
            if not name or len(name) > 180 or name != Path(name).name or '/' in name or '\\' in name or ':' in name or re.search(r'[\x00-\x1f\x7f]', name) or name in ('.', '..'):
                raise ValueError('invalid_attachment_name')
            from task_station.attachment_worker import SUPPORTED
            if Path(name).suffix.lower() not in SUPPORTED:
                raise ValueError('unsupported_attachment_type')
            try:
                raw = base64.b64decode(p.get('content_base64', ''), validate=True)
            except (ValueError, TypeError):
                raise ValueError('invalid_attachment_encoding') from None
            if not raw or len(raw) > MAX_FILE:
                raise ValueError('attachment_size_limit')
            folder = self.data_dir / 'remote_uploads' / uuid.uuid4().hex
            folder.mkdir(parents=True)
            source = folder / name
            try:
                source.write_bytes(raw)
                if p.get('purpose')=='presentation':row=self.bridge.attachments.add(source,image_asset=True)
                else:row=self.bridge.attachments.add(source)
            finally:
                source.unlink(missing_ok=True)
                folder.rmdir()
            with self._db() as db:
                db.execute('INSERT INTO owned VALUES(?,?)', ('attachment', row['id']))
            return self._attachment_public(row)
        if action == 'attachment_get':
            self._owned('attachment', p.get('id'))
            row = self.bridge.attachments.bundle([p['id']])['items'][0]
            return self._attachment_public(row)
        if action == 'collaboration_artifact':
            self._owned('collaboration',p.get('id'))
            data=self._call('api_collaboration_file',p)
            raw=base64.b64decode(data['content_base64'],validate=True)
            if data.get('name')!=p['name'] or not 0<len(raw)<=MAX_FILE:raise ValueError('artifact_size_or_path_limit')
            return {'name':data['name'],'size':len(raw),'content_base64':data['content_base64']}
        if action == 'task_artifact':
            self._owned('task', p.get('id'))
            self._call('station_get', {'id': p['id']})
            name = p.get('name')
            # Service.file_path validates basename, extension-independent containment,
            # and rejects symlinks. Recheck resolved containment for junction ancestors.
            service = self.bridge._station.service
            path = service.file_path(p['id'], name)
            expected = service.data.resolve() / 'tasks' / p['id'] / 'results'
            if path.resolve().parent != expected or path.stat().st_size > MAX_FILE:
                raise ValueError('artifact_size_or_path_limit')
            raw = path.read_bytes()
            if len(raw) > MAX_FILE:
                raise ValueError('artifact_size_limit')
            return {'name': name, 'size': len(raw), 'content_base64': base64.b64encode(raw).decode('ascii')}
        if action == 'catalog':
            boot = self._call('api_bootstrap', {})
            profiles = [{k: row.get(k) for k in ('id', 'name', 'model', 'kind', 'has_key', 'requires_key')} for row in boot['profiles']]
            catalog = self._call('station_catalog', {})
            # Only public capability fields. Never transport adapter/settings objects.
            roles = {name: {k: row[k] for k in ('label', 'mode', 'can_run', 'detail') if k in row}
                     for name, row in catalog.get('roles', {}).items()}
            from collaboration_files import FORMATS
            return {'presentation_images':True,'delivery_formats':list(FORMATS),'profiles': profiles, 'limits': boot['limits'], 'task_catalog': clean({'version': catalog.get('version'), 'tasks': catalog.get('tasks', []), 'roles': roles})}
        if action == 'list':
            result = {'collaborations': [], 'tasks': [], 'receipts': []}
            with self._db() as db:
                rows = db.execute("SELECT kind,id FROM owned WHERE kind IN ('task','collaboration') ORDER BY rowid DESC LIMIT 200").fetchall()
                receipts = db.execute('SELECT id,response FROM receipts ORDER BY rowid DESC LIMIT 100').fetchall()
            for rid, response in receipts:
                receipt = {'request_id': rid, 'state': 'uncertain'}
                if response is not None:
                    response = json.loads(response)
                    receipt['state'] = ('confirmed' if response.get('ok') else
                                        'uncertain' if response.get('error') in ('desktop_operation_failed', 'operation_uncertain_inspect_desktop', 'gateway_operation_failed') else 'rejected')
                    if response.get('ok') and isinstance(response.get('data'), dict):
                        target_id = response['data'].get('id')
                        if isinstance(target_id, str) and re.fullmatch('[a-f0-9]{32}', target_id):
                            receipt['target_id'] = target_id
                result['receipts'].append(receipt)
            for kind, identifier in rows:
                if kind not in ('collaboration', 'task'):
                    continue
                try:
                    data = self._call('api_session' if kind == 'collaboration' else 'station_get', {'id': identifier})
                    public = self._public(kind, data)
                    # List is a summary, avoid repeatedly transporting full results.
                    result['collaborations' if kind == 'collaboration' else 'tasks'].append({k: public[k] for k in ('id', 'title', 'status', 'updated', 'updated_at', 'task_type', 'role', 'call_count', 'call_limit') if k in public})
                except ValueError:
                    continue
            result['tasks'].extend(clean(self.programs.summaries()))
            return result
        kind = 'collaboration' if action.startswith('collaboration_') else 'task'
        if action in ('collaboration_start', 'task_create'):
            ids = p.get('attachment_ids' if kind == 'collaboration' else 'attachments', [])
            for identifier in ids:
                self._owned('attachment', identifier)
            if kind == 'collaboration':
                p = {**p, 'persona': p.get('persona', 'conductor'), 'context_count': 0}
                p.pop('attachment_ids', None)
                if ids:
                    bundle = self.bridge.attachments.bundle(ids)
                    images=[row['id'] for row in bundle['items'] if row['kind']=='image_asset']
                    if images and p.get('output_format')!='pptx':raise ValueError('配图仅用于PPTX；请选择PPTX或移除配图')
                    if images:p['image_ids']=images
                    task = p.get('task', '') + ('\n\n' + bundle['text'] if bundle['text'] else '')
                    if len(task.strip()) > 8000:
                        raise ValueError('collaboration_materials_exceed_8000')
                    p['task'] = task
            data = self._call('api_start' if kind == 'collaboration' else 'station_create', p)
            identifier = data['id']
            with self._db() as db:
                db.execute('INSERT INTO owned VALUES(?,?)', (kind, identifier))
            return self._public(kind, data)
        self._owned(kind, p.get('id'))
        if action in ('collaboration_stop', 'collaboration_note'):
            auto = self.bridge._auto
            if auto is None:
                raise ValueError('target_not_active')
            engine = auto.engine
            # engine.start/_launch, stop, and note use this same RLock.
            with engine.lock:
                if not engine.run or engine.run['id'] != p['id'] or engine.run['status'] not in ('running', 'stopping'):
                    raise ValueError('target_not_active')
                if action == 'collaboration_note':
                    return clean(engine.note(p['text']))
                return self._public(kind, engine.stop())
        if action == 'task_note':
            # A station task prompt is immutable after submission. This is a durable
            # human annotation, not an implicit new model call or result overwrite.
            self._call('station_get', {'id': p['id']})
            with self._db() as db:
                if db.execute('SELECT count(*) FROM notes WHERE id=?', (p['id'],)).fetchone()[0] >= 100:
                    raise ValueError('note_limit')
                db.execute('INSERT INTO notes(id,text) VALUES(?,?)', (p['id'], p['text']))
            return self._public(kind, self._call('station_get', {'id': p['id']}))
        method = 'api_session' if kind == 'collaboration' else 'station_' + action[5:]
        return self._public(kind, self._call(method, p))

    @staticmethod
    def _attachment_public(row):
        return {**clean({k: row[k] for k in ('id', 'name', 'kind', 'size', 'sha256', 'characters', 'suffix') if k in row}), 'status': 'ready'}

    def rpc(self, request):
        try:
            if not isinstance(request, dict) or set(request) - {'action', 'payload', 'request_id'}:
                raise ValueError('invalid_request')
            action, p = request.get('action'), request.get('payload', {})
            if not isinstance(action, str) or action not in FIELDS:
                raise ValueError('unknown_action')
            if len(json.dumps(request, ensure_ascii=False).encode('utf-8')) > (MAX_UPLOAD_BODY if action == 'attachment_import' else MAX_BODY):
                raise ValueError('request_too_large')
            if not isinstance(p, dict) or set(p) - FIELDS[action]:
                raise ValueError('invalid_fields')
            required = ({'task', 'primary_id', 'reviewer_id'} if action == 'collaboration_start'
                        else {'task_type', 'role', 'instruction'} if action == 'task_create'
                        else {'name', 'content_base64'} if action == 'attachment_import'
                        else {'preview_id'} if action == 'pack_start'
                        else set() if action in ('room_status', 'catalog', 'list', 'pack_preview') else {'id'})
            if action in CENTER_REQUIRED:required=CENTER_REQUIRED[action]
            if action.endswith('_note'):
                required.add('text')
            if action in ('task_artifact','collaboration_artifact'):
                required.add('name')
            if required - set(p):
                raise ValueError('missing_fields')
            for field, value in p.items():
                if action in ('center_prepare','center_edit_plan') and field=='jobs':
                    validate_center_jobs(value)
                elif field in ('attachments', 'attachment_ids'):
                    if not isinstance(value, list) or len(value) > 5 or any(not isinstance(v, str) for v in value) or len(set(value)) != len(value):
                        raise ValueError('invalid_attachment_ids')
                elif field in ('rounds', 'call_limit', 'max_tokens', 'context_count','history_limit','plan_revision'):
                    if type(value) is not int:
                        raise ValueError('invalid_field_type')
                elif field=='archived':
                    if type(value) is not bool:raise ValueError('invalid_field_type')
                elif not isinstance(value, str):
                    raise ValueError('invalid_field_type')
                elif len(value) > (MAX_UPLOAD_BODY if field == 'content_base64' else 24000 if field in ('instruction', 'materials', 'requirements') else 8000 if field == 'task' else 8000 if field == 'text' and action in ('center_prepare','center_draft') else 4000 if field == 'text' and action=='center_send' else 1000 if field == 'text' else 200):
                    raise ValueError('field_too_large')
            if action=='center_get' and 'history_limit' in p and not 12<=p['history_limit']<=60:raise ValueError('invalid_history_limit')
            if action in CENTER_FIELDS:
                for field in ('id','run_id','turn_id','primary_id','reviewer_id','third_id'):
                    if field in p and (not isinstance(p[field],str) or not re.fullmatch('[a-f0-9]{32}',p[field])):raise ValueError('invalid_target')
            if 'purpose' in p and p['purpose']!='presentation':raise ValueError('invalid_attachment_purpose')
            if 'text' in p and not p['text'].strip():
                raise ValueError('empty_note')
            if action == 'collaboration_start' and (p.get('context_count', 0) != 0 or p.get('persona', 'conductor') not in ('conductor', 'qinghe', 'lele', 'jingshui')):
                raise ValueError('invalid_collaboration_options')
            if action=='collaboration_start' and p.get('output_format','text') not in ('text','docx','xlsx','pptx'):raise ValueError('invalid_delivery_format')
            if action in READS:
                with self.lock:
                    return {'ok': True, 'data': self._dispatch(action, p)}
            rid = request.get('request_id')
            if not isinstance(rid, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', rid):
                raise ValueError('request_id_required')
            digest = hashlib.sha256(json.dumps({'action': action, 'payload': p}, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
            with self.lock:
                with self._db() as db:
                    old = db.execute('SELECT digest,response FROM receipts WHERE id=?', (rid,)).fetchone()
                    if old:
                        if old[0] != digest:
                            raise ValueError('request_id_conflict')
                        if old[1] is None:
                            raise ValueError('request_pending_inspect_desktop')
                        return json.loads(old[1])
                    db.execute('INSERT INTO receipts VALUES(?,?,NULL)', (rid, digest))
                try:
                    result = {'ok': True, 'data': self._dispatch(action, p)}
                except ValueError as exc:
                    result = {'ok': False, 'data': None, 'error': str(exc)}
                except Exception:
                    # Leave durable pending receipt for uncertain side effects.
                    return {'ok': False, 'data': None, 'error': 'operation_uncertain_inspect_desktop'}
                result = clean(result)
                with self._db() as db:
                    db.execute('UPDATE receipts SET response=? WHERE id=?', (json.dumps(result, ensure_ascii=False), rid))
                return result
        except ValueError as exc:
            return {'ok': False, 'data': None, 'error': str(exc)}
        except Exception:
            return {'ok': False, 'data': None, 'error': 'gateway_operation_failed'}
