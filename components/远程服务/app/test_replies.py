import tempfile,unittest,io,threading,json
from unittest.mock import patch
from pathlib import Path
from reply_queue import ReplyQueue,resume_session,SessionBusy

class Reader:
    status='running'
    def get(self,i):return {'id':i,'title':'原会话','cwd':str(Path.cwd())}
    def progress(self,i):return {'status':self.status}

class ReplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.reader=Reader();self.calls=[]
        def runner(job,stop):
            if self.reader.status=='running':raise SessionBusy('目标仍被占用')
            self.calls.append(job['thread_id']);return '收到了'
        self.q=ReplyQueue(Path(self.tmp.name),self.reader,runner=runner,start_worker=False)
    def tearDown(self):self.q.close();self.tmp.cleanup()
    def create(self,**kw):return self.q.create('web','a',kw.get('request','r1'),kw.get('thread','old-thread'),kw.get('text','你好'))
    def test_wait_then_resume_exact_thread_once(self):
        job=self.create();self.q.tick();self.assertEqual(self.q.get(job['id'])['status'],'waiting');self.assertEqual(self.calls,[])
        self.assertIn('占用',self.q.get(job['id'])['waiting_reason'])
        self.reader.status='completed';self.q.update(job['id'],next_attempt_at=0);self.q.tick()
        self.assertEqual(self.q.get(job['id'])['status'],'completed');self.assertEqual(self.calls,['old-thread'])
        self.assertEqual(self.create()['id'],job['id']);self.q.tick();self.assertEqual(len(self.calls),1)
        self.assertGreaterEqual(self.q.get(job['id'])['finished_at'],self.q.get(job['id'])['started_at'])
    def test_unknown_or_abandoned_logs_do_not_block_native_resume(self):
        self.q.runner=lambda job,stop:self.calls.append(job['thread_id']) or '收到了'
        for state in ['unknown','unconfirmed','running']:
            job=self.create(request=state);self.reader.status=state;self.q.tick()
            self.assertEqual(self.q.get(job['id'])['status'],'completed')
        self.assertEqual(self.calls,['old-thread','old-thread','old-thread'])
    def test_busy_retries_are_backed_off_and_cancellable(self):
        job=self.create();self.q.tick()
        first=self.q.get(job['id'])
        self.assertEqual(first['status'],'waiting')
        self.assertGreater(first['next_attempt_at'],first['updated'])
        self.q.tick();self.assertEqual(self.q.get(job['id'])['attempts'],1)
        self.q.cancel('web','a',job['id']);self.reader.status='completed';self.q.tick();self.assertEqual(self.calls,[])
    def test_busy_backoff_preserves_order_within_each_thread(self):
        first=self.create(request='first',text='A')
        second=self.create(request='second',text='B')
        self.create(request='other',thread='other-thread',text='C')
        attempts=[]
        def runner(job,stop):
            attempts.append(job['text'])
            if job['text']=='A' and attempts.count('A')==1:raise SessionBusy('占用')
            self.calls.append(job['text']);return '完成'
        self.q.runner=runner;self.q.tick();self.q.tick()
        self.assertEqual(self.calls,['C'])
        self.assertEqual(self.q.get(second['id'])['status'],'queued')
        self.q.update(first['id'],next_attempt_at=0);self.q.tick();self.q.tick()
        self.assertEqual(self.calls,['C','A','B'])

    def test_later_instruction_reports_real_native_writer_blocker(self):
        first=self.create(request='first',text='older private instruction')
        self.q.tick()
        second=self.create(request='second')
        other=self.create(request='other',thread='another-thread')
        jobs={j['id']:j for j in self.q.list('web','a')}
        self.assertEqual(jobs[second['id']]['queue_position'],2)
        self.assertEqual(jobs[second['id']]['blocked_by'],'native_writer_busy')
        self.assertIn('退出',jobs[second['id']]['waiting_reason'])
        self.assertNotIn('older private instruction',jobs[second['id']]['waiting_reason'])
        self.assertNotIn('blocked_by',jobs[other['id']])
        self.assertEqual(self.q.get(second['id'])['status'],'queued')

    def test_other_source_blocker_is_explained_without_disclosing_content(self):
        self.q.create('web','private-source','private-id','old-thread','private-text')
        self.q.tick()
        second=self.create(request='visible')
        jobs=self.q.list('web','a','old-thread')
        self.assertEqual([j['id'] for j in jobs],[second['id']])
        self.assertEqual(jobs[0]['blocked_by'],'native_writer_busy')
        self.assertNotIn('private',json.dumps(jobs))

    def test_cancelled_blocker_no_longer_appears_in_queue_position(self):
        first=self.create(request='first');self.q.tick()
        second=self.create(request='second')
        self.q.cancel('web','a',first['id'])
        jobs={j['id']:j for j in self.q.list('web','a')}
        self.assertEqual(jobs[second['id']]['queue_position'],1)
        self.assertNotIn('blocked_by',jobs[second['id']])

    def test_retry_claim_does_not_report_old_lock_as_current(self):
        first=self.create();self.q.tick();self.q.claim(first['id'])
        self.assertIsNone(self.q.get(first['id'])['observed_status'])

    def test_pending_handoff_guard_includes_backoff_and_exact_target(self):
        first=self.create()
        self.assertTrue(self.q.has_pending('old-thread'))
        self.q.tick()
        self.assertTrue(self.q.has_pending('old-thread'))
        self.assertFalse(self.q.has_pending('other-thread'))
        self.assertTrue(self.q.has_pending(None))
        self.q.cancel('web','a',first['id'])
        self.assertFalse(self.q.has_pending('old-thread'))
    def test_any_turn_or_item_activity_prevents_automatic_busy_retry(self):
        job=self.q.get(self.create()['id'])
        for event in ['turn.failed','item.updated','turn.future_event']:
            class Process:
                pid=999999
                stdin=io.StringIO()
                stdout=io.StringIO(json.dumps({'type':event})+'\n')
                def poll(self):return 1
                def wait(self,timeout=None):return 1
            def launch(*args,**kwargs):
                kwargs['stderr'].write('already has an active writer\n');return Process()
            with patch('reply_queue.codex_path',return_value='codex.exe'),patch('reply_queue.subprocess.Popen',side_effect=launch):
                with self.assertRaises(RuntimeError) as error:resume_session(job,threading.Event())
            self.assertNotIsInstance(error.exception,SessionBusy)
    def test_active_writer_conflict_is_reported_without_raw_logs(self):
        job=self.q.get(self.create()['id'])
        class Process:
            pid=999999
            stdin=io.StringIO()
            stdout=io.StringIO('')
            def poll(self):return 1
            def wait(self,timeout=None):return 1
        def launch(*args,**kwargs):
            kwargs['stderr'].write('PRIVATE_DETAILS: thread already has an active writer\n')
            return Process()
        with patch('reply_queue.codex_path',return_value='codex.exe'),patch('reply_queue.subprocess.Popen',side_effect=launch):
            with self.assertRaisesRegex(SessionBusy,'占用') as error:
                resume_session(job,threading.Event())
        self.assertNotIn('PRIVATE_DETAILS',str(error.exception))
    def test_cancel_and_target_immutable(self):
        job=self.create();self.q.cancel('web','a',job['id']);self.reader.status='completed';self.q.tick();self.assertEqual(self.calls,[])
        with self.assertRaises(ValueError):self.create(thread='another')
    def test_thread_filtered_list_keeps_older_pending_target_visible(self):
        first=self.create(thread='first')
        for i in range(25):self.create(thread='other',request='other-'+str(i))
        self.assertEqual(self.q.list('web','a','first')[0]['id'],first['id'])
    def test_failed_send_not_reported_as_completed(self):
        job=self.create();self.reader.status='completed'
        def fail(*_):raise RuntimeError('连接失败')
        self.q.runner=fail;self.q.tick();self.assertEqual(self.q.get(job['id'])['status'],'needs_attention')
    def test_permission_marker_pauses_reply_without_replay(self):
        job=self.create();self.reader.status='completed';calls=[]
        def blocked(*_):calls.append(1);return '[需要你处理：权限] 需要管理员授权。'
        self.q.runner=blocked;self.q.tick();self.q.tick()
        saved=self.q.get(job['id'])
        self.assertEqual(saved['status'],'needs_attention');self.assertEqual(saved['result'],'')
        self.assertIn('电脑端',saved['error']);self.assertEqual(calls,[1])
    def test_structured_permission_reply_cannot_be_completed(self):
        job=self.create();self.reader.status='completed'
        self.q.runner=lambda *_:json.dumps({'status':'needs_attention','summary':'[需要你处理：权限] 需要授权','completed_parts':[]})
        self.q.tick();saved=self.q.get(job['id'])
        self.assertEqual(saved['status'],'needs_attention');self.assertIn('电脑端',saved['error'])
    def test_interrupted_sending_not_auto_retried(self):
        job=self.create();self.q.update(job['id'],status='sending');self.q.close()
        self.q=ReplyQueue(Path(self.tmp.name),self.reader,runner=lambda *_:'wrong',start_worker=False)
        self.assertEqual(self.q.get(job['id'])['status'],'needs_attention')
    def test_second_instance_cannot_take_over_live_queue(self):
        job=self.create();self.q.update(job['id'],status='sending')
        second=None
        try:
            try:second=ReplyQueue(Path(self.tmp.name),self.reader,start_worker=False)
            except RuntimeError:pass
            else:self.fail('Second instance must not initialize or recover a live queue')
            self.assertEqual(self.q.get(job['id'])['status'],'sending')
        finally:
            if second:second.close()

if __name__=='__main__':unittest.main()
