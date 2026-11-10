import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from deepseek_history import DeepSeekHistoryReader


NODE = DeepSeekHistoryReader._runtime()


class NativeHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)/'sessions'
        self.file = self.root/'project'/'session-test'/'session.v4.jsonl.zstd'
        self.file.parent.mkdir(parents=True)
        self.rows = [dict(type='session',version=4,id='session-test',createdAt=10,cwd='PRIVATE_PATH'),
                     dict(type='system/message',seq=0,data={'message':{'content':'SYSTEM_SECRET'}}),
                     dict(type='session/title',seq=1,data={'title':'公开标题'}),
                     dict(type='user/message',seq=2,time=11,data={'role':'user','content':[{'type':'text','text':'问题'},{'type':'image','url':'PRIVATE_IMAGE'}]}),
                     dict(type='assistant/message',seq=3,time=12,data={'message':{'role':'assistant','content':[{'type':'reasoning','text':'THINK_SECRET'},{'type':'text','text':'回答'},{'type':'tool-call','arguments':'TOOL_SECRET'}]},'stream':'STREAM_SECRET'}),
                     dict(type='turn/end',seq=4,data={'reason':{'kind':'completed'}})]
        self.write(self.rows)
        self.reader = DeepSeekHistoryReader(self.root, runtime=NODE, cache_seconds=0)

    def tearDown(self):
        self.tmp.cleanup()

    def compressed(self, data):
        return subprocess.run([str(NODE),'-e',"const z=require('zlib');let a=[];process.stdin.on('data',x=>a.push(x));process.stdin.on('end',()=>process.stdout.write(z.zstdCompressSync(Buffer.concat(a))));"],input=data,stdout=subprocess.PIPE,check=True).stdout

    def write(self, rows):
        self.file.write_bytes(self.compressed(('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n').encode()))

    def test_resume_preflight_restores_exact_workspace_and_model_but_never_exports_them(self):
        from unittest.mock import Mock
        self.rows[0]['cwd']=self.tmp.name
        self.rows.insert(-1,{'type':'request/header','data':{'header':{'config':{'provider':'deepseek-official','model':'deepseek-original'}}}})
        self.rows.insert(-1,{'type':'model/selection','data':{'provider':'deepseek-official','model':'deepseek-original','api_key':'NEVER_COPY'}})
        self.write(self.rows)
        identifier=self.reader.session_page()['sessions'][0]['id']
        meta=self.reader.resolve(identifier);self.assertEqual(meta['native_id'],'session-test');self.assertEqual(meta['cwd'],self.tmp.name);self.assertEqual(meta['model']['model'],'deepseek-original');self.assertNotIn('NEVER_COPY',json.dumps(meta))
        queue=Mock();queue.list.return_value=[];queue.has_pending.return_value=False
        public=self.reader.conversation(identifier,'phone',replies=queue);self.assertTrue(public['can_reply'])
        self.assertNotIn(self.tmp.name,json.dumps(public));self.assertNotIn('cwd',public)
        self.rows.append({'type':'agent-preset/selected','data':{'agentPreset':'custom'}});self.write(self.rows)
        with self.assertRaises(ValueError):self.reader.resolve(identifier)
        self.assertFalse(self.reader.conversation(identifier,'phone',replies=queue)['can_reply'])

    def test_original_reasoning_effort_is_preserved_instead_of_making_history_readonly(self):
        self.rows[0]['cwd']=self.tmp.name
        self.rows.insert(-1,{'type':'request/header','data':{'header':{'config':{'provider':'deepseek-official','model':'deepseek-flash','reasoningEffort':'high'}}}})
        self.write(self.rows);identifier=self.reader.session_page()['sessions'][0]['id']
        meta=self.reader.resolve(identifier);self.assertEqual(meta['model'],{'provider':'deepseek-official','model':'deepseek-flash','reasoningEffort':'high'})

    def test_only_public_messages_readonly(self):
        original = self.file.read_bytes()
        page = self.reader.session_page()
        self.assertEqual(len(page['sessions']),1)
        item = page['sessions'][0]
        self.assertEqual(item['title'],'公开标题')
        self.assertEqual(item['session_id'],'session-test')
        view = self.reader.conversation(item['id'],'phone')
        self.assertFalse(view['can_reply']);self.assertIsNone(view['thread_id'])
        self.assertEqual(view['provider'],'deepseek-harness')
        self.assertEqual([m['text'] for m in view['history']['messages']],['问题\n[图片]','回答'])
        output = json.dumps(view)+json.dumps(page)
        for secret in ('PRIVATE_PATH','PRIVATE_IMAGE','SYSTEM_SECRET','THINK_SECRET','TOOL_SECRET','STREAM_SECRET'):
            self.assertNotIn(secret,output)
        self.assertEqual(original,self.file.read_bytes())
        self.assertEqual(len(list(self.root.rglob('*json*'))),1)

    def test_paging_search_refresh_and_no_duplicate_messages(self):
        rows = self.rows[:3]+[dict(type='user/message',seq=i+2,data={'role':'user','content':[{'type':'text','text':str(i)}]}) for i in range(65)]
        self.write(rows)
        item = self.reader.session_page(search='公开')['sessions'][0]
        latest = self.reader.conversation(item['id'],'phone')['history']
        older = self.reader.conversation(item['id'],'phone',before=latest['next_before'])['history']
        self.assertEqual(len(latest['messages']),30)
        self.assertFalse(set(m['id'] for m in latest['messages']) & set(m['id'] for m in older['messages']))
        self.assertEqual(self.reader.session_page(search='未匹配')['sessions'],[])
        rows.append(dict(type='user/message',seq=99,data={'role':'user','content':[{'type':'text','text':'新消息'}]}))
        self.write(rows)
        self.assertEqual(self.reader.conversation(item['id'],'phone')['history']['messages'][-1]['text'],'新消息')

    def test_invalid_targets_and_newer_format(self):
        for value in ('../credentials','a'*63,'A'*64):
            with self.assertRaises(ValueError):self.reader.conversation(value,'phone')
        with self.assertRaises(KeyError):self.reader.conversation('0'*64,'phone')
        with self.assertRaises(ValueError):self.reader.conversation(self.reader.session_page()['sessions'][0]['id'],'')
        self.file.rename(self.file.with_name('session.v9.jsonl.zstd'))
        page = self.reader.session_page()
        self.assertEqual(page['sessions'],[]);self.assertTrue(page['warning'])

    def test_incomplete_raw_tail_and_untrusted_role(self):
        self.file.unlink()
        self.file = self.file.with_name('session.v4.jsonl')
        rows=self.rows+[dict(type='user/message',seq=5,data={'role':'developer','content':[{'type':'text','text':'DEVELOPER_SECRET'}]})]
        self.file.write_text('\n'.join(json.dumps(r) for r in rows)+'\n{"type":"user/message"',encoding='utf-8')
        item=self.reader.session_page()['sessions'][0]
        history=self.reader.conversation(item['id'],'phone')['history']
        self.assertEqual(len(history['messages']),2)
        self.assertEqual(history['status'],'unconfirmed')
        self.assertTrue(history['scan_limited'])

    def test_native_read_does_not_call_models_or_accept_codex_thread(self):
        item=self.reader.session_page()['sessions'][0]
        with self.assertRaises(ValueError):self.reader.conversation(item['id'],'phone',before=-1)
        self.assertEqual(self.reader.session_page(limit=1)['next_offset'],None)
        self.assertEqual(self.reader.session_page(offset=100)['sessions'],[])

    def test_compressed_append_tail_uses_only_complete_lines(self):
        good=self.file.read_bytes()
        extra=self.compressed((json.dumps(dict(type='user/message',seq=5,data={'role':'user','content':[{'type':'text','text':'NOT_COMMITTED'}]}))+'\n').encode())
        self.file.write_bytes(good+extra[:len(extra)//2])
        item=self.reader.session_page()['sessions'][0]
        view=self.reader.conversation(item['id'],'phone')
        self.assertEqual(view['status'],'unconfirmed')
        self.assertNotIn('NOT_COMMITTED',json.dumps(view))
        self.assertEqual(len(view['history']['messages']),2)

    def test_symlink_session_is_not_read(self):
        link=self.root/'project'/'linked'
        try:link.symlink_to(self.file.parent,target_is_directory=True)
        except OSError:self.skipTest('Windows symlink permission unavailable')
        self.assertEqual(len(self.reader.session_page()['sessions']),1)

    def test_long_public_message_marks_truncation(self):
        self.rows[3]['data']['content']=[{'type':'text','text':'a'*13000}]
        self.write(self.rows)
        item=self.reader.session_page()['sessions'][0]
        message=self.reader.conversation(item['id'],'phone')['history']['messages'][0]
        self.assertEqual(len(message['text']),12000)
        self.assertTrue(message.get('truncated'))

    def test_corrupt_history_reports_error_without_leaking_content(self):
        self.file.write_bytes(b'not zstandard CREDENTIAL_SECRET')
        self.assertEqual(self.reader.session_page()['sessions'],[])
        target=__import__('hashlib').sha256(b'project/session-test').hexdigest()
        with self.assertRaises(OSError) as caught:self.reader.conversation(target,'phone')
        self.assertNotIn('CREDENTIAL_SECRET',str(caught.exception))


if __name__=='__main__':unittest.main()
