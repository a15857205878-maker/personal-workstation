import base64
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from remote_gateway import RemoteGateway

class PackBridge:
    def __init__(self, root):
        self.root = root
        self.input = root / 'notes.txt'; self.input.write_text('isolated input')
        self.output = root / 'output'; self.output.mkdir()
        self.calls = []; self.starts = 0; self.jobs = {}; self.uncertain = False
    def call(self, action, payload):
        assert action == 'workstation_tool_call', action
        operation = payload['action']; p = payload['payload']; self.calls.append((operation, p))
        if operation == 'pack_previous':
            data = {'files': [{'path': str(self.input), 'name': self.input.name, 'exists': True}], 'output_dir': str(self.output)}
        elif operation == 'pack_start':
            self.starts += 1
            if self.uncertain: raise TimeoutError('private path')
            spec = importlib.util.spec_from_file_location('isolated_quickpack', Path(__file__).resolve().parents[2] / '个人工具中心' / 'quickpack.py')
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            result = module.create_zip(p['files'], p['output_dir'], lambda message: None)
            job = {'id': 'c' * 32, 'status': 'completed', 'result_path': str(result), 'error': ''}
            self.jobs[job['id']] = job; data = {'job': job}
        elif operation == 'job_status': data = {'job': self.jobs[p['id']]}
        else: raise AssertionError(operation)
        return {'ok': True, 'data': data}

class ProgramTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.bridge = PackBridge(self.root); self.gateway = RemoteGateway(self.bridge, self.root / 'data', port=0)
    def tearDown(self): self.tmp.cleanup()
    def rpc(self, action, p=None, rid=None):
        return self.gateway.rpc({'action': action, 'payload': p or {}, 'request_id': rid})
    def preview(self):
        result = self.rpc('pack_preview'); self.assertTrue(result['ok'], result); return result['data']
    def start(self, preview, rid='start'):
        result = self.rpc('pack_start', {'preview_id': preview['preview_id']}, rid); self.assertTrue(result['ok'], result); return result['data']
    def test_lazy_preview_public_snapshot_real_quickpack_download_and_idempotency(self):
        self.assertEqual(self.rpc('list')['data']['tasks'], []); self.assertEqual(self.bridge.calls, [])
        p = self.preview(); self.assertEqual(p['files'], [{'name': 'notes.txt', 'size': self.bridge.input.stat().st_size}])
        self.assertEqual(p['source'], '电脑上次选定文件'); self.assertNotIn(str(self.root), str(p))
        task = self.start(p); self.assertEqual(task['status'], '已完成'); self.assertEqual(task['task_type'], 'program_pack')
        self.assertEqual(task['role'], 'tools_pack'); self.assertEqual(task['mode'], 'program')
        self.assertEqual(self.start(p, 'other')['id'], task['id']); self.assertEqual(self.bridge.starts, 1)
        self.assertEqual(self.rpc('list')['data']['tasks'][0]['id'], task['id'])
        name = task['files'][0]['name']; artifact = self.rpc('task_artifact', {'id': task['id'], 'name': name})
        self.assertTrue(artifact['ok'], artifact); self.assertTrue(base64.b64decode(artifact['data']['content_base64']).startswith(b'PK'))
        self.assertFalse(self.rpc('task_artifact', {'id': task['id'], 'name': '../' + name})['ok'])
        self.assertFalse(self.rpc('task_cancel', {'id': task['id']}, 'cancel')['ok'])
        self.gateway = RemoteGateway(self.bridge, self.root / 'data', port=0)
        self.assertEqual(self.start(p, 'restart')['id'], task['id']); self.assertEqual(self.bridge.starts, 1)
        self.assertNotIn(str(self.root), str(self.rpc('task_get', {'id': task['id']})))
    def test_changed_expired_and_arbitrary_inputs_rejected(self):
        p = self.preview(); self.bridge.input.write_text('changed')
        self.assertEqual(self.rpc('pack_start', {'preview_id': p['preview_id']}, 'changed')['error'], 'pack_inputs_changed')
        p = self.preview()
        with closing(sqlite3.connect(self.root / 'data/remote_programs.sqlite3')) as db:
            db.execute('UPDATE previews SET expires=0'); db.commit()
        self.assertEqual(self.rpc('pack_start', {'preview_id': p['preview_id']}, 'expired')['error'], 'pack_preview_expired')
        self.assertEqual(self.rpc('pack_start', {'preview_id': p['preview_id'], 'files': ['arbitrary']}, 'bad')['error'], 'invalid_fields')
        self.assertEqual(self.rpc('pack_preview', {'id': 'a' * 32})['error'], 'invalid_fields')
        self.assertEqual(self.bridge.starts, 0)
    def test_uncertain_start_never_replays_for_new_rid_or_restart(self):
        p = self.preview(); self.bridge.uncertain = True
        task = self.start(p); self.assertEqual(task['status'], '需要检查')
        self.gateway = RemoteGateway(self.bridge, self.root / 'data', port=0)
        self.assertEqual(self.start(p, 'again')['id'], task['id']); self.assertEqual(self.bridge.starts, 1)
    def test_foreign_artifact_and_symlink_or_size_boundary(self):
        self.assertEqual(self.rpc('task_get', {'id': 'f' * 32})['error'], 'target_not_remote_owned')
        task = self.start(self.preview()); name = task['files'][0]['name']; output = self.bridge.output / name
        with output.open('wb') as stream: stream.truncate(10 * 1024 * 1024 + 1)
        self.assertFalse(self.rpc('task_artifact', {'id': task['id'], 'name': name})['ok'])

    def test_concurrent_preview_starts_and_request_replays_are_one_shot(self):
        p = self.preview()
        with ThreadPoolExecutor(max_workers=4) as pool:
            tasks = list(pool.map(lambda n: self.start(p, 'concurrent-' + str(n)), range(8)))
        self.assertEqual(len({t['id'] for t in tasks}), 1)
        self.assertEqual(self.bridge.starts, 1)
        first = self.rpc('pack_start', {'preview_id': p['preview_id']}, 'concurrent-0')
        self.assertTrue(first['ok']); self.assertEqual(self.bridge.starts, 1)

    def test_pending_is_durable_before_original_start_and_restart_never_launches_worker(self):
        original = self.bridge.call
        def pending(action, payload):
            if payload['action'] != 'pack_start': return original(action, payload)
            with closing(sqlite3.connect(self.root / 'data/remote_programs.sqlite3')) as db:
                row = db.execute('SELECT task_id FROM previews').fetchone()
                self.assertTrue(row[0])
                self.assertEqual(db.execute('SELECT count(*) FROM tasks').fetchone()[0], 1)
            return {'ok': True, 'data': {'job': {'id': 'd' * 32, 'status': 'queued'}}}
        self.bridge.call = pending
        task = self.start(self.preview()); self.assertEqual(task['status'], '排队中')
        before = list(self.bridge.calls)
        self.gateway = RemoteGateway(self.bridge, self.root / 'data', port=0)
        loaded = self.rpc('task_get', {'id': task['id']})['data']
        self.assertEqual(loaded['status'], '需要检查'); self.assertEqual(self.bridge.calls, before)

    def test_symlink_result_rejected_even_when_same_basename(self):
        task = self.start(self.preview()); name = task['files'][0]['name']; output = self.bridge.output / name
        foreign = self.root / 'foreign.zip'; foreign.write_bytes(output.read_bytes()); output.unlink()
        try: os.symlink(foreign, output)
        except OSError as error: self.skipTest('Symlink privilege unavailable: ' + str(error.winerror))
        self.assertFalse(self.rpc('task_artifact', {'id': task['id'], 'name': name})['ok'])

    def test_output_junction_ancestor_is_rejected(self):
        task = self.start(self.preview()); name = task['files'][0]['name']
        original = Path.lstat
        def with_junction(path, *args, **kwargs):
            if path == self.bridge.output:
                return SimpleNamespace(st_file_attributes=0x400, st_mode=original(path).st_mode)
            return original(path, *args, **kwargs)
        with patch.object(Path, 'lstat', with_junction):
            result = self.rpc('task_artifact', {'id': task['id'], 'name': name})
        self.assertFalse(result['ok']); self.assertEqual(result['error'], 'artifact_size_or_path_limit')

    def test_successful_zip_over_download_limit_stays_completed(self):
        self.bridge.input.write_bytes(os.urandom(11 * 1024 * 1024))
        task = self.start(self.preview())
        self.assertEqual(task['status'], '已完成')
        self.assertGreater(task['files'][0]['size'], 10 * 1024 * 1024)
        self.assertIn('10 MiB', task['result'])
        result = self.rpc('task_artifact', {'id': task['id'], 'name': task['files'][0]['name']})
        self.assertFalse(result['ok']); self.assertEqual(result['error'], 'artifact_size_limit')

    def test_oversize_inputs_reject_before_hashing_on_preview_and_start(self):
        p = self.preview()
        with self.bridge.input.open('wb') as stream:
            stream.truncate(256 * 1024 * 1024 + 1)
        with patch('remote_programs.fingerprint', side_effect=AssertionError('must reject before hash')) as digest:
            preview = self.rpc('pack_preview')
            start = self.rpc('pack_start', {'preview_id': p['preview_id']}, 'oversize')
        self.assertEqual(preview.get('error'), 'pack_inputs_too_large')
        self.assertEqual(start.get('error'), 'pack_inputs_too_large')
        digest.assert_not_called(); self.assertEqual(self.bridge.starts, 0)

if __name__ == '__main__': unittest.main()
