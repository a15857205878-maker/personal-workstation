"""Passive, bounded text extraction. Called in a disposable process; never executes files."""
from pathlib import Path
import json,re,sys,zipfile,xml.etree.ElementTree as ET,subprocess,os
MAX_CHARS=18000
SUPPORTED={'.txt','.md','.csv','.tsv','.json','.log','.docx','.pptx','.xlsx','.pdf','.png','.jpg','.jpeg','.bmp','.webp'}
def finish(text):
    text=text.replace('\x00','').strip()
    if not text:raise ValueError('未识别出可用文字；扫描PDF请先转成文字，图片OCR不代表理解图表内容。')
    if len(text)>MAX_CHARS:raise ValueError('识别文字超过18000字符，请先拆分或精简附件；未自动截断。')
    return text

def xml(raw):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('附件包含不支持的XML声明。')
    return ET.fromstring(raw)
def local(e):return e.tag.rsplit('}',1)[-1]
def paragraphs(raw):
    root=xml(raw);rows=[''.join(t.text or '' for t in e.iter() if local(t) in ('t','tab','br')) for e in root.iter() if local(e)=='p']
    return '\n'.join(rows)
def office(path):
    with zipfile.ZipFile(path) as z:
        entries=z.infolist();names=[e.filename for e in entries]
        if len(entries)>2000 or len(set(names))!=len(names) or sum(e.file_size for e in entries)>32*1024*1024 or any(e.file_size>8*1024*1024 or e.flag_bits&1 or '..' in Path(e.filename).parts for e in entries):raise ValueError('Office文件过大、已加密或结构异常。')
        if any('vbaproject' in n.lower() or n.startswith('xl/externalLinks/') for n in names):raise ValueError('含宏或外部数据的文件暂不识别。')
        if path.suffix.lower()=='.docx':return paragraphs(z.read('word/document.xml'))
        if path.suffix.lower()=='.pptx':
            if 'ppt/presentation.xml' not in names or 'ppt/_rels/presentation.xml.rels' not in names:raise ValueError('PPTX缺少页面顺序信息，请提供完整文件。')
            presentation=xml(z.read('ppt/presentation.xml'));relations=xml(z.read('ppt/_rels/presentation.xml.rels'))
            mapping={e.get('Id'):e.get('Target','') for e in relations if e.get('Type','').endswith('/slide') and e.get('TargetMode')!='External'}
            slides=[]
            for element in presentation.iter():
                if local(element)!='sldId':continue
                rid=element.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                target=mapping.get(rid,'');target=target.lstrip('/') if target.startswith('/ppt/') else 'ppt/'+target
                if '..' in target or '\\' in target or target not in names or not re.fullmatch(r'ppt/slides/slide\d+\.xml',target):raise ValueError('PPTX页面关系无效。')
                slides.append(target)
            if not slides:raise ValueError('PPTX没有可识别页面。')
            return '\n\n'.join('第'+str(i)+'页\n'+paragraphs(z.read(n)) for i,n in enumerate(slides,1))
        docs={n:xml(z.read(n)) for n in names if n.endswith(('.xml','.rels'))}
        shared=[''.join(t.text or '' for t in e.iter() if local(t)=='t') for e in docs.get('xl/sharedStrings.xml',[]) ]
        rels={e.get('Id'):e.get('Target','') for e in docs.get('xl/_rels/workbook.xml.rels',[]) if e.get('Type','').endswith('/worksheet')}
        rows=[]
        for sheet in docs.get('xl/workbook.xml',ET.Element('x')).iter():
            if local(sheet)!='sheet':continue
            rid=sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id');target=rels.get(rid,'')
            target=target.lstrip('/') if target.startswith('/xl/') else 'xl/'+target
            if '..' in target or '\\' in target or target not in docs or not target.startswith('xl/worksheets/'):raise ValueError('Excel工作表引用无效。')
            rows.append('工作表：'+sheet.get('name','未命名')+'（公式只读取缓存值，不重算）')
            for row in docs[target].iter():
                if local(row)!='row':continue
                cells=[]
                for c in row:
                    if local(c)!='c':continue
                    value=next((e.text or '' for e in c if local(e)=='v'),'')
                    if c.get('t')=='s':value=shared[int(value)] if value else ''
                    if c.get('t')=='inlineStr':value=''.join(t.text or '' for t in c.iter() if local(t)=='t')
                    formula=next((e.text for e in c if local(e)=='f'),None)
                    if formula and not value:value='[公式无缓存值：'+formula+']'
                    cells.append(c.get('r','')+'='+value)
                rows.append(' | '.join(cells))
        return '\n'.join(rows)

def extract(path):
    path=Path(path);ext=path.suffix.lower()
    if ext not in SUPPORTED:raise ValueError('暂不支持此附件格式。')
    if path.stat().st_size>10*1024*1024:raise ValueError('每个附件最多10MB。')
    if ext in ('.docx','.pptx','.xlsx'):return finish(office(path))
    if ext=='.pdf':
        from pypdf import PdfReader
        reader=PdfReader(str(path),strict=False)
        if reader.is_encrypted:raise ValueError('不读取加密PDF，请提供未加密副本。')
        if len(reader.pages)>80:raise ValueError('PDF最多80页，请拆分后添加。')
        parts=[]
        for i,page in enumerate(reader.pages,1):
            text=page.extract_text() or ''
            if text.strip():parts.append('第'+str(i)+'页\n'+text)
            if sum(len(t) for t in parts)>MAX_CHARS:raise ValueError('PDF文字超过18000字符，请拆分。')
        return finish('\n\n'.join(parts))
    if ext in ('.png','.jpg','.jpeg','.bmp','.webp'):
        script=Path(__file__).with_name('image_ocr.ps1')
        command=script.read_text(encoding='utf-8-sig').replace('param([string]$ImagePath)','$ImagePath=$env:AGENT_ATTACHMENT_OCR_PATH',1)
        p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,timeout=25,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),env={**os.environ,'AGENT_ATTACHMENT_OCR_PATH':str(path)})
        if p.returncode:raise ValueError('本机图片OCR不可用或未识别成功，请换成清晰PNG/JPG或直接粘贴文字。')
        return finish(p.stdout.decode('utf-8-sig'))
    raw=path.read_bytes()
    if b'\x00' in raw and not raw.startswith((b'\xff\xfe',b'\xfe\xff')):raise ValueError('附件不是可识别的文本文件。')
    for encoding in (('utf-16',) if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else ('utf-8-sig','gb18030')):
        try:return finish(raw.decode(encoding))
        except UnicodeDecodeError:continue
    raise ValueError('文本编码无法识别，请另存为UTF-8。')

if __name__=='__main__':
    try:print(json.dumps(dict(ok=True,text=extract(Path(sys.argv[1]))),ensure_ascii=False))
    except Exception as e:print(json.dumps(dict(ok=False,error=str(e)[:400] or '附件识别失败'),ensure_ascii=False))
