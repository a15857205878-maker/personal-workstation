import unittest,sys,tempfile,json
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from backend import Bridge
from remote_gateway import RemoteGateway
class MobileAppearanceTests(unittest.TestCase):
 def test_phone_receives_only_public_appearance_without_model_calls(self):
  with tempfile.TemporaryDirectory() as tmp:
   b=Bridge(Path(tmp)/'missing',data_dir=Path(tmp)/'data');b.call('api_appearance_save',{'chat_background':'coast','background_strength':45,'color_scheme':'dark'})
   g=RemoteGateway(b,Path(tmp)/'gateway',port=0);v=g.rpc({'action':'center_bootstrap','payload':{}})
   self.assertTrue(v['ok'],v);self.assertEqual(v['data']['appearance'],{'color_scheme':'dark','chat_background':'coast','background_strength':45})
   self.assertEqual(set(v['data']['appearance']),{'color_scheme','chat_background','background_strength'})
   self.assertNotIn(str(tmp),json.dumps(v));self.assertFalse(g.rpc({'action':'api_appearance_save','payload':{'chat_background':'none'}})['ok'])
