import unittest,tempfile,json,threading,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from task_station.catalog import load_catalog
class AllocationTests(unittest.TestCase):
 def test_new_choices_and_legacy_suffix_without_writing_saved_catalog(self):
  packaged=Path(__file__).resolve().parents[1]/'task_station/templates.json'
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'templates.json';value=json.loads(packaged.read_text(encoding='utf-8'));next(t for t in value['tasks'] if t['id']=='pptx')['suffix']='自定义后缀';p.write_text(json.dumps(value),encoding='utf-8');before=p.read_bytes()
   tasks={t['id']:t for t in load_catalog(p,packaged)['tasks']}
   self.assertEqual([a['role_ref'] for a in tasks['text']['agents']],['text_claude','text_2'])
   for kind,role in [('pptx','presentation_gemini'),('xlsx','excel_gemini'),('image','image_gemini'),('animation','animation_gemini'),('research','research_kimi')]:self.assertEqual(tasks[kind]['default_role_ref'],role)
   self.assertEqual(tasks['pptx']['suffix'],'自定义后缀');self.assertEqual(p.read_bytes(),before)
 def test_animation_rejects_active_content_and_preserves_css_svg(self):
  from task_station.generation_channels import animation_html
  good='<html><style>@keyframes spin{to{transform:rotate(360deg)}}svg{animation:spin 2s linear infinite}</style><svg viewBox="0 0 40 40"><circle cx="20" cy="20" r="8"/></svg></html>'
  self.assertIn('Content-Security-Policy',animation_html(good))
  for bad in ['<svg><set attributeName="href" to="https://example.com"/></svg>','<svg><a href="#local">链接</a></svg>','<script>alert(1)</script>','<img src="https://example.com/a.png">','<svg onload="x()"></svg>','<style>@import "https://example.com/x";</style>']:
   with self.assertRaises(ValueError):animation_html(bad)
 def test_official_hosts_only_and_image_model_separate(self):
  from task_station.adapters import Settings
  with tempfile.TemporaryDirectory() as d:
   s=Settings(d,encrypt=lambda x:'mock:'+x,decrypt=lambda x:x[5:])
   for name,base in [('claude','https://api.anthropic.com/v1'),('kimi','https://api.moonshot.ai/v1'),('gemini','https://generativelanguage.googleapis.com/v1beta/openai')]:
    v=s.save(dict(provider=name,base_url=base,model='explicit-model',image_model='image-model' if name=='gemini' else '',key='test-only'))
    self.assertTrue(v[name]['has_key']);self.assertNotIn('secret',v[name])
   self.assertEqual(s.public()['gemini']['image_model'],'image-model')
   with self.assertRaises(ValueError):s.save(dict(provider='kimi',base_url='https://example.com/v1',model='x',key='test-only'))
