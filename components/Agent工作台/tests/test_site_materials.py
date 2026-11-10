from pathlib import Path
import json,tempfile,unittest,zipfile
from site_materials import SiteMaterials

class MaterialsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.s=SiteMaterials(self.root/'data')
    def tearDown(self):self.tmp.cleanup()
    def create(self,title='个人工作站'):
        return self.s.create(title,self.s.listing()['revision'])['projects'][-1]
    def add(self,project,**kwargs):
        return self.s.add_entry(project['id'],self.s.listing()['revision'],**kwargs)['projects'][0]
    def save(self,project):return self.s.save(project,self.s.listing()['revision'])
    def test_projects_conflict_and_preserve_manual_edits(self):
        p=self.create();old=self.s.listing()['revision'];p['todo']='继续核对';p['version']='v1';self.save(p)
        with self.assertRaises(ValueError):self.s.save(p,old)
        self.create('其他项目');self.assertEqual(self.s.listing()['projects'][0]['todo'],'继续核对')
        self.assertEqual(SiteMaterials(self.root/'data').listing()['projects'][0]['version'],'v1')
    def test_export_only_selected_public_no_private_paths_or_notes(self):
        p=self.create('<项目>');p=self.add(p,title='公开步骤',description='<script>alert(1)</script>',source='第2行',excerpt='正文摘录')
        p=self.add(p,title='私有内容');p=self.add(p,title='未选择内容')
        p['entries'][0]['public']=True;p['entries'][0]['notes']='绝密备注';p['entries'][2]['public']=True;self.save(p)
        with self.assertRaises(ValueError):self.s.export(p['id'],[p['entries'][1]['id']],self.s.listing()['revision'])
        out=self.s.export(p['id'],[p['entries'][0]['id']],self.s.listing()['revision'])
        with zipfile.ZipFile(out['path']) as z:
            body='\n'.join(z.read(n).decode('utf-8') for n in z.namelist())
            for secret in ['私有内容','未选择内容','绝密备注',str(self.root)]:self.assertNotIn(secret,body)
            self.assertIn('&lt;script&gt;',z.read('storyboard.html').decode())
            manifest=json.loads(z.read('manifest.json'));self.assertEqual(manifest['entries'][0]['source'],'第2行')
        second=self.s.export(p['id'],[p['entries'][0]['id']],self.s.listing()['revision'])
        self.assertNotEqual(out['path'],second['path'])
    def test_reference_changed_missing_and_delete_keeps_original(self):
        file=self.root/'截图.png';file.write_bytes(b'\x89PNG\r\n\x1a\noriginal')
        p=self.create();p=self.add(p,title='截图',path=file);p['entries'][0]['public']=True;self.save(p)
        out=self.s.export(p['id'],[p['entries'][0]['id']],self.s.listing()['revision'])
        with zipfile.ZipFile(out['path']) as z:self.assertEqual(z.read('media/01.png'),file.read_bytes())
        file.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.s.export(p['id'],[p['entries'][0]['id']],self.s.listing()['revision'])
        self.assertEqual(self.s.listing()['projects'][0]['entries'][0]['file_status'],'changed')
        self.s.delete(p['id'],self.s.listing()['revision']);self.assertEqual(file.read_bytes(),b'changed')
    def test_cannot_inject_reference_or_duplicate_or_other_project_entry(self):
        p=self.create();p=self.add(p,title='one');other=self.create('other')
        p['entries'][0]['reference']={'path':'C:/secret'}
        with self.assertRaises(ValueError):self.save(p)
        p.pop('reference',None);p['entries'][0].pop('reference')
        other['entries']=p['entries']
        with self.assertRaises(ValueError):self.save(other)
        p['entries']*=2
        with self.assertRaises(ValueError):self.save(p)
    def test_reorder_is_export_order_and_missing_file_visible(self):
        p=self.create();p=self.add(p,title='first');p=self.add(p,title='second')
        p['entries'].reverse()
        for row in p['entries']:row['public']=True
        self.save(p);out=self.s.export(p['id'],[e['id'] for e in p['entries']],self.s.listing()['revision'])
        with zipfile.ZipFile(out['path']) as z:self.assertEqual([e['title'] for e in json.loads(z.read('manifest.json'))['entries']],['second','first'])
        f=self.root/'gone.md';f.write_text('x');p=self.s.listing()['projects'][0];p=self.add(p,path=f,title='missing');f.unlink()
        self.assertEqual(self.s.listing()['projects'][0]['entries'][-1]['file_status'],'missing')
    def test_reference_must_match_selected_content_digest(self):
        import hashlib
        file=self.root/'doc.md';file.write_text('原文',encoding='utf-8');digest=hashlib.sha256(file.read_bytes()).hexdigest()
        p=self.create();file.write_text('替换内容',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'变化'):
            self.s.add_entry(p['id'],self.s.listing()['revision'],path=file,expected_sha256=digest)
        self.assertEqual(self.s.listing()['projects'][0]['entries'],[])
    def test_oversized_metadata_is_rejected_before_replacing_readable_data(self):
        from unittest.mock import patch
        p=self.create();p=self.add(p,title='notes');before=self.s.path.read_bytes()
        with patch('site_materials.MAX_METADATA_BYTES',len(before)+100):
            p['entries'][0]['description']='中'*200
            with self.assertRaisesRegex(ValueError,'容量'):
                self.save(p)
            self.assertEqual(self.s.path.read_bytes(),before)
            self.assertEqual(self.s.listing()['projects'][0]['entries'][0]['description'],'')
    def test_preview_never_displays_bytes_replaced_after_fingerprint(self):
        from unittest.mock import patch
        from site_materials import fingerprint
        file=self.root/'doc.txt';file.write_text('approved original',encoding='utf-8')
        p=self.create();p=self.add(p,path=file)
        def swap(path):
            stamp=fingerprint(path);file.write_text('UNREVIEWED replacement',encoding='utf-8');return stamp
        with patch('site_materials.fingerprint',side_effect=swap):
            result=self.s.preview(p['id'],p['entries'][0]['id'])
        self.assertEqual(result['text'],'approved original')

if __name__=='__main__':unittest.main()
