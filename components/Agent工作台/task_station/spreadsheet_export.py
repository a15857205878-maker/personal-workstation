"""Bounded offline XLSX export from model JSON. No macros, links or code execution."""
import ast
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import re
import zipfile
from xml.sax.saxutils import escape

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
CONTRACT = '''交付方式：仅返回一个JSON对象，不写文件、不编造下载链接。格式：
{"version":1,"sheets":[{"name":"预算","columns":["项目","数量","单价","小计"],"rows":[["材料",2,12.5,{"formula":"=B2*C2"}],["合计",null,null,{"formula":"=SUM(D2:D2)"}]]}]}
示例仅演示格式，不是用户数据，不能照搬。columns是第1行标题，rows从第2行开始。最多3张表、每张2000行20列，总计10000个数据单元格。只使用给定或有依据的数据，缺失用null并在列名或备注中明确，不补造数值。普通文字是字符串；计算必须用{"formula":"=..."}，只支持同表A1引用、加减乘除、括号、SUM(A2:A5)。不支持跨表、外部链接、宏、代码或其他函数。公式引用须在本表数据区域内且无循环；不要用完整表格大纲冒充数据。工作站会校验后生成真正XLSX；若材料不足可返回空数据行或留空，不得杜撰。'''

def col(index):
    value = ''
    while index:
        index, rem = divmod(index - 1, 26)
        value = chr(65 + rem) + value
    return value

def parse(text):
    if not isinstance(text, str) or len(text) > 180000:
        raise ValueError('表格数据过大，最多180000字符')
    text = text.strip()
    if text.startswith('```json\n') and text.endswith('```'):
        text = text[8:-3].strip()
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        raise ValueError('需要完整的表格JSON数据，普通文字不能转换成表格') from None
    if not isinstance(value, dict) or (type(value.get('version')) is not int or value.get('version') != 1) or set(value) != {'version', 'sheets'}:
        raise ValueError('表格须包含version=1和sheets')
    sheets = value['sheets']
    if not isinstance(sheets, list) or not 1 <= len(sheets) <= 3:
        raise ValueError('表格须包含1至3个工作表')
    total, names = 0, set()
    for sheet in sheets:
        if not isinstance(sheet, dict) or set(sheet) != {'name', 'columns', 'rows'}:
            raise ValueError('工作表须包含name、columns、rows')
        name, columns, rows = sheet['name'], sheet['columns'], sheet['rows']
        if not isinstance(name, str) or not name.strip() or len(name) > 31 or re.search(r'[\x00-\x1f\\/?*\[\]:]', name) or name.startswith("'") or name.endswith("'") or name.casefold() in names:
            raise ValueError('工作表名称无效或重复')
        names.add(name.casefold())
        if not isinstance(columns, list) or not 1 <= len(columns) <= 20 or any(not isinstance(c, str) or not c.strip() or len(c) > 120 or re.search(r'[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]', c) for c in columns):
            raise ValueError('请提供1至20列明确标题')
        if not isinstance(rows, list) or len(rows) > 2000:
            raise ValueError('每个工作表最多2000行')
        for row in rows:
            if not isinstance(row, list) or len(row) != len(columns):
                raise ValueError('每行数据数量必须与标题列数相同')
            total += len(row)
            if total > 10000:
                raise ValueError('数据单元格最多10000个')
            for cell in row:
                if cell is None or type(cell) is bool:
                    continue
                if type(cell) in (int, float):
                    if not math.isfinite(cell) or abs(cell) > 1e100:
                        raise ValueError('数值超出有效范围')
                elif isinstance(cell, str):
                    if len(cell) > 4000 or re.search(r'[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]', cell):
                        raise ValueError('单元格文本过长或含无效字符')
                elif not isinstance(cell, dict) or set(cell) != {'formula'} or not isinstance(cell['formula'], str):
                    raise ValueError('单元格只接受文字、数字、空值或公式')
    return sheets

