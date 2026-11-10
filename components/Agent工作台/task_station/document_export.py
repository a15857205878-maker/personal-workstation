"""Small, offline Word export of an existing text result. No model or Office dependency."""
import hashlib
from io import BytesIO
from pathlib import Path
import re
import zipfile
from xml.sax.saxutils import escape


def document_bytes(text):
    # XML 1.0 rejects control characters, even when escaped.
    text = re.sub(r'[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]', '', text)
    paragraphs = []
    for line in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        heading = re.match(r'^#{1,3}\s+(.+)$', line)
        value = heading.group(1) if heading else line
        value = re.sub(r'^[-*]\s+', '• ', value)
        properties = '<w:b/><w:sz w:val="30"/>' if heading else '<w:sz w:val="22"/>'
        paragraphs.append('<w:p><w:pPr><w:spacing w:after="120"/></w:pPr><w:r><w:rPr>'
                          '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Microsoft YaHei"/>'
                          + properties + '</w:rPr><w:t xml:space="preserve">' + escape(value) + '</w:t></w:r></w:p>')
    parts = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        'word/document.xml': '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + ''.join(paragraphs) + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>',
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
