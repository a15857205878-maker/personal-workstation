import unittest
import json
import io
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
from adapters import parse_codex_event, parse_codex_result, run_codex, NeedsAttention


class AdapterTests(unittest.TestCase):
    def test_standalone_codex_env_drops_desktop_routing_but_keeps_permissions(self):
        from adapters import codex_cli_env
        source={'PATH':'existing','CODEX_WINDOWS_REGISTERED_CORE':'1','CODEX_APP_TOOLS_PIPE_PATH':'desktop-pipe','CODEX_SESSION_ID':'desktop-session','CODEX_PERMISSION_PROFILE':'keep-profile','CODEX_SANDBOX_NETWORK_DISABLED':'1','CODEX_WINDOWS_SANDBOX_PACKAGE_FAMILY':'keep-package'}
        cleaned=codex_cli_env(source)
        self.assertNotIn('CODEX_WINDOWS_REGISTERED_CORE',cleaned);self.assertNotIn('CODEX_APP_TOOLS_PIPE_PATH',cleaned);self.assertNotIn('CODEX_SESSION_ID',cleaned)
        for key in ['PATH','CODEX_PERMISSION_PROFILE','CODEX_SANDBOX_NETWORK_DISABLED','CODEX_WINDOWS_SANDBOX_PACKAGE_FAMILY']:self.assertEqual(cleaned[key],source[key])
        self.assertIn('CODEX_WINDOWS_REGISTERED_CORE',source)

    def test_failed_process_does_not_publish_raw_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            class Process:
                pid = 999999
                stdin = io.StringIO()
                stdout = io.StringIO('{"type":"item.completed","item":{"type":"reasoning","text":"PRIVATE_TOOL_MARKER"}}\n')
                def poll(self): return 1
                def wait(self, timeout=None): return 1
            with patch('adapters.codex_path', return_value='codex.exe'), patch('adapters.subprocess.Popen', return_value=Process()):
                with self.assertRaises(NeedsAttention) as error:
                    run_codex({'goal': '测试'}, Path(tmp), lambda *_: None, threading.Event(), lambda _: None)
            self.assertNotIn('PRIVATE_TOOL_MARKER', str(error.exception))

    def test_stale_final_cannot_complete_a_new_codex_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace=Path(tmp)/'workspace';workspace.mkdir()
            (workspace.parent/'final.txt').write_text(json.dumps({'status':'completed','summary':'old result','completed_parts':[]}))
            class Process:
                pid=999999
                stdin=io.StringIO()
                stdout=io.StringIO('{"type":"turn.completed"}\n')
                def poll(self):return 0
                def wait(self,timeout=None):return 0
            with patch('adapters.codex_path',return_value='codex.exe'),patch('adapters.subprocess.Popen',return_value=Process()),self.assertRaises(NeedsAttention):
                run_codex({'goal':'new task'},workspace,lambda *x:None,threading.Event(),lambda x:None)

    def test_codex_maps_session_and_agent_report_only(self):
        reports, sessions = [], []
        report = lambda title, text: reports.append((title, text))
        parse_codex_event({'type': 'thread.started', 'thread_id': 'remote-123'}, report, sessions.append)
        parse_codex_event({'type': 'item.completed', 'item': {'type': 'reasoning', 'text': 'private reasoning'}}, report, sessions.append)
        parse_codex_event({'type': 'item.completed', 'item': {'type': 'command_execution', 'command': 'secret command'}}, report, sessions.append)
        parse_codex_event({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '报告已保存。'}}, report, sessions.append)
        self.assertEqual(sessions, ['remote-123'])
        self.assertEqual(reports, [])
        parse_codex_event({'type': 'item.completed', 'item': {'type': 'file_change', 'status': 'completed', 'changes': [{'path': 'report.md'}]}}, report, sessions.append)
        self.assertEqual(reports, [('文件修改已完成', 'report.md')])

    def test_quota_or_execution_error_requires_attention(self):
        with self.assertRaisesRegex(NeedsAttention, 'usage limit'):
            parse_codex_event({'type': 'turn.failed', 'error': {'message': 'usage limit reached'}}, lambda *_: None, lambda _: None)

    def test_agent_end_is_not_automatically_goal_completed(self):
        reports = []
        result = {'status': 'needs_attention', 'summary': '缺少读取文件的权限', 'completed_parts': [{'title': '已创建目录', 'detail': '目录已保存'}]}
        with self.assertRaisesRegex(NeedsAttention, '缺少读取'):
            parse_codex_result(json.dumps(result), lambda title, detail: reports.append((title, detail)))
        self.assertEqual(reports, [('已创建目录', '目录已保存')])
        result['status'] = 'completed'
        result['summary'] = '目标已完成'
        self.assertEqual(parse_codex_result(json.dumps(result), lambda *_: None), '目标已完成')

    def test_invalid_final_result_is_not_success(self):
        for text in ['not JSON', '[]', '{"status":"completed"}']:
            with self.assertRaises(NeedsAttention):
                parse_codex_result(text, lambda *_: None)

    def test_subprocess_adapter_with_structured_result_and_real_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / 'workspace'
            workspace.mkdir()
            reports, sessions = [], []
            class Process:
                pid = 999999
                stdin = io.StringIO()
                stdout = io.StringIO('\n'.join(json.dumps(event) for event in [
                    {'type': 'thread.started', 'thread_id': 'fixture-session'},
                    {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '我将创建文件。'}},
                    {'type': 'item.completed', 'item': {'type': 'command_execution', 'exit_code': 0}},
                    {'type': 'turn.completed'},
                ]))
                def poll(self): return 0
                def wait(self, timeout=None): return 0
            def launch(command, **kwargs):
                self.assertIsInstance(kwargs.get('env'),dict)
                self.assertNotIn('CODEX_WINDOWS_REGISTERED_CORE',kwargs['env'])
                self.assertIn('--output-schema', command)
                self.assertEqual(command[command.index('--sandbox')+1], 'workspace-write')
                (workspace / 'result.txt').write_text('real fixture result')
                final = Path(command[command.index('-o')+1])
                final.write_text(json.dumps({'status': 'completed', 'summary': '结果文件已生成', 'completed_parts': [{'title': '已验证文件', 'detail': 'result.txt'}]}), encoding='utf-8')
                return Process()
            with patch('adapters.codex_path', return_value='codex.exe'), patch('adapters.subprocess.Popen', side_effect=launch):
                result = run_codex({'goal': '生成文件'}, workspace, lambda title, detail: reports.append((title, detail)), threading.Event(), sessions.append)
            self.assertEqual(result, '结果文件已生成')
            self.assertEqual(sessions, ['fixture-session'])
            self.assertTrue(any(title == '成果文件已生成' for title, _ in reports))
            self.assertFalse(any('我将' in detail for _, detail in reports))