class Formulas:
    def __init__(self, sheet):
        self.cells = {col(c) + str(r): value for r, row in enumerate(sheet['rows'], 2) for c, value in enumerate(row, 1)}
        self.cache, self.visiting = {}, set()
    def value(self, ref, summed=False):
        if ref not in self.cells:
            raise ValueError('公式引用超出当前表格数据区域')
        cell = self.cells[ref]
        if cell is None:
            return 0
        if type(cell) in (int, float, bool):
            return int(cell) if type(cell) is bool else cell
        if isinstance(cell, str):
            if summed:
                return 0
            raise ValueError('计算引用了文字单元格')
        if ref in self.cache:
            return self.cache[ref]
        if ref in self.visiting or len(self.visiting) >= 80:
            raise ValueError('公式存在循环或引用链过长')
        self.visiting.add(ref)
        try:
            result = self.calculate(cell['formula'])
            if not math.isfinite(result) or abs(result) > 1e100:
                raise ValueError('公式结果超出有效范围')
            self.cache[ref] = result
            return result
        finally:
            self.visiting.remove(ref)
    def calculate(self, formula):
        if not re.fullmatch(r'=[A-Z0-9+*/().:\s-]{1,255}', formula):
            raise ValueError('公式只支持同表引用、加减乘除和SUM范围')
        expr = formula[1:]
        def summed(match):
            a, first, b, last = match.groups()
            # Only same-column ranges keep this first version easy to inspect.
            if a != b or int(first) > int(last) or int(last) - int(first) > 2000:
                raise ValueError('SUM仅支持同一列的有效数据范围')
            return str(sum(self.value(a + str(r), True) for r in range(int(first), int(last) + 1)))
        expr = re.sub(r'SUM\(([A-T])([1-9][0-9]{0,3}):([A-T])([1-9][0-9]{0,3})\)', summed, expr)
        expr = re.sub(r'\b([A-T][1-9][0-9]{0,3})\b', lambda m: '(' + str(self.value(m[1])) + ')', expr)
        try:
            tree = ast.parse(expr, mode='eval')
            if len(list(ast.walk(tree))) > 100:
                raise ValueError('公式过于复杂')
            def visit(node):
                if isinstance(node, ast.Expression): return visit(node.body)
                if isinstance(node, ast.Constant) and type(node.value) in (int, float): return node.value
                if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                    return visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
                if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
                    left, right = visit(node.left), visit(node.right)
                    if isinstance(node.op, ast.Add): return left + right
                    if isinstance(node.op, ast.Sub): return left - right
                    if isinstance(node.op, ast.Mult): return left * right
                    return left / right
                raise ValueError('公式不受支持')
            return visit(tree)
        except (SyntaxError, ZeroDivisionError, OverflowError, RecursionError):
            raise ValueError('公式有语法错误、除零或超出计算范围') from None

def text_cell(ref, value, style=0):
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(value)}</t></is></c>'

def spreadsheet_bytes(text):
    sheets = parse(text)
    parts = {'_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'}
    overrides, links, tabs = [], [], []
    for number, sheet in enumerate(sheets, 1):
        formulas = Formulas(sheet)
        rows = ['<row r="1" ht="28" customHeight="1">' + ''.join(text_cell(col(i)+'1',v,1) for i,v in enumerate(sheet['columns'],1)) + '</row>']
        for r, row in enumerate(sheet['rows'], 2):
            cells = []
            for c, value in enumerate(row, 1):
                ref = col(c)+str(r)
                if isinstance(value, dict): cells.append(f'<c r="{ref}" s="3"><f>{escape(value["formula"][1:])}</f><v>{formulas.value(ref)}</v></c>')
                elif value is None: cells.append(f'<c r="{ref}"/>')
                elif type(value) is bool: cells.append(f'<c r="{ref}" t="b"><v>{int(value)}</v></c>')
                elif type(value) in (int,float): cells.append(f'<c r="{ref}" s="2"><v>{value}</v></c>')
                else: cells.append(text_cell(ref,value))
            rows.append(f'<row r="{r}">'+''.join(cells)+'</row>')
        end=col(len(sheet['columns']))+str(len(sheet['rows'])+1)
        parts[f'xl/worksheets/sheet{number}.xml']=f'<worksheet xmlns="{NS}"><dimension ref="A1:{end}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="22"/><cols><col min="1" max="{len(sheet["columns"])}" width="22" customWidth="1"/></cols><sheetData>'+''.join(rows)+f'</sheetData><autoFilter ref="A1:{end}"/><pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/><pageSetup orientation="landscape" paperSize="9" fitToWidth="1" fitToHeight="0"/></worksheet>'
        tabs.append(f'<sheet name="{escape(sheet["name"], {chr(34):"&quot;"})}" sheetId="{number}" r:id="rId{number}"/>')
        links.append(f'<Relationship Id="rId{number}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{number}.xml"/>')
        overrides.append(f'<Override PartName="/xl/worksheets/sheet{number}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
    parts['xl/workbook.xml']=f'<workbook xmlns="{NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(tabs)+'</sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>'
    links.append('<Relationship Id="styles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>')
    parts['xl/_rels/workbook.xml.rels']='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(links)+'</Relationships>'
    parts['xl/styles.xml']=f'<styleSheet xmlns="{NS}"><fonts count="3"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font><font><color rgb="FF2463A8"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF24486A"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="4"><xf fontId="0" fillId="0" borderId="0" xfId="0"><alignment vertical="center" wrapText="1"/></xf><xf fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1"/><xf fontId="2" fillId="0" borderId="0" xfId="0" numFmtId="4" applyNumberFormat="1" applyFont="1"/><xf fontId="0" fillId="0" borderId="0" xfId="0" numFmtId="4" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
    parts['[Content_Types].xml']='<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'+''.join(overrides)+'</Types>'
    output=BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,xml in parts.items():archive.writestr(zipfile.ZipInfo(name),'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+xml,compress_type=zipfile.ZIP_DEFLATED)
    return output.getvalue()

def write_spreadsheet(folder,text):
    raw=spreadsheet_bytes(text)
    folder=Path(folder);folder.mkdir(exist_ok=True)
    target=folder/('表格-'+hashlib.sha256(raw).hexdigest()[:16]+'.xlsx')
    if target.is_symlink():raise ValueError('成果文件不能是链接')
    if target.exists():
        if target.read_bytes()!=raw:raise ValueError('已有同名文件，未覆盖')
        return target
    with target.open('xb') as stream:
        try:stream.write(raw)
        except Exception:
            stream.close();target.unlink(missing_ok=True);raise
    return target
