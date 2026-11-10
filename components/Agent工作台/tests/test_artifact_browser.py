from pathlib import Path
import tempfile,unittest,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
class ArtifactTests(unittest.TestCase):
 def test_folder_refresh_and_unlink_do_not_copy_or_delete(self):
  from artifact_browser import ArtifactBrowser
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);folder=root/'outside';folder.mkdir();(folder/'budget.xlsx').write_bytes(b'fixture')
   browser=ArtifactBrowser(root/'data');browser.add([folder],folder=True)
   first=browser.list([]);self.assertEqual([i['name'] for i in first['items']],['budget.xlsx'])
   (folder/'slides.pptx').write_bytes(b'fixture');self.assertEqual(len(browser.list([])['items']),2)
   browser.remove(first['sources'][0]['id']);self.assertTrue((folder/'budget.xlsx').exists());self.assertEqual(browser.list([])['items'],[])
 def test_file_ids_and_safe_open(self):
  from artifact_browser import ArtifactBrowser
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);file=root/'report.pdf';file.write_bytes(b'fixture');browser=ArtifactBrowser(root/'data');browser.add([file])
   item=browser.list([])['items'][0];self.assertEqual(browser.path(item['id']),file)
   with self.assertRaises(ValueError):browser.path('../../auth.json')
   file.unlink()
   with self.assertRaises(ValueError):browser.path(item['id'])
 def test_dual_real_file_and_hostile_html_static_preview(self):
  import hashlib,json
  from artifact_browser import ArtifactBrowser
  from session_store import SessionStore
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);identifier='a'*32;raw=b'fixture';name='协作成果-'+hashlib.sha256(raw).hexdigest()[:16]+'.docx';folder=root/'collaboration-artifacts'/identifier;folder.mkdir(parents=True);(folder/name).write_bytes(raw)
   SessionStore(root/'sessions').save(dict(id=identifier,title='双模型文档',steps=[],status='completed',call_count=3,call_limit=9,files=[dict(name=name,size=len(raw),sha256=hashlib.sha256(raw).hexdigest())]))
   browser=ArtifactBrowser(root);item=browser.list([])['items'][0];self.assertEqual(item['source_kind'],'collaboration');self.assertEqual(browser.path(item['id']),folder/name)
   html=root/'page.html';html.write_text('<script>bad()</script><h1>成果</h1>',encoding='utf-8');browser.add([html]);item=next(i for i in browser.list([])['items'] if i['name']=='page.html');view=browser.preview(item['id']);self.assertIn("script-src 'none'",view['html']);self.assertNotIn('<script',view['html'])
 def test_duplicates_and_replaced_folder_cannot_escape(self):
  from unittest.mock import patch
  from artifact_browser import ArtifactBrowser
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);outside=root/'downloads';outside.mkdir();file=outside/'report.pdf';file.write_bytes(b'fixture');b=ArtifactBrowser(root/'data');b.add([file]);b.add([outside],folder=True)
   items=b.list([])['items'];self.assertEqual(len(items),1)
   with patch('artifact_browser.linked',side_effect=lambda p:Path(p)==outside):
    with self.assertRaises(ValueError):b.path(items[0]['id'])
 def test_listing_dual_does_not_initialize_model_engine(self):
  from backend import Bridge
  with tempfile.TemporaryDirectory() as d:
   b=Bridge(Path(d)/'unused-room',data_dir=Path(d)/'data')
   try:
    r=b.call('workstation_artifacts',{});self.assertTrue(r['ok'],r);self.assertIsNone(b._auto)
   finally:b.close_station()
 def test_station_ancestor_link_is_rejected_after_listing(self):
  from unittest.mock import patch
  from artifact_browser import ArtifactBrowser
  with tempfile.TemporaryDirectory() as d:
   data=Path(d);task=data/'station/tasks'/('a'*32);results=task/'results';results.mkdir(parents=True);(results/'result.txt').write_text('fixture',encoding='utf-8')
   b=ArtifactBrowser(data);item=b.list([dict(task_id='a'*32,title='任务',folder=str(task),name='result.txt',size=7)])['items'][0]
   with patch('artifact_browser.linked',side_effect=lambda p:Path(p)==task):
    with self.assertRaises(ValueError):b.path(item['id'])
if __name__=='__main__':unittest.main()


