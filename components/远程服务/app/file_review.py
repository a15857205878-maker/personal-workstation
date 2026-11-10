"""Bounded, passive review of registered task artifacts; never executes a file."""
import csv
import difflib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import threading
import time
import zipfile
import xml.etree.ElementTree as ET

from artifact_preview import safe_path, opened_path

MAX_TEXT=2*1024*1024
MAX_XLSX=8*1024*1024
SNAPSHOT_BYTES=128*1024
MAX_ROWS=200
MAX_COLS=50
TABLE_CHARS=400000
TABLE_SLOTS=threading.BoundedSemaphore(2)
CODE={'.py','.js','.mjs','.cjs','.jsx','.ts','.tsx','.css','.html','.htm','.json','.yaml','.yml','.toml','.xml','.sql','.sh','.ps1','.bat','.cmd','.c','.h','.cpp','.hpp','.cs','.java','.go','.rs','.rb','.php','.swift','.kt','.vue','.svelte','.r','.ini','.cfg','.dockerfile'}
OFFICE={'.pdf','.docx','.pptx','.xls','.ods','.odt','.odp','.xlsx'}
IMAGES={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.gif':'image/gif','.bmp':'image/bmp'}
BLOCKED={'inputs','node_modules','vendor','venv','__pycache__','keys','secrets','credentials'}


def allowed(name):
    if not isinstance(name,str) or not name or len(name)>1000 or '\\' in name or ':' in name or any(ord(c)<32 for c in name):return False
    p=PurePosixPath(name)
    if p.is_absolute() or name!=p.as_posix():return False
    for part in p.parts:
        s=part.lower()
        if s in ('.','..') or s.startswith('.') or s in BLOCKED:return False
        if s.rstrip(' .')!=s:return False
    base=p.name.lower()
    return not (base in {'pairing.json','runtime.json'} or re.search(r'(?:^|[._-])(?:credentials?|secrets?|tokens?|passwords?|auth|api[-_]?keys?)(?:[._-]|$)',base)
                or p.suffix.lower() in {'.pem','.key','.p12','.pfx','.kdbx','.sqlite','.sqlite3','.db'}
                or base.startswith('id_rsa') or base.startswith('id_ed25519'))


def kind(name):
    ext=PurePosixPath(name).suffix.lower()
    if ext in ('.csv','.tsv','.xlsx'):return 'table'
    if ext in IMAGES:return 'image'
    if ext in OFFICE:return 'pdf'
    if ext in ('.md','.markdown'):return 'markdown'
    if ext in ('.log','.out','.err'):return 'log'
    if ext in CODE or PurePosixPath(name).name.lower() in ('dockerfile','makefile'):return 'code'
    if ext in ('.txt','.diff','.patch'):return 'text'
    return 'unsupported'


def clean(text):
    text=re.sub(r'\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|$))','',text)
    text=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]','',text)
    text=re.sub(r'(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]+',r'\1[已隐藏]',text)
    text=re.sub(r'(?im)(\bauthorization\s*[:=]\s*)[^\r\n]+',r'\1[已隐藏]',text)
    text=re.sub(r'''(?im)(["']?(?:api[_-]?key|access[_-]?token|password|secret|token)["']?\s*[:=]\s*)(?:"[^"\n]*"|'[^'\n]*'|[^\s,;]+)''',r'\1[已隐藏]',text)
    text=re.sub(r'\bsk-[A-Za-z0-9_-]{12,}\b','[已隐藏]',text)
    return text


def decode(data):
    if b'\0' in data:raise ValueError('该文件不是可预览的文本，请下载原文件。')
    for encoding in ('utf-8-sig','gb18030'):
        try:return data.decode(encoding)
        except UnicodeError:pass
    raise ValueError('无法识别文本编码，请下载原文件。')


def clipped(text):
    lines=text.splitlines(keepends=True)
    value=''.join(lines[:2000])[:30000]
    return value,len(value)<len(text)


