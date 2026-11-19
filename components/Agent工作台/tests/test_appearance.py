import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import Bridge

class AppearanceTests(unittest.TestCase):
    def test_new_scenes_persist_without_affecting_current_theme(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp)
            bridge=Bridge(data/'room',data_dir=data)
            bridge.call('api_appearance_save',{'color_scheme':'dark'})
            for scene in ('garden','observatory','coast','aurora','none','auto'):
                saved=bridge.call('api_appearance_save',{'chat_background':scene,'background_strength':47})
                self.assertTrue(saved['ok'],saved)
                actual=Bridge(data/'room',data_dir=data).call('api_appearance_get')['data']
                self.assertEqual((actual['chat_background'],actual['background_strength'],actual['color_scheme']),(scene,47,'dark'))

    def test_theme_persists_independently_of_models_and_chat(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp)/'data';bridge=Bridge(Path(temp)/'room',data_dir=data)
            self.assertEqual(bridge.call('api_appearance_get')['data']['theme'],'mint')
            self.assertTrue(bridge.call('api_appearance_save',{'theme':'lavender'})['ok'])
            other=Bridge(Path(temp)/'room',data_dir=data)
            self.assertEqual(other.call('api_appearance_get')['data']['theme'],'lavender')
            self.assertIsNone(other._auto)
            self.assertFalse(other.call('api_appearance_save',{'theme':'unknown'})['ok'])
            self.assertEqual(other.call('api_appearance_get')['data']['theme'],'lavender')
            self.assertFalse((data/'providers.json').exists())
    def test_invalid_appearance_falls_back_without_rewriting_it(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp);path=data/'appearance.json';path.write_text('invalid',encoding='utf-8')
            bridge=Bridge(data/'room',data_dir=data)
            self.assertEqual(bridge.call('api_appearance_get')['data']['theme'],'mint')
            self.assertEqual(path.read_text(encoding='utf-8'),'invalid')
