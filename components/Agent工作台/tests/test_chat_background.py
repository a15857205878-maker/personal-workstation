import unittest,tempfile,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import Bridge
class BackgroundTests(unittest.TestCase):
 def test_background_persists_without_resetting_theme_or_models(self):
  with tempfile.TemporaryDirectory() as tmp:
   data=Path(tmp);b=Bridge(data/'room',data_dir=data)
   self.assertEqual(b.call('api_appearance_get')['data']['chat_background'],'auto')
   self.assertTrue(b.call('api_appearance_save',{'color_scheme':'dark','chat_background':'coast','background_strength':50})['ok'])
   self.assertTrue(b.call('api_appearance_save',{'color_scheme':'light'})['ok'])
   v=Bridge(data/'room',data_dir=data).call('api_appearance_get')['data']
   self.assertEqual((v['color_scheme'],v['chat_background'],v['background_strength']),('light','coast',50));self.assertIsNone(b._auto)
   self.assertFalse((data/'providers.json').exists())
 def test_rejects_invalid_background_and_keeps_old_preferences(self):
  with tempfile.TemporaryDirectory() as tmp:
   data=Path(tmp);p=data/'appearance.json';p.write_text(json.dumps({'theme':'blue','color_scheme':'dark'}))
   b=Bridge(data/'room',data_dir=data);self.assertEqual(b.call('api_appearance_get')['data']['background_strength'],35)
   before=p.read_bytes()
   for patch in ({'chat_background':'http://invalid'},{'background_strength':61},{'background_strength':True},{'background_strength':float('nan')},{'background_strength':-1}):self.assertFalse(b.call('api_appearance_save',patch)['ok'])
   self.assertEqual(before,p.read_bytes())
