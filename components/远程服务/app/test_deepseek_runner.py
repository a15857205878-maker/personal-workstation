import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from adapters import Cancelled, NeedsAttention
from deepseek_runner import run_deepseek, deepseek_command


class DeepSeekRunnerTests(unittest.TestCase):
    def run_fixture(self, events, code=0):
        class Input(io.StringIO):
            def close(self):self.saved=self.getvalue();super().close()
        class Process:
            stdin=Input()
            stdout=io.StringIO('\n'.join(json.dumps(e) for e in events)+'\n')
            pid=123456
            def poll(self):return code
            def wait(self,timeout=None):return code
        process=Process();reports=[];sessions=[];calls=[]
        with tempfile.TemporaryDirectory() as directory:
            workspace=Path(directory)/'workspace';workspace.mkdir()
            def launch(command,**kwargs):calls.append((command,kwargs));return process
            with patch('deepseek_runner.harness_paths',return_value=(Path('harness.exe'),Path('cli.js'))),patch('deepseek_runner.subprocess.Popen',side_effect=launch),patch('deepseek_runner.OwnedProcessGroup'):
                result=run_deepseek({'goal':'原始需求 $(do-not-run)','mode':'task','attachments':['ref.png']},workspace,lambda *args:reports.append(args),threading.Event(),sessions.append)
            self.assertEqual(list(workspace.parent.glob('*.log')),[])
        return result,reports,sessions,calls,process.stdin.saved

    def test_complete_requires_final_and_completed_terminal(self):
        result={'status':'completed','summary':'完成','completed_parts':[{'title':'材料已检查','detail':'已生成结果'}]}
        output,reports,sessions,calls,prompt=self.run_fixture([
            {'type':'session','sessionId':'session-flash'},
            {'type':'thinking','text':'PRIVATE_REASONING'},
            {'type':'tool_call','input':{'token':'PRIVATE_TOKEN'}},
            {'type':'status','phase':'turn_end','reason':{'kind':'completed'}},
            {'type':'final','text':json.dumps(result)}])
        self.assertEqual(output,'完成');self.assertEqual(sessions,['session-flash'])
        self.assertNotIn('PRIVATE',str(reports));self.assertIn('ref.png',prompt)
        self.assertIn('$(do-not-run)',prompt);self.assertNotIn('$(do-not-run)',str(calls[0][0]))
        self.assertNotIn('--session-id',calls[0][0]);self.assertIn('--json',calls[0][0])

    def test_missing_final_bad_terminal_and_error_are_not_success(self):
        for events in ([],[{'type':'final','text':'hello'}],
                       [{'type':'final','text':'{}','reason':{'kind':'error'}}],
                       [{'type':'error','message':'PRIVATE_TOKEN'}]):
            with self.assertRaises(NeedsAttention) as caught:self.run_fixture(events)
            self.assertNotIn('PRIVATE',str(caught.exception))

    def test_cancelled_before_start_does_not_launch(self):
        stop=threading.Event();stop.set()
        with patch('deepseek_runner.subprocess.Popen') as launch:
            with self.assertRaises(Cancelled):run_deepseek({'goal':'test'},Path('.'),lambda *args:None,stop,lambda *args:None)
        launch.assert_not_called()

    def test_permission_error_shows_safe_actionable_notice(self):
        with self.assertRaises(NeedsAttention) as caught:
            self.run_fixture([{'type':'error','message':'EACCES: permission denied PRIVATE_KEY'}],code=1)
        self.assertIn('需要你处理：权限',str(caught.exception))
        self.assertIn('电脑端',str(caught.exception));self.assertNotIn('PRIVATE',str(caught.exception))

    def test_review_not_claimed_read_only(self):
        with self.assertRaises(NeedsAttention):run_deepseek({'goal':'review','mode':'review'},Path('.'),lambda *args:None,threading.Event(),lambda *args:None)

    def test_command_pins_patch_without_resuming_old_session(self):
        with patch('deepseek_runner.harness_paths',return_value=(Path('harness.exe'),Path('cli.js'))):
            command=deepseek_command()
        self.assertIn('headless',command);self.assertIn('--patch',command)
        self.assertEqual(command[-1],'-')

    def test_cancel_stops_only_this_invocation(self):
        ended=threading.Event();stop=threading.Event()
        class Output:
            def __iter__(self):
                ended.wait(3);return iter(())
            def close(self):pass
        class Process:
            stdin=io.StringIO();stdout=Output();pid=424242
            def poll(self):return -1 if ended.is_set() else None
            def wait(self,timeout=None):ended.wait(3);return -1
            def kill(self):ended.set()
            def terminate(self):ended.set()
        timer=threading.Timer(.05,stop.set)
        group=type('Group',(),{'terminate':lambda self:ended.set(),'close':lambda self:None})()
        process=Process()
        with tempfile.TemporaryDirectory() as directory,patch('deepseek_runner.harness_paths',return_value=(Path('harness.exe'),Path('cli.js'))),patch('deepseek_runner.subprocess.Popen',return_value=process),patch('deepseek_runner.OwnedProcessGroup',return_value=group) as owner:
            timer.start()
            with self.assertRaises(Cancelled):run_deepseek({'goal':'测试'},Path(directory),lambda *args:None,stop,lambda *args:None)
            timer.join()
        owner.assert_called_once_with(process)
