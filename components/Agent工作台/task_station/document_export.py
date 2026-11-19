"""Small, offline Word export of an existing text result. No model or Office dependency."""
import hashlib
from io import BytesIO
from pathlib import Path
import re
from unicodedata import east_asian_width
import zipfile
from xml.sax.saxutils import escape


WORD_TABLE_GUIDANCE = (
    '需要表格时，请用 Markdown 管道表格，包含表头、分隔行和数据行，列数保持一致。'
    '如果要求无表头或恰好若干行，把表格分别用 ```word-table 和 ``` 单独成行包住；'
    '块内每行用 | 单元格 | 单元格 | 表示一个实际的 Word 表格行，不写分隔行或额外表头。'
    '单元格内的竖线写作 \\|，标题和其他正文放在表格之外。'
)
FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})[ \t]*(.*)$')
DIVIDER = re.compile(r':?-{3,}:?')
TABLE_WIDTH = 11906 - 2 * 1440
CELL_PADDING = 110
MIN_COLUMN_WIDTH = 840


def _paragraph(text, bold=False, size=22, spacing=120, alignment=None):
    properties = (
        f'<w:spacing w:after="{spacing}"/>'
        + (f'<w:jc w:val="{alignment}"/>' if alignment else '')
    )
    return (
        f'<w:p><w:pPr>{properties}</w:pPr><w:r><w:rPr>'
        '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Microsoft YaHei"/>'
        + ('<w:b/>' if bold else '')
        + f'<w:sz w:val="{size}"/></w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'
    )


def _pipe_row(line):
    line = line.strip()
    cells = ['']
    for piece in re.split(r'(\\[\\|]|\|)', line):
        if piece == '|':
            cells.append('')
        else:
            cells[-1] += piece[1:] if piece in (r'\|', r'\\') else piece
    if len(cells) < 2:
        return []
    if line.startswith('|'):
        cells.pop(0)
    if cells and not cells[-1]:
        cells.pop()
    return [cell.strip() for cell in cells]


def _alignment(divider):
    if divider.endswith(':'):
        return 'center' if divider.startswith(':') else 'right'
    return 'left'


