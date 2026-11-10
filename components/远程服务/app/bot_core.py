"""Channel-neutral routing with an optional explicit existing-session reply queue."""
from contextlib import closing
import json
import sqlite3
import threading
import time


class BotCore:
    def __init__(self, database, reader, reply_queue=None):
        self.database=database
        self.reader=reader
        self.replies=reply_queue
        self.lock=threading.RLock()
        with closing(sqlite3.connect(database)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS bot_bindings(channel TEXT,source TEXT,body TEXT,PRIMARY KEY(channel,source))')
            db.execute('CREATE TABLE IF NOT EXISTS bot_lists(channel TEXT,source TEXT,body TEXT,created REAL,PRIMARY KEY(channel,source))')
            db.execute('CREATE TABLE IF NOT EXISTS bot_requests(channel TEXT,source TEXT,request_id TEXT,input TEXT,body TEXT,created REAL,PRIMARY KEY(channel,source,request_id))')

    def _key(self, channel, source):
        if not isinstance(channel,str) or not 1<=len(channel)<=30 or not isinstance(source,str) or not 1<=len(source)<=120:
            raise ValueError('网页来源标识无效，请刷新后重试。')

    def state(self, channel, source):
        self._key(channel,source)
        with closing(sqlite3.connect(self.database)) as db:
            row=db.execute('SELECT body FROM bot_bindings WHERE channel=? AND source=?',(channel,source)).fetchone()
            history=db.execute('SELECT input,body FROM bot_requests WHERE channel=? AND source=? ORDER BY rowid DESC LIMIT 20',(channel,source)).fetchall()
        return {'binding':json.loads(row[0]) if row else None,
                'capabilities':{'list':True,'read':True,'reply':self.replies is not None,'steer':False,'interrupt':False},
                'history':[{'input':r[0],'reply':json.loads(r[1])} for r in reversed(history)]}

    def reply(self, channel, source, text, request_id, expected_thread_id, attachments=None):
        self._key(channel,source)
        with self.lock:
            binding=self.state(channel,source)['binding']
            if not binding or not expected_thread_id or binding['id']!=expected_thread_id:
                raise ValueError('会话选择已变化或尚未绑定，未发送；请重新确认目标。')
            if self.replies is None:raise ValueError('回复执行器未接通。')
            job=self.replies.create(channel,source,request_id,binding['id'],text,attachments=attachments)
            return {'kind':'reply','text':'已加入原会话的回复队列；当前轮执行中时等待结束，不代表已经送达。','job':job}

    def reply_to(self, channel, source, thread_id, text, request_id, attachments=None):
        """Explicit immutable target; independent of old pages' mutable bindings."""
        self._key(channel, source)
        if not isinstance(thread_id, str) or not 1 <= len(thread_id) <= 120:
            raise ValueError('请先选择历史会话。')
        if self.replies is None:
            raise ValueError('回复执行器未接通。')
        job = self.replies.create(channel, source, request_id, thread_id, text, attachments=attachments)
        return {'kind': 'reply', 'text': '指令已入队，等待原会话空闲后执行；尚不代表已经送达。', 'job': job}

    def list_sessions(self, channel, source):
        self._key(channel,source)
        sessions=self.reader.sessions()
        with self.lock, closing(sqlite3.connect(self.database)) as db, db:
            db.execute('INSERT OR REPLACE INTO bot_lists VALUES(?,?,?,?)',(channel,source,json.dumps(sessions,ensure_ascii=False),time.time()))
        return sessions

    def progress(self, channel, source):
        self._key(channel,source)
        with closing(sqlite3.connect(self.database)) as db:
            row=db.execute('SELECT body FROM bot_bindings WHERE channel=? AND source=?',(channel,source)).fetchone()
        binding=json.loads(row[0]) if row else None
        if not binding:return {'kind':'unbound','text':'还未绑定会话。先发送“列表”，再选择要查看的会话。'}
        try:
            progress=self.reader.progress(binding['id'])
            return {'kind':'progress','text':'已读取绑定会话的最近公开记录；状态依据本地日志推断。','progress':progress}
        except (OSError,ValueError,KeyError,sqlite3.Error) as e:
            return {'kind':'error','text':'暂时无法读取绑定会话：'+str(e)}

    def handle(self, channel, source, text, request_id):
        self._key(channel,source)
        if not isinstance(text,str) or not text.strip() or len(text)>20000:raise ValueError('请输入指令，最多 20000 字。')
        if not isinstance(request_id,str) or not 1<=len(request_id)<=100:raise ValueError('请求标识无效。')
        with self.lock:
            with closing(sqlite3.connect(self.database)) as db:
                row=db.execute('SELECT input,body FROM bot_requests WHERE channel=? AND source=? AND request_id=?',(channel,source,request_id)).fetchone()
            if row:
                if row[0]!=text:raise ValueError('请求标识重复，请重新发送。')
                return json.loads(row[1])
            try:reply=self._command(channel,source,text)
            except (OSError,ValueError,KeyError,sqlite3.Error) as e:reply={'kind':'error','text':str(e)}
            with closing(sqlite3.connect(self.database)) as db, db:
                db.execute('INSERT INTO bot_requests VALUES(?,?,?,?,?,?)',(channel,source,request_id,text,json.dumps(reply,ensure_ascii=False),time.time()))
            return reply

    def _command(self, channel, source, text):
        command=text.strip().lstrip('/')
        head,_,argument=command.partition(' ')
        if command in ('列表','会话','sessions'):
            sessions=self.list_sessions(channel,source)
            return {'kind':'sessions','text':f'找到 {len(sessions)} 个近期会话。选择一个绑定后查看进度。','sessions':sessions}
        if head in ('绑定','bind'):
            argument=argument.strip()
            if not argument:raise ValueError('请使用“绑定 会话编号”，或点击会话旁的绑定按钮。')
            if argument.isdecimal():
                with closing(sqlite3.connect(self.database)) as db:
                    row=db.execute('SELECT body,created FROM bot_lists WHERE channel=? AND source=?',(channel,source)).fetchone()
                if not row or time.time()-row[1]>600:raise ValueError('列表已过期，请重新发送“列表”。')
                items=json.loads(row[0]);index=int(argument)-1
                if not 0<=index<len(items):raise ValueError('会话编号不在本次列表中。')
                argument=items[index]['id']
            item=self.reader.get(argument)
            binding={'id':item['id'],'title':item['title']}
            with closing(sqlite3.connect(self.database)) as db, db:
                db.execute('INSERT OR REPLACE INTO bot_bindings VALUES(?,?,?)',(channel,source,json.dumps(binding,ensure_ascii=False)))
            return {'kind':'binding','text':'已绑定「'+binding['title']+'」。以后查询固定读取此会话，不随列表顺序变化。','binding':binding}
        if command in ('进度','状态','progress'):return self.progress(channel,source)
        if command in ('解绑','unbind'):
            with closing(sqlite3.connect(self.database)) as db, db:
                db.execute('DELETE FROM bot_bindings WHERE channel=? AND source=?',(channel,source))
            return {'kind':'binding','text':'已解除绑定。','binding':None}
        if head in ('补充','停止','打断','继续','steer','stop'):
            return {'kind':'unsupported','text':'未执行：运行中即时补充和打断控制尚未接通。请用回复框排队续接原会话；不会新建会话。'}
        return {'kind':'help','text':'可用指令：列表、绑定 <编号>、进度、解绑。\n回复请使用回复框，查询不调用模型。运行中即时补充和打断尚未接通。'}
