from pathlib import Path
import json,sys,tempfile,threading,time,unittest,zipfile
from io import BytesIO
from xml.etree import ElementTree as ET
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from task_station.spreadsheet_export import spreadsheet_bytes,write_spreadsheet
from task_station.core import Service

SPEC={'version':1,'sheets':[{'name':'预算','columns':['项目','数量','单价','小计'],'rows':[['材料',2,12.5,{'formula':'=B2*C2'}],['合计',None,None,{'formula':'=SUM(D2:D2)'}],['原样文本','=HYPERLINK("https://example.com")',None,None]]}]}
class SpreadsheetTests(unittest.TestCase):
 def test_real_xlsx_values_formulas_cached_totals_and_literal_text(self):
  raw=spreadsheet_bytes(json.dumps(SPEC,ensure_ascii=False));self.assertTrue(raw.startswith(b'PK'))
  with zipfile.ZipFile(BytesIO(raw)) as z:
   self.assertIsNone(z.testzip())
   for name in z.namelist():ET.fromstring(z.read(name))
   ns={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'};sheet=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
   cells={c.attrib['r']:c for c in sheet.findall('.//x:c',ns)}
   self.assertEqual(cells['D2'].find('x:f',ns).text,'B2*C2');self.assertEqual(float(cells['D3'].find('x:v',ns).text),25)
   self.assertEqual(cells['B4'].attrib['t'],'inlineStr');self.assertEqual(len(sheet.findall('.//x:f',ns)),2)
 def test_rejects_invalid_structure_external_code_cycles_and_formula_errors(self):
  for formula in ['=WEBSERVICE("https://example.com")','=SUM([book]Sheet!A1)','=D2','=1/0','=A2+1','=B20000','=2**300']:
   spec=json.loads(json.dumps(SPEC));spec['sheets'][0]['rows'][0][3]={'formula':formula}
   with self.subTest(formula=formula),self.assertRaises(ValueError):spreadsheet_bytes(json.dumps(spec))
  for value in ['只有文字，没有数据','{}','{"version":1,"sheets":[]}',json.dumps({'version':1,'sheets':[{'name':'../x','columns':['a'],'rows':[[1]]}]})]:
   with self.assertRaises(ValueError):spreadsheet_bytes(value)
 def test_fenced_json_resource_limits_and_repeat_export(self):
  raw=json.dumps(SPEC);self.assertTrue(spreadsheet_bytes('```json\n'+raw+'\n```'))
  spec=json.loads(raw);spec['sheets'][0]['rows']=[[0]*21]
  with self.assertRaises(ValueError):spreadsheet_bytes(json.dumps(spec))
  with tempfile.TemporaryDirectory() as folder:
   a=write_spreadsheet(Path(folder),raw);b=write_spreadsheet(Path(folder),raw);self.assertEqual(a,b);self.assertEqual(len(list(Path(folder).iterdir())),1)
class Fake:
 def __init__(self):self.calls=0
 def capabilities(self):return {'text_1':{'can_run':True,'mode':'test'},'excel':{'can_run':False,'mode':'manual'}}
 def run(self,role,prompt,cancel,chunk,folder):self.calls+=1;return json.dumps(SPEC,ensure_ascii=False)
class SpreadsheetServiceTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.adapter=Fake();self.s=Service(Path(self.tmp.name),self.adapter)
 def tearDown(self):self.s.close();self.tmp.cleanup()
 def create(self):return self.s.call('create',{'task_type':'xlsx','role':'text_1','instruction':'材料2件，每件12.5元，做一份预算表'})
 def wait(self):
  end=time.monotonic()+5
  while self.s.jobs and time.monotonic()<end:time.sleep(.01)
 def test_model_response_exports_file_once_and_retry_does_not_call_model(self):
  t=self.create();self.assertIn('"version":1',t['prompt']);self.s.call('submit',{'id':t['id']});self.wait();t=self.s.call('get',{'id':t['id']});self.assertEqual(t['status'],'结果待确认');self.assertEqual(len(t['files']),1);self.assertTrue(t['files'][0]['name'].endswith('.xlsx'))
  again=self.s.call('export_spreadsheet',{'id':t['id']});self.assertEqual(again['files'],t['files']);self.assertEqual(self.adapter.calls,1)
 def test_export_failure_retains_result_and_can_retry_without_model(self):
  t=self.create()
  with patch('task_station.core.write_spreadsheet',side_effect=ValueError('公式不受支持')):self.s.call('submit',{'id':t['id']});self.wait()
  t=self.s.call('get',{'id':t['id']});self.assertEqual(t['status'],'结果待确认');self.assertIn('公式不受支持',t['events'][-1]['message']);self.assertTrue(t['result']);self.assertEqual(t['files'],[])
  t=self.s.call('export_spreadsheet',{'id':t['id']});self.assertEqual(len(t['files']),1);self.assertEqual(self.adapter.calls,1)
 def test_saved_catalog_keeps_default_suffix_and_manual_role(self):
  from task_station.catalog import load_catalog
  folder=Path(self.tmp.name);packaged=Path(__file__).resolve().parents[1]/'task_station/templates.json'
  saved=json.loads(packaged.read_text(encoding='utf-8'));entry=next(t for t in saved['tasks'] if t['id']=='xlsx');entry['agents']=[{'role_ref':'excel','label':'Kimi'}];entry['suffix']='用户自己的要求';entry['default_role_ref']='excel'
  path=folder/'saved.json';original=json.dumps(saved,ensure_ascii=False);path.write_text(original,encoding='utf-8');catalog=load_catalog(path,packaged);entry=next(t for t in catalog['tasks'] if t['id']=='xlsx');self.assertEqual(entry['default_role_ref'],'excel_gemini');self.assertEqual(entry['suffix'],'用户自己的要求');self.assertEqual(path.read_text(encoding='utf-8'),original);self.assertEqual([a['role_ref'] for a in entry['agents']],['excel_gemini'])
 def test_running_empty_and_wrong_task_cannot_export(self):
  t=self.create()
  with self.assertRaises(ValueError):self.s.call('export_spreadsheet',{'id':t['id']})
  self.s._save_text({'id':t['id'],'text':json.dumps(SPEC)})
  task=self.s._load(t['id']);task['status']='执行中';self.s._save(task)
  with self.assertRaises(ValueError):self.s.call('export_spreadsheet',{'id':t['id']})
if __name__=='__main__':unittest.main()
