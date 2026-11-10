import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from tasks import TaskManager
from file_review import FileReview, capture_baseline


def xlsx(rows='<row r="1"><c r="A1" t="inlineStr"><is><t>名称</t></is></c><c r="B1"><v>0</v></c></row>'):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('xl/workbook.xml','<workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="数据" r:id="r1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml','<worksheet><sheetData>'+rows+'</sheetData></worksheet>')
    return out.getvalue()


class FileReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.tasks=TaskManager(self.root,start_worker=False)
        self.task=self.tasks.create({'goal':'文件查看','agent':'demo','client_id':'files'})
        self.id=self.task['id'];self.ws=self.tasks.workspace(self.id);self.service=FileReview(self.tasks)

    def tearDown(self):
        self.tasks.close();self.tmp.cleanup()

    def put(self,name,content):
        p=self.ws/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(content if isinstance(content,bytes) else content.encode())
        self.tasks.collect_artifacts(self.id)
        return p

    def test_text_kinds_and_unknown_baseline_no_writes(self):
        for name,kind in [('src/main.py','code'),('README.md','markdown'),('run.log','log'),('note.txt','text'),('page.html','code')]:
            self.put(name,'# hello\n<script>alert(1)</script>')
            before=self.tasks.get(self.id)
            r=self.service.read(self.id,name)
            self.assertEqual(r['kind'],kind);self.assertIn('<script>',r['text'])
            self.assertFalse(r['diff']['available']);self.assertEqual(self.tasks.get(self.id),before)
        self.assertEqual(len(self.service.files(self.id)['files']),5)
        self.assertFalse((self.tasks.data/self.id/'review-baseline.json').exists())

    def test_baseline_added_modified_and_unchanged(self):
        self.put('a.py','old\n');capture_baseline(self.tasks,self.id)
        self.put('a.py','new\n');self.put('b.js','const n=1;\n')
        d=self.service.read(self.id,'a.py')['diff'];self.assertTrue(d['available']);self.assertIn('-old',d['text']);self.assertIn('+new',d['text'])
        self.assertIn('+const',self.service.read(self.id,'b.js')['diff']['text'])
        # A second capture must not erase the task-start baseline.
        capture_baseline(self.tasks,self.id)
        self.assertIn('-old',self.service.read(self.id,'a.py')['diff']['text'])

    def test_diff_keeps_separate_lines_without_final_newline(self):
        self.put('a.py','old');capture_baseline(self.tasks,self.id);self.put('a.py','new')
        d=self.service.read(self.id,'a.py')['diff']['text']
        self.assertIn('-old\n',d);self.assertIn('+new\n',d)

    def test_xlsx_display_budget_for_repeated_large_strings(self):
        rows=''.join('<row r="'+str(r)+'">'+''.join('<c r="'+chr(65+c)+str(r)+'" t="inlineStr"><is><t>'+('x'*1000)+'</t></is></c>' for c in range(10))+'</row>' for r in range(1,101))
        self.put('large.xlsx',xlsx(rows))
        sheets=self.service.read(self.id,'large.xlsx')['sheets']
        self.assertLessEqual(sum(len(v) for s in sheets for row in s['rows'] for v in row),400000)
        self.assertTrue(sheets[0]['truncated'])

    def test_csv_quotes_encoding_zero_and_bounds(self):
        self.put('table.csv','名称,数量\n"a,b",0\n空,\n'.encode('gb18030'))
        s=self.service.read(self.id,'table.csv')['sheets'][0]
        self.assertEqual(s['rows'][1],['a,b','0']);self.assertEqual(s['rows'][2],['空',''])
        self.put('many.csv','a,b\n'+'1,2\n'*300)
        s=self.service.read(self.id,'many.csv')['sheets'][0];self.assertEqual(len(s['rows']),200);self.assertTrue(s['truncated'])
        self.put('wide.tsv','\t'.join(map(str,range(60))))
        s=self.service.read(self.id,'wide.tsv')['sheets'][0];self.assertEqual(len(s['rows'][0]),50);self.assertTrue(s['truncated'])

    def test_xlsx_values_sparse_cells_and_formula_not_evaluated(self):
        self.put('sheet.xlsx',xlsx('<row r="1"><c r="A1" t="inlineStr"><is><t>&lt;script&gt;</t></is></c><c r="C1"><f>1+1</f><v>2</v></c></row><row r="3"><c r="A3"><v>0</v></c><c r="B3"><f>HYPERLINK("http://evil")</f></c></row>'))
        s=self.service.read(self.id,'sheet.xlsx')['sheets'][0]
        self.assertEqual(s['name'],'数据');self.assertEqual(s['rows'][0],['<script>','','2'])
        self.assertEqual(s['rows'][1],[]);self.assertEqual(s['rows'][2],['0','[公式无缓存值]'])

    def test_rejects_unsafe_sources(self):
        for name in ['.env','keys/private.pem','auth.json','credentials.yaml','config/secrets.json','node_modules/pkg/x.py']:
            self.put(name,'sensitive')
            with self.assertRaises((ValueError,FileNotFoundError)):self.service.read(self.id,name)
        self.put('ok.py','ok')
        for name in ['../outside.py','/ok.py','ok.py:stream','x\\ok.py','not-registered.py']:
            with self.assertRaises((ValueError,FileNotFoundError)):self.service.read(self.id,name)
        self.assertEqual([f['path'] for f in self.service.files(self.id)['files']],['ok.py'])

    def test_size_binary_and_redaction(self):
        self.put('big.py',b'x'*(2*1024*1024+1))
        with self.assertRaises(ValueError):self.service.read(self.id,'big.py')
        self.put('binary.py',b'abc\x00secret')
        with self.assertRaises(ValueError):self.service.read(self.id,'binary.py')
        self.put('large.txt','x'*40000)
        r=self.service.read(self.id,'large.txt');self.assertTrue(r['truncated']);self.assertLessEqual(len(r['text']),30000)
        self.put('run.log','\x1b[31mError\x1b[0m Authorization: Bearer abc123secret\napi_key="sensitive-key"\n')
        t=self.service.read(self.id,'run.log')['text'];self.assertNotIn('\x1b',t);self.assertNotIn('abc123secret',t);self.assertNotIn('sensitive-key',t)

    def test_xlsx_rejects_hostile_or_corrupt_packages(self):
        for payload in [b'not a zip',b'PK\x00']:
            self.put('bad.xlsx',payload)
            with self.assertRaises(ValueError):self.service.read(self.id,'bad.xlsx')
        for name,body in [('xl/evil.xml','<!DOCTYPE x [<!ENTITY a "hello">]><x>&a;</x>'),('xl/vbaProject.bin','macro')]:
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w') as z:z.writestr(name,body)
            self.put('bad.xlsx',out.getvalue())
            with self.assertRaises(ValueError):self.service.read(self.id,'bad.xlsx')

    def test_image_and_office_kinds(self):
        self.put('shot.png',bytes.fromhex('89504e470d0a1a0a')+b'fixture')
        self.assertEqual(self.service.read(self.id,'shot.png')['kind'],'image')
        data,mime=self.service.image(self.id,'shot.png');self.assertEqual(mime,'image/png')
        self.put('fake.png',b'<html>bad</html>')
        with self.assertRaises(ValueError):self.service.image(self.id,'fake.png')
        self.put('deck.pptx',b'PK');self.assertEqual(self.service.read(self.id,'deck.pptx')['kind'],'pdf')
        self.put('archive.zip',b'PK');self.assertEqual(self.service.read(self.id,'archive.zip')['kind'],'unsupported')

    def test_incomplete_baseline_never_claims_new_files(self):
        with patch('file_review.os.scandir',side_effect=PermissionError('unreadable')):
            capture_baseline(self.tasks,self.id)
        b=json.loads((self.tasks.data/self.id/'review-baseline.json').read_text(encoding='utf-8'))
        self.assertFalse(b['complete'])
        self.put('later.py','later')
        self.assertFalse(self.service.read(self.id,'later.py')['diff']['available'])

    def test_baseline_bounds_empty_directory_walk(self):
        for i in range(205):(self.ws/('dir'+str(i))).mkdir()
        capture_baseline(self.tasks,self.id)
        b=json.loads((self.tasks.data/self.id/'review-baseline.json').read_text(encoding='utf-8'))
        self.assertFalse(b['complete'])

    def test_reparse_file_is_not_read(self):
        outside=self.root/'outside.py';outside.write_text('PRIVATE')
        link=self.ws/'link.py'
        try:link.symlink_to(outside)
        except OSError:self.skipTest('Windows symlink privilege unavailable')
        self.tasks.update(self.id,artifacts=[{'path':'link.py','name':'link.py','size':7}])
        with self.assertRaises((ValueError,OSError)):self.service.read(self.id,'link.py')


if __name__=='__main__':unittest.main()
