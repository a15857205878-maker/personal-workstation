import unittest,tempfile,json,sys,zipfile,hashlib
from pathlib import Path
from io import BytesIO
from xml.etree import ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from task_station.attachments import AttachmentStore
from task_station.presentation_export import presentation_bytes,parse

def photo():
 out=BytesIO();Image.new('RGB',(640,360),'#5a986f').save(out,format='PNG');return out.getvalue()
def deck(identifier='a'*32):
 return json.dumps({'version':2,'title':'季节','slides':[{'layout':'image_left','palette':'spring','title':'春日花园','subtitle':'配图实际嵌入','bullets':['观察植物与色彩'],'image_id':identifier}]},ensure_ascii=False)

class PresentationImagesTests(unittest.TestCase):
 def test_photo_import_without_ocr_and_verified_asset_snapshot(self):
  from task_station.presentation_assets import prepare_assets,load_assets
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'花园.png';source.write_bytes(photo())
   store=AttachmentStore(root/'station/attachments',extractor=lambda p: self.fail('photo must not OCR'))
   row=store.add(source,image_asset=True);self.assertEqual(row['kind'],'image_asset')
   manifest=prepare_assets(root,'b'*32,[row['id']]);assets=load_assets(root,'b'*32,manifest)
   self.assertIn(row['id'],assets);self.assertEqual(source.read_bytes(),photo())
   # Uploaded original may later disappear; the run owns an immutable snapshot.
   source.unlink();self.assertEqual(load_assets(root,'b'*32,manifest),assets)
   p=root/'collaboration-artifacts'/('b'*32)/'media'/manifest[0]['file'];p.write_bytes(b'tampered')
   with self.assertRaises(ValueError):load_assets(root,'b'*32,manifest)
 def test_real_embedded_image_and_editable_text(self):
  raw=presentation_bytes(deck(),{'a'*32:{'data':photo(),'width':640,'height':360,'extension':'png'}})
  with zipfile.ZipFile(BytesIO(raw)) as z:
   for name in z.namelist():
    if name.endswith(('.xml','.rels')):ET.fromstring(z.read(name))
   slide=z.read('ppt/slides/slide1.xml').decode();self.assertIn('<p:pic>',slide);self.assertIn('春日花园',slide)
   media=[n for n in z.namelist() if n.startswith('ppt/media/')];self.assertEqual(len(media),1);self.assertEqual(z.read(media[0]),photo())
   self.assertNotIn('TargetMode="External"',z.read('ppt/slides/_rels/slide1.xml.rels').decode())
 def test_missing_or_untrusted_images_never_become_placeholders(self):
  for payload in [deck(),deck('../secret'),deck('https://example.com/x.png')]:
   with self.assertRaises(ValueError):presentation_bytes(payload)
  value=json.loads(deck());value['slides'][0]['url']='https://example.com'
  with self.assertRaises(ValueError):parse(json.dumps(value))
 def test_cover_and_cards_and_v1_compatibility(self):
  value=json.loads(deck());value['slides']=[{k:v for k,v in value['slides'][0].items() if k!='image_id'}]
  for layout in ['cover','cards']:
   value['slides'][0]['layout']=layout;self.assertTrue(presentation_bytes(json.dumps(value)).startswith(b'PK'))
  value['slides'][0]['layout']='unknown'
  with self.assertRaises(ValueError):parse(json.dumps(value))
 def test_single_task_rejects_presentation_only_assets(self):
  from task_station.core import Service
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'photo.png';source.write_bytes(photo())
   row=AttachmentStore(root/'attachments').add(source,image_asset=True)
   service=Service(root,adapter=None)
   try:
    template=service.templates['tasks'][0]
    with self.assertRaisesRegex(ValueError,'配图'):
     service._create({'task_type':template['id'],'role':template['agents'][0]['role_ref'],'instruction':'test','attachments':[row['id']]})
   finally:service.close()
