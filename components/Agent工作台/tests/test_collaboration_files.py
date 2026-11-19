import unittest,tempfile,sys,json,time,zipfile
from pathlib import Path
from xml.etree import ElementTree
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_api as api_tests
from test_api import FakeClient,await_done
from collaboration_files import create_artifact,artifact_path

SHEET=json.dumps({'version':1,'sheets':[{'name':'预算','columns':['项目','数量','单价','小计'],'rows':[['材料',2,5,{'formula':'=B2*C2'}],['合计',None,None,{'formula':'=SUM(D2:D2)'}]]}]},ensure_ascii=False)
DECK=json.dumps({'version':1,'title':'协作演示','slides':[{'title':'一起完成任务','subtitle':'双模型实验','bullets':['一方制作','另一方审查']} ]},ensure_ascii=False)
class DualFilesTests(unittest.TestCase):
 setUp=api_tests.ApiTests.setUp
 engine=api_tests.ApiTests.engine
 payload=api_tests.ApiTests.payload
 def test_image_collaboration_uses_verified_snapshots_without_model_file_access(self):
  from test_presentation_images import photo,deck
  from task_station.attachments import AttachmentStore
  source=self.base/'garden.png';source.write_bytes(photo())
  row=AttachmentStore(self.base/'station/attachments').add(source,image_asset=True)
  class ImageClient(FakeClient):
   def complete(inner,*args):
    result=super(ImageClient,inner).complete(*args);result['content']='审查：图片ID与版式正确，未查看图片像素。' if len(inner.calls)==2 else deck(row['id']);return result
  client=ImageClient();engine=self.engine(client);engine.start(self.payload(output_format='pptx',image_ids=[row['id']]))
  run=await_done(engine);self.assertEqual(run['status'],'completed',run.get('error'));self.assertEqual(len(client.calls),3)
  self.assertEqual(run['artifact_preview']['image_count'],1);self.assertIn(row['id'],client.calls[0][0]['content']);self.assertNotIn(str(source),str(client.calls))
  with zipfile.ZipFile(artifact_path(self.base,run,run['files'][0]['name'])) as z:self.assertEqual(len([n for n in z.namelist() if n.startswith('ppt/media/')]),1)
 def test_image_invalid_ids_or_wrong_format_never_dispatch(self):
  for fields in [dict(output_format='docx',image_ids=['a'*32]),dict(output_format='pptx',image_ids=['../x']),dict(output_format='pptx',image_ids=['a'*32,'a'*32])]:
   client=FakeClient()
   with self.assertRaises(ValueError):self.engine(client).start(self.payload(**fields))
   self.assertEqual(client.calls,[])
 def run_file(self,fmt,final):
  class FilesClient(FakeClient):
   def complete(inner,*args):
    result=super(FilesClient,inner).complete(*args);result['content']=final if len(inner.calls)==3 else ('需检查公式与内容' if len(inner.calls)==2 else final);return result
  client=FilesClient();engine=self.engine(client);engine.start(self.payload(output_format=fmt));return engine,await_done(engine),client
 def test_xlsx_finishes_only_after_real_export_and_reopens(self):
  engine,run,client=self.run_file('xlsx',SHEET);self.assertEqual(run['status'],'completed');self.assertEqual(run['output_format'],'xlsx');self.assertEqual(run['call_count'],3)
  path=artifact_path(self.base,run,run['files'][0]['name']);self.assertTrue(path.is_file());self.assertEqual(path.suffix,'.xlsx')
  with zipfile.ZipFile(path) as z:self.assertIn(b'<v>10</v>',z.read('xl/worksheets/sheet1.xml'))
  self.assertIn('返回一个JSON',client.calls[0][0]['content']);self.assertIn('审查',client.calls[1][0]['content']);self.assertEqual(self.sessions.load(run['id'])['files'],run['files'])
 def test_pptx_and_docx_export_without_extra_model_calls(self):
  word = '# 示例 · 三步验收安排\n\n```word-table\n| 周一整理资料 |\n| 周三核对进度 |\n| 周五提交文档 |\n```'
  for fmt,value in [('pptx',DECK),('docx',word)]:
   engine,run,client=self.run_file(fmt,value);self.assertEqual(run['status'],'completed',run.get('error'));self.assertEqual(len(client.calls),3)
   path=artifact_path(self.base,run,run['files'][0]['name']);self.assertTrue(zipfile.is_zipfile(path))
   if fmt=='docx':
    self.assertIn('word-table',client.calls[-1][0]['content'])
    with zipfile.ZipFile(path) as archive:
     table=ElementTree.fromstring(archive.read('word/document.xml')).find('.//{*}tbl')
    self.assertEqual([row.findtext('.//{*}t') for row in table.findall('{*}tr')],['周一整理资料','周三核对进度','周五提交文档'])
 def test_invalid_final_is_failure_not_fake_download(self):
  _,run,client=self.run_file('xlsx','这里是一份表格大纲');self.assertEqual(run['status'],'failed');self.assertEqual(run.get('files',[]),[]);self.assertIn('文件',run['error']);self.assertEqual(len(client.calls),3)
 def test_unknown_output_rejected_before_dispatch(self):
  client=FakeClient()
  with self.assertRaises(ValueError):self.engine(client).start(self.payload(output_format='exe'))
  self.assertEqual(client.calls,[])
 def test_file_reads_reject_other_names_and_tampering(self):
  _,run,_=self.run_file('xlsx',SHEET);name=run['files'][0]['name']
  for bad in ['../'+name,'other.xlsx']:
   with self.assertRaises(ValueError):artifact_path(self.base,run,bad)
  p=artifact_path(self.base,run,name);p.write_bytes(b'not the original')
  with self.assertRaises(ValueError):artifact_path(self.base,run,name)
 def test_manual_content_retry_reasks_only_final_revision_with_feedback(self):
  class RepairClient(FakeClient):
   def complete(inner,*args):
    result=super(RepairClient,inner).complete(*args);result['content']=SHEET if len(inner.calls)>=4 else 'invalid final';return result
  client=RepairClient();engine=self.engine(client);engine.start(self.payload(output_format='xlsx'));first=await_done(engine)
  self.assertEqual(first['status'],'failed');engine.retry(first['id']);fixed=await_done(engine)
  self.assertEqual(fixed['status'],'completed');self.assertEqual(len(client.calls),4);self.assertIn('校验',str(client.calls[-1]))
 def test_manual_export_retry_does_not_call_models_again(self):
  from unittest.mock import patch
  import collaboration_files
  class ContentClient(FakeClient):
   def complete(inner,*args):result=super(ContentClient,inner).complete(*args);result['content']=SHEET;return result
  client=ContentClient();engine=self.engine(client)
  with patch('collaboration_files.create_artifact',side_effect=OSError('test disk unavailable')):
   payload=self.payload(output_format='xlsx');payload['call_limit']=3;engine.start(payload);first=await_done(engine)
  self.assertEqual(first['status'],'failed');self.assertEqual(first['call_count'],3);engine.retry(first['id']);fixed=await_done(engine)
  self.assertEqual(fixed['status'],'completed');self.assertEqual(len(client.calls),3)
 def test_registered_bridge_exposes_only_verified_own_files(self):
  from backend import Bridge
  import base64
  opened=[];bridge=Bridge(self.base/'unused-room',data_dir=self.base/'bridge-data',api_client=FakeClient(),opener=opened.append)
  profile=bridge.call('api_profile_save',dict(name='Test',kind='compatible',base_url='https://mock.invalid',model='mock',api_key='test-only'))['data']
  response=bridge.call('api_start',dict(task='文档测试',primary_id=profile['id'],reviewer_id=profile['id'],output_format='docx'))
  self.assertTrue(response['ok']);run=await_done(bridge._auto.engine);self.assertEqual(run['status'],'completed')
  name=run['files'][0]['name'];payload={'id':run['id'],'name':name}
  content=bridge.call('api_collaboration_file',payload);self.assertTrue(content['ok']);self.assertTrue(base64.b64decode(content['data']['content_base64']).startswith(b'PK'))
  self.assertTrue(bridge.call('api_collaboration_open_file',payload)['ok']);self.assertEqual(len(opened),1)
  self.assertFalse(bridge.call('api_collaboration_open_file',{**payload,'name':'../secret.txt'})['ok']);self.assertEqual(len(opened),1)
 def test_stop_or_failed_review_never_exports_a_file(self):
  for client in (FakeClient(cancel_at=1),FakeClient(fail_at=2)):
   engine=self.engine(client);engine.start(self.payload(output_format='xlsx'));run=await_done(engine)
   self.assertIn(run['status'],('cancelled','failed'));self.assertEqual(run.get('files',[]),[])
if __name__=='__main__':unittest.main()
