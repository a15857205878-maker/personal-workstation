import http.client
import json
import os
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path
from urllib.parse import quote

from transfer import create_server


class TransferTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'photos'
        self.server = create_server('127.0.0.1', 0, self.root, 'test-secret')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, method, path, data=None, headers=None):
        c = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        c.request(method, path, body=data, headers=headers or {})
        r = c.getresponse()
        result = r.status, r.read()
        c.close()
        return result

    def test_auth_required(self):
        self.assertEqual(self.request('GET', '/api/files')[0], 403)
        self.assertEqual(self.request('POST', '/api/upload?name=x.png', b'x')[0], 403)

    def test_persistent_link_survives_server_restart_and_reset_revokes_it(self):
        from pairing import load_token, save_token
        path = Path(self.tmp.name) / 'pairing.json'
        original = load_token(path)
        for reset in (False, False, True):
            if reset:
                save_token(path, 'Z' * 32)
            server = create_server('127.0.0.1', 0, Path(self.tmp.name) / 'isolated' / 'photos', load_token(path))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection(*server.server_address, timeout=5)
                connection.request('GET', '/api/files?token=' + original)
                response = connection.getresponse()
                self.assertEqual(response.status, 403 if reset else 200)
                response.read()
                connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_tailscale_address_can_appear_after_receiver_started(self):
        from unittest.mock import Mock
        network=self.server.network_access
        network.probe=Mock(return_value={'state':'connected','provider':'tailscale','ipv4':['100.90.1.2'],'message':'已连接'})
        network.cached=None
        code,body=self.request('GET','/api/info?token=test-secret')
        self.assertEqual(code,200)
        info=json.loads(body)
        remote='http://100.90.1.2:'+str(self.server.server_port)+'/?token=test-secret'
        self.assertIn(remote,info['urls'])
        self.assertEqual(info['remote_access']['state'],'connected')
        index=info['urls'].index(remote)
        self.assertEqual(self.request('GET','/qr.svg?token=test-secret&index='+str(index))[0],200)
        network.probe=Mock(return_value={'state':'needs_approval','provider':'tailscale','ipv4':[],'message':'等待批准'})
        network.expires=0
        info=json.loads(self.request('GET','/api/info?token=test-secret')[1])
        self.assertNotIn(remote,info['urls'])

    def test_qr_expired_remote_address_is_not_silently_replaced(self):
        remote='http://100.90.1.2:'+str(self.server.server_port)+'/?token=test-secret'
        self.server.network_access.probe=lambda:{'state':'connected','provider':'tailscale','ipv4':['100.91.1.3'],'message':'已连接'}
        self.server.network_access.cached=None
        code,body=self.request('GET','/qr.svg?token=test-secret&index=1&address='+quote(remote,safe=''))
        self.assertEqual(code,410,body[:100])

    def test_qr_uses_a_single_local_address_snapshot(self):
        address='http://100.90.1.2:'+str(self.server.server_port)+'/?token=test-secret'
        def refresh():
            self.server.urls=[]
            return {'urls':[address]}
        with patch.object(self.server,'refresh_network',side_effect=refresh):
            self.assertEqual(self.request('GET','/qr.svg?token=test-secret&address='+quote(address,safe=''))[0],200)

    def test_second_receiver_cannot_modify_live_task_before_owner_check(self):
        self.server.tasks.close()
        task=self.server.tasks.create({'goal':'in flight','agent':'demo','client_id':'live-task'})
        self.server.tasks.update(task['id'],status='running')
        with self.assertRaises(RuntimeError):
            create_server('127.0.0.1',0,self.root,'second-secret')
        self.assertEqual(self.server.tasks.get(task['id'])['status'],'running')

    def test_failed_initialization_does_not_start_queued_execution(self):
        import time
        from tasks import TaskManager
        from unittest.mock import Mock
        directory=Path(self.tmp.name)/'other'
        directory.mkdir()
        manager=TaskManager(directory,start_worker=False)
        manager.create({'goal':'must stay queued','agent':'demo','client_id':'not-yet'})
        manager.close()
        runner=Mock(return_value='should not run')
        def fail(*args,**kwargs):
            time.sleep(.2)
            raise RuntimeError('initialization failed')
        with patch('tasks.RUNNERS',{'demo':runner}),patch('transfer.BotCore',side_effect=fail):
            with self.assertRaises(RuntimeError):
                create_server('127.0.0.1',0,directory/'photos','isolated')
        runner.assert_not_called()

    def test_history_read_and_direct_instruction_api(self):
        self.server.bot.replies.close()
        reader = self.server.bot.reader
        with patch.object(reader, 'session_page', return_value={'sessions':[{'id':'old-thread','title':'历史任务'}],'next_offset':None}) as listed:
            code, body = self.request('GET','/api/bot/history/sessions?token=test-secret&q=test&offset=20')
            self.assertEqual(code,200,body)
            listed.assert_called_once_with(limit=20,offset=20,search='test')
        with patch.object(reader, 'history', return_value={'id':'old-thread','messages':[],'next_before':None}) as history:
            self.assertEqual(self.request('GET','/api/bot/history?token=test-secret&thread_id=old-thread&before=12')[0],200)
            history.assert_called_once_with('old-thread',before=12)
            self.assertEqual(self.request('GET','/api/bot/history?thread_id=old-thread')[0],403)
        payload=json.dumps({'source_id':'history-user','thread_id':'old-thread','text':'继续检查','request_id':'direct-one'}).encode()
        with patch.object(reader,'get',return_value={'id':'old-thread','title':'历史任务','cwd':str(self.root)}):
            code, body=self.request('POST','/api/bot/history/reply?token=test-secret',payload)
            self.assertEqual(code,200,body)
            job=json.loads(body)['job']
            self.assertEqual(job['thread_id'],'old-thread')
            self.assertEqual(job['status'],'queued')
            self.assertEqual(self.request('POST','/api/bot/history/reply',payload)[0],403)
            again=self.request('POST','/api/bot/history/reply?token=test-secret',payload)
            self.assertEqual(json.loads(again[1])['job']['id'],job['id'])

    def test_history_image_reply_and_source_scoped_snapshot_download(self):
        self.server.bot.replies.close()
        picture=b'\x89PNG\r\n\x1a\nimage-data'
        code,upload=self.request('POST','/api/task-upload?token=test-secret&name=picture.png',picture)
        self.assertEqual(code,201,upload)
        name=json.loads(upload)['name']
        payload=json.dumps({'source_id':'image-phone','request_id':'image-reply','thread_id':'old-thread','text':'','attachments':[name]}).encode()
        with patch.object(self.server.bot.reader,'get',return_value={'id':'old-thread','title':'history','cwd':str(self.root)}):
            code,body=self.request('POST','/api/bot/history/reply?token=test-secret',payload)
            self.assertEqual(code,200,body)
            job=json.loads(body)['job']
            self.assertEqual(job['thread_id'],'old-thread')
            self.assertEqual(job['attachments'],[name])
            self.assertTrue(job['text'])
            again=self.request('POST','/api/bot/history/reply?token=test-secret',payload)
            self.assertEqual(json.loads(again[1])['job']['id'],job['id'])
        route='/api/bot/reply-input/'+job['id']+'/'+quote(name)
        self.assertEqual(self.request('GET',route+'?source_id=image-phone')[0],403)
        self.assertEqual(self.request('GET',route+'?token=test-secret&source_id=other')[0],404)
        (self.server.tasks.uploads/name).unlink()
        code,download=self.request('GET',route+'?token=test-secret&source_id=image-phone')
        self.assertEqual(code,200,download)
        self.assertEqual(download,picture)
        self.assertEqual(self.request('GET',route.replace(quote(name),'missing.png')+'?token=test-secret&source_id=image-phone')[0],404)

    def test_unified_conversation_detail_before_and_after_session_creation(self):
        self.server.tasks.close()
        task=self.server.tasks.create({'goal':'图文新目标','agent':'codex','client_id':'unified'})
        route='/api/bot/conversation?token=test-secret&source_id=phone&task_id='+task['id']
        code,body=self.request('GET',route)
        self.assertEqual(code,200,body)
        self.assertFalse(json.loads(body)['can_reply'])
        self.assertEqual(json.loads(body)['status'],'queued')
        self.assertEqual(self.request('GET','/api/bot/conversation?task_id='+task['id'])[0],403)
        self.assertEqual(self.request('GET','/api/bot/conversation?token=test-secret&task_id='+task['id'])[0],400)
        self.assertEqual(self.request('GET','/api/bot/conversation?token=test-secret&source_id=phone&task_id=missing')[0],404)
        self.server.tasks.update(task['id'],remote_session='fixed-thread',status='running')
        with patch.object(self.server.bot.reader,'get',return_value={'id':'fixed-thread','title':'已建立会话'}),patch.object(self.server.bot.reader,'history',return_value={'id':'fixed-thread','status':'running','messages':[],'next_before':None}):
            code,body=self.request('GET',route)
            self.assertEqual(code,200,body)
            self.assertEqual(json.loads(body)['thread_id'],'fixed-thread')
            self.assertTrue(json.loads(body)['can_reply'])
            self.assertEqual(self.request('GET',route+'&thread_id=wrong-thread')[0],400)

    def test_bot_new_task_accepts_text_and_image_without_session_binding(self):
        self.server.tasks.close()
        code, body = self.request('POST', '/api/task-upload?token=test-secret&name=screen.png', b'\x89PNG\r\n\x1a\nfixture')
        self.assertEqual(code, 201)
        name = json.loads(body)['name']
        payload = json.dumps({'text': '解释截图', 'attachments': [name], 'request_id': 'bot-new'}).encode()
        code, body = self.request('POST', '/api/bot/tasks?token=test-secret', payload)
        self.assertEqual(code, 201, body)
        task = json.loads(body)
        self.assertEqual(task['attachments'], [name])
        self.assertEqual(task['goal'], '解释截图')
        self.assertEqual(task['remote_session'], '')
        code, image = self.request('GET', '/input/' + task['id'] + '/' + quote(name) + '?token=test-secret')
        self.assertEqual((code, image), (200, b'\x89PNG\r\n\x1a\nfixture'))
        self.assertEqual(self.request('GET', '/input/' + task['id'] + '/missing.png?token=test-secret')[0], 404)
        self.assertEqual(self.request('GET', '/input/' + task['id'] + '/..%2Foutside?token=test-secret')[0], 404)
        self.assertEqual(self.request('GET', '/api/bot/tasks?token=test-secret')[0], 200)
        self.assertEqual(self.request('POST', '/api/bot/tasks', payload)[0], 403)

    def test_mobile_console_is_default_and_session_receiver_remains_available(self):
        code,page=self.request('GET','/?token=test-secret')
        self.assertEqual(code,200)
        self.assertIn(b'id="mobile-controller-script"',page)
        for route in ['/sessions', '/bot']:
            code, page = self.request('GET', route + '?token=test-secret')
            self.assertEqual(code, 200)
            self.assertIn(b'id="composer"', page)
            self.assertIn(b'id="newConversation"', page)
        self.assertEqual(self.request('GET', '/sessions?token=test-secret')[0], 200)

    def test_input_directory_redirected_outside_task_is_rejected(self):
        self.server.tasks.close()
        manager = self.server.tasks
        (manager.uploads / 'sample.txt').write_text('original')
        task = manager.create({'goal': 'test', 'agent': 'demo', 'client_id': 'redirect', 'attachments': ['sample.txt']})
        inputs = manager.workspace(task['id']) / 'inputs'
        inputs.rename(inputs.with_name('original-inputs'))
        outside = Path(self.tmp.name) / 'outside'
        outside.mkdir()
        (outside / 'sample.txt').write_text('EXTERNAL_SECRET')
        if os.name == 'nt':
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(inputs), str(outside)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            inputs.symlink_to(outside, target_is_directory=True)
        try:
            code, body = self.request('GET', '/input/' + task['id'] + '/sample.txt?token=test-secret')
            self.assertEqual(code, 404)
            self.assertNotIn(b'EXTERNAL_SECRET', body)
        finally:
            if os.name == 'nt':
                os.rmdir(inputs)
            else:
                inputs.unlink()

    def test_rejected_post_bodies_return_errors_without_connection_reset(self):
        for _ in range(20):
            self.assertEqual(self.request('POST', '/api/tasks', b'{}')[0], 403)
            self.assertEqual(self.request('POST', '/api/upload?token=test-secret&name=bad.exe', b'bad-file')[0], 400)

    def test_upload_preserves_bytes_unicode_and_duplicates(self):
        data = b'\x89PNG\r\n\x1a\n' + bytes(range(256))
        path = '/api/upload?token=test-secret&name=' + quote('照片.png')
        for _ in range(2):
            code, body = self.request('POST', path, data)
            self.assertEqual(code, 201, body)
        files = list(self.root.glob('*.png'))
        self.assertEqual(len(files), 2)
        self.assertTrue(all(f.read_bytes() == data for f in files))
        code, body = self.request('GET', '/api/files?token=test-secret')
        self.assertEqual(code, 200)
        self.assertEqual(len(json.loads(body)), 2)

    def test_paths_empty_files_and_non_images_rejected(self):
        for name, data in [('../bad.png', b'x'), ('bad.exe', b'x'), ('empty.jpg', b'')]:
            code, _ = self.request('POST', '/api/upload?token=test-secret&name=' + quote(name), data)
            self.assertEqual(code, 400)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_page_and_download(self):
        code, page = self.request('GET', '/transfer?token=test-secret')
        self.assertEqual(code, 200)
        self.assertIn(b'XMLHttpRequest', page)
        code, body = self.request('POST', '/api/upload?token=test-secret&name=a.heic', b'heic-original')
        item = json.loads(body)
        code, data = self.request('GET', '/file/' + quote(item['name']) + '?token=test-secret')
        self.assertEqual((code, data), (200, b'heic-original'))

    def send_text(self, text, sender='phone', client_id='sample-1'):
        return self.request('POST', '/api/messages?token=test-secret',
                            json.dumps({'text': text, 'sender': sender, 'client_id': client_id}, ensure_ascii=False).encode('utf-8'),
                            {'Content-Type': 'application/json'})

    def test_messages_bidirectional_unicode_multiline_and_retry(self):
        text = '你好 👋\nhttps://example.com/?a=1&b=2\n<script>alert(1)</script>'
        code, body = self.send_text(text)
        self.assertEqual(code, 201, body)
        first = json.loads(body)
        code, body = self.send_text(text)
        self.assertEqual(code, 201)
        self.assertEqual(json.loads(body)['id'], first['id'])
        code, _ = self.send_text('电脑回复', 'computer', 'sample-2')
        self.assertEqual(code, 201)
        code, body = self.request('GET', '/api/messages?token=test-secret')
        self.assertEqual(code, 200)
        items = json.loads(body)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['text'], text)
        self.assertEqual(items[1]['sender'], 'computer')
        self.assertEqual(self.server.messages.list(), items)

    def test_messages_require_auth_and_validate_input(self):
        self.assertEqual(self.request('GET', '/api/messages')[0], 403)
        self.assertEqual(self.request('POST', '/api/messages', b'{}')[0], 403)
        for text in ['', '   ', 'x'*10001, 123]:
            code, _ = self.send_text(text)
            self.assertEqual(code, 400)
        for payload in [b'not-json', b'[]']:
            code, _ = self.request('POST', '/api/messages?token=test-secret', payload)
            self.assertEqual(code, 400)
        self.assertEqual(self.send_text('hello', sender='unknown')[0], 400)

    def test_messages_persist_after_restart(self):
        self.assertEqual(self.send_text('重启后保留的消息')[0], 201)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.server = create_server('127.0.0.1', 0, self.root, 'new-token')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        code, body = self.request('GET', '/api/messages?token=new-token')
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)[0]['text'], '重启后保留的消息')

    def test_task_api_attachment_and_cancel(self):
        self.assertEqual(self.request('GET', '/api/tasks')[0], 403)
        self.assertEqual(self.request('POST', '/api/tasks', b'{}')[0], 403)
        self.assertEqual(self.request('GET', '/api/agents?token=test-secret')[0], 200)
        code, body = self.request('POST', '/api/task-upload?token=test-secret&name=notes.txt', '任务附件'.encode())
        self.assertEqual(code, 201)
        attachment = json.loads(body)['name']
        payload = json.dumps({'goal': '使用附件生成示例', 'agent': 'demo', 'client_id': 'task-request', 'attachments': [attachment]}).encode()
        code, body = self.request('POST', '/api/tasks?token=test-secret', payload)
        self.assertEqual(code, 201, body)
        task = json.loads(body)
        self.assertEqual(self.request('GET', '/api/tasks/'+task['id']+'?token=test-secret')[0], 200)
        code, body = self.request('POST', '/api/tasks/'+task['id']+'/cancel?token=test-secret')
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)['status'], 'cancelled')
        self.assertEqual(self.request('GET', '/artifact/'+task['id']+'/../../notes.txt?token=test-secret')[0], 404)
        self.assertEqual(self.request('POST', '/api/task-upload?token=test-secret&name=../bad.txt', b'x')[0], 400)

    def test_bot_http_bridge_auth_binding_and_progress(self):
        class Reader:
            def sessions(self):return [{'id':'fixture-thread','title':'会话测试','cwd':'fixture','updated':1,'status':'running','status_hint':'日志推断','number':1}]
            def get(self, session_id):return {'id':session_id,'title':'会话测试','cwd':str(Path.cwd())}
            def progress(self, session_id):return {'id':session_id,'title':'会话测试','cwd':'fixture','status':'running','status_hint':'日志推断','events':[{'kind':'message','text':'已读取资料','time':''}],'truncated':False,'observed_at':1}
        self.server.bot.reader=Reader()
        self.assertEqual(self.request('GET','/api/bot/sessions')[0],403)
        self.assertEqual(self.request('GET','/api/bot/sessions?source_id=test-browser&token=test-secret')[0],200)
        payload=json.dumps({'source_id':'test-browser','request_id':'bind-1','text':'绑定 1'}).encode()
        code,body=self.request('POST','/api/bot/message?token=test-secret',payload)
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body)['binding']['id'],'fixture-thread')
        code,body=self.request('GET','/api/bot/progress?source_id=test-browser&token=test-secret')
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body)['progress']['events'][0]['text'],'已读取资料')
        code,body=self.request('GET','/api/bot/state?source_id=test-browser&token=test-secret')
        self.assertEqual(code,200)
        self.assertFalse(json.loads(body)['capabilities']['interrupt'])
        self.server.bot.replies.reader=Reader()
        self.server.bot.replies.runner=lambda *_:'收到了'
        payload=json.dumps({'source_id':'test-browser','request_id':'reply-1','text':'你好','expected_thread_id':'fixture-thread'}).encode()
        code,body=self.request('POST','/api/bot/reply?token=test-secret',payload)
        self.assertEqual(code,200)
        job=json.loads(body)['job']
        code,body=self.request('GET','/api/bot/replies?source_id=test-browser&token=test-secret')
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body)['jobs'][0]['thread_id'],'fixture-thread')
        code,body=self.request('POST','/api/bot/replies/'+job['id']+'/cancel?token=test-secret',b'{"source_id":"test-browser"}')
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body)['job']['status'],'cancelled')


if __name__ == '__main__':
    unittest.main()
