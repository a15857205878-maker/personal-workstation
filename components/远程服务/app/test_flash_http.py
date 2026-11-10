import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from transfer import create_server


class FlashHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        # Never let a routing regression invoke a real model in this test.
        with patch('transfer.TaskManager.start'),patch('transfer.ReplyQueue.start'):
            self.server=create_server('127.0.0.1',0,Path(self.tmp.name)/'photos','flash-http')
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.worker.join();self.tmp.cleanup()

    def request(self,method,path,payload=None,auth=True):
        connection=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        connection.request(method,path+('&' if '?' in path else '?')+'token='+('flash-http' if auth else 'bad'),
                           body=json.dumps(payload).encode() if payload is not None else None,
                           headers={'Content-Type':'application/json'})
        response=connection.getresponse();result=response.status,json.loads(response.read());connection.close();return result

    def test_new_flash_task_receipt_projection_and_cancel(self):
        body={'text':'Flash入口测试','agent':'deepseek-flash','request_id':'same'}
        self.assertEqual(self.request('POST','/api/bot/tasks',body,False)[0],403)
        code,task=self.request('POST','/api/bot/tasks',body)
        self.assertEqual(code,201);self.assertEqual(task['agent'],'deepseek-flash')
        self.assertEqual(self.request('POST','/api/bot/tasks',body)[1]['id'],task['id'])
        self.assertEqual(self.request('POST','/api/bot/tasks',dict(body,agent='codex'))[0],400)
        code,view=self.request('GET','/api/bot/conversation?source_id=phone&task_id='+task['id'])
        self.assertEqual(code,200);self.assertEqual(view['provider'],'deepseek-flash');self.assertFalse(view['can_reply'])
        self.assertEqual(self.request('POST','/api/bot/desktop-open',{'task_id':task['id']})[0],400)
        self.assertEqual(self.server.desktop_open.requests,{})
        code,stopped=self.request('POST','/api/tasks/'+task['id']+'/cancel',{})
        self.assertEqual(code,200);self.assertEqual(stopped['status'],'cancelled')

    def test_code_project_shared_receipt_local_files_and_readonly_projection(self):
        body={'text':'做本地小工具','agent':'codex-deepseek-code','request_id':'code-one','project_kind':'local-tool','reference_url':''}
        self.assertEqual(self.request('POST','/api/bot/tasks',body,False)[0],403)
        code,task=self.request('POST','/api/bot/tasks',body);self.assertEqual(code,201)
        self.assertEqual(self.request('POST','/api/bot/tasks',body)[1]['id'],task['id'])
        self.assertEqual(self.request('POST','/api/bot/tasks',dict(body,project_kind='web'))[0],400)
        self.assertEqual(self.request('POST','/api/bot/tasks',dict(body,request_id='escape',cwd='C:/Windows'))[0],400)
        workspace=self.server.tasks.workspace(task['id']);self.assertEqual(workspace.parent.name,'代码项目');self.assertTrue((self.server.tasks.data/task['id']).is_dir())
        (workspace/'README.md').write_text('local source');self.server.tasks.collect_artifacts(task['id'])
        code,view=self.request('GET','/api/bot/conversation?source_id=phone&task_id='+task['id']);self.assertEqual(code,200);self.assertFalse(view['can_reply']);self.assertEqual(view['provider'],'codex-deepseek-code')
        self.assertIn('README.md',[f['path'] for f in view['task']['artifacts']])
        self.assertEqual(self.request('POST','/api/tasks/'+task['id']+'/cancel',{})[1]['status'],'cancelled')

    def test_codex_default_and_only_flash_exposed_for_deepseek(self):
        code,task=self.request('POST','/api/bot/tasks',{'text':'默认路由','request_id':'default'})
        self.assertEqual(task['agent'],'codex')
        code,agents=self.request('GET','/api/agents')
        self.assertEqual([x['id'] for x in agents if x['id'].startswith('deepseek')],['deepseek-flash'])
        self.assertEqual(self.request('POST','/api/bot/tasks',{'text':'不支持','request_id':'bad','agent':'deepseek-v4-pro'})[0],400)
