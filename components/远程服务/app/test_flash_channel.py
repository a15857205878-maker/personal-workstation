from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from adapters import RUNNERS
from bot_tasks import create_bot_task
from conversation_view import conversation_detail
from tasks import TaskManager


class FlashChannelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.manager=TaskManager(Path(self.tmp.name),start_worker=False)

    def tearDown(self):
        self.manager.close();self.tmp.cleanup()

    def test_agent_explicit_and_codex_still_default(self):
        codex=create_bot_task(self.manager,{'text':'默认','request_id':'codex'})
        flash=create_bot_task(self.manager,{'text':'Flash测试','request_id':'flash','agent':'deepseek-flash'})
        self.assertEqual(codex['agent'],'codex');self.assertEqual(flash['agent'],'deepseek-flash')
        with self.assertRaises(ValueError):create_bot_task(self.manager,{'text':'Flash测试','request_id':'flash','agent':'codex'})

    def test_unsupported_model_and_review_rejected(self):
        for payload in ({'agent':'deepseek-v4-pro'},{'agent':[]},{'agent':'deepseek-flash','mode':'review','attachments':['x.png']}):
            with self.assertRaises(ValueError):create_bot_task(self.manager,dict(text='测试',request_id='bad',**payload))

    def test_provider_session_cannot_become_codex_thread(self):
        def fake(task,workspace,report,stop,remote):
            remote('session-flash-only');return 'Flash结果'
        with patch.dict(RUNNERS,{'deepseek-flash':fake,'codex':fake,'demo':fake}):
            task=create_bot_task(self.manager,{'text':'测试','request_id':'run','agent':'deepseek-flash'})
            self.manager.start()
            for _ in range(100):
                current=self.manager.get(task['id'])
                if current['status']=='completed':break
                time.sleep(.01)
        self.assertEqual(current['agent'],'deepseek-flash')
        self.assertEqual(current['remote_session'],'')
        self.assertEqual(current['provider_session'],'session-flash-only')
        reader=Mock();replies=Mock()
        result=conversation_detail(self.manager,reader,replies,'phone',task_id=task['id'])
        self.assertEqual(result['provider'],'deepseek-flash');self.assertIsNone(result['thread_id'])
        self.assertFalse(result['can_reply']);self.assertIn('新建',result['reply_hint'])
        reader.get.assert_not_called();reader.history.assert_not_called();replies.list.assert_not_called()
