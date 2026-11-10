import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from bot_core import BotCore
from session_reader import CodexSessionReader


class BotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / 'codex'
        self.home.mkdir()
        self.logs = self.home / 'sessions'
        self.logs.mkdir()
        self.log = self.logs / 'session.jsonl'
        entries = [
            {'type':'event_msg','timestamp':'2026-10-27T01:00:00Z','payload':{'type':'task_started'}},
            {'type':'response_item','timestamp':'2026-10-27T01:00:01Z','payload':{'type':'message','role':'assistant','phase':'commentary','content':[{'type':'output_text','text':'资料读取完成'}]}},
            {'type':'response_item','payload':{'type':'reasoning','text':'PRIVATE_REASONING'}},
            {'type':'response_item','payload':{'type':'custom_tool_call_output','output':'SECRET_TOOL_OUTPUT'}},
        ]
        self.log.write_text('\n'.join(json.dumps(e) for e in entries)+'\n', encoding='utf-8')
        db=sqlite3.connect(self.home/'state_5.sqlite')
        db.execute('CREATE TABLE threads(id TEXT,rollout_path TEXT,title TEXT,cwd TEXT,updated_at INTEGER,archived INTEGER)')
        db.execute('INSERT INTO threads VALUES(?,?,?,?,?,?)',('thread-one',str(self.log),'测试会话',str(self.root),100,0))
        db.commit();db.close()
        self.reader = CodexSessionReader(self.home)
        self.bot = BotCore(self.root/'bot.sqlite3', self.reader)

    def tearDown(self):
        self.tmp.cleanup()

    def test_history_paginates_public_user_and_assistant_messages(self):
        entries=[]
        for i in range(7):
            role='user' if i%2==0 else 'assistant'
            entries.append({'type':'response_item','timestamp':str(i),'payload':{'type':'message','role':role,'phase':'final_answer','content':[{'type':'input_text' if role=='user' else 'output_text','text':f'消息{i}'}]}})
        entries += [{'type':'response_item','payload':{'type':'message','role':'assistant','phase':'analysis','content':[{'type':'output_text','text':'PRIVATE_REASONING'}]}},
                    {'type':'response_item','payload':{'type':'message','role':'developer','content':[{'type':'input_text','text':'PRIVATE_SYSTEM'}]}}]
        self.log.write_text('\n'.join(json.dumps(e) for e in entries)+'\n',encoding='utf-8')
        first=self.reader.history('thread-one',limit=3)
        second=self.reader.history('thread-one',before=first['next_before'],limit=3)
        third=self.reader.history('thread-one',before=second['next_before'],limit=3)
        messages=third['messages']+second['messages']+first['messages']
        self.assertEqual([m['text'] for m in messages],[f'消息{i}' for i in range(7)])
        self.assertEqual(len({m['id'] for m in messages}),7)
        self.assertIsNone(third['next_before'])
        self.assertNotIn('PRIVATE_',json.dumps([first,second,third]))
        for cursor in ['bad',-1,self.log.stat().st_size+1]:
            with self.assertRaises(ValueError):self.reader.history('thread-one',before=cursor)

    def test_session_list_search_and_pagination(self):
        with closing(sqlite3.connect(self.home/'state_5.sqlite')) as db, db:
            db.execute('INSERT INTO threads VALUES(?,?,?,?,?,?)',('thread-two',str(self.log),'手机新任务',str(self.root),200,0))
        first=self.reader.session_page(limit=1)
        second=self.reader.session_page(limit=1,offset=first['next_offset'])
        self.assertEqual(first['sessions'][0]['id'],'thread-two')
        self.assertEqual(second['sessions'][0]['id'],'thread-one')
        self.assertIsNone(second['next_offset'])
        self.assertEqual(self.reader.session_page(search='手机')['sessions'][0]['id'],'thread-two')

    def test_history_can_cross_large_private_records_without_leaking_or_looping(self):
        def message(text):return {'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':text}]}}
        entries=[message('较早消息'),{'type':'response_item','payload':{'type':'custom_tool_call_output','output':'PRIVATE_TOOL_'+('x'*1100000)}},message('较新消息')]
        self.log.write_text('\n'.join(json.dumps(e) for e in entries)+'\n',encoding='utf-8')
        cursor=None;seen=[];previous=self.log.stat().st_size+1
        for _ in range(5):
            page=self.reader.history('thread-one',before=cursor)
            self.assertNotIn('PRIVATE_TOOL_',json.dumps(page))
            seen=page['messages']+seen
            cursor=page['next_before']
            if cursor is None:break
            self.assertLess(cursor,previous);previous=cursor
        else:self.fail('历史分页没有前进')
        self.assertEqual([m['text'] for m in seen],['较早消息','较新消息'])

    def test_history_marks_images_and_truncation_without_exporting_embedded_data(self):
        entry={'type':'response_item','payload':{'type':'message','role':'user','content':[
            {'type':'input_image','image_url':'data:image/png;base64,PRIVATE_IMAGE'},
            {'type':'input_text','text':'文字'*8000}]}}
        self.log.write_text(json.dumps(entry)+'\n',encoding='utf-8')
        page=self.reader.history('thread-one')
        self.assertTrue(page['messages'][0]['truncated'])
        self.assertIn('图片附件',page['messages'][0]['text'])
        self.assertNotIn('PRIVATE_IMAGE',json.dumps(page))
        self.assertEqual(len(page['messages'][0]['text']),12000)

    def test_direct_history_reply_does_not_depend_on_binding(self):
        from reply_queue import ReplyQueue
        queue=ReplyQueue(self.root,self.reader,runner=lambda *_:'收到了',start_worker=False)
        self.bot.replies=queue
        try:
            first=self.bot.reply_to('web','a','thread-one','执行指令','fixed-request')
            self.assertEqual(first['job']['thread_id'],'thread-one')
            self.assertIsNone(self.bot.state('web','a')['binding'])
            self.assertEqual(self.bot.reply_to('web','a','thread-one','执行指令','fixed-request')['job']['id'],first['job']['id'])
            with self.assertRaises(ValueError):self.bot.reply_to('web','a','other-thread','执行指令','fixed-request')
        finally:queue.close()

    def test_list_bind_progress_persist_and_idempotency(self):
        listed=self.bot.handle('web','alice','列表','r1')
        self.assertEqual(listed['kind'],'sessions')
        reply=self.bot.handle('web','alice','绑定 1','r2')
        self.assertEqual(reply['binding']['id'],'thread-one')
        self.assertEqual(self.bot.handle('web','alice','绑定 1','r2'),reply)
        self.bot=BotCore(self.root/'bot.sqlite3',self.reader)
        progress=self.bot.handle('web','alice','进度','r3')
        self.assertEqual(progress['kind'],'progress')
        self.assertIn('资料读取完成',json.dumps(progress,ensure_ascii=False))
        self.assertNotIn('PRIVATE_REASONING',json.dumps(progress))
        self.assertNotIn('SECRET_TOOL_OUTPUT',json.dumps(progress))
        self.assertEqual(self.bot.handle('web','bob','进度','other')['kind'],'unbound')

    def test_unavailable_control_never_executes_or_unbinds(self):
        self.bot.handle('web','a','列表','l')
        self.bot.handle('web','a','绑定 1','b')
        for cmd in ['停止','补充 继续处理']:
            r=self.bot.handle('web','a',cmd,cmd)
            self.assertEqual(r['kind'],'unsupported')
            self.assertIn('未执行',r['text'])
        self.assertEqual(self.bot.state('web','a')['binding']['id'],'thread-one')

    def test_public_updates_are_refreshed_and_outside_paths_denied(self):
        before=self.reader.progress('thread-one')
        self.log.write_text(self.log.read_text() + json.dumps({'type':'event_msg','payload':{'type':'task_complete'}})+'\n')
        self.assertEqual(self.reader.progress('thread-one')['status'],'completed')
        external=self.root/'outside.jsonl';external.write_text('{"secret":"dont read"}')
        db=sqlite3.connect(self.home/'state_5.sqlite')
        db.execute('UPDATE threads SET rollout_path=?',(str(external),));db.commit();db.close()
        with self.assertRaises(ValueError):self.reader.progress('thread-one')
        with self.assertRaises(ValueError):self.reader.history('thread-one')

    def test_binding_is_not_changed_by_newer_session(self):
        self.bot.handle('web','a','列表','l')
        self.bot.handle('web','a','绑定 1','b')
        db=sqlite3.connect(self.home/'state_5.sqlite')
        db.execute('INSERT INTO threads VALUES(?,?,?,?,?,?)',('thread-two',str(self.log),'更新的会话',str(self.root),200,0));db.commit();db.close()
        self.bot.handle('web','a','列表','new-list')
        self.assertEqual(self.bot.state('web','a')['binding']['id'],'thread-one')

    def test_displayed_list_snapshot_is_used_after_reordering(self):
        self.bot.list_sessions('web','a')
        db=sqlite3.connect(self.home/'state_5.sqlite')
        db.execute('INSERT INTO threads VALUES(?,?,?,?,?,?)',('thread-two',str(self.log),'新的第一条',str(self.root),200,0));db.commit();db.close()
        shown=self.bot.list_sessions('web','a')
        self.assertEqual(shown[0]['id'],'thread-two')
        reply=self.bot.handle('web','a','绑定 1','after-reload')
        self.assertEqual(reply['binding']['id'],shown[0]['id'])

    def test_user_title_preferred_and_internal_review_sessions_hidden(self):
        db=sqlite3.connect(self.home/'state_5.sqlite')
        for name in ['name','source','thread_source']:db.execute('ALTER TABLE threads ADD COLUMN '+name+' TEXT')
        db.execute('UPDATE threads SET name=?,source=?,thread_source=?',('用户设置的标题','vscode','user'))
        db.execute('INSERT INTO threads VALUES(?,?,?,?,?,?,?,?,?)',('internal-review',str(self.log),'Guardian review',str(self.root),300,0,'Guardian review','{"subagent":{"other":"guardian"}}','guardian_review'))
        db.commit();db.close()
        shown=self.reader.sessions()
        self.assertEqual(len(shown),1)
        self.assertEqual(shown[0]['title'],'用户设置的标题')
        with self.assertRaises(KeyError):self.reader.get('internal-review')

    def test_reply_checks_bound_target_before_enqueue(self):
        from reply_queue import ReplyQueue
        queue=ReplyQueue(self.root,self.reader,runner=lambda *_:'收到了',start_worker=False)
        self.bot.replies=queue
        try:
            self.bot.handle('web','a','绑定 thread-one','bind')
            with self.assertRaises(ValueError):self.bot.reply('web','a','你好','r','wrong-thread')
            reply=self.bot.reply('web','a','你好','r','thread-one')
            self.assertEqual(reply['job']['thread_id'],'thread-one')
            self.assertEqual(reply['job']['status'],'queued')
        finally:queue.close()


if __name__=='__main__':unittest.main()
