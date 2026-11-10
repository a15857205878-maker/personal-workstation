"""Persisted replies targeting an existing session; never uses --last or forks."""
from contextlib import closing
import json,os,secrets,sqlite3,subprocess,threading,time
from pathlib import Path
from adapters import codex_path,codex_cli_env
from bot_tasks import DEFAULT_GOAL
from reply_images import image_names, snapshot_images, checked_image, execution_images
from permission_notices import PERMISSION_INSTRUCTIONS,permission_error,permission_notice,reply_blocker


class SessionBusy(RuntimeError):
    """Native resume rejected ownership before any turn was accepted."""


WRITER_WAIT = ('目标会话仍被电脑端 Codex 或其他执行器占用，指令尚未送达。'
               '桌面端离开会话后也可能保留占用；如需立即交给后台，请退出 Codex 桌面应用，保持工作台接收服务运行。'
               '倒计时只取消打开请求，不会释放已经打开的会话。')


def resume_session(job,stop):
    executable=codex_path()
    if not executable:raise RuntimeError('未找到 Codex CLI，请先在电脑登录。')
    final=Path(job['output'])
    command=[executable,'exec','resume','--skip-git-repo-check','--json','-o',str(final)]
    for path in execution_images(job):command.extend(['--image',str(path)])
    command.extend([job['thread_id'],'-'])
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    finished=False;matched=False;turn_started=False;done=threading.Event();failure=''
    with (final.parent/'stderr.log').open('w',encoding='utf-8') as errors:
        process=subprocess.Popen(command,cwd=job['cwd'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True,encoding='utf-8',errors='replace',creationflags=flags,env=codex_cli_env())
        def terminate():
            if process.poll() is None:
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,creationflags=flags)
                else:process.terminate()
        def watch():
            deadline=time.monotonic()+900
            while not done.wait(.25):
                if stop.is_set() or time.monotonic()>deadline:terminate();return
        watcher=threading.Thread(target=watch,daemon=True);watcher.start()
        try:
            process.stdin.write(PERMISSION_INSTRUCTIONS+'\n\n用户后续指令：\n'+job['text']);process.stdin.close()
            for line in process.stdout:
                try:event=json.loads(line)
                except ValueError:continue
                if not isinstance(event,dict):continue
                event_type=event.get('type','')
                if isinstance(event_type,str) and event_type.startswith(('turn.','item.')):turn_started=True
                if event.get('type')=='thread.started':
                    if event.get('thread_id')!=job['thread_id']:
                        raise RuntimeError('执行器返回了不同会话编号，已停止，未标记发送成功。')
                    matched=True
                if event.get('type')=='turn.completed':finished=True
                if event.get('type') in ('turn.failed','error'):
                    error=event.get('error') or event.get('message') or ''
                    message=error.get('message','') if isinstance(error,dict) else str(error)
                    failure=permission_notice() if permission_error(message) else 'Codex 额度不足，请在电脑检查额度后重试。' if any(s in message.lower() for s in ('usage limit','rate limit','quota')) else 'Codex 未正常完成回复，请在电脑检查登录、权限或连接。'
            code=process.wait()
            if stop.is_set():raise RuntimeError('服务关闭时回复执行中断，未自动重试，请核对原会话。')
            if code or not finished or not matched:
                errors.flush()
                with (final.parent/'stderr.log').open('rb') as diagnostic_file:
                    diagnostic_file.seek(max(0,(final.parent/'stderr.log').stat().st_size-16000))
                    diagnostic=diagnostic_file.read(16000).decode('utf-8',errors='replace')
                if 'already has an active writer' in diagnostic:
                    if code != 0 and not matched and not turn_started:
                        raise SessionBusy(WRITER_WAIT)
                    raise RuntimeError('目标会话仍被另一个 Codex 进程占用，本次未确认送达。请先结束占用该会话的执行，再核对原会话后决定是否重试。')
                raise RuntimeError(failure or (permission_notice() if permission_error(diagnostic) else '未确认原会话回复完成，请检查会话后再决定是否重试。'))
            if failure.startswith('需要你处理：权限'):raise RuntimeError(failure)
            result=final.read_text(encoding='utf-8') if final.exists() else ''
            if not result.strip():raise RuntimeError('执行已结束但未返回回复内容，请核对原会话。')
            return result[:60000]
        finally:
            done.set();terminate();process.wait(timeout=10);watcher.join(timeout=2)
            if process.stdin and not process.stdin.closed:process.stdin.close()
            process.stdout.close()


