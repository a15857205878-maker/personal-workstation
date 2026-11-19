import unittest,tempfile,sys,io,base64
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image

class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
    def picture(self):
        p=self.base/'portrait.png';Image.new('RGB',(400,250),(120,80,190)).save(p);return p
    def test_picture_is_small_square_and_source_is_preserved(self):
        from member_identity import import_avatar
        p=self.picture();before=p.read_bytes();avatar=import_avatar(p)
        self.assertTrue(avatar.startswith('data:image/webp;base64,'));self.assertLessEqual(len(avatar),24000)
        with Image.open(io.BytesIO(base64.b64decode(avatar.split(',')[1]))) as im:self.assertEqual(im.size,(128,128))
        self.assertEqual(p.read_bytes(),before)
    def test_save_reopen_reset_and_no_model_data(self):
        from member_identity import IdentityStore,import_avatar
        s=IdentityStore(self.base/'data');v=s.save('a'*32,'小紫',import_avatar(self.picture()))
        self.assertEqual(v['items']['a'*32]['nickname'],'小紫')
        self.assertEqual(IdentityStore(self.base/'data').get(),v)
        self.assertEqual(s.save('a'*32,'','')['items'],{})
    def test_invalid_payload_and_image_are_rejected(self):
        from member_identity import IdentityStore,import_avatar
        s=IdentityStore(self.base)
        for name,avatar in [('x'*25,''),('bad\nname',''),('ok','https://example.invalid/a.png'),('ok','data:image/svg+xml;base64,AAAA')]:
            with self.assertRaises(ValueError):s.save('user',name,avatar)
        p=self.base/'bad.png';p.write_text('not image')
        with self.assertRaises(ValueError):import_avatar(p)
    def test_bridge_picker_cancel_strict_parameters_and_no_model_initialization(self):
        from backend import Bridge
        b=Bridge(self.base/'missing',data_dir=self.base/'data');b.identity_picker=lambda:None
        self.assertTrue(b.call('api_center_identity_get',{})['ok']);self.assertIsNone(b._auto)
        self.assertEqual(b.call('api_center_identity_pick',{})['data'],{'cancelled':True})
        for action,payload in [('api_center_identity_pick',{'path':'secret.png'}),('api_center_identity_get',{'id':'user'}),('api_center_identity_save',{'id':'user','nickname':'x','avatar':'','model':'wrong'})]:
            self.assertFalse(b.call(action,payload)['ok'])
        self.assertTrue(b.call('api_center_identity_save',{'id':'user','nickname':'我','avatar':''})['ok']);self.assertIsNone(b._auto)
        self.assertFalse(b.call('api_center_identity_save',{'id':'b'*32,'nickname':'fake','avatar':''})['ok'])
    def test_image_pick_and_busy_gate(self):
        from backend import Bridge
        b=Bridge(self.base/'missing',data_dir=self.base/'data');p=self.picture();b.identity_picker=lambda:[str(p)]
        result=b.call('api_center_identity_pick',{});self.assertTrue(result['ok']);self.assertFalse(result['data']['cancelled'])
        b._command_lock.acquire()
        try:
            self.assertFalse(b.call('api_center_identity_pick',{})['ok'])
            self.assertFalse(b.call('api_center_identity_save',{'id':'user','nickname':'new','avatar':''})['ok'])
        finally:b._command_lock.release()
        self.assertEqual(b.identities.get()['items'],{})
    def test_deleted_profile_can_reset_its_existing_identity_to_free_capacity(self):
        from backend import Bridge
        from unittest.mock import patch
        b=Bridge(self.base/'missing',data_dir=self.base/'data')
        for i in range(32):b.identities.save(format(i,'032x'),'旧成员','')
        b.identities.save('user','我','')
        new='f'*32
        with patch('credential_store.ProfileStore.list',return_value=[{'id':new}]):
            self.assertFalse(b.call('api_center_identity_save',dict(id=new,nickname='新成员',avatar=''))['ok'])
            self.assertFalse(b.call('api_center_identity_save',dict(id='0'*32,nickname='篡改旧名',avatar=''))['ok'])
            self.assertTrue(b.call('api_center_identity_save',dict(id='0'*32,nickname='',avatar=''))['ok'])
            self.assertTrue(b.call('api_center_identity_save',dict(id=new,nickname='新成员',avatar=''))['ok'])

if __name__=='__main__':unittest.main()
