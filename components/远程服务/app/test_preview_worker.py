import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class PreviewWorkerTests(unittest.TestCase):
    def test_multi_page_tiff_preserves_all_pages(self):
        runtime=Path(sys.executable)
        script='''
import sys,tempfile
from pathlib import Path
from PIL import Image
from pypdf import PdfReader
sys.path.insert(0,sys.argv[1])
import preview_worker
with tempfile.TemporaryDirectory() as raw:
 root=Path(raw);source=root/'two.tiff'
 Image.new('RGB',(100,100),'red').save(source,save_all=True,append_images=[Image.new('RGB',(100,100),'blue')])
 result=preview_worker.image_pdf(source,root)
 assert len(PdfReader(result).pages)==2
'''
        result=subprocess.run([str(runtime),'-c',script,str(Path(__file__).parent)],stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))

    def test_office_profile_and_input_use_short_private_temporary_paths(self):
        runtime=Path(sys.executable)
        script='''
import sys,tempfile,zipfile,json
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from urllib.parse import urlsplit,unquote
sys.path.insert(0,sys.argv[1])
import preview_worker
with tempfile.TemporaryDirectory() as raw:
 root=Path(raw);out=root/('a'*70)/('b'*70);out.mkdir(parents=True)
 source=root/'document.docx'
 with zipfile.ZipFile(source,'w') as z:z.writestr('word/document.xml','<document/>')
 seen=[]
 def run(args,**kwargs):
  uri=next(x.split('=',1)[1] for x in args if x.startswith('-env:UserInstallation='))
  value=unquote(urlsplit(uri).path).lstrip('/')
  assert len(value)<160, len(value)
  assert Path(value).is_relative_to(Path.home()/'AppData/Local/Temp/AgentWorkbenchPreview')
  assert len(args[-1])<160
  target=Path(args[args.index('--outdir')+1]);target.mkdir(exist_ok=True)
  (target/(Path(args[-1]).stem+'.pdf')).write_bytes(b'%PDF-1.4 test')
  seen.append(value);return SimpleNamespace(returncode=0)
 with patch.object(preview_worker.subprocess,'run',run),patch.object(tempfile,'mkdtemp',side_effect=AssertionError('owner-only temporary ACL must not be used')):result=preview_worker.office_pdf(source,out)
 assert result.is_file() and len(seen)==1
 assert not Path(seen[0]).exists()
 print(json.dumps({'shortProfile':True,'sourceStaged':True,'privateProfileRemoved':True}))
'''
        result=subprocess.run([str(runtime),'-c',script,str(Path(__file__).parent)],stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
        self.assertTrue(json.loads(result.stdout)['shortProfile'])

    def test_pptx_uses_installed_filee_and_keeps_original(self):
        runtime=Path(sys.executable)
        script="""
import sys,tempfile,zipfile,json,hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,sys.argv[1]);import preview_worker
with tempfile.TemporaryDirectory() as raw:
 root=Path(raw);source=root/'slides.pptx';out=root/'out';out.mkdir()
 with zipfile.ZipFile(source,'w') as z:z.writestr('ppt/presentation.xml','<presentation/>')
 before=hashlib.sha256(source.read_bytes()).hexdigest();seen=[]
 def run(args,**kwargs):
  assert '--to' in args and args[args.index('--to')+1]=='pdf'
  assert '--overwrite' not in args and '--move-originals' not in args
  assert Path(args[2])==source
  folder=Path(args[args.index('--output')+1]);target=folder/'slides.pdf';target.write_bytes(b'%PDF-1.4 test')
  seen.append(args);return SimpleNamespace(returncode=0,stdout=json.dumps({'converted':1,'failed':0}).encode(),stderr=b'')
 with patch.object(preview_worker,'find_filee',return_value=Path('filee-cli.exe')),patch.object(preview_worker.subprocess,'run',run):target=preview_worker.office_pdf(source,out)
 assert target.read_bytes().startswith(b'%PDF-') and len(seen)==1
 assert hashlib.sha256(source.read_bytes()).hexdigest()==before
 empty=root/'empty-output';empty.mkdir()
 with patch.object(preview_worker.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=b'{"converted":1,"failed":0}',stderr=b'')):
  try:preview_worker.filee_pdf(source,empty,Path('filee-cli.exe'))
  except preview_worker.ConversionError:pass
  else:raise AssertionError('CLI success without a PDF must be rejected')
"""
        result=subprocess.run([str(runtime),'-c',script,str(Path(__file__).parent)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))

    def test_office_permission_failure_is_not_reported_as_a_bad_document(self):
        runtime=Path(sys.executable)
        script="""
import sys,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,sys.argv[1]);import preview_worker
with tempfile.TemporaryDirectory() as raw:
 root=Path(raw);source=root/'a.xlsx';source.write_bytes(b'fixture');out=root/'out';out.mkdir();short=root/'short';short.mkdir()
 with patch.object(preview_worker.subprocess,'run',return_value=SimpleNamespace(returncode=77,stdout=b'',stderr=b'User installation cannot be completed due to insufficient permissions')):
  try:preview_worker._office_pdf_short(source,out,Path('soffice.com'),short)
  except preview_worker.ConversionError as error:
   assert '权限' in str(error),str(error)
   assert '密码' not in str(error),str(error)
  else:raise AssertionError('conversion should fail')
"""
        result=subprocess.run([str(runtime),'-c',script,str(Path(__file__).parent)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))

    def test_xlsx_data_pdf_reads_cached_values_without_office_or_changing_source(self):
        runtime=Path(sys.executable)
        script="""
import sys,tempfile,zipfile,hashlib
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfReader
sys.path.insert(0,sys.argv[1]);import preview_worker
with tempfile.TemporaryDirectory() as raw:
 root=Path(raw);source=root/'test.xlsx'
 parts={'xl/workbook.xml':'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="预算" sheetId="1" r:id="rId1"/></sheets></workbook>','xl/_rels/workbook.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>','xl/worksheets/sheet1.xml':'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>项目</t></is></c><c r="B1" t="inlineStr"><is><t>金额</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>合计</t></is></c><c r="B2"><f>SUM(B3:B4)</f><v>49</v></c></row><row r="3"><c r="B3"><v>25</v></c></row><row r="4"><c r="B4"><v>24</v></c></row><row r="5"><c r="B5"><f>SUM(B3:B4)</f></c></row></sheetData></worksheet>'}
 with zipfile.ZipFile(source,'w') as z:
  for name,body in parts.items():z.writestr(name,body)
 before=hashlib.sha256(source.read_bytes()).hexdigest()
 with patch.object(preview_worker,'office_pdf',side_effect=AssertionError('Office must not run for basic XLSX')):
  result=preview_worker.convert(source,root)
 assert result['pages']>=1
 text=''.join(page.extract_text() for page in PdfReader(root/'source-xlsx.pdf').pages)
 assert '49' in text and '合计' in text and '未缓存' in text,text
 assert (root/'document.pdf').read_bytes().startswith(b'%PDF-')
 assert hashlib.sha256(source.read_bytes()).hexdigest()==before
"""
        result=subprocess.run([str(runtime),'-c',script,str(Path(__file__).parent)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))

    def test_failure_receipt_is_valid_json_even_with_ascii_process_output(self):
        runtime=Path(sys.executable)
        if not runtime.is_file():self.skipTest('bundled PDF runtime unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'invalid.pdf';source.write_bytes(b'not a pdf')
            result=subprocess.run([str(runtime),str(Path(__file__).with_name('preview_worker.py')),str(source),tmp],
                                  env=dict(os.environ,PYTHONIOENCODING='ascii'),stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.assertNotEqual(result.returncode,0)
            self.assertIn('error',json.loads(result.stdout))
            self.assertNotIn(b'UnicodeEncodeError',result.stderr)


if __name__=='__main__':unittest.main()
