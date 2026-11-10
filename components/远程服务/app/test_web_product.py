import tempfile,unittest
from pathlib import Path
from tasks import TaskManager
from web_product import WebProducts
class WebProductsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.tasks=TaskManager(Path(self.tmp.name),start_worker=False);self.task=self.tasks.create({'agent':'codex-deepseek-code','goal':'web','client_id':'one','project_kind':'web'});self.root=self.tasks.workspace(self.task['id']);(self.root/'frontend').mkdir();(self.root/'frontend/index.html').write_text('<h1>Hello</h1>');self.tasks.update(self.task['id'],status='completed');self.service=WebProducts(self.tasks)
 def tearDown(self):self.tasks.close();self.tmp.cleanup()
 def test_ticket_only_serves_own_frontend_and_not_parent_or_application(self):
  receipt=self.service.prepare(self.task['id']);self.assertTrue(receipt['url'].startswith('/web-product/'));token=receipt['url'].split('/')[2];raw,mime=self.service.asset(token,'index.html');self.assertIn(b'Hello',raw);self.assertIn('html',mime)
  for name in ['../backend/secret','/index.html','.env','node_modules/a.js']:
   with self.assertRaises((ValueError,FileNotFoundError)):self.service.asset(token,name)
  with self.assertRaises(ValueError):self.service.asset('bad','index.html')
 def test_local_tools_and_unbuilt_react_are_not_claimed_previewable(self):
  self.tasks.update(self.task['id'],project_kind='local-tool')
  with self.assertRaises(ValueError):self.service.prepare(self.task['id'])
  self.tasks.update(self.task['id'],project_kind='web');(self.root/'frontend/index.html').write_text('<script type="module" src="/src/main.jsx"></script>')
  with self.assertRaisesRegex(ValueError,'构建'):self.service.prepare(self.task['id'])
 def test_built_dist_is_preferred_and_junctions_are_refused(self):
  from unittest.mock import patch
  dist=self.root/'frontend/dist';dist.mkdir();(dist/'index.html').write_text('BUILD');receipt=self.service.prepare(self.task['id']);token=receipt['url'].split('/')[2];self.assertIn(b'BUILD',self.service.asset(token,'index.html')[0])
  with patch('pathlib.Path.is_junction',lambda p:p.name=='frontend'),self.assertRaises(ValueError):self.service.prepare(self.task['id'])
 def test_static_src_folder_is_valid_but_build_template_is_not(self):
  (self.root/'frontend/index.html').write_text('<script type="module" src="./src/app.js"></script>');self.service.prepare(self.task['id'])
  (self.root/'frontend/index.html').write_text('<link href="%PUBLIC_URL%/favicon.ico"><div id="root"></div>')
  with self.assertRaisesRegex(ValueError,'构建'):self.service.prepare(self.task['id'])
 def test_dependency_directory_case_variant_is_never_served(self):
  folder=self.root/'frontend/NODE_MODULES';folder.mkdir();(folder/'secret.js').write_text('secret');receipt=self.service.prepare(self.task['id']);token=receipt['url'].split('/')[2]
  with self.assertRaises(ValueError):self.service.asset(token,'NODE_MODULES/secret.js')
 def test_opened_file_compares_lexical_expected_path_not_changed_resolve(self):
  from unittest.mock import patch
  receipt=self.service.prepare(self.task['id']);token=receipt['url'].split('/')[2];outside=Path(self.tmp.name)/'outside.html'
  with patch('web_product.opened_path',return_value=outside),patch('pathlib.Path.resolve',return_value=outside),self.assertRaises(ValueError):self.service.asset(token,'index.html')
 def test_coding_view_only_offers_preview_after_real_entry_exists(self):
  from conversation_view import conversation_detail
  from unittest.mock import Mock
  self.tasks.update(self.task['id'],status='needs_attention')
  view=conversation_detail(self.tasks,Mock(),Mock(),'phone',task_id=self.task['id'])
  self.assertIs(view['task'].get('web_preview_ready'),True)
  (self.root/'frontend/index.html').unlink()
  view=conversation_detail(self.tasks,Mock(),Mock(),'phone',task_id=self.task['id'])
  self.assertIs(view['task'].get('web_preview_ready'),False)
if __name__=='__main__':unittest.main()
