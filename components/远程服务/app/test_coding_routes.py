import unittest,tempfile,threading
from pathlib import Path
from unittest.mock import patch
from coding_runner import coding_route,run_coding
from adapters import NeedsAttention
from tasks import TaskManager
class CodingRoutes(unittest.TestCase):
 def test_simple_web_and_negated_backend_are_static(self):
  for goal in ['帮我生成一个可以查看日历的简单网页','做一个番茄钟网页','纯前端待办页面，数据存浏览器，不需要登录和数据库','设计登录页面，只演示界面','日历网页，不需要后端接口','展示API文档的静态页面','纯前端迷你日历，无后端、无登录、无数据库']:
   with self.subTest(goal=goal):self.assertEqual(coding_route({'goal':goal,'project_kind':'web'}),'static')
 def test_explicit_backend_and_local_tools_keep_fullstack(self):
  for goal in ['做一个有登录功能的网站','需要后端接口和数据库的预算应用','做个网站，调用天气API','不需要登录，但需要数据库保存多人数据']:
   with self.subTest(goal=goal):self.assertEqual(coding_route({'goal':goal,'project_kind':'web'}),'fullstack')
  self.assertEqual(coding_route({'goal':'做一个日历','project_kind':'local-tool'}),'fullstack')
  self.assertEqual(coding_route({'goal':'无障碍网页，需要用户登录','project_kind':'web'}),'fullstack')
 def test_negative_scope_and_browser_storage_do_not_change_intent(self):
  cases={'不需要登录而是需要数据库保存日程':'fullstack','日历网页，不需后端':'static','不要纯前端，需要后端和数据库':'fullstack','纯前端日历，用IndexedDB数据库保存日程':'static','日历网页，使用浏览器本地数据库 IndexedDB':'static'}
  for goal,route in cases.items():
   with self.subTest(goal=goal):self.assertEqual(coding_route({'goal':goal,'project_kind':'web'}),route)
 def test_conflicting_static_and_server_requirements_do_not_launch(self):
  with self.assertRaisesRegex(ValueError,'冲突'):coding_route({'goal':'纯前端，但是需要服务器数据库','project_kind':'web'})
 def test_static_pipeline_never_dispatches_backend_or_requires_api_contract(self):
  with tempfile.TemporaryDirectory() as raw:
   root=Path(raw);events=[];metadata=[];calls=[]
   def frontend(task,workspace,report,stop,remote):
    calls.append('deepseek');self.assertIn('不创建backend/',task['goal']);self.assertNotIn('先读取docs/API.md与实际backend/',task['goal']);(root/'frontend').mkdir();(root/'frontend/index.html').write_text('<main>calendar</main>');return 'front ready'
   def review(task,workspace,report,stop,remote):
    calls.append('codex');self.assertIn('纯前端验收',task['goal']);(root/'docs').mkdir();(root/'docs/验收报告.md').write_text('mock verified');(root/'README.md').write_text('open frontend/index.html');return 'verified'
   with patch('deepseek_runner.run_deepseek',frontend),patch('adapters.run_codex',review):result=run_coding({'goal':'简单日历网页','project_kind':'web','code_route':'static','mode':'task','attachments':[]},root,lambda *args:events.append(args),threading.Event(),metadata.append)
   self.assertEqual(calls,['deepseek','codex']);self.assertFalse((root/'backend').exists());self.assertFalse((root/'docs/API.md').exists());self.assertIn('2',result);self.assertEqual(metadata[-1]['code_stage'],'completed')
 def test_missing_static_entry_stops_before_codex_review(self):
  with tempfile.TemporaryDirectory() as raw:
   root=Path(raw)
   def frontend(task,workspace,*args):
    (root/'frontend').mkdir();(root/'frontend/readme.txt').write_text('no webpage');return 'claimed ready'
   with patch('deepseek_runner.run_deepseek',frontend),patch('adapters.run_codex') as review,self.assertRaises(NeedsAttention):
    run_coding({'goal':'简单日历网页','project_kind':'web','code_route':'static','mode':'task','attachments':[]},root,lambda *args:None,threading.Event(),lambda *args:None)
   review.assert_not_called()
 def test_conflict_fails_before_workspace_and_queue_are_created(self):
  with tempfile.TemporaryDirectory() as raw:
   manager=TaskManager(Path(raw),start_worker=False)
   try:
    with self.assertRaisesRegex(ValueError,'冲突'):manager.create({'agent':'codex-deepseek-code','goal':'纯前端，但要数据库','client_id':'conflict'})
    self.assertEqual(manager.list(),[]);self.assertFalse((manager.root/'代码项目').exists());self.assertTrue(manager.queue.empty())
   finally:manager.close()
 def test_existing_receipt_is_not_reclassified_under_new_rules(self):
  with tempfile.TemporaryDirectory() as raw:
   manager=TaskManager(Path(raw),start_worker=False)
   try:
    task=manager.create({'agent':'codex-deepseek-code','goal':'日历网页','client_id':'legacy'})
    manager.update(task['id'],goal='纯前端，但需要数据库',code_route=None,code_plan=None)
    restored=manager.create({'agent':'codex-deepseek-code','goal':'纯前端，但需要数据库','client_id':'legacy'})
    self.assertEqual(restored['id'],task['id']);self.assertIsNone(restored['code_route']);self.assertEqual(len(manager.list()),1)
   finally:manager.close()
 def test_new_task_records_route_without_touching_other_records(self):
  with tempfile.TemporaryDirectory() as raw:
   manager=TaskManager(Path(raw),start_worker=False)
   try:
    task=manager.create({'agent':'codex-deepseek-code','goal':'简单日历网页','client_id':'static','project_kind':'web'});self.assertEqual(task['code_route'],'static');self.assertEqual(task['code_plan'],['frontend','integration'])
   finally:manager.close()
if __name__=='__main__':unittest.main()