def csv_sheets(data,name):
    text=decode(data)
    try:
        dialect='excel-tab' if name.lower().endswith('.tsv') else csv.Sniffer().sniff(text[:8192],delimiters=',;\t')
    except csv.Error:dialect='excel'
    result=[];truncated=False;budget=TABLE_CHARS
    try:
        for row in csv.reader(io.StringIO(text,newline=''),dialect):
            if len(result)>=MAX_ROWS:truncated=True;break
            if len(row)>MAX_COLS or any(len(cell)>1000 for cell in row[:MAX_COLS]):truncated=True
            values=[]
            for cell in row[:MAX_COLS]:
                value=clean(cell[:1000])
                if len(value)>budget:truncated=True
                value=value[:budget];budget-=len(value);values.append(value)
            result.append(values)
            if budget==0:truncated=True;break
    except csv.Error:raise ValueError('表格内容无法解析，请下载原文件。') from None
    return [{'name':PurePosixPath(name).name,'rows':result,'truncated':truncated}]


def tag(e):return e.tag.rsplit('}',1)[-1]


def xlsx_sheets(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            entries=z.infolist()
            if len(entries)>2000 or sum(e.file_size for e in entries)>20*1024*1024 or any(e.file_size>8*1024*1024 or e.flag_bits&1 for e in entries):
                raise ValueError('表格展开后过大或已加密，请下载原文件。')
            names={e.filename for e in entries}
            if len(names)!=len(entries):raise ValueError('表格包含重复内容，无法预览。')
            docs={}
            for entry in entries:
                name=entry.filename
                if 'vbaproject' in name.lower() or name.startswith('xl/externalLinks/'):
                    raise ValueError('含宏或外部数据的表格不直接预览，请下载原文件。')
                if name.endswith(('.xml','.rels')):
                    raw=z.read(entry)
                    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper() or b'\0' in raw:
                        raise ValueError('表格包含不支持的XML内容。')
                    doc=ET.fromstring(raw);docs[name]=doc
                    if name.endswith('.rels') and any(e.get('TargetMode')=='External' and not e.get('Type','').endswith('/hyperlink') for e in doc):
                        raise ValueError('含外部数据的表格不直接预览。')
            shared=[]
            if 'xl/sharedStrings.xml' in docs:
                for item in docs['xl/sharedStrings.xml']:
                    shared.append(''.join(t.text or '' for t in item.iter() if tag(t)=='t'))
            rels={e.get('Id'):e.get('Target','') for e in docs['xl/_rels/workbook.xml.rels'] if e.get('Type','').endswith('/worksheet')}
            result=[];budget=TABLE_CHARS
            sheets=[e for e in docs['xl/workbook.xml'].iter() if tag(e)=='sheet']
            for sheet in sheets[:10]:
                rid=sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                target=rels.get(rid,'')
                path=target.lstrip('/') if target.startswith('/xl/') else 'xl/'+target
                if '..' in PurePosixPath(path).parts or '\\' in path or ':' in path or not path.startswith('xl/worksheets/') or path not in docs:
                    raise ValueError('表格工作表位置无效。')
                rows=[];truncated=len(sheets)>10
                for row in (e for e in docs[path].iter() if tag(e)=='row'):
                    rownum=int(row.get('r',str(len(rows)+1)))
                    if rownum<1 or rownum<=len(rows):raise ValueError('表格行编号无效。')
                    if rownum>MAX_ROWS:truncated=True;break
                    while len(rows)<rownum-1:rows.append([])
                    values=[]
                    for cell in row:
                        if tag(cell)!='c':continue
                        match=re.fullmatch(r'([A-Z]{1,4})([1-9][0-9]{0,6})',cell.get('r',''))
                        if not match:raise ValueError('表格单元格编号无效。')
                        col=0
                        for char in match[1]:col=col*26+ord(char)-64
                        if col>MAX_COLS:truncated=True;continue
                        if col<=len(values):raise ValueError('表格单元格顺序无效。')
                        while len(values)<col:values.append('')
                        value=next((e.text or '' for e in cell if tag(e)=='v'),None)
                        formula=any(tag(e)=='f' for e in cell)
                        if cell.get('t')=='s':
                            index=int(value or '-1')
                            if not 0<=index<len(shared):raise ValueError('表格文字索引无效。')
                            value=shared[index]
                        elif cell.get('t')=='inlineStr':value=''.join(e.text or '' for e in cell.iter() if tag(e)=='t')
                        elif value is None:value='[公式无缓存值]' if formula else ''
                        if len(value)>1000:truncated=True
                        value=clean(value[:1000])
                        if len(value)>budget:truncated=True
                        value=value[:budget];budget-=len(value);values[col-1]=value
                    rows.append(values)
                    if budget==0:truncated=True;break
                result.append({'name':sheet.get('name','工作表')[:200],'rows':rows,'truncated':truncated})
                if budget==0:break
            if not result:raise ValueError('表格没有可显示的工作表。')
            return result
    except (zipfile.BadZipFile,KeyError,ET.ParseError,RuntimeError,OverflowError,TypeError,UnicodeError,NotImplementedError):
        raise ValueError('表格格式损坏或不受支持，请下载原文件。') from None


def workbench_sheet(proxy, identifier, name,kind="task"):
    """Read only an owned workbench XLSX; never imports it into history tasks."""
    import base64
    if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{32}',identifier):
        raise ValueError('任务编号无效。')
    if not isinstance(name,str) or not name.lower().endswith('.xlsx') or len(name)>220 or name in ('.','..') or re.search(r'[\\/:\x00-\x1f]',name):
        raise ValueError('请选择任务内的XLSX成果。')
    from workbench_proxy import artifact_action
    result=proxy.call(artifact_action(kind),{'id':identifier,'name':name})
    if not result.get('ok'):raise ValueError('无法读取该任务成果，请刷新任务后重试。')
    data=result['data']
    if data.get('name')!=name:raise ValueError('返回成果与所选文件不一致。')
    raw=base64.b64decode(data['content_base64'],validate=True)
    if not 0<len(raw)<=MAX_XLSX:raise ValueError('XLSX超过8MiB在线预览上限，请下载原件。')
    if not TABLE_SLOTS.acquire(blocking=False):raise ValueError('表格预览繁忙，请稍后重试。')
    try:sheets=xlsx_sheets(raw)
    finally:TABLE_SLOTS.release()
    return {'kind':'table','path':name,'name':name,'size':len(raw),'sheets':sheets,
            'truncated':any(sheet.get('truncated') for sheet in sheets),
            'message':'XLSX原文件只读预览，可切换工作表；公式使用文件保存的结果，不执行计算。复杂排版、图表及完整功能请下载原件查看。'}


class FileReview:
    def __init__(self,tasks):self.tasks=tasks

    def _path(self,task_id,name):
        if not allowed(name):raise ValueError('该文件不在可预览范围内。')
        self.tasks.artifact_path(task_id,name)
        workspace=self.tasks.workspace(task_id).absolute()
        safe_path(self.tasks.root,workspace)
        return safe_path(workspace,workspace/name,file=True)

    def _read(self,task_id,name,limit):
        path=self._path(task_id,name)
        with path.open('rb') as stream:
            if os.path.normcase(str(opened_path(stream,path)))!=os.path.normcase(str(path)):
                raise ValueError('文件位置已变化，请刷新后重试。')
            st=os.fstat(stream.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_size>limit:raise ValueError('文件超过预览大小限制，请下载原文件。')
            data=stream.read(limit+1)
            after=os.fstat(stream.fileno())
            if len(data)>limit:raise ValueError('文件超过预览大小限制。')
            if (st.st_size,st.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('文件仍在更新，请稍后重试。')
        return data

    def files(self,task_id):
        task=self.tasks.get(task_id);files=[]
        for item in task.get('artifacts',[])[:200]:
            name=item.get('path')
            try:p=self._path(task_id,name)
            except (OSError,ValueError):continue
            files.append({'path':name,'name':p.name,'size':p.stat().st_size,'kind':kind(name)})
        return {'title':task['title'],'files':sorted(files,key=lambda f:f['path'].lower())}

    def read(self,task_id,name):
        path=self._path(task_id,name);k=kind(name)
        result={'path':name,'name':path.name,'kind':k}
        if k in ('image','pdf','unsupported'):return result
        data=self._read(task_id,name,MAX_XLSX if path.suffix.lower()=='.xlsx' else MAX_TEXT)
        if k=='table':
            if not TABLE_SLOTS.acquire(blocking=False):raise ValueError('表格预览正在忙，请稍后重试。')
            try:result['sheets']=xlsx_sheets(data) if path.suffix.lower()=='.xlsx' else csv_sheets(data,name)
            finally:TABLE_SLOTS.release()
            result['message']='首行作表头；只读缓存值，不计算公式。'
            return result
        text=decode(data);visible=clean(text)
        result['text'],result['truncated']=clipped(visible)
        result['diff']=self._diff(task_id,name,text)
        if result['truncated']:result['message']='仅显示部分内容，下载原文件查看全部。'
        return result

    def _diff(self,task_id,name,text):
        no={'available':False,'text':'','message':'没有任务开始前的记录，无法对比。'}
        if len(text.encode('utf-8'))>SNAPSHOT_BYTES or len(text.splitlines())>2000:
            return dict(no,message='文件较大，暂不生成修改对比。')
        path=self.tasks.data/task_id/'review-baseline.json'
        try:
            safe_path(self.tasks.root,path,file=True)
            if path.stat().st_size>4*1024*1024:return no
            baseline=json.loads(path.read_text(encoding='utf-8'))
            if baseline.get('version')!=1 or baseline.get('task_id')!=task_id:return no
            entries=baseline['files']
            if name in entries:
                previous=entries[name]
                if not isinstance(previous,str):return no
            elif baseline.get('complete') is True:previous=''
            else:return no
            if len(previous.encode('utf-8'))>SNAPSHOT_BYTES or len(previous.splitlines())>2000:return no
            chunks=difflib.unified_diff(clean(previous).splitlines(True),clean(text).splitlines(True),fromfile='修改前/'+name,tofile='当前/'+name,n=3)
            diff=''.join(line if line.endswith('\n') else line+'\n\\ No newline at end of file\n' for line in chunks)
            value,truncated=clipped(diff)
            return {'available':True,'text':value,'message':'对比相对本次任务开始前的记录。'+('仅显示部分改动。' if truncated else ('内容未变化。' if not value else ''))}
        except (OSError,ValueError,KeyError,TypeError,AttributeError):return no

    def image(self,task_id,name):
        data=self._read(task_id,name,20*1024*1024)
        ext=PurePosixPath(name).suffix.lower()
        valid=(ext=='.png' and data.startswith(b'\x89PNG\r\n\x1a\n') or ext in ('.jpg','.jpeg') and data.startswith(b'\xff\xd8\xff')
               or ext=='.webp' and data[:4]==b'RIFF' and data[8:12]==b'WEBP' or ext=='.gif' and data[:6] in (b'GIF87a',b'GIF89a')
               or ext=='.bmp' and data[:2]==b'BM')
        if not valid:raise ValueError('图片内容与格式不匹配，无法预览。')
        return data,IMAGES[ext]


def capture_baseline(tasks,task_id):
    """Only called at execution start, never by the read endpoints. Best effort."""
    destination=tasks.data/task_id/'review-baseline.json'
    try:
        safe_path(tasks.root,destination)
        if destination.exists():return
        workspace=tasks.workspace(task_id).absolute();safe_path(tasks.root,workspace)
        entries={};total=0;count=0;complete=True;seen=0;directories=0
        pending=[workspace];deadline=time.monotonic()+2
        while pending:
            directory=pending.pop();directories+=1
            if directories>200 or time.monotonic()>deadline:complete=False;break
            try:
                safe_path(workspace,directory)
                with os.scandir(directory) as children:
                    for entry in children:
                        seen+=1
                        if seen>2000 or time.monotonic()>deadline:complete=False;pending.clear();break
                        path=Path(entry.path);relative=path.relative_to(workspace).as_posix()
                        if not allowed(relative) or path.is_symlink() or path.is_junction():continue
                        if entry.is_dir(follow_symlinks=False):pending.append(path);continue
                        count+=1
                        if count>200:complete=False;pending.clear();break
                        entries[relative]=None
                        if kind(relative) not in ('code','markdown','log','text'):continue
                        try:
                            safe_path(workspace,path,file=True)
                            with path.open('rb') as stream:
                                if os.path.normcase(str(opened_path(stream,path)))!=os.path.normcase(str(path)):continue
                                data=stream.read(SNAPSHOT_BYTES+1)
                            if len(data)>SNAPSHOT_BYTES or total+len(data)>2*1024*1024:continue
                            value=decode(data)
                            if len(value.splitlines())>2000:continue
                            entries[relative]=clean(value);total+=len(data)
                        except (ValueError,OSError):continue
            except (OSError,ValueError):complete=False
        body=json.dumps({'version':1,'task_id':task_id,'complete':complete,'files':entries},ensure_ascii=False)
        if len(body.encode('utf-8'))>4*1024*1024:return
        temp=destination.with_suffix('.tmp');temp.write_text(body,encoding='utf-8');os.replace(temp,destination)
    except (OSError,ValueError):pass  # A missing diff baseline must never block the task.
