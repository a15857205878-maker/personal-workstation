import tempfile,unittest,threading,json
from pathlib import Path
from deepseek_resume import DeepSeekReplies
class Reader:
    def __init__(self):self.allowed=True
    def resolve(self,identifier):
        if not self.allowed:raise ValueError('当前会话只读')
        return {'id':identifier,'title':'公开标题','cwd':'PRIVATE_CWD','native_id':'session-original','model':{'provider':'deepseek-official','model':'deepseek-test'}}
class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.reader=Reader();self.calls=[]
        self.queue=DeepSeekReplies(Path(self.temp.name),self.reader,runner=lambda job,stop:self.calls.append(job.copy()) or '原会话回复',start_worker=False)
    def tearDown(self):self.queue.close();self.temp.cleanup()
    def create(self,rid='one'):return self.queue.create('web','phone',rid,'a'*64,'继续分析')
    def test_receipt_and_single_inflight_then_completed_without_native_id_exposure(self):
        a=self.create();self.assertEqual(a,self.create())
        with self.assertRaises(ValueError):self.create('two')
        self.queue.tick();job=self.queue.list('web','phone','a'*64)[0]
        self.assertEqual(job['status'],'completed');self.assertEqual(job['result'],'原会话回复');self.assertEqual(len(self.calls),1)
        self.assertNotIn('PRIVATE_CWD',json.dumps(job));self.assertNotIn('session-original',json.dumps(job))
    def test_restart_never_replays_uncertain_sending(self):
        job=self.create();self.queue.update(job['id'],status='sending');self.queue.close()
        self.queue=DeepSeekReplies(Path(self.temp.name),self.reader,runner=lambda job,stop:self.calls.append(job),start_worker=False)
        self.queue.tick();self.assertEqual(self.queue.list('web','phone')[0]['status'],'needs_attention');self.assertEqual(self.calls,[])

    def test_readonly_and_attachments_are_rejected_without_execution(self):
        self.reader.allowed=False
        with self.assertRaises(ValueError):self.create()
        with self.assertRaises(ValueError):self.queue.create('web','phone','two','a'*64,'继续',['image.png'])
        self.assertEqual(self.calls,[])
    def test_failure_never_retries_and_cannot_be_cancelled_by_other_source(self):
        a=self.create()
        with self.assertRaises(KeyError):self.queue.cancel('web','other',a['id'])
        self.queue.runner=lambda job,stop:(_ for _ in ()).throw(RuntimeError('会话占用，未确认送达'))
        self.queue.tick();self.queue.tick();self.assertEqual(self.queue.list('web','phone')[0]['status'],'needs_attention')

if __name__=='__main__':unittest.main()

class RunnerContractTests(unittest.TestCase):
    def test_exact_native_session_and_original_model_are_used_not_flash_defaults(self):
        import io
        from unittest.mock import Mock,patch
        from deepseek_resume import resume
        with tempfile.TemporaryDirectory() as directory:
            reader=Reader();reader.resolve=lambda identifier:{'cwd':directory,'native_id':'session-exact','model':{'provider':'original-provider','model':'original-model','reasoningEffort':'high'}}
            process=Mock();process.stdin=io.StringIO();process.stdout=io.StringIO('\n'.join(json.dumps(e) for e in [{'type':'session','sessionId':'session-exact'},{'type':'final','text':'真实公开回复','reason':{'kind':'completed'}}]));process.wait.return_value=0
            with patch('deepseek_resume.harness_paths',return_value=(Path('fixture.exe'),Path('cli.js'))),patch('deepseek_resume.subprocess.Popen',return_value=process) as spawn,patch('deepseek_resume.OwnedProcessGroup'):
                self.assertEqual(resume(reader,{'thread_id':'a'*64,'cwd':directory,'output':str(Path(directory)/'result.txt'),'text':'继续'},threading.Event()),'真实公开回复')
                args=spawn.call_args.args[0];self.assertEqual(args[args.index('--session-id')+1],'session-exact');self.assertEqual(spawn.call_args.kwargs['cwd'],directory)
                config=json.loads((Path(directory)/'resume.patch.yml').read_text());self.assertEqual(config[1]['config'],{'provider':'original-provider','model':'original-model','reasoningEffort':'high'})

class HTTPResumeTests(unittest.TestCase):
    def test_paired_exact_session_send_and_no_request_replay(self):
        import http.client,time
        from transfer import create_server
        with tempfile.TemporaryDirectory() as folder:
            server=create_server('127.0.0.1',0,Path(folder)/'photos','test-pair')
            calls=[]
            def read(mode,identifier='',before=None):
                if mode=='resolve':return {'allowed':True,'title':'测试','id':identifier,'native_id':'session-fixed','cwd':folder,'model':{'provider':'deepseek-official','model':'deepseek-test'}}
                return {'title':'测试','status':'completed','status_hint':'结束','messages':[]}
            server.deepseek_history._read=read
            server.deepseek_replies.runner=lambda job,stop:calls.append(job.copy()) or '接着分析的测试回复'
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def request(path,body=None):
                client=http.client.HTTPConnection(*server.server_address,timeout=5)
                client.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,{'Content-Type':'application/json'})
                r=client.getresponse();result=(r.status,json.loads(r.read()));client.close();return result
            try:
                payload={'source_id':'phone','session_id':'a'*64,'text':'继续','request_id':'resume-test'}
                self.assertEqual(request('/api/bot/deepseek/reply',payload)[0],403)
                self.assertEqual(request('/api/bot/deepseek/reply?token=test-pair',{**payload,'cwd':folder})[0],400)
                code,value=request('/api/bot/deepseek/reply?token=test-pair',payload);self.assertEqual(code,200)
                code,repeat=request('/api/bot/deepseek/reply?token=test-pair',payload);self.assertEqual(value['job']['id'],repeat['job']['id'])
                until=time.monotonic()+5
                while not calls and time.monotonic()<until:time.sleep(.05)
                self.assertEqual(len(calls),1)
                code,view=request('/api/bot/deepseek/conversation?token=test-pair&source_id=phone&session_id='+'a'*64)
                self.assertEqual(code,200);self.assertTrue(view['resume_supported']);self.assertEqual(view['jobs'][0]['result'],'接着分析的测试回复')
                self.assertNotIn(folder,json.dumps(view));self.assertNotIn('session-fixed',json.dumps(view))
            finally:server.shutdown();server.server_close();thread.join()
