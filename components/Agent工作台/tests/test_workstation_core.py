import io
import json
from pathlib import Path
import sys
import types
import tempfile
import time
import zipfile
import queue
import subprocess
import threading
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workstation_core import WorkstationCore,ToolProcess,TOOL_ACTIONS

class FakeBridge:
    def __init__(self):self.calls=[];self.station_window=None
    def call(self,action,payload):
        self.calls.append((action,payload))
        if action=='station_list':data=[{'id':'a'*32,'title':'Task','status':'结果待确认'}]
        elif action=='station_get':data={'id':'a'*32,'title':'Task','files':[{'name':'result.txt','size':7}]}
        elif action=='api_bootstrap':data={'sessions':[{'id':'b'*32,'title':'Collaboration','status':'completed'}]}
        else:raise AssertionError(action)
        return {'ok':True,'data':data}

class CoreTests(unittest.TestCase):
    def test_worker_eof_after_command_blocks_followup_and_marks_jobs_uncertain(self):
        p=ToolProcess();p.process=Mock();p.process.poll.return_value=None;p.process.stdin=io.StringIO()
        p.jobs={'job':{'status':'running'}};p.responses.put(None);p.responses.put(None)
        with self.assertRaises(ValueError):p.call('pack_start',{'files':['chosen']})
        with self.assertRaisesRegex(ValueError,'连接已中断'):p.call('pack_start',{'files':['chosen']})
        self.assertEqual(len(p.process.stdin.getvalue().splitlines()),1)
        self.assertEqual(p.jobs['job']['status'],'uncertain')

    def test_readonly_summary_endpoints_reject_unexpected_payload(self):
        b=FakeBridge();c=WorkstationCore(b,Mock())
        for action in ('workstation_overview','workstation_artifacts','workstation_diagnostics'):
            with self.assertRaises(ValueError):c.call(action,{'unexpected':'value'})
        self.assertFalse(b.calls)

    def test_late_eof_or_invalid_reply_never_recovers_as_success(self):
        for reply in (None,'not-json','[]'):
            with self.subTest(reply=reply):
                p=ToolProcess();p.process=Mock();p.process.poll.return_value=None
                p.pending=True;p.jobs={'job':{'status':'running'}};p.responses.put(reply)
                p._recover()
                self.assertTrue(p.disconnected)
                self.assertEqual(p.jobs['job']['status'],'uncertain')
                with self.assertRaisesRegex(ValueError,'连接已中断'):p.call('wheel_draw',{})
                p.process.stdin.write.assert_not_called()

    def test_remote_first_calls_share_one_adapter(self):
        c=WorkstationCore(FakeBridge(),Mock());barrier=threading.Barrier(2);created=[];results=[]
        def construct():
            value=Mock();value.start.return_value={'online':True};created.append(value);time.sleep(.03);return value
        def run():
            barrier.wait();results.append(c.call('workstation_remote_start',{}))
        with patch('remote_surface.RemoteSurface',side_effect=construct):
            threads=[threading.Thread(target=run) for _ in range(2)]
            for thread in threads:thread.start()
            for thread in threads:thread.join(2)
        self.assertEqual(len(results),2)
        self.assertEqual(len(created),1)

    def test_overview_and_artifacts_only_query_existing_engine(self):
        b=FakeBridge();tools=Mock();c=WorkstationCore(b,tools)
        overview=c.call('workstation_overview',{})
        self.assertEqual(overview['counts']['attention'],1)
        self.assertEqual(overview['counts']['collaborations'],1)
        artifacts=c.call('workstation_artifacts',{})
        self.assertEqual(artifacts['items'][0]['name'],'result.txt')
        self.assertNotIn('path',artifacts['items'][0])
        self.assertEqual(set(a for a,p in b.calls),{'station_list','station_get','api_bootstrap'})
        tools.call.assert_not_called()
    def test_partial_read_failure_is_visible(self):
        b=FakeBridge();original=b.call
        b.call=lambda action,payload: {'ok':False,'error':'unavailable'} if action=='api_bootstrap' else original(action,payload)
        result=WorkstationCore(b,Mock()).overview()
        self.assertEqual(len(result['tasks']),1)
        self.assertEqual(result['warnings'],['unavailable'])
    def test_tool_boundary_never_accepts_pet_or_arbitrary_launch(self):
        c=WorkstationCore(FakeBridge(),ToolProcess())
        for action in ('pet_launch','launch_tool','open_folder','unknown'):
            with self.assertRaises(ValueError):c.call('workstation_tool_call',{'action':action,'payload':{}})
        with self.assertRaises(ValueError):c.call('workstation_tool_call',{'action':'wheel_get','path':'private'})
    def test_worker_dialog_callback_and_result(self):
        window=Mock();window.create_file_dialog.return_value=['C:/chosen.txt']
        p=ToolProcess(lambda:window)
        p.process=Mock();p.process.poll.return_value=None
        p.process.stdin=io.StringIO();p.process.stdout=io.StringIO()
        p.responses.put(json.dumps({'event':'dialog','kind':10,'options':{'allow_multiple':True}}))
        p.responses.put(json.dumps({'ok':True,'data':{'files':[{'name':'chosen.txt'}]}}))
        value=p.call('pick_files',{})
        self.assertEqual(value['files'][0]['name'],'chosen.txt')
        self.assertEqual(json.loads(p.process.stdin.getvalue().splitlines()[1]),{'selection':['C:/chosen.txt']})
        window.create_file_dialog.assert_called_once_with(10,allow_multiple=True)
    def test_busy_refreshes_job_status_after_completion(self):
        p=ToolProcess();p.process=Mock();p.process.poll.return_value=None
        p.jobs['job']={'status':'running'}
        def call(action,payload):p.jobs['job']={'status':'completed'}
        p.call=call
        self.assertFalse(p.busy())
    def test_worker_command_is_fixed_and_isolated(self):
        p=ToolProcess()
        with patch('workstation_core.subprocess.Popen') as spawn:
            p._start()
        args=spawn.call_args.args[0]
        self.assertEqual(len(args),2)
        self.assertEqual(Path(args[1]).name,'tool_worker.py')
        self.assertNotIn('shell',spawn.call_args.kwargs)
    def test_response_timeout_never_replays_uncertain_mutation(self):
        p=ToolProcess();p.process=Mock();p.process.poll.return_value=None
        p.responses=Mock();p.responses.get.side_effect=queue.Empty;p.responses.get_nowait.side_effect=queue.Empty
        with self.assertRaisesRegex(ValueError,'回执超时'):p.call('pack_start',{'files':['chosen']})
        with self.assertRaisesRegex(ValueError,'未重复执行'):p.call('pack_start',{'files':['chosen']})
        self.assertEqual(p.process.stdin.write.call_count,1)
    def test_late_dialog_is_cancelled_before_accepting_another_command(self):
        p=ToolProcess();p.process=Mock();p.process.poll.return_value=None;p.process.stdin=io.StringIO();p.pending=True
        p.responses.put(json.dumps({'event':'dialog','kind':10,'options':{}}))
        with self.assertRaisesRegex(ValueError,'未重复执行'):p.call('wheel_draw',{})
        self.assertTrue(p.pending)
        self.assertEqual(json.loads(p.process.stdin.getvalue()),{'selection':None})
        p.responses.put(json.dumps({'ok':True,'data':{'cancelled':True}}))
        p._recover();self.assertFalse(p.pending)
    def test_busy_never_releases_close_guard_on_status_timeout(self):
        p=ToolProcess();p.process=Mock();p.process.poll.return_value=None;p.jobs={'j':{'status':'running'}}
        def timeout(*a):p.pending=True;raise ValueError('timeout')
        p.call=timeout
        self.assertTrue(p.busy())
    def test_late_dialog_broken_pipe_becomes_uncertain_without_closing_exception(self):
        for still_running in (False,True):
            with self.subTest(still_running=still_running):
                p=ToolProcess();p.process=Mock();p.process.poll.return_value=None if still_running else 1
                p.process.stdin.write.side_effect=BrokenPipeError('worker exited')
                p.pending=True;p.jobs={'job':{'status':'running'}}
                p.responses.put(json.dumps({'event':'dialog','kind':10,'options':{}}))
                self.assertEqual(p.busy(),still_running)
                self.assertEqual(p.jobs['job']['status'],'uncertain')
                self.assertTrue(p.disconnected)
                with self.assertRaisesRegex(ValueError,'连接已中断'):p.call('pack_start',{'files':['old']})
                self.assertEqual(p.process.stdin.write.call_count,1)
    def test_close_timeout_does_not_close_pipe_while_reader_may_block(self):
        p=ToolProcess();process=Mock();p.process=process;process.poll.return_value=None
        release=threading.Event();finished=threading.Event();calls=[]
        def wait(timeout=None):
            calls.append(timeout)
            if timeout is not None:raise subprocess.TimeoutExpired('owned worker',timeout)
            release.wait(2);finished.set();return 0
        process.wait.side_effect=wait
        p.close()
        process.stdout.close.assert_not_called()
        with self.assertRaisesRegex(ValueError,'正在退出'):p.call('wheel_get',{})
        release.set();self.assertTrue(finished.wait(2))
    def test_real_isolated_worker_picker_and_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for relative in ('个人工具中心新版/data','个人工具中心/data','游戏管家/data'):(root/relative).mkdir(parents=True)
            source=root/'notes.txt';source.write_text('isolated tool contents',encoding='utf-8')
            out=root/'zip-output';out.mkdir()
            window=Mock();window.create_file_dialog.side_effect=[[str(source)],[str(out)]]
            worker=ToolProcess(lambda:window,test_root=root)
            try:
                data=worker.call('bootstrap',{})
                self.assertIn('games',data)
                with self.assertRaises(ValueError):worker.call('pack_start',{'files':[str(source)]})
                picked=worker.call('pick_files',{})
                self.assertEqual(picked['files'][0]['name'],'notes.txt')
                output=worker.call('pick_output',{})['path']
                job=worker.call('pack_start',{'files':[str(source)],'output_dir':output})['job']
                deadline=time.monotonic()+10
                while job['status'] in ('queued','running') and time.monotonic()<deadline:
                    time.sleep(.05);job=worker.call('job_status',{'id':job['id']})['job']
                self.assertEqual(job['status'],'completed',job)
                with zipfile.ZipFile(job['result_path']) as archive:self.assertEqual(archive.read('notes.txt').decode(),'isolated tool contents')
                self.assertFalse(worker.busy())
                worker.call('wheel_add',{'name':'隔离候选'})
                self.assertTrue(any(e['name']=='隔离候选' for e in worker.call('wheel_get',{})['wheel']['entries']))
            finally:worker.close()

if __name__=='__main__':unittest.main()
