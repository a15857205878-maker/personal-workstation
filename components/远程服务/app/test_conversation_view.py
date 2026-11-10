import unittest
from unittest.mock import Mock
from conversation_view import conversation_detail


class ConversationViewTests(unittest.TestCase):
    def setUp(self):
        self.task={'id':'task-one','title':'手机目标','goal':'手机目标','agent':'codex','status':'completed',
                   'updated':100,'remote_session':'thread-one','completed_parts':[],'result':'完成'}
        self.tasks=Mock();self.tasks.get.return_value=self.task;self.tasks.list.return_value=[self.task]
        self.reader=Mock();self.reader.get.return_value={'id':'thread-one','title':'电脑命名的会话'}
        self.reader.history.return_value={'id':'thread-one','messages':[],'next_before':None,'status':'completed','status_hint':'日志记录本轮已结束'}
        self.replies=Mock();self.replies.list.return_value=[]

    def detail(self,**changes):
        return conversation_detail(self.tasks,self.reader,self.replies,'phone',**changes)

    def test_new_task_pending_session_can_show_progress_without_enabling_reply(self):
        self.task.update(remote_session='',status='queued')
        result=self.detail(task_id='task-one')
        self.assertEqual(result['task']['id'],'task-one')
        self.assertEqual(result['status'],'queued')
        self.assertIsNone(result['thread_id'])
        self.assertFalse(result['can_reply'])
        self.reader.history.assert_not_called()

    def test_existing_thread_links_own_task_and_scopes_jobs_to_source_and_target(self):
        result=self.detail(thread_id='thread-one',before=12)
        self.assertEqual(result['task']['id'],'task-one')
        self.assertEqual(result['title'],'电脑命名的会话')
        self.assertTrue(result['can_reply'])
        self.reader.history.assert_called_once_with('thread-one',before=12)
        self.replies.list.assert_called_once_with('web','phone','thread-one')

    def test_target_mismatch_is_rejected_before_reading_other_history(self):
        with self.assertRaises(ValueError):self.detail(task_id='task-one',thread_id='different')
        self.reader.history.assert_not_called()

    def test_index_not_ready_keeps_task_progress(self):
        self.reader.get.side_effect=KeyError('not indexed')
        result=self.detail(task_id='task-one')
        self.assertEqual(result['task']['id'],'task-one')
        self.assertIsNone(result['history'])
        self.assertFalse(result['can_reply'])
        self.assertTrue(result['history_error'])

    def test_body_error_does_not_hide_received_task_or_reply_status(self):
        self.reader.history.side_effect=OSError('private diagnostic')
        self.replies.list.return_value=[{'status':'waiting','updated':200,'waiting_reason':'仍被占用'}]
        result=self.detail(task_id='task-one')
        self.assertEqual(result['status'],'waiting')
        self.assertEqual(result['status_hint'],'仍被占用')
        self.assertTrue(result['can_reply'])
        self.assertNotIn('private diagnostic',result['history_error'])

    def test_running_initial_task_takes_precedence_over_queued_followup(self):
        self.task['status']='running'
        self.replies.list.return_value=[{'status':'waiting','updated':200}]
        self.assertEqual(self.detail(task_id='task-one')['status'],'running')

    def test_sending_instruction_is_not_hidden_by_a_newer_queued_instruction(self):
        self.replies.list.return_value=[{'status':'queued','updated':300},{'status':'sending','updated':200}]
        result=self.detail(task_id='task-one')
        self.assertEqual(result['status'],'running')
        self.assertIn('执行',result['status_hint'])

    def test_missing_pure_history_target_and_invalid_arguments(self):
        self.tasks.list.return_value=[];self.reader.get.side_effect=KeyError('missing')
        with self.assertRaises(KeyError):self.detail(thread_id='missing')
        for target in [{},{'task_id':'task-one','before':-1},{'thread_id':[]}]:
            with self.assertRaises(ValueError):self.detail(**target)
