"""Paired remote surface for the desktop workbench's narrow loopback gateway."""
import base64
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.request

MAX_ATTACHMENT = 10 * 1024 * 1024
EXTENSIONS = {'.txt', '.md', '.csv', '.tsv', '.json', '.log', '.docx', '.pptx', '.xlsx', '.pdf', '.png', '.jpg', '.jpeg', '.bmp', '.webp'}
READS = {'room_status', 'catalog', 'list', 'collaboration_get', 'task_get', 'attachment_get', 'task_artifact', 'collaboration_artifact', 'app_list', 'pack_preview'}
FIELDS = {
    'room_status': set(), 'catalog': set(), 'list': set(), 'app_list': set(),
    'collaboration_start': {'task', 'primary_id', 'reviewer_id', 'rounds', 'call_limit', 'max_tokens', 'persona', 'context_count', 'attachment_ids', 'seat_styles', 'output_format'},
    'collaboration_get': {'id'}, 'collaboration_stop': {'id'}, 'collaboration_note': {'id', 'text'},
    'task_create': {'task_type', 'role', 'instruction', 'materials', 'requirements', 'attachments'},
    'task_get': {'id'}, 'task_submit': {'id'}, 'task_cancel': {'id'}, 'task_complete': {'id'}, 'task_export_document': {'id'}, 'task_export_spreadsheet': {'id'},
    'task_note': {'id', 'text'}, 'attachment_import': {'upload', 'purpose'}, 'attachment_get': {'id'},
    'task_artifact': {'id', 'name'}, 'collaboration_artifact':{'id','name'}, 'app_launch': {'id'},
    'pack_preview': set(), 'pack_start': {'preview_id'},
}
APPS = {'home': '个人主页', 'tools': '个人工具中心', 'workbench': 'Agent 工作台', 'pet': 'Agent 桌宠', 'dock': '快捷方式控制中心'}
ERRORS = {
    'invalid_delivery_format':'请选择文字、Word、Excel或PPTX交付。',
    'pack_preview_invalid': '打包预览无效，请重新读取电脑上次选定文件。',
    'pack_preview_expired': '打包预览已过期，请重新预览并确认。',
    'pack_inputs_changed': '电脑所选文件已变化或不可读取，请在电脑重新选择，再预览确认。',
    'pack_inputs_too_large': '手机打包首版最多支持合计 256 MiB 输入文件，请在电脑减少所选文件后重新预览；未开始打包。',
    'pack_no_previous_files': '电脑尚未选定打包文件，请先在电脑资料打包页面选择文件。',
    'pack_job_unavailable': '打包状态无法确认，请在电脑检查，未自动重复执行。',
    'gateway_unavailable_or_uncertain': '电脑工作台未连接或回执超时。请先打开工作台并刷新记录核对，未自动重复启动。',
    'desktop_operation_failed': '电脑工作台未完成操作，请检查是否忙碌、所选模型是否配置好，或材料是否超出上限。',
    'target_not_active': '这项协作当前未运行，未影响电脑上的其他任务。请刷新记录。',
    'target_not_remote_owned': '该记录不是从手机工作台创建的任务，无法远程操作。',
    'request_id_conflict': '同一请求编号对应了不同内容，请重新检查。',
    'request_pending_inspect_desktop': '电脑已收到请求，但回执未确定。请先检查电脑任务，未自动重复执行。',
    'operation_uncertain_inspect_desktop': '操作回执未确定，请先检查电脑已有任务，未自动重复执行。',
    'gateway_operation_failed': '电脑工作台暂时无法完成操作，请刷新状态后检查。',
    'collaboration_materials_exceed_8000': '协作任务加附件文字超过 8000 字，请精简材料后提交。',
    'invalid_attachment_ids': '附件编号无效，一次最多 5 个，请移除后重新添加。',
    'artifact_size_or_path_limit': '成果暂不可下载，或超过 10 MiB，请在电脑查看。',
    'artifact_size_limit': '压缩包已完成，但超过手机 10 MiB 下载上限，请在电脑查看。',
    'attachment_size_limit': '单个附件需为 1 字节至 10 MiB。',
    'note_limit': '该任务补充意见已达上限。',
}


def artifact_action(kind='task'):
    if kind not in ('task','collaboration'):raise ValueError('成果来源无效。')
    return 'collaboration_artifact' if kind=='collaboration' else 'task_artifact'


