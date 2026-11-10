import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
from workbench_proxy import WorkbenchProxy


class ProxyTests(unittest.TestCase):
    def test_room_status_is_fixed_read_only_and_explains_old_gateway(self):
        self.proxy.call('room_status')
        self.assertEqual(self.calls,[('room_status',{},None)])
        with self.assertRaises(ValueError):self.proxy.call('room_status',{'path':'private'})
        self.proxy.transport=lambda *args:{'ok':False,'error':'unknown_action'}
        result=self.proxy.call('room_status')
        self.assertEqual(result['error_code'],'unknown_action');self.assertIn('重开',result['error'])
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.uploads = self.root / 'uploads'
        self.uploads.mkdir()
        self.calls = []
        def transport(action, payload, request_id):
            self.calls.append((action, payload, request_id))
            return {'ok': True, 'data': {'id': 'a' * 32}}
        self.proxy = WorkbenchProxy(self.root, self.uploads, transport=transport)

    def tearDown(self):
        self.temp.cleanup()

    def test_read_does_not_execute_and_mutations_need_request_id(self):
        self.proxy.call('catalog', {})
        self.assertEqual(self.calls, [('catalog', {}, None)])
        with self.assertRaises(ValueError):
            self.proxy.call('collaboration_start', {'task': 'test'})
        self.assertEqual(len(self.calls), 1)

    def test_pack_preview_read_and_preview_only_start(self):
        self.proxy.call('pack_preview')
        self.assertEqual(self.calls[-1], ('pack_preview', {}, None))
        self.proxy.call('pack_start', {'preview_id': 'b' * 32}, 'pack-1')
        self.assertEqual(self.calls[-1], ('pack_start', {'preview_id': 'b' * 32}, 'pack-1'))
        for action, payload, rid in [('pack_start', {}, 'missing'), ('pack_start', {'preview_id': 'bad'}, 'invalid'),
                                     ('pack_start', {'preview_id': 'b' * 32}, None),
                                     ('pack_start', {'preview_id': 'b' * 32, 'files': ['arbitrary']}, 'paths'),
                                     ('pack_preview', {'output_dir': 'arbitrary'}, None)]:
            with self.subTest(action=action, payload=payload), self.assertRaises(ValueError):
                self.proxy.call(action, payload, rid)

    def test_old_gateway_explains_update_and_pack_errors_are_mapped(self):
        self.proxy.transport = lambda *args: {'ok': False, 'error': 'unknown_action'}
        result = self.proxy.call('pack_preview')
        self.assertEqual(result['error_code'], 'unknown_action')
        self.assertIn('重开', result['error'])
        self.proxy.transport = lambda *args: {'ok': False, 'error': 'pack_preview_expired'}
        self.assertIn('过期', self.proxy.call('pack_start', {'preview_id': 'b' * 32}, 'expired')['error'])
        self.proxy.transport = lambda *args: {'ok': False, 'error': 'pack_inputs_too_large'}
        self.assertIn('256 MiB', self.proxy.call('pack_preview')['error'])

    def test_no_generic_rpc_or_command_or_config_forwarding(self):
        for action, payload in [('api_profile_save', {}), ('app_launch', {'id': 'tools', 'command': 'cmd.exe'}), ('catalog', {'path': 'secret'}), ('attachment_import', {'content_base64': 'aaa'})]:
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.proxy.call(action, payload, 'request-1')
        self.assertEqual(self.calls, [])

    def test_uploaded_attachment_is_resolved_locally_and_encoded(self):
        (self.uploads / 'abc-notes.txt').write_bytes('资料'.encode())
        self.proxy.call('attachment_import', {'upload': 'abc-notes.txt'}, 'upload-1')
        action, payload, req = self.calls[-1]
        self.assertEqual(action, 'attachment_import')
        self.assertEqual(payload['name'], 'abc-notes.txt')
        self.assertEqual(base64.b64decode(payload['content_base64']), '资料'.encode())
        self.assertEqual(req, 'upload-1')
        for path in ('../notes.txt', 'sub/file.txt', 'x.exe', 'C:\\secret.txt'):
            with self.assertRaises(ValueError):
                self.proxy.call('attachment_import', {'upload': path}, 'upload-2')

    def test_presentation_image_purpose_preserved_without_arbitrary_paths(self):
        (self.uploads / 'photo.png').write_bytes(b'photo fixture')
        self.proxy.call('attachment_import', {'upload': 'photo.png','purpose':'presentation'}, 'photo-1')
        self.assertEqual(self.calls[-1][1]['purpose'],'presentation')
        with self.assertRaises(ValueError):
            self.proxy.call('attachment_import', {'upload':'photo.png','purpose':'execute'}, 'photo-invalid')

    def test_unavailable_gateway_has_actionable_message(self):
        proxy = WorkbenchProxy(self.root, self.uploads)
        result = proxy.call('catalog', {})
        self.assertFalse(result['ok'])
        self.assertIn('工作台', result['error'])
        self.assertNotIn(str(self.root), result['error'])
        self.assertEqual(result['error_code'], 'gateway_unavailable_or_uncertain')

    def test_accepted_request_with_lost_reply_keeps_uncertain_identity(self):
        key = self.root / 'local.key'
        key.write_text('a'*48)
        (self.root / 'workbench_link.json').write_text(json.dumps({'gateway_key_file': str(key)}))
        proxy = WorkbenchProxy(self.root, self.uploads)
        with patch.object(proxy, '_send', side_effect=urllib.error.URLError('timed out after execution')):
            result = proxy.call('collaboration_start', {'task': 'test'}, 'same-request')
        self.assertFalse(result['ok'])
        self.assertEqual(result['error_code'], 'gateway_unavailable_or_uncertain')

    def test_original_180_character_upload_name_is_supported(self):
        original = 'n'*176 + '.txt'
        name = 'a'*12+'-'+original
        (self.uploads / name).write_text('notes')
        self.proxy.call('attachment_import', {'upload': name}, 'upload-long')
        self.assertEqual(self.calls[-1][1]['name'], original)

    def test_app_launch_only_known_id_with_persistent_replay(self):
        calls = []
        self.proxy.hub_transport = lambda action, payload: calls.append((action, payload)) or {'ok': True, 'data': {'message': '已请求打开'}}
        first = self.proxy.call('app_launch', {'id': 'workbench'}, 'launch-1')
        self.assertEqual(first, self.proxy.call('app_launch', {'id': 'workbench'}, 'launch-1'))
        self.assertEqual(len(calls), 1)
        with self.assertRaises(ValueError):
            self.proxy.call('app_launch', {'id': 'pet'}, 'launch-1')
        with self.assertRaises(ValueError):
            self.proxy.call('app_launch', {'id': 'arbitrary'}, 'launch-2')

    def test_artifact_uses_owned_gateway_and_validates_download_name(self):
        with self.assertRaises(ValueError):
            self.proxy.call('task_artifact', {'id': 'a'*32, 'name': '../secrets'}, None)
        self.proxy.call('task_artifact', {'id': 'a'*32, 'name': 'result.txt'})
        self.assertEqual(self.calls[-1][0], 'task_artifact')


if __name__ == '__main__':
    unittest.main()
