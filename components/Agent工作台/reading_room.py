"""Local reading/audio copies, bounded IDs and atomic metadata. No remote actions."""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import threading
import uuid

BOOKS={'.txt','.md','.pdf'}
AUDIO={'.mp3','.wav','.ogg','.m4a'}
MAX_INDEX_BYTES=32*1024*1024

def valid_item(x):
    if not isinstance(x,dict) or not isinstance(x.get('id'),str) or not re.fullmatch('[a-f0-9]{32}',x['id']):return False
    if x.get('format') not in BOOKS|AUDIO or x.get('kind')!=('book' if x['format'] in BOOKS else 'audio'):return False
    if not isinstance(x.get('title'),str) or len(x['title'])>160 or not isinstance(x.get('notes'),str) or len(x['notes'])>8000:return False
    if x.get('state') not in ('unread','reading','finished') or type(x.get('archived')) is not bool:return False
    def position(n):return type(n) in (int,float) and math.isfinite(n) and 0<=n<=1
    def page(n):return type(n) is int and 1<=n<=100000
    if not position(x.get('position')) or not page(x.get('page')):return False
    marks=x.get('bookmarks')
    return isinstance(marks,list) and len(marks)<=50 and all(isinstance(m,dict) and set(m)=={'position','page'} and position(m['position']) and page(m['page']) for m in marks)

