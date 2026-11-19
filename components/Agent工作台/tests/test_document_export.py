from pathlib import Path
import sys, tempfile, threading, time, unittest, zipfile
from io import BytesIO
from xml.etree import ElementTree as ET
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from task_station.core import Service
from task_station.document_export import TABLE_WIDTH, document_bytes


class WordTableTests(unittest.TestCase):
    def parse_word(self, text):
        with zipfile.ZipFile(BytesIO(document_bytes(text))) as archive:
            return ET.fromstring(archive.read('word/document.xml'))

    def test_three_rows_from_original_collaboration_and_headerless_table(self):
        values = ['周一整理资料', '周三核对进度', '周五提交文档']
        lines = ['| ' + value + ' |' for value in values]
        for source, headers in [([lines[0], '| :--- |', *lines[1:]], 1),
                                (['```word-table', *lines, '```'], 0)]:
            with self.subTest(headers=headers):
                document = self.parse_word('\n'.join(['# 示例 · 三步验收安排', '', *source]))
                tables = document.findall('.//{*}tbl')
                self.assertEqual(len(tables), 1)
                rows = tables[0].findall('{*}tr')
                self.assertEqual([row.findtext('.//{*}t') for row in rows], values)
                self.assertEqual(len(tables[0].findall('.//{*}tblHeader')), headers)

    def test_table_cells_and_surrounding_prose_preserve_content(self):
        text = '# 安排\n| 日期 | 要求 |\n| :---: | ---: |\n| 周一 | A \\| B & <说明> |\n\n正文 A | B'
        document = self.parse_word(text)
        body = document.find('{*}body')
        table = body.find('{*}tbl')
        row = table.findall('{*}tr')[1]
        self.assertEqual([cell.findtext('.//{*}t') for cell in row.findall('{*}tc')], ['周一', 'A | B & <说明>'])
        self.assertEqual([node.findtext('.//{*}t') for node in body.findall('{*}p')], ['安排', '', '正文 A | B'])

    def test_unmarked_pipe_prose_and_literal_code_are_not_tables(self):
        text = '结果 A | B\n\n```text\n| 字段 |\n| --- |\n| 示例 |\n```'
        document = self.parse_word(text)
        self.assertIsNone(document.find('.//{*}tbl'))
        self.assertIn('| 示例 |', ''.join(document.itertext()))

    def test_long_description_gets_more_width_with_fixed_page_grid(self):
        text = ('| 编号 | 验收说明 | 状态 |\n| :---: | --- | :---: |\n| 01 | '
                + '核对日期和版本，保留需要确认的材料。' * 5 + ' | 待确认 |')
        table = self.parse_word(text).find('.//{*}tbl')
        word_ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        widths = [int(column.get(word_ns + 'w')) for column in table.findall('.//{*}gridCol')]
        self.assertEqual(sum(widths), TABLE_WIDTH)
        self.assertGreater(widths[1], max(widths[0], widths[2]))
        self.assertEqual(table.find('.//{*}tblLayout').get(word_ns + 'type'), 'fixed')
        for row in table.findall('{*}tr'):
            self.assertEqual([int(cell.get(word_ns + 'w')) for cell in row.findall('.//{*}tcW')], widths)

class Fake:
    def __init__(self): self.calls=0
    def capabilities(self): return {'text_1': {'mode':'test','can_run':True}}
    def run(self, role, prompt, cancel, chunk, folder):
        self.calls+=1
        return '# 项目说明\n\n中文正文 & <测试>\n- 需要核对的数据'

class DocumentExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.fake=Fake();self.s=Service(Path(self.tmp.name),self.fake)
    def tearDown(self): self.s.close();self.tmp.cleanup()
    def create(self): return self.s.call('create',{'task_type':'text','role':'text_1','instruction':'写项目说明文档'})
    def check_doc(self,task):
        files=[f for f in task['files'] if f['name'].endswith('.docx')];self.assertEqual(len(files),1)
        path=self.s.file_path(task['id'],files[0]['name'])
        with zipfile.ZipFile(path) as z:
            self.assertIsNone(z.testzip())
            for name in z.namelist(): ET.fromstring(z.read(name))
            xml=z.read('word/document.xml').decode();self.assertIn('中文正文',xml);self.assertIn('&amp;',xml)
        return path.read_bytes()
    def test_model_text_automatically_has_real_word_artifact(self):
        t=self.create();self.s.call('submit',{'id':t['id']})
        until=time.monotonic()+5
        while self.s.jobs and time.monotonic()<until: time.sleep(.01)
        t=self.s.call('get',{'id':t['id']});self.assertEqual(t['status'],'结果待确认');self.check_doc(t);self.assertEqual(self.fake.calls,1)
    def test_existing_result_can_export_without_model_or_completion_and_is_idempotent(self):
        t=self.create()
        with self.s.lock:
            raw=self.s._load(t['id']);raw.update(result='# 标题\n中文正文 & <测试>',status='结果待确认');self.s._save(raw)
        a=self.s.call('export_document',{'id':t['id']});content=self.check_doc(a)
        b=self.s.call('export_document',{'id':t['id']});self.assertEqual(self.check_doc(b),content)
        self.assertEqual(b['status'],'结果待确认');self.assertEqual(self.fake.calls,0)
    def test_empty_or_running_results_cannot_be_exported(self):
        t=self.create()
        with self.assertRaises(ValueError):self.s.call('export_document',{'id':t['id']})
        with self.s.lock:
            raw=self.s._load(t['id']);raw.update(result='未完正文',status='执行中');self.s._save(raw)
        with self.assertRaises(ValueError):self.s.call('export_document',{'id':t['id']})
    def test_file_failure_preserves_returned_text(self):
        t=self.create()
        with patch('task_station.core.write_document',side_effect=OSError('disk unavailable')):
            self.s.call('submit',{'id':t['id']})
            until=time.monotonic()+5
            while self.s.jobs and time.monotonic()<until:time.sleep(.01)
        t=self.s.call('get',{'id':t['id']});self.assertEqual(t['status'],'结果待确认');self.assertIn('中文正文',t['result']);self.assertIn('Word',t['events'][-1]['message'])

if __name__=='__main__':unittest.main()