class ReplyQueue:
    def __init__(self,root,reader,runner=None,start_worker=True):
        self.root=Path(root)/'Bot回复';self.root.mkdir(exist_ok=True,parents=True)
        self.owner=(self.root/'.owner.lock').open('a+b')
        self.owner.seek(0,2)
        if self.owner.tell()==0:self.owner.write(b'0');self.owner.flush()
        self.owner.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.owner.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.owner.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.owner.close();self.owner=None
            raise RuntimeError('回复队列正由另一个工作台实例管理，未重复启动。') from None
        self.database=self.root/'queue.sqlite3';self.reader=reader;self.runner=runner or resume_session
        self.lock=threading.RLock();self.stop=threading.Event();self.worker=None
        with closing(sqlite3.connect(self.database)) as db,db:
            db.execute('CREATE TABLE IF NOT EXISTS replies(id TEXT PRIMARY KEY,channel TEXT,source TEXT,request_id TEXT,body TEXT,UNIQUE(channel,source,request_id))')
            for task_id,body in db.execute('SELECT id,body FROM replies').fetchall():
                job=json.loads(body)
                if job['status']=='sending':
                    job.update(status='needs_attention',error='服务曾在回复执行中中断，未自动重发，请核对原会话。')
                    db.execute('UPDATE replies SET body=? WHERE id=?',(json.dumps(job,ensure_ascii=False),task_id))
        if start_worker:
            self.start()

    def start(self):
        with self.lock:
            if self.worker is None and not self.stop.is_set():
                self.worker=threading.Thread(target=self._work,daemon=True)
                self.worker.start()

    def create(self,channel,source,request_id,thread_id,text,attachments=None):
        names=image_names(attachments)
        if not isinstance(text,str) or len(text)>20000 or not text.strip() and not names:
            raise ValueError('请输入文字或添加图片，文字最多20000字。')
        if not text.strip():text=DEFAULT_GOAL
        if not isinstance(request_id,str) or not 1<=len(request_id)<=100:raise ValueError('回复请求编号无效。')
        with self.lock,closing(sqlite3.connect(self.database)) as db,db:
            old=db.execute('SELECT body FROM replies WHERE channel=? AND source=? AND request_id=?',(channel,source,request_id)).fetchone()
            if old:
                job=json.loads(old[0])
                if job['thread_id']!=thread_id or job['text']!=text or job.get('attachments',[])!=names:
                    raise ValueError('重复请求内容不一致，未发送。')
                return self.public(job)
            session=self.reader.get(thread_id)
            job_id=secrets.token_hex(16);folder=self.root/job_id;folder.mkdir()
            try:
                if names:snapshot_images(self.root.parent/'任务附件',folder/'inputs',names)
            except (ValueError,OSError):
                for name in names:(folder/'inputs'/name).unlink(missing_ok=True)
                if (folder/'inputs').exists():(folder/'inputs').rmdir()
                folder.rmdir()
                raise
            now=time.time()
            job={'id':job_id,'thread_id':thread_id,'title':session['title'],'cwd':session['cwd'],'text':text,'attachments':names,'status':'queued','result':'','error':'','created':now,'updated':now,'output':str(folder/'result.txt')}
            db.execute('INSERT INTO replies VALUES(?,?,?,?,?)',(job_id,channel,source,request_id,json.dumps(job,ensure_ascii=False)))
            return self.public(job)

    def attachment_path(self, channel, source, job_id, name):
        with closing(sqlite3.connect(self.database)) as db:
            row=db.execute('SELECT body FROM replies WHERE id=? AND channel=? AND source=?',(job_id,channel,source)).fetchone()
        if not row:raise KeyError('图片记录不存在')
        job=json.loads(row[0])
        if name not in job.get('attachments',[]):raise FileNotFoundError('图片不存在')
        return checked_image(Path(job['output']).parent/'inputs',name)

    @staticmethod
    def public(job):
        value={k:v for k,v in job.items() if k not in ('cwd','output')}
        if job['status'] in ('queued','waiting'):value['waiting_seconds']=max(0,int(time.time()-job['created']))
        return value
    def get(self,job_id):
        with closing(sqlite3.connect(self.database)) as db:row=db.execute('SELECT body FROM replies WHERE id=?',(job_id,)).fetchone()
        if not row:raise KeyError('回复不存在')
        return json.loads(row[0])
    def update(self,job_id,**changes):
        with self.lock,closing(sqlite3.connect(self.database)) as db,db:
            row=db.execute('SELECT body FROM replies WHERE id=?',(job_id,)).fetchone();job=json.loads(row[0]);job.update(changes);job['updated']=time.time()
            db.execute('UPDATE replies SET body=? WHERE id=?',(json.dumps(job,ensure_ascii=False),job_id));return job
    def claim(self,job_id):
        with self.lock,closing(sqlite3.connect(self.database)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT body FROM replies WHERE id=?',(job_id,)).fetchone()
            if not row:return False
            job=json.loads(row[0])
            if job['status'] not in ('queued','waiting'):return False
            now=time.time();job.update(status='sending',updated=now,started_at=now,last_attempt_at=now,
                                       attempts=job.get('attempts',0)+1,waiting_reason='',observed_status=None)
            db.execute('UPDATE replies SET body=? WHERE id=?',(json.dumps(job,ensure_ascii=False),job_id))
            return True
    def list(self,channel,source,thread_id=None):
        result=[];queues={}
        with closing(sqlite3.connect(self.database)) as db:
            # FIFO spans browser sources. Explain an older blocker without
            # returning its message, request ID, or source to another browser.
            for row in db.execute('SELECT body FROM replies ORDER BY rowid'):
                entry=json.loads(row[0])
                if entry['status'] in ('queued','waiting','sending'):
                    queues.setdefault(entry['thread_id'],[]).append(entry)
            for row in db.execute('SELECT body FROM replies WHERE channel=? AND source=? ORDER BY rowid DESC',(channel,source)):
                job=json.loads(row[0])
                if thread_id is not None and job['thread_id']!=thread_id:continue
                value=self.public(job)
                if job['status'] in ('queued','waiting'):
                    pending=queues.get(job['thread_id'],[])
                    position=next((i+1 for i,entry in enumerate(pending) if entry['id']==job['id']),1)
                    value['queue_position']=position
                    head=pending[0] if pending else job
                    if head.get('observed_status')=='native_writer_busy' and head['status']=='waiting':
                        value['blocked_by']='native_writer_busy'
                        prefix=f'前面还有 {position-1} 条指令等待同一会话。' if position>1 else ''
                        value['waiting_reason']=prefix+WRITER_WAIT
                    elif position>1:
                        value['waiting_reason']=f'前面还有 {position-1} 条指令等待或正在执行同一会话，尚未轮到本条。'
                result.append(value)
                if len(result)>=20:break
        return result
    def is_sending(self, thread_id):
        with self.lock, closing(sqlite3.connect(self.database)) as db:
            return any((thread_id is None or json.loads(row[0]).get('thread_id') == thread_id)
                       and json.loads(row[0]).get('status') == 'sending'
                       for row in db.execute('SELECT body FROM replies'))

    def has_pending(self, thread_id):
        with self.lock, closing(sqlite3.connect(self.database)) as db:
            for row in db.execute('SELECT body FROM replies'):
                job=json.loads(row[0])
                if (thread_id is None or job['thread_id']==thread_id) and job['status'] in ('queued','waiting','sending'):
                    return True
        return False

    def cancel(self,channel,source,job_id):
        with self.lock,closing(sqlite3.connect(self.database)) as db,db:
            row=db.execute('SELECT body FROM replies WHERE id=? AND channel=? AND source=?',(job_id,channel,source)).fetchone()
            if not row:raise KeyError('回复不存在')
            job=json.loads(row[0])
            if job['status'] not in ('queued','waiting'):raise ValueError('回复已开始或已结束，不能作为待发送消息取消。')
            job.update(status='cancelled',updated=time.time());db.execute('UPDATE replies SET body=? WHERE id=?',(json.dumps(job,ensure_ascii=False),job_id))
            return self.public(job)
    def tick(self):
        with closing(sqlite3.connect(self.database)) as db:rows=db.execute('SELECT body FROM replies ORDER BY rowid').fetchall()
        blocked_threads=set()
        for row in rows:
            job=json.loads(row[0])
            if job['status'] not in ('queued','waiting'):continue
            if job['thread_id'] in blocked_threads:continue
            blocked_threads.add(job['thread_id'])
            if job.get('next_attempt_at',0)>time.time():continue
            try:
                with self.lock:
                    if self.get(job['id'])['status'] not in ('queued','waiting'):continue
                    if self.stop.is_set():return
                    if time.time()-job['created']>21600:
                        self.update(job['id'],status='needs_attention',finished_at=time.time(),error='排队超过6小时，未继续自动尝试，请核对原会话。')
                        continue
                    # Native exclusive-writer ownership is authoritative. Historical
                    # log status can remain "running" after the desktop was closed.
                    if not self.claim(job['id']):continue
                result=self.runner(job,self.stop)
                blocked=reply_blocker(result)
                if blocked:raise RuntimeError(blocked)
                self.update(job['id'],status='completed',result=result,finished_at=time.time())
            except SessionBusy as error:
                self.update(job['id'],status='waiting',waiting_reason=str(error),observed_status='native_writer_busy',
                            next_attempt_at=time.time()+10,started_at=None)
            except Exception as error:self.update(job['id'],status='needs_attention',error=str(error)[:2000],finished_at=time.time())
            return
    def _work(self):
        while not self.stop.wait(1):self.tick()
    def close(self):
        self.stop.set()
        if self.worker:self.worker.join(timeout=15)
        if self.worker and self.worker.is_alive():return
        if self.owner:
            self.owner.close();self.owner=None