def _column_widths(rows):
    columns = len(rows[0])
    if columns == 1:
        return [TABLE_WIDTH]
    minimum = min(MIN_COLUMN_WIDTH, TABLE_WIDTH // columns)
    # A wide CJK character takes roughly one 11 pt em, while Latin text averages half.
    # Limit each cell's influence so a single long entry cannot crowd every other column.
    preferred = []
    for column in zip(*rows):
        text_width = max(sum(220 if east_asian_width(char) in ('W', 'F') else 110 for char in cell)
                         for cell in column)
        preferred.append(max(minimum, min(TABLE_WIDTH // 2, text_width + 2 * CELL_PADDING)))

    if sum(preferred) <= TABLE_WIDTH:
        widths, weights = preferred, preferred
    else:
        widths = [minimum] * columns
        weights = [width - minimum for width in preferred]

    available = TABLE_WIDTH - sum(widths)
    total_weight = sum(weights)
    cumulative = assigned = 0
    result = []
    for width, weight in zip(widths, weights):
        cumulative += weight
        allocated = available * cumulative // total_weight
        result.append(width + allocated - assigned)
        assigned = allocated
    return result


def _table(rows, alignments, has_header):
    widths = _column_widths(rows)
    grid = ''.join(f'<w:gridCol w:w="{value}"/>' for value in widths)
    borders = ''.join(f'<w:{edge} w:val="single" w:sz="4" w:color="D9D9D9"/>'
                      for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'))
    margins = ''.join(f'<w:{edge} w:w="{CELL_PADDING}" w:type="dxa"/>' for edge in ('top', 'left', 'bottom', 'right'))
    result = [
        f'<w:tbl><w:tblPr><w:tblW w:w="{TABLE_WIDTH}" w:type="dxa"/>'
        f'<w:tblBorders>{borders}</w:tblBorders><w:tblLayout w:type="fixed"/>'
        f'<w:tblCellMar>{margins}</w:tblCellMar></w:tblPr><w:tblGrid>{grid}</w:tblGrid>'
    ]
    for index, row in enumerate(rows):
        header = has_header and index == 0
        result.append('<w:tr><w:trPr>' + ('<w:tblHeader/>' if header else '') + '</w:trPr>')
        for value, cell_width, alignment in zip(row, widths, alignments):
            fill = '<w:shd w:val="clear" w:fill="EDF2F7"/>' if header else ''
            result.append(
                f'<w:tc><w:tcPr><w:tcW w:w="{cell_width}" w:type="dxa"/>{fill}'
                '<w:vAlign w:val="center"/></w:tcPr>'
                + _paragraph(value, bold=header, spacing=0, alignment=alignment)
                + '</w:tc>'
            )
        result.append('</w:tr>')
    result.append('</w:tbl>')
    return ''.join(result)


def _closing_fence(line, marker):
    fence = FENCE.fullmatch(line)
    return (
        fence and not fence[2].strip() and fence[1][0] == marker[0]
        and len(fence[1]) >= len(marker)
    )


def _body_xml(lines):
    index = 0
    literal_fence = None
    while index < len(lines):
        line = lines[index]
        fence = FENCE.fullmatch(line)
        if literal_fence:
            if _closing_fence(line, literal_fence):
                literal_fence = None
        elif fence:
            marker, language = fence.groups()
            if language.strip() == 'word-table':
                end = next((i for i in range(index + 1, len(lines))
                            if _closing_fence(lines[i], marker)), len(lines))
                rows = [_pipe_row(row) for row in lines[index + 1:end]]
                if end < len(lines) and rows and 1 <= len(rows[0]) <= 63 and all(len(row) == len(rows[0]) for row in rows):
                    yield _table(rows, ['left'] * len(rows[0]), has_header=False)
                    index = end + 1
                    continue
            literal_fence = marker
        elif '|' in line and index + 1 < len(lines):
            header = _pipe_row(line)
            divider = _pipe_row(lines[index + 1])
            if 1 <= len(header) <= 63 and len(divider) == len(header) and all(DIVIDER.fullmatch(cell) for cell in divider):
                rows = [header]
                index += 2
                while index < len(lines):
                    row = _pipe_row(lines[index])
                    if len(row) != len(header):
                        break
                    rows.append(row)
                    index += 1
                yield _table(rows, [_alignment(cell) for cell in divider], has_header=True)
                continue

        heading = re.match(r'^#{1,3}\s+(.+)$', line)
        value = heading.group(1) if heading else line
        value = re.sub(r'^[-*]\s+', '• ', value)
        yield _paragraph(value, bold=bool(heading), size=30 if heading else 22)
        index += 1


def document_bytes(text):
    # XML 1.0 rejects control characters, even when escaped.
    text = re.sub(r'[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]', '', text)
    body = ''.join(_body_xml(text.replace('\r\n', '\n').replace('\r', '\n').split('\n')))
    parts = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        'word/document.xml': '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + body + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>',
    }
    output = BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, xml in parts.items():
            archive.writestr(zipfile.ZipInfo(name), '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + xml,
                             compress_type=zipfile.ZIP_DEFLATED)
    return output.getvalue()


def write_document(folder, text):
    folder = Path(folder)
    folder.mkdir(exist_ok=True)
    raw = document_bytes(text)
    target = folder / ('文档-' + hashlib.sha256(raw).hexdigest()[:16] + '.docx')
    if target.is_symlink():
        raise ValueError('成果文件不能是链接')
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError('已有同名文件，未覆盖')
        return target
    # Exclusive creation never overwrites imported files. Remove only our failed partial write.
    with target.open('xb') as stream:
        try:
            stream.write(raw)
        except Exception:
            stream.close()
            target.unlink(missing_ok=True)
            raise
    return target