class ChannelTests(unittest.TestCase):
 def setUp(self):
  from task_station.generation_channels import GenerationChannels
  class Config:
   def public(self):return {k:dict(has_key=True,model='test-model',image_model='image-model',base_url=base) for k,base in [('gemini','https://generativelanguage.googleapis.com/v1beta/openai'),('claude','https://api.anthropic.com/v1'),('kimi','https://api.moonshot.ai/v1')]}
   def secret(self,p):return 'fake-private-key'
  self.config=Config();self.Channel=GenerationChannels
 def test_image_returns_real_validated_file_not_text(self):
  from PIL import Image
  from io import BytesIO
  import base64
  raw=BytesIO();Image.new('RGB',(8,8),'blue').save(raw,format='PNG')
  replies=[{'candidates':[{'finishReason':'STOP','content':{'parts':[{'inlineData':{'mimeType':'image/png','data':base64.b64encode(raw.getvalue()).decode()}}]}}]}]
  calls=[]
  def request(*args):calls.append(args);return replies[0]
  with tempfile.TemporaryDirectory() as d:
   result=self.Channel(self.config,request).run('image_gemini','生成图片',threading.Event(),lambda _:None,Path(d))
   path=next((Path(d)/'results').glob('*.png'));self.assertIn(path.name,result);self.assertTrue(path.read_bytes().startswith(b'\x89PNG'))
   self.assertIn('image-model',calls[0][4])
   replies[0]={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'只有描述'}]}}]}
   with self.assertRaises(ValueError):self.Channel(self.config,request).run('image_gemini','图片',threading.Event(),lambda _:None,Path(d))
 def test_kimi_search_sources_and_bounded_summary(self):
  calls=[]
  def request(*args):
   calls.append(args)
   return {'search_results':[{'url':'https://example.org/source','title':'已返回来源','chunks':[{'text':'资料'}]}]} if args[4]=='/tools/search_pro' else {'choices':[{'finish_reason':'stop','message':{'content':'归纳结果'}}]}
  text=self.Channel(self.config,request).run('research_kimi','查资料',threading.Event(),lambda _:None,Path('.'))
  self.assertEqual(len(calls),2);self.assertIn('https://example.org/source',text)
  calls.clear()
  def empty(*args):calls.append(args);return {'search_results':[]}
  with self.assertRaises(ValueError):self.Channel(self.config,empty).run('research_kimi','搜索',threading.Event(),lambda _:None,Path('.'))
  self.assertEqual(len(calls),1)
 def test_animation_roundtrip_and_cancellation_no_files(self):
  from task_station.generation_channels import animation_html
  def request(*args):return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'<svg><circle cx="10" cy="10" r="5"><animate attributeName="r" values="5;8;5" dur="2s" repeatCount="indefinite"/></circle></svg>'}]}}]}
  with tempfile.TemporaryDirectory() as d:
   text=self.Channel(self.config,request).run('animation_gemini','动画',threading.Event(),lambda _:None,Path(d));path=next((Path(d)/'results').glob('*.html'))
   self.assertIn(path.name,text);self.assertIn('Content-Security-Policy',animation_html(path.read_text(encoding='utf-8')))
  cancel=threading.Event();cancel.set()
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError):self.Channel(self.config,request).run('animation_gemini','动画',cancel,lambda _:None,Path(d))
   self.assertFalse((Path(d)/'results').exists())
 def test_claude_refuses_partial_reply(self):
  def request(*args):return {'stop_reason':'max_tokens','content':[{'type':'text','text':'半篇正文'}]}
  with self.assertRaises(ValueError):self.Channel(self.config,request).run('text_claude','正文',threading.Event(),lambda _:None,Path('.'))

class ExportTests(unittest.TestCase):
 def test_gemini_office_jobs_generate_actual_archives_and_legacy_roles_stay(self):
  import time,zipfile
  from task_station.core import Service
  from task_station.adapters import LABELS
  spec={'version':2,'title':'测试','slides':[{'layout':'cards','palette':'blue','title':'第一页','subtitle':'','bullets':['要点']} ]}
  sheet={'version':1,'sheets':[{'name':'预算','columns':['项目','数值'],'rows':[['材料',5],['配件',2]]}]}
  class Fake:
   def capabilities(self):return {k:dict(label=v,mode='test',can_run=True) for k,v in LABELS.items()}
   def run(self,role,prompt,cancel,chunk,folder):return json.dumps(spec if role=='presentation_gemini' else sheet,ensure_ascii=False)
  with tempfile.TemporaryDirectory() as d:
   service=Service(Path(d),Fake())
   try:
    for kind,role,suffix in [('pptx','presentation_gemini','.pptx'),('xlsx','excel_gemini','.xlsx')]:
     task=service.call('create',dict(task_type=kind,role=role,instruction='预算或演示'));service.call('submit',dict(id=task['id']))
     deadline=time.monotonic()+5
     while task['id'] in service.jobs and time.monotonic()<deadline:time.sleep(.02)
     result=service.call('get',dict(id=task['id']));files=[f for f in result['files'] if f['name'].endswith(suffix)]
     self.assertEqual(result['status'],'结果待确认');self.assertEqual(len(files),1,result)
     with zipfile.ZipFile(service.file_path(task['id'],files[0]['name'])) as archive:self.assertIsNone(archive.testzip())
    legacy=service.call('create',dict(task_type='text',role='text_1',instruction='旧调用兼容'));self.assertEqual(legacy['role'],'text_1')
   finally:service.close()
if __name__=='__main__':unittest.main()