class WorkbenchProxy:
    def __init__(self, root, uploads, transport=None, hub_transport=None):
        self.root = Path(root)
        self.uploads = Path(uploads)
        self.transport = transport or self._gateway
        self.hub_transport = hub_transport or self._hub
        self.lock = threading.RLock()

    def _config(self):
        # This file is maintained locally, never accepted from the phone.
        return json.loads((self.root / 'workbench_link.json').read_text(encoding='utf-8'))

    @staticmethod
    def _send(url, key, header, payload=None, timeout=25):
        headers = {header: key}
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(url, data=body, headers=headers)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=timeout) as response:
                raw = response.read(16 * 1024 * 1024 + 1)
                if len(raw) > 16 * 1024 * 1024:
                    raise ValueError('返回内容过大，请在电脑上查看。')
                result = json.loads(raw)
                if not isinstance(result, dict) or type(result.get('ok')) is not bool:
                    raise ValueError('工作台返回格式不正确。')
                return result
        except urllib.error.HTTPError as exc:
            try:
                result = json.loads(exc.read(8192))
                if isinstance(result, dict) and isinstance(result.get('error'), str):
                    return {'ok': False, 'error': result['error'][:1000]}
            except (ValueError, OSError):
                pass
            return {'ok': False, 'error': '工作台请求未完成，请刷新状态后检查。'}

    def _gateway(self, action, payload, request_id):
        try:
            config = self._config()
            key = Path(config['gateway_key_file']).read_text(encoding='utf-8').strip()
            if not 32 <= len(key) <= 256:
                raise ValueError('invalid local key')
            return self._send('http://127.0.0.1:47633/rpc', key, 'X-Workbench-Key',
                              {'action': action, 'payload': payload, 'request_id': request_id}, timeout=55 if action == 'attachment_import' else 25)
        except (OSError, ValueError, KeyError, TimeoutError):
            return {'ok': False, 'error': 'gateway_unavailable_or_uncertain'}

    def _hub(self, action, payload):
        try:
            root = Path(self._config()['integration_root'])
            key = (root / 'data/access.key').read_text(encoding='utf-8').strip()
            return self._send('http://127.0.0.1:47631/api/' + action, key, 'X-App-Link-Key', payload)
        except (OSError, ValueError, KeyError, TimeoutError):
            return {'ok': False, 'error': '电脑应用联动服务未连接，请在电脑打开“应用联动”后重试。'}

    def call(self, action, payload=None, request_id=None):
        payload = {} if payload is None else payload
        if not isinstance(action, str) or action not in FIELDS or not isinstance(payload, dict) or set(payload) - FIELDS[action]:
            raise ValueError('不支持的工作台操作或参数。')
        if len(json.dumps(payload, ensure_ascii=False).encode()) > 256 * 1024:
            raise ValueError('提交内容过大。')
        if action not in READS and (not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', request_id)):
            raise ValueError('缺少有效请求编号，请刷新后重试。')
        if 'id' in payload and action != 'app_launch' and (not isinstance(payload['id'], str) or not re.fullmatch('[a-f0-9]{32}', payload['id'])):
            raise ValueError('无效的目标编号。')
        if action == 'pack_start' and (not isinstance(payload.get('preview_id'), str) or not re.fullmatch('[a-f0-9]{32}', payload['preview_id'])):
            raise ValueError('打包预览编号无效，请重新预览。')
        if action == 'app_list':
            return {'ok': True, 'data': {'apps': [{'id': k, 'name': v} for k, v in APPS.items() if k != 'home']}}
        if action == 'app_launch':
            if payload.get('id') not in APPS or payload['id'] == 'home':
                raise ValueError('只允许打开已登记的电脑应用。')
            return self._launch_once(payload, request_id)
        if action == 'attachment_import':
            name = payload.get('upload')
            original = name[13:] if isinstance(name, str) and re.match(r'^[a-f0-9]{12}-', name) else name
            if not self._filename(original) or Path(original).suffix.lower() not in EXTENSIONS:
                raise ValueError('附件名称或格式无效。')
            path = self.uploads / name
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(self.uploads.resolve()):
                raise ValueError('附件不存在，请重新上传。')
            if not 0 < path.stat().st_size <= MAX_ATTACHMENT:
                raise ValueError('每个工作台附件需为 1 字节至 10 MiB。')
            content = path.read_bytes()
            if len(content) > MAX_ATTACHMENT:
                raise ValueError('附件超过 10 MiB。')
            purpose=payload.get('purpose')
            if purpose is not None and purpose!='presentation':raise ValueError('附件用途无效。')
            payload = {'name': original, 'content_base64': base64.b64encode(content).decode('ascii')}
            if purpose:payload['purpose']=purpose
        if action in ('task_artifact','collaboration_artifact') and not self._filename(payload.get('name')):
            raise ValueError('成果文件名无效。')
        result = self.transport(action, payload, request_id)
        if not result.get('ok'):
            code = result.get('error', '')
            message = ('电脑网关尚不支持远程打包，请正常重开已更新的个人工作站与接收服务。'
                       if action in ('pack_preview', 'pack_start') and code == 'unknown_action' else
                       '小屋状态接口尚未载入，请在任务结束后正常重开个人工作站。' if action == 'room_status' and code == 'unknown_action' else
                       ERRORS.get(code, code if not re.fullmatch(r'[a-z_]+', code) else '工作台未接受此操作，请检查任务内容和所选目标。'))
            result = {**result, 'error_code': code, 'error': message}
        return result

    @staticmethod
    def _filename(name):
        return isinstance(name, str) and 0 < len(name) <= 180 and name not in ('.', '..') and not any(c in name for c in '/\\<>:"|?*') and not any(ord(c) < 32 for c in name)

    def _launch_once(self, payload, request_id):
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.lock, closing(sqlite3.connect(self.root / 'workbench_actions.sqlite3')) as db:
            db.execute('CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY,digest TEXT NOT NULL,result TEXT)')
            row = db.execute('SELECT digest,result FROM receipts WHERE id=?', (request_id,)).fetchone()
            if row:
                if row[0] != digest:
                    raise ValueError('请求编号已用于其他操作，请创建新请求。')
                return json.loads(row[1]) if row[1] else {'ok': False, 'error': '打开请求已接收，回执未确定。请检查电脑状态；未自动重复打开。'}
            db.execute('INSERT INTO receipts VALUES(?,?,NULL)', (request_id, digest))
            db.commit()
            result = self.hub_transport('launch', payload)
            db.execute('UPDATE receipts SET result=? WHERE id=?', (json.dumps(result, ensure_ascii=False), request_id))
            db.commit()
            return result
