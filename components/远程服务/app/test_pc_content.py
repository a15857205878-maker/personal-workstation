from pathlib import Path
import json, os, tempfile, unittest
from pc_files import ComputerFiles

class ContentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.folder=self.root/'资料'; self.folder.mkdir(); self.service=ComputerFiles(self.root/'service')
        self.service.set_library(self.folder)
    def tearDown(self): self.tmp.cleanup()
    def test_body_line_and_original_ticket(self):
        p=self.folder/'设计.md'; p.write_text('第一行\n第二行：海岸主题\n保留原件',encoding='utf-8')
        result=self.service.library_content('海岸')
        self.assertEqual(len(result['files']),1); row=result['files'][0]
        self.assertEqual(row['location'],'第2行'); self.assertIn('海岸主题',row['excerpt'])
        self.assertNotIn(str(self.root),json.dumps(result,ensure_ascii=False))
        with self.service.open_file(row['id']) as f:self.assertEqual(f.read(),p.read_bytes())
    def test_cache_refresh_delete_and_library_change(self):
        p=self.folder/'note.txt'; p.write_text('旧关键词',encoding='utf-8')
        self.assertEqual(len(self.service.library_content('旧关键词')['files']),1)
        p.write_text('新关键词',encoding='utf-8')
        self.assertEqual(self.service.library_content('旧关键词')['files'],[])
        result=self.service.library_content('新关键词'); self.assertEqual(len(result['files']),1)
        other=self.root/'other'; other.mkdir(); self.service.set_library(other)
        self.assertEqual(self.service.library_content('新关键词')['files'],[])
        with self.assertRaises(ValueError):self.service.open_file(result['files'][0]['id'])
        self.service.set_library(self.folder); p.unlink()
        self.assertEqual(self.service.library_content('新关键词')['files'],[])
    def test_limits_bad_pdf_and_private(self):
        (self.folder/'large.txt').write_bytes(b'x'*(2*1024*1024+1))
        (self.folder/'broken.pdf').write_bytes(b'not pdf')
        (self.folder/'secret.key').write_text('海岸')
        result=self.service.library_content('海岸')
        self.assertEqual(result['files'],[]); self.assertTrue(result['warnings'])
        self.assertEqual((self.folder/'broken.pdf').read_bytes(),b'not pdf')
        for q in ['', 'x'*121]:
            with self.assertRaises(ValueError):self.service.library_content(q)
    def test_hardlinks_are_excluded(self):
        source=self.root/'outside.txt';source.write_text('海岸',encoding='utf-8')
        os.link(source,self.folder/'link.txt')
        self.assertEqual(self.service.library_content('海岸')['files'],[])
    def test_pdf_page_number(self):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, NameObject, DictionaryObject
        writer=PdfWriter()
        for text in ['alpha','coastal material']:
            page=writer.add_blank_page(width=300,height=300)
            font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
            page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
            stream=DecodedStreamObject();stream.set_data(('BT /F1 12 Tf 10 100 Td ('+text+') Tj ET').encode())
            page[NameObject('/Contents')]=writer._add_object(stream)
        with (self.folder/'book.pdf').open('wb') as f:writer.write(f)
        row=self.service.library_content('coastal')['files'][0]
        self.assertEqual(row['location'],'第2页'); self.assertIn('coastal',row['excerpt'])

if __name__=='__main__': unittest.main()
