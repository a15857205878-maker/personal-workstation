import unittest,sys,json,zipfile
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from task_station.presentation_export import presentation_bytes,parse

SAMPLE={'version':1,'title':'工作站介绍','slides':[{'title':'手机与电脑协作','subtitle':'从需求到成果','bullets':['单模型完成日常任务','双模型制作并审查文件']}]}
class PresentationExportTests(unittest.TestCase):
 def test_editable_shapes_and_self_contained_package(self):
  raw=presentation_bytes(json.dumps(SAMPLE,ensure_ascii=False))
  with zipfile.ZipFile(BytesIO(raw)) as z:
   for name in z.namelist():
    if name.endswith(('.xml','.rels')):ET.fromstring(z.read(name))
   slide=z.read('ppt/slides/slide1.xml').decode();self.assertIn('手机与电脑协作',slide);self.assertIn('<a:t>',slide);self.assertNotIn('<p:pic',slide)
   self.assertIn('ppt/slideMasters/slideMaster1.xml',z.namelist());self.assertIn('ppt/slideLayouts/slideLayout1.xml',z.namelist());self.assertIn('ppt/theme/theme1.xml',z.namelist())
   for name in z.namelist():
    if name.endswith('.rels'):
     self.assertNotIn('TargetMode="External"',z.read(name).decode())
     import posixpath
     base=posixpath.dirname(posixpath.dirname(name))
     for rel in ET.fromstring(z.read(name)):self.assertIn(posixpath.normpath(posixpath.join(base,rel.attrib['Target'])),z.namelist())
 def test_rejects_unknown_fields_oversized_decks_and_long_text(self):
  for value in [{**SAMPLE,'url':'https://example.com'}, {**SAMPLE,'slides':SAMPLE['slides']*13},{**SAMPLE,'slides':[{**SAMPLE['slides'][0],'bullets':['x'*66]}]}, {'version':True,'title':'x','slides':[]}]:
   with self.subTest(value=str(value)[:70]),self.assertRaises(ValueError):parse(json.dumps(value))
 def test_embedded_line_breaks_cannot_overflow_fixed_text_boxes(self):
  for value in ['a\n'*14,'a\r'*14,'a\t'*14]:
   data={**SAMPLE,'slides':[{**SAMPLE['slides'][0],'title':value}]}
   with self.subTest(value=repr(value)),self.assertRaises(ValueError):parse(json.dumps(data))
 def test_xml_text_is_escaped_and_invalid_control_characters_rejected(self):
  data={**SAMPLE,'title':'<a&b>','slides':[{**SAMPLE['slides'][0],'title':'<script>&test'}]}
  with zipfile.ZipFile(BytesIO(presentation_bytes(json.dumps(data)))) as z:self.assertIn('&lt;script&gt;&amp;test',z.read('ppt/slides/slide1.xml').decode())
  data['title']='a\x00b'
  with self.assertRaises(ValueError):parse(json.dumps(data))
if __name__=='__main__':unittest.main()
