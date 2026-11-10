import sys,tempfile,unittest,zipfile,io,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from task_station.attachments import AttachmentStore
from task_station.attachment_worker import extract
class AttachmentTests(unittest.TestCase):
 def test_snapshot_and_bound_bundle(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);src=root/'例子.txt';src.write_text('第一行\n第二行',encoding='utf-8');store=AttachmentStore(root/'inputs',extractor=lambda p:extract(p))
   row=store.add(src);src.write_text('外部变化',encoding='utf-8')
   bundle=store.bundle([row['id']]);self.assertIn('第一行',bundle['text']);self.assertNotIn(str(root),bundle['text']);self.assertEqual(bundle['items'][0]['name'],'例子.txt')
   with self.assertRaises(ValueError):store.bundle(['../outside'])
   with self.assertRaises(ValueError):store.bundle([row['id']]*6)
 def test_unsupported_binary_and_total_limit(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);store=AttachmentStore(root/'inputs',extractor=lambda p:'x'*10000)
   bad=root/'a.exe';bad.write_bytes(b'not safe')
   with self.assertRaises(ValueError):store.add(bad)
   ids=[]
   for n in range(2):
    f=root/(str(n)+'.txt');f.write_text('ok');ids.append(store.add(f)['id'])
   with self.assertRaises(ValueError):store.bundle(ids)
 def test_office_paragraphs_and_slide_order(self):
  with tempfile.TemporaryDirectory() as d:
   f=Path(d)/'a.docx'
   with zipfile.ZipFile(f,'w') as z:z.writestr('word/document.xml','<document><p><t>中文内容</t></p></document>')
   self.assertIn('中文内容',extract(f))
   f=Path(d)/'a.pptx'
   with zipfile.ZipFile(f,'w') as z:
    for n in [10,2,1]:z.writestr('ppt/slides/slide'+str(n)+'.xml','<root><p><t>页'+str(n)+'</t></p></root>')
    z.writestr('ppt/presentation.xml','<root xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'+''.join('<sldId r:id="r'+str(n)+'"/>' for n in [2,10,1])+'</root>')
    z.writestr('ppt/_rels/presentation.xml.rels','<root>'+''.join('<rel Id="r'+str(n)+'" Target="slides/slide'+str(n)+'.xml" Type="x/slide"/>' for n in [1,2,10])+'</root>')
   text=extract(f);self.assertLess(text.index('页2'),text.index('页10'));self.assertLess(text.index('页10'),text.rindex('页1'))
 def test_macro_and_xml_entities_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   f=Path(d)/'a.docx'
   for entries in [{'word/document.xml':'<!DOCTYPE d [<!ENTITY q "no">]><d/>'},{'word/vbaProject.bin':'x','word/document.xml':'<d/>'}]:
    with zipfile.ZipFile(f,'w') as z:
     for k,v in entries.items():z.writestr(k,v)
    with self.assertRaises(ValueError):extract(f)
 def test_csv_text_and_blank_failure(self):
  with tempfile.TemporaryDirectory() as d:
   f=Path(d)/'a.csv';f.write_bytes('项目,金额\n测试,23'.encode('utf-8'));self.assertIn('23',extract(f))
   f.write_bytes(b'')
   with self.assertRaises(ValueError):extract(f)
if __name__=='__main__':unittest.main()
