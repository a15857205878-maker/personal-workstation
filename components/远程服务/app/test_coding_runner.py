import tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from coding_runner import run_coding
from adapters import NeedsAttention,Cancelled
from tasks import TaskManager
from bot_tasks import create_bot_task
class CodingTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.workspace=self.root/'project';self.workspace.mkdir();self.calls=[];self.metadata=[];self.stop=threading.Event()
 def tearDown(self):self.tmp.cleanup()
 def fake(self,task,workspace,report,stop,remote):
  self.calls.append(task['goal']);remote('session-'+str(len(self.calls)))
  if len(self.calls)==1:
   (workspace/'backend').mkdir();(workspace/'backend/service.py').write_text('def health(): return True');(workspace/'docs').mkdir();(workspace/'docs/API.md').write_text('GET /api/health -> {ok:true}',encoding='utf-8')
  if len(self.calls)==2:
   (workspace/'frontend').mkdir();(workspace/'frontend/index.html').write_text('<main>test</main>')
  if len(self.calls)==3:
   (workspace/'README.md').write_text('Run python server.py');(workspace/'docs/验收报告.md').write_text('Mock test evidence')
  return 'mock completed'
 def run_fake(self,codex=None,deepseek=None):
  with patch('adapters.run_codex',codex or self.fake),patch('deepseek_runner.run_deepseek',deepseek or self.fake):
   return run_coding({'id':'a'*32,'number':'TEST','goal':'做一个需要后端接口和数据库的预算应用','mode':'task','attachments':[]},self.workspace,lambda *x:None,self.stop,self.metadata.append)
 def test_three_stages_share_workspace_and_fixed_ownership(self):
  result=self.run_fake();self.assertEqual(len(self.calls),3);self.assertIn('backend/',self.calls[0]);self.assertIn('frontend/',self.calls[1]);self.assertIn('docs/API.md',self.calls[2]);self.assertIn('联调',result);self.assertEqual(self.metadata[-1]['code_stage'],'completed')
 def test_integration_accepts_existing_docs_readme(self):
  def runner(task,*args):
   result=self.fake(task,*args)
   if len(self.calls)==3:
    (self.workspace/'docs/README.md').write_text((self.workspace/'README.md').read_text())
    (self.workspace/'README.md').unlink()
   return result
  self.run_fake(codex=runner)
  self.assertEqual(self.metadata[-1]['code_stage'],'completed')
  self.assertFalse((self.workspace/'README.md').exists())
 def test_integration_still_requires_readme_and_acceptance_report(self):
  for missing in ('README.md','docs/验收报告.md'):
   with self.subTest(missing=missing):
    self.calls.clear()
    def runner(task,*args):
     result=self.fake(task,*args)
     if len(self.calls)==3:(self.workspace/missing).unlink()
     return result
    with self.assertRaises(NeedsAttention):self.run_fake(codex=runner)
    import shutil
    for child in self.workspace.iterdir():
     if child.is_dir():shutil.rmtree(child)
     else:child.unlink()
 def test_empty_primary_readme_cannot_be_hidden_by_fallback(self):
  from coding_runner import evidence
  (self.workspace/'docs').mkdir()
  (self.workspace/'docs/README.md').write_text('Existing instructions')
  (self.workspace/'README.md').write_text('')
  with self.assertRaises(NeedsAttention):evidence(self.workspace,'README.md',alternative='docs/README.md')
 def test_no_frontend_after_backend_blocker_or_missing_contract(self):
  def blocked(*args):raise NeedsAttention('no permission')
  with self.assertRaises(NeedsAttention):self.run_fake(codex=blocked)
  self.assertEqual(self.calls,[])
  with self.assertRaises(NeedsAttention):self.run_fake(codex=lambda *args:'text only')
  self.assertEqual(self.calls,[])
 def test_stages_have_separate_private_execution_directories(self):
  paths=[]
  def runner(task,*args):paths.append(task.get('_execution_dir'));return self.fake(task,*args)
  self.run_fake(codex=runner,deepseek=runner)
  self.assertEqual(len(set(paths)),3);self.assertTrue(all(p and Path(p).is_relative_to(self.workspace) for p in paths))
 def test_api_document_without_backend_code_never_dispatches_frontend(self):
  def docs_only(task,workspace,*args):
   (workspace/'docs').mkdir();(workspace/'docs/API.md').write_text('API only');return 'completed'
  with self.assertRaises(NeedsAttention):self.run_fake(codex=docs_only)
  self.assertEqual(self.calls,[])
 def test_legacy_task_without_route_keeps_original_three_stage_flow(self):
  with patch('adapters.run_codex',self.fake),patch('deepseek_runner.run_deepseek',self.fake):
   run_coding({'id':'b'*32,'number':'LEGACY','goal':'简单日历网页','mode':'task','attachments':[]},self.workspace,lambda *x:None,self.stop,self.metadata.append)
  self.assertEqual(len(self.calls),3);self.assertIn('Codex后端负责人',self.calls[0])
 def test_stop_before_start_never_launches(self):
  self.stop.set()
  with self.assertRaises(Cancelled):self.run_fake()
  self.assertEqual(self.calls,[])
 def test_coding_workspace_idempotency_and_remote_scope(self):
  manager=TaskManager(self.root/'manager',start_worker=False)
  try:
   payload={'agent':'codex-deepseek-code','mode':'task','request_id':'code-one','text':'做一个应用','attachments':[]};first=create_bot_task(manager,payload);self.assertEqual(first['id'],create_bot_task(manager,payload)['id']);self.assertEqual(manager.workspace(first['id']),manager.root/'代码项目'/first['id']);self.assertTrue(manager.workspace(first['id']).is_dir())
   with self.assertRaises(ValueError):create_bot_task(manager,{**payload,'cwd':str(self.root)})
   with self.assertRaises(ValueError):create_bot_task(manager,{**payload,'mode':'review'})
  finally:manager.close()
if __name__=='__main__':unittest.main()