class ReadingRoom:
    def __init__(self,root):
        self.root=Path(root)/'reading-room';self.index=self.root/'index.json';self.lock=threading.RLock()
    def _load(self):
        if not self.index.exists():return {'version':1,'items':[]}
        if self.index.stat().st_size>MAX_INDEX_BYTES:raise ValueError('书库记录过大，原记录已保留。')
        try:
            value=json.loads(self.index.read_text(encoding='utf-8'))
            if value.get('version')!=1 or not isinstance(value.get('items'),list):raise ValueError()
            if len(value['items'])>500 or any(not valid_item(x) for x in value['items']) or len({x['id'] for x in value['items']})!=len(value['items']):raise ValueError()
            return value
        except (ValueError,TypeError,AttributeError):raise ValueError('书库记录暂不可读，原记录已保留，请检查备份。') from None
    def _save(self,value):
        self.root.mkdir(parents=True,exist_ok=True)
        raw=json.dumps(value,ensure_ascii=False,indent=2)
        if len(raw.encode('utf-8'))>MAX_INDEX_BYTES:raise ValueError('书库笔记总量超过上限，请先整理，原记录未改。')
        temp=self.root/(uuid.uuid4().hex+'.tmp')
        try:
            with temp.open('w',encoding='utf-8') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            if self.index.exists():shutil.copy2(self.index,self.root/'index.previous.json')
            os.replace(temp,self.index)
        finally:temp.unlink(missing_ok=True)
    @staticmethod
    def _public(item):return {k:v for k,v in item.items() if k!='digest'}
    def listing(self):
        with self.lock:
            items=self._load()['items'];return {'items':[self._public(x) for x in items if not x.get('archived')],'archived':[self._public(x) for x in items if x.get('archived')]}
    def _item(self,value,identifier,include_archived=False):
        if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('读物编号无效。')
        item=next((x for x in value['items'] if x['id']==identifier and (include_archived or not x.get('archived'))),None)
        if item is None:raise ValueError('这份内容不在书库中。')
        return item
    def _path(self,item):
        path=self.root/(item['id']+item['format'])
        if path.is_symlink() or not path.is_file() or path.resolve().parent!=self.root.resolve():raise ValueError('书库副本暂不可读，原文件未改动。')
        if path.stat().st_size>24*1024*1024:raise ValueError('内容超过读取上限。')
        return path
    @staticmethod
    def _text(raw):
        for encoding in (['utf-16','utf-8-sig','gb18030'] if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else ['utf-8-sig','gb18030']):
            try:
                text=raw.decode(encoding)
                if '\x00' in text:continue
                return text
            except UnicodeError:pass
        raise ValueError('文字编码暂不支持，请另存为UTF-8后导入。')
    def import_paths(self,paths,kind='book'):
        if kind not in ('book','audio') or not isinstance(paths,(list,tuple)) or len(paths)>5:raise ValueError('一次最多导入5个本地文件。')
        errors=[]
        with self.lock:
            value=self._load()
            if len(value['items'])+len(paths)>500:raise ValueError('书库已达500项，请先整理归档。')
            for original in paths:
                path=Path(original);ext=path.suffix.lower()
                try:
                    if path.is_symlink() or not path.is_file() or ext not in (BOOKS if kind=='book' else AUDIO):raise ValueError('文件格式不支持。')
                    limit=4*1024*1024 if ext in ('.txt','.md') else 24*1024*1024
                    if not 0<path.stat().st_size<=limit:raise ValueError('文字最多4MiB，PDF和音频最多24MiB。')
                    raw=path.read_bytes()
                    if not 0<len(raw)<=limit:raise ValueError('文件大小发生变化。')
                    if ext in ('.txt','.md'):self._text(raw)
                    if ext=='.pdf' and not raw.startswith(b'%PDF-'):raise ValueError('不是有效的PDF文件。')
                    digest=hashlib.sha256(raw).hexdigest()
                    if any(x.get('digest')==digest and x.get('kind')==kind and not x.get('archived') for x in value['items']):continue
                    identifier=uuid.uuid4().hex;self.root.mkdir(parents=True,exist_ok=True)
                    target=self.root/(identifier+ext);target.write_bytes(raw)
                    item=dict(id=identifier,title=path.stem[:160],format=ext,kind=kind,state='unread',position=0,page=1,bookmarks=[],notes='',size=len(raw),digest=digest,archived=False)
                    value['items'].append(item)
                    try:self._save(value)
                    except Exception:value['items'].pop();target.unlink(missing_ok=True);raise
                except (OSError,ValueError) as error:errors.append(path.name[:160]+'：'+str(error))
            return dict(self.listing(),errors=errors)
    def read(self,identifier):
        with self.lock:
            item=self._item(self._load(),identifier);raw=self._path(item).read_bytes()
            return dict(item=self._public(item),**({'text':self._text(raw)} if item['format'] in ('.txt','.md') else {'base64':base64.b64encode(raw).decode('ascii')}))
    def update(self,payload):
        if not isinstance(payload,dict) or set(payload)-{'id','state','position','page','bookmark','remove_bookmark','notes','archive'}:raise ValueError('书签参数无效。')
        with self.lock:
            value=self._load();item=self._item(value,payload.get('id'),include_archived=payload.get('archive') is False)
            for key in ('position','page'):
                if key in payload:
                    n=payload[key]
                    if type(n) not in (int,float) or not math.isfinite(n) or not (0<=n<=1 if key=='position' else type(n) is int and 1<=n<=100000):raise ValueError('阅读位置无效。')
                    item[key]=n
            if 'state' in payload:
                if payload['state'] not in ('unread','reading','finished'):raise ValueError('阅读状态无效。')
                item['state']=payload['state']
            if 'notes' in payload:
                if not isinstance(payload['notes'],str) or len(payload['notes'])>8000:raise ValueError('读书笔记最多8000字。')
                item['notes']=payload['notes']
            if 'bookmark' in payload:
                if payload['bookmark'] is not True:raise ValueError('书签参数无效。')
                mark={'position':item['position'],'page':item['page']}
                if mark not in item['bookmarks']:item['bookmarks']=(item['bookmarks']+[mark])[-50:]
            if 'remove_bookmark' in payload:
                mark=payload['remove_bookmark']
                if not isinstance(mark,dict) or set(mark)!={'position','page'} or type(mark['position']) not in (int,float) or not math.isfinite(mark['position']) or not 0<=mark['position']<=1 or type(mark['page']) is not int or not 1<=mark['page']<=100000:raise ValueError('书签标记无效。')
                if mark not in item['bookmarks']:raise ValueError('书签已变化，请刷新后再整理。')
                item['bookmarks']=[m for m in item['bookmarks'] if m!=mark]
            if 'archive' in payload:
                if type(payload['archive']) is not bool:raise ValueError('归档参数无效。')
                item['archived']=payload['archive']
            self._save(value);return self._public(item)
    def open_copy(self,identifier,opener=os.startfile):
        with self.lock:path=self._path(self._item(self._load(),identifier));opener(str(path))
        return {'opened':True}

    @staticmethod
    def _valid_preferences(value):
        return (isinstance(value,dict) and set(value)=={'font','paper','volume','last_book_id'}
                and type(value['font']) is int and 14<=value['font']<=28 and value['paper'] in ('warm','light','dark')
                and type(value['volume']) in (int,float) and math.isfinite(value['volume']) and 0<=value['volume']<=1
                and isinstance(value['last_book_id'],str) and (not value['last_book_id'] or re.fullmatch('[a-f0-9]{32}',value['last_book_id'])))
    def preferences(self):
        with self.lock:
            p=self.root/'preferences.json'
            if not p.exists():return dict(font=18,paper='warm',volume=.18,last_book_id='')
            try:
                if p.is_symlink() or p.stat().st_size>4096:raise ValueError()
                value=json.loads(p.read_text(encoding='utf-8'))
                if not self._valid_preferences(value):raise ValueError()
                return value
            except (ValueError,OSError,TypeError,KeyError):raise ValueError('阅读偏好暂不可读，原设置已保留。') from None
    def preferences_save(self,payload):
        with self.lock:
            if not isinstance(payload,dict) or not payload or set(payload)-{'font','paper','volume','last_book_id'}:raise ValueError('阅读偏好参数无效。')
            value={**self.preferences(),**payload}
            if not self._valid_preferences(value):raise ValueError('阅读偏好超出范围。')
            if payload.get('last_book_id'):
                if self._item(self._load(),payload['last_book_id'])['kind']!='book':raise ValueError('继续阅读只接受书库中的读物。')
            from credential_store import atomic_json
            atomic_json(self.root/'preferences.json',value);return value
    def overview(self):
        with self.lock:
            items=self.listing()['items'];prefs=self.preferences();resume=next((x for x in items if x['id']==prefs['last_book_id'] and x['kind']=='book'),None);warnings=[]
            if resume:
                try:self._path(resume)
                except (OSError,ValueError):resume=None;warnings.append('上次读物的副本暂不可用，请到书房检查或重新选择。')
            return dict(counts=dict(books=sum(x['kind']=='book' for x in items),reading=sum(x['kind']=='book' and x['state']=='reading' for x in items),audio=sum(x['kind']=='audio' for x in items)),resume={k:resume[k] for k in ('id','title','format','position','page','state')} if resume else None,warnings=warnings)

    def export_notes(self,identifier):
        with self.lock:
            item=self._item(self._load(),identifier,include_archived=True)
            if item['kind']!='book':raise ValueError('只支持导出读物的笔记。')
            position='第 '+str(item['page'])+' 页' if item['format']=='.pdf' else str(round(item['position']*100))+'%'
            lines=['# '+item['title']+' · 阅读笔记','','阅读位置：'+position,'','## 笔记','',item['notes'] or '（暂无已保存笔记）','','## 书签','']
            for mark in item['bookmarks']:lines.append('- '+('第 '+str(mark['page'])+' 页' if item['format']=='.pdf' else str(round(mark['position']*100))+'%'))
            if not item['bookmarks']:lines.append('（暂无书签）')
            name=re.sub(r'[\\/:*?"<>|\r\n]','_',item['title']).strip(' .')[:60] or '读物'
            text='\n'.join(lines)+'\n'
            if len(text.encode('utf-8'))>65536:raise ValueError('笔记导出超过64KiB上限。')
            return dict(filename=name+'-阅读笔记.md',text=text)
