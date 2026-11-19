"""Isolated gateway contract tests. Never contact a real provider or desktop."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from remote_gateway import RemoteGateway
from task_station.attachments import AttachmentStore


class FakeEngine:
    def __init__(self):
        self.lock = threading.RLock()
        self.run = None
        self.stops = 0
        self.notes = []

    def stop(self):
        self.stops += 1
        self.run['status'] = 'stopping'
        return self.run.copy()

    def note(self, text):
        self.notes.append(text)
        return {'message': '已加入'}


class FakeBridge:
    def __init__(self, directory):
        self.calls = []
        self.runs = {}
        self.tasks = {}
        self._auto = types.SimpleNamespace(engine=FakeEngine())
        self.attachments = AttachmentStore(directory / 'attachments', extractor=lambda p: p.read_text())
        self._station = types.SimpleNamespace(service=types.SimpleNamespace(data=directory))
        self._station.service.file_path = self.file_path

    def file_path(self, identifier, name):
        if not isinstance(name, str) or Path(name).name != name or '/' in name or '\\' in name:
            raise ValueError('bad path')
        path = self._station.service.data / 'tasks' / identifier / 'results' / name
        if not path.is_file() or path.is_symlink():
            raise ValueError('missing file')
        return path

    def call(self, action, p):
        self.calls.append((action, p.copy()))
        if action == 'api_bootstrap':
            data = {'profiles': [{'id': 'p', 'name': 'local', 'model': 'fake', 'kind': 'codex_local', 'has_key': False, 'requires_key': False, 'base_url': 'https://private', 'encrypted_key': 'TOP_SECRET'}], 'limits': {'max_calls': 30}, 'sessions': [{'id': 'private'}]}
        elif action == 'station_catalog':
            data = {'tasks': [], 'roles': {}, 'version': 'test'}
        elif action in ('api_start', 'station_create'):
            kind = action == 'api_start'
            identifier = ('a' if kind else 'b') * 32
            data = {'id': identifier, 'title': 'test', 'status': 'running' if kind else '草稿', 'steps': [], 'result': '', 'roles': {'A': {'base_url': 'private', 'encrypted_key': 'TOP_SECRET'}}, 'folder': 'C:\\Users\\secret', **p}
            (self.runs if kind else self.tasks)[identifier] = data
            if kind:
                self._auto.engine.run = data
        elif action == 'api_session':
            data = self.runs[p['id']]
        elif action == 'station_get':
            data = self.tasks[p['id']]
        elif action == 'station_export_document':
            data = self.tasks[p['id']]
        elif action in ('station_submit', 'station_cancel', 'station_complete'):
            data = self.tasks[p['id']]
            data['status'] = action
        else:
            raise AssertionError(action)
        return {'ok': True, 'data': data}


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.bridge = FakeBridge(self.directory)
        self.gateway = RemoteGateway(self.bridge, self.directory, port=0)

    def tearDown(self):
        self.gateway.close()
        self.temp.cleanup()

    def rpc(self, action, p=None, rid=None):
        request = {'action': action, 'payload': p or {}}
        if rid is not None:
            request['request_id'] = rid
        return self.gateway.rpc(request)

    def create(self):
        return self.rpc('task_create', {'task_type': 'text', 'role': 'text_1', 'instruction': 'hello'}, 'task-1')['data']['id']

    def start(self):
        return self.rpc('collaboration_start', {'task': 'hello', 'primary_id': 'p', 'reviewer_id': 'p'}, 'collab-1')['data']['id']

    def test_export_document_is_owned_mutation_and_receipt_is_idempotent(self):
        identifier=self.create()
        self.assertEqual(self.rpc('task_export_document',{'id':identifier})['error'],'request_id_required')
        self.assertFalse(self.rpc('task_export_document',{'id':'c'*32},'foreign-export')['ok'])
        reply=self.rpc('task_export_document',{'id':identifier},'export-1')
        self.assertTrue(reply['ok'],reply)
        before=len(self.bridge.calls)
        self.assertEqual(self.rpc('task_export_document',{'id':identifier},'export-1'),reply)
        self.assertEqual(len(self.bridge.calls),before)

    def test_file_collaboration_format_and_owned_artifact(self):
        payload={'task':'预算','primary_id':'p','reviewer_id':'p','output_format':'xlsx'}
        started=self.rpc('collaboration_start',payload,'file-start');self.assertTrue(started['ok'],started)
        identifier=started['data']['id'];self.assertEqual(started['data']['output_format'],'xlsx')
        self.assertFalse(self.rpc('collaboration_start',{**payload,'output_format':'pptx'},'file-start')['ok'])
        self.assertFalse(self.rpc('collaboration_start',{**payload,'output_format':'exe'},'bad-format')['ok'])
        self.bridge.runs[identifier]['files']=[{'name':'test.xlsx','size':2,'sha256':'private'}]
        original=self.bridge.call
        def call(action,p):
            if action=='api_collaboration_file':return {'ok':True,'data':{'name':p['name'],'content_base64':base64.b64encode(b'PK').decode()}}
            return original(action,p)
        self.bridge.call=call
        response=self.rpc('collaboration_artifact',{'id':identifier,'name':'test.xlsx'});self.assertTrue(response['ok'],response)
        self.assertEqual(response['data']['size'],2)
        self.assertEqual(self.rpc('collaboration_artifact',{'id':'f'*32,'name':'test.xlsx'})['error'],'target_not_remote_owned')
        public=self.rpc('collaboration_get',{'id':identifier})['data'];self.assertEqual(public['files'],[{'name':'test.xlsx','size':2}])
        self.assertIn('xlsx',self.rpc('catalog')['data']['delivery_formats'])

    def test_catalog_public_profiles_and_no_local_history(self):
        result = self.rpc('catalog')
        self.assertTrue(result['ok'])
        self.assertEqual(set(result['data']['profiles'][0]), {'id', 'name', 'model', 'kind', 'has_key', 'requires_key'})
        self.assertNotIn('TOP_SECRET', json.dumps(result))
        self.assertEqual(self.rpc('list')['data'], {'collaborations': [], 'tasks': [], 'receipts': []})

    def test_desktop_failure_receipt_remains_uncertain_after_refresh(self):
        original = self.bridge.call
        def fail_start(action, payload):
            if action == 'api_start':
                return {'ok': False, 'error': 'unexpected interruption'}
            return original(action, payload)
        self.bridge.call = fail_start
        result = self.rpc('collaboration_start', {'task': 'hello', 'primary_id': 'p', 'reviewer_id': 'p'}, 'uncertain-start')
        self.assertFalse(result['ok'])
        receipts = self.rpc('list')['data']['receipts']
        self.assertEqual(receipts, [{'request_id': 'uncertain-start', 'state': 'uncertain'}])
        self.assertEqual(self.rpc('collaboration_start', {'task': 'hello', 'primary_id': 'p', 'reviewer_id': 'p'}, 'uncertain-start'), result)

    def test_mutation_requires_id_and_rejects_unknown_fields_and_actions(self):
        self.assertEqual(self.rpc('task_submit', {'id': 'b' * 32})['error'], 'request_id_required')
        self.assertEqual(self.rpc('task_create', {'api_key': 'secret'}, 'x')['error'], 'invalid_fields')
        self.assertEqual(self.rpc('api_profile_save', {}, 'x')['error'], 'unknown_action')
        self.assertEqual(self.rpc('collaboration_start', {'task': 'hello', 'primary_id': 'p', 'reviewer_id': 'p', 'context_count': 1}, 'x')['error'], 'invalid_collaboration_options')
        self.assertFalse(self.rpc('task_note', {'id': 'b' * 32, 'text': 'a' * 1001}, 'x')['ok'])
        self.assertFalse(self.rpc('task_submit', {'id': 123}, 'x')['ok'])
        self.assertEqual(self.bridge.calls, [])

    def test_durable_idempotency_and_conflict(self):
        identifier = self.create()
        request = {'action': 'task_submit', 'payload': {'id': identifier}, 'request_id': 'submit-1'}
        result = self.gateway.rpc(request)
        self.gateway = RemoteGateway(self.bridge, self.directory, port=0)
        self.assertEqual(self.gateway.rpc(request), result)
        self.assertEqual(len([a for a, _ in self.bridge.calls if a == 'station_submit']), 1)
        request['action'] = 'task_cancel'
        self.assertEqual(self.gateway.rpc(request)['error'], 'request_id_conflict')

    def test_concurrent_duplicate_only_runs_once(self):
        identifier = self.create()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.rpc('task_submit', {'id': identifier}, 'same'), range(8)))
        self.assertTrue(all(r == results[0] for r in results))
        self.assertEqual(len([a for a, _ in self.bridge.calls if a == 'station_submit']), 1)

    def test_pending_never_replayed_after_restart(self):
        payload = {'task_type': 'text', 'role': 'text_1', 'instruction': 'test'}
        request = {'action': 'task_create', 'payload': payload, 'request_id': 'pending'}
        digest = hashlib.sha256(json.dumps({'action': request['action'], 'payload': payload}, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        with self.gateway._db() as db:
            db.execute('INSERT INTO receipts VALUES(?,?,NULL)', ('pending', digest))
        self.gateway = RemoteGateway(self.bridge, self.directory, port=0)
        self.assertEqual(self.gateway.rpc(request)['error'], 'request_pending_inspect_desktop')
        self.assertEqual(self.bridge.calls, [])

    def test_foreign_targets_never_reach_bridge(self):
        for action in ('task_get', 'task_cancel', 'collaboration_get', 'collaboration_stop', 'collaboration_note'):
            p = {'id': 'c' * 32}
            if action.endswith('note'):
                p['text'] = 'hello'
            self.assertEqual(self.rpc(action, p, action)['error'], 'target_not_remote_owned')
        self.assertEqual(self.bridge.calls, [])

    def test_exact_active_collaboration_and_public_session(self):
        identifier = self.start()
        self.assertEqual(self.bridge.calls[-1][1]['context_count'], 0)
        self.assertEqual(self.bridge.calls[-1][1]['persona'], 'conductor')
        self.assertNotIn('roles', self.rpc('collaboration_get', {'id': identifier})['data'])
        self.assertTrue(self.rpc('collaboration_note', {'id': identifier, 'text': 'check'}, 'note')['ok'])
        self.bridge._auto.engine.run = {'id': 'c' * 32, 'status': 'running'}
        self.assertEqual(self.rpc('collaboration_stop', {'id': identifier}, 'stop')['error'], 'target_not_active')
        self.assertEqual(self.rpc('collaboration_note', {'id': identifier, 'text': 'check'}, 'note2')['error'], 'target_not_active')
        self.assertEqual(self.bridge._auto.engine.stops, 0)
        self.assertEqual(self.bridge._auto.engine.notes, ['check'])

    def test_task_annotations_do_not_overwrite_or_submit(self):
        identifier = self.create()
        result = self.rpc('task_note', {'id': identifier, 'text': 'follow up'}, 'note')
        self.assertEqual(result['data']['remote_notes'][0]['text'], 'follow up')
        self.assertEqual(result['data']['result'], '')
        self.assertNotIn('folder', result['data'])
        self.assertFalse(any(a == 'station_submit' for a, _ in self.bridge.calls))
        self.assertEqual(len(self.rpc('list')['data']['tasks']), 1)
        receipt = next(r for r in self.rpc('list')['data']['receipts'] if r['request_id'] == 'task-1')
        self.assertEqual(receipt, {'request_id': 'task-1', 'state': 'confirmed', 'target_id': identifier})

    def test_many_attachments_do_not_evict_tasks_from_list(self):
        identifier = self.create()
        with self.gateway._db() as db:
            db.executemany('INSERT INTO owned VALUES(?,?)', [('attachment', f'{n:032x}') for n in range(205)])
        self.assertEqual(self.rpc('list')['data']['tasks'][0]['id'], identifier)

    def test_public_text_redacts_paths_and_tokens(self):
        identifier = self.create()
        self.bridge.tasks[identifier]['result'] = 'file C:\\Users\\example\\private\\report.txt key sk-123456789secret'
        result = self.rpc('task_get', {'id': identifier})
        self.assertNotIn('private', json.dumps(result))
        self.assertNotIn('123456789secret', json.dumps(result))

    def test_upload_get_and_owned_attachments(self):
        p = {'name': 'notes.txt', 'content_base64': base64.b64encode(b'hello material').decode()}
        upload = self.rpc('attachment_import', p, 'upload')
        self.assertTrue(upload['ok'], upload)
        identifier = upload['data']['id']
        self.assertEqual(self.rpc('attachment_get', {'id': identifier})['data']['status'], 'ready')
        self.assertEqual(list((self.directory / 'remote_uploads').iterdir()), [])
        result = self.rpc('task_create', {'task_type': 'text', 'role': 'text_1', 'instruction': 'test', 'attachments': [identifier]}, 'task-upload')
        self.assertTrue(result['ok'])
        self.assertEqual(self.rpc('task_create', {'task_type': 'text', 'role': 'text_1', 'instruction': 'test', 'attachments': ['f' * 32]}, 'foreign-upload')['error'], 'target_not_remote_owned')
        self.assertFalse(self.rpc('attachment_import', {**p, 'name': '../bad.txt'}, 'bad')['ok'])
        self.assertFalse(self.rpc('attachment_import', {**p, 'content_base64': '!bad'}, 'bad2')['ok'])

    def test_collaboration_attachment_total_budget(self):
        upload = self.rpc('attachment_import', {'name': 'long.txt', 'content_base64': base64.b64encode(b'a' * 7900).decode()}, 'upload')
        result = self.rpc('collaboration_start', {'task': 'x' * 100, 'primary_id': 'p', 'reviewer_id': 'p', 'attachment_ids': [upload['data']['id']]}, 'collab-long')
        self.assertEqual(result['error'], 'collaboration_materials_exceed_8000')
        self.assertFalse(any(a == 'api_start' for a, _ in self.bridge.calls))

    def test_artifact_owned_name_and_limit(self):
        identifier = self.create()
        folder = self.directory / 'tasks' / identifier / 'results'
        folder.mkdir(parents=True)
        (folder / 'result.txt').write_bytes(b'output')
        result = self.rpc('task_artifact', {'id': identifier, 'name': 'result.txt'})
        self.assertEqual(base64.b64decode(result['data']['content_base64']), b'output')
        self.assertFalse(self.rpc('task_artifact', {'id': identifier, 'name': '../result.txt'})['ok'])
        with (folder / 'large.txt').open('wb') as stream:
            stream.truncate(10 * 1024 * 1024 + 1)
        self.assertFalse(self.rpc('task_artifact', {'id': identifier, 'name': 'large.txt'})['ok'])

    def test_loopback_http_auth_no_cors_health_and_stable_key(self):
        key = self.gateway.key
        self.assertGreaterEqual(len(key), 32)
        self.assertEqual(RemoteGateway(self.bridge, self.directory, port=0).key, key)
        self.gateway.start()
        self.assertEqual(self.gateway.server.server_address[0], '127.0.0.1')
        def request(method, path, body=None, headers=None):
            conn = http.client.HTTPConnection('127.0.0.1', self.gateway.port, timeout=3)
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            status, raw = response.status, response.read()
            conn.close()
            return status, raw
        self.assertNotIn(key.encode(), request('GET', '/health')[1])
        body = json.dumps({'action': 'catalog', 'payload': {}})
        self.assertEqual(request('POST', '/rpc', body)[0], 401)
        self.assertEqual(request('POST', '/rpc', body, {'X-Workbench-Key': key, 'Origin': 'https://evil.test'})[0], 401)
        status, raw = request('POST', '/rpc', body, {'X-Workbench-Key': key})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(raw)['ok'])
        self.assertEqual(request('POST', '/rpc', '{', {'X-Workbench-Key': key})[0], 400)

    def test_real_bridge_reuses_existing_engine_and_gate_with_fake_models(self):
        from backend import Bridge
        class Client:
            calls = 0
            def complete(self, profile, key, messages, max_tokens, cancel, on_chunk, deadline):
                self.calls += 1
                on_chunk('fake reply')
                return {'content': 'fake reply', 'model': 'fake', 'usage': {}, 'finish_reason': 'stop'}
        client = Client()
        bridge = Bridge(root=self.directory / 'room', data_dir=self.directory / 'real', api_client=client)
        gateway = RemoteGateway(bridge, self.directory / 'real', port=0)
        try:
            self.assertTrue(gateway.rpc({'action': 'catalog'})['ok'])
            existing = bridge._auto.engine
            profile = bridge._auto.profiles.save({'name': 'isolated fake', 'kind': 'codex_local', 'model': 'fake'})
            result = gateway.rpc({'action': 'collaboration_start', 'payload': {'task': 'isolated test', 'primary_id': profile['id'], 'reviewer_id': profile['id'], 'rounds': 1, 'call_limit': 3}, 'request_id': 'real-start'})
            self.assertTrue(result['ok'], result)
            deadline = time.monotonic() + 5
            while existing.busy() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertFalse(existing.busy())
            self.assertIs(bridge._auto.engine, existing)
            self.assertIs(existing.gate, bridge._command_lock)
            self.assertIs(bridge._station.service.execution_gate, bridge._command_lock)
            run = gateway.rpc({'action': 'collaboration_get', 'payload': {'id': result['data']['id']}})
            self.assertEqual(run['data']['status'], 'completed')
            self.assertEqual(client.calls, 3)
            class Adapter:
                def capabilities(self):
                    return {'text_1': {'mode': 'fake', 'can_run': True}}
                def run(self, role, prompt, cancel, chunk, folder):
                    chunk('station fake reply')
                    return 'station fake reply'
            bridge._station.service.adapter = Adapter()
            created = gateway.rpc({'action': 'task_create', 'payload': {'task_type': 'text', 'role': 'text_1', 'instruction': 'isolated task'}, 'request_id': 'real-task'})
            self.assertTrue(created['ok'], created)
            task_id = created['data']['id']
            self.assertTrue(gateway.rpc({'action': 'task_submit', 'payload': {'id': task_id}, 'request_id': 'real-submit'})['ok'])
            deadline = time.monotonic() + 5
            while bridge._station.service.jobs and time.monotonic() < deadline:
                time.sleep(.01)
            task = gateway.rpc({'action': 'task_get', 'payload': {'id': task_id}})
            self.assertEqual(task['data']['result'], 'station fake reply')
            self.assertTrue(gateway.rpc({'action': 'task_complete', 'payload': {'id': task_id}, 'request_id': 'real-complete'})['ok'])
        finally:
            gateway.close()
            bridge._stop_api()
            bridge.close_station()


if __name__ == '__main__':
    unittest.main()
