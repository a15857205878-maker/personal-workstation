"""Rebuildable, bounded library text cache. Originals and tickets stay with ComputerFiles."""
from pathlib import Path
from contextlib import closing
import hashlib, io, json, os, sqlite3, subprocess, sys, time

VERSION=1
TEXT_LIMIT=2*1024*1024
PDF_LIMIT=8*1024*1024

def extract(raw, suffix):
    if suffix!='.pdf':
        try:text=raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:text=raw.decode('utf-16') if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else raw.decode('gb18030')
            except UnicodeError:raise ValueError('文字编码无法识别') from None
        if '\x00' in text:raise ValueError('不是可检索文字')
        if len(text)>300000:raise ValueError('正文超过30万字符')
        return [[f'第{i}行',line] for i,line in enumerate(text.splitlines(),1)]
    from pypdf import PdfReader
    reader=PdfReader(io.BytesIO(raw),strict=False)
    if reader.is_encrypted or len(reader.pages)>80:raise ValueError('加密或超过80页的PDF')
    parts=[];count=0
    for i,page in enumerate(reader.pages,1):
        text=page.extract_text() or '';count+=len(text)
        if count>300000:raise ValueError('PDF正文超过30万字符')
        parts.append([f'第{i}页',text])
    if not any(text.strip() for _,text in parts):raise ValueError('PDF无可提取正文，扫描件请用原文件查看')
    return parts

def pdf_parts(raw):
    bundled=Path(sys.executable)
    executable=str(bundled) if bundled.is_file() else sys.executable.replace('pythonw.exe','python.exe')
    try:
        result=subprocess.run([executable,'-B',str(Path(__file__).resolve()),'--pdf'],input=raw,capture_output=True,timeout=4,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),env={**os.environ,'PYTHONIOENCODING':'utf-8'})
        if result.returncode or len(result.stdout)>2*1024*1024:raise ValueError('PDF损坏、无文本或超过提取限制')
        return json.loads(result.stdout.decode('utf-8'))
    except (subprocess.TimeoutExpired,UnicodeError,json.JSONDecodeError):raise ValueError('PDF提取超时或不可用') from None

def search(service,query):
    if not isinstance(query,str) or not 1<=len(query.strip())<=120 or any(ord(c)<32 for c in query):raise ValueError('请输入1–120字正文关键词')
    query=query.strip();tokens=query.casefold().split();listing=service._search('',library=True,limit=500)
    service.root.mkdir(parents=True,exist_ok=True)
    cache=service.root/'file-content-cache.sqlite3'
    if cache.is_symlink() or getattr(cache,'is_junction',lambda:False)():raise ValueError('检索缓存位置无效')
    deadline=time.monotonic()+8;budget=16*1024*1024;hits=[];warnings=[];limited=listing['limited']
    with closing(sqlite3.connect(cache,timeout=2)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS content (key TEXT PRIMARY KEY, fingerprint TEXT, version INTEGER, parts TEXT, error TEXT)')
        for row in listing['files']:
            if time.monotonic()>deadline or budget<=0 or len(hits)>=50:limited=True;break
            suffix=Path(row['name']).suffix.lower();parts=[];error=''
            if suffix in ('.txt','.md','.pdf'):
                maximum=PDF_LIMIT if suffix=='.pdf' else TEXT_LIMIT
                if row['size']>maximum:error='超过正文大小限制'
                else:
                    try:
                        with service.open_file(row['id']) as stream:
                            raw=stream.read(maximum+1)
                        budget-=len(raw)
                        if len(raw)>maximum:raise ValueError('文件超过正文大小限制')
                        ticket=service._tickets[row['id']]
                        key=hashlib.sha256((ticket['root']+'\0'+ticket['path']).encode()).hexdigest()
                        digest=hashlib.sha256(raw).hexdigest()
                        old=db.execute('SELECT parts,error FROM content WHERE key=? AND fingerprint=? AND version=?',(key,digest,VERSION)).fetchone()
                        if old:parts=json.loads(old[0]);error=old[1]
                        else:
                            try:parts=pdf_parts(raw) if suffix=='.pdf' else extract(raw,suffix)
                            except Exception as exc:error=str(exc)[:180]
                            db.execute('INSERT OR REPLACE INTO content VALUES (?,?,?,?,?)',(key,digest,VERSION,json.dumps(parts,ensure_ascii=False),error))
                    except (OSError,ValueError,KeyError):error='原文件已变化或暂不可读'
            if error:warnings.append(row['name']+'：'+error+'，仍可按文件名查找。')
            match=next(((where,text) for where,text in parts if all(t in text.casefold() for t in tokens)),None)
            if match:
                where,text=match;start=max(0,text.casefold().find(tokens[0])-60)
                hits.append(dict(row,location=where,excerpt=text[start:start+240],match='content',content_sha256=digest))
            elif all(t in row['name'].casefold() for t in tokens):
                hits.append(dict(row,location='文件名',excerpt='未匹配可提取正文',match='filename'))
        # Bound rebuildable cache independently of source count; purged entries re-extract on demand.
        db.execute('DELETE FROM content WHERE rowid NOT IN (SELECT rowid FROM content ORDER BY rowid DESC LIMIT 1000)')
    return dict(listing,files=hits,query=query,limited=limited,warnings=warnings[:20],mode='content')

if __name__=='__main__':
    try:
        raw=sys.stdin.buffer.read(PDF_LIMIT+1)
        if len(raw)>PDF_LIMIT:raise ValueError('PDF过大')
        print(json.dumps(extract(raw,'.pdf'),ensure_ascii=False))
    except Exception:sys.exit(1)
