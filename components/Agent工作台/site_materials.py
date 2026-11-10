"""Project metadata for website preparation. Referenced originals remain with their owners."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import base64,hashlib,json,os,threading,uuid
from credential_store import atomic_json

MAX_FILE=100*1024*1024
MAX_METADATA_BYTES=8*1024*1024
MEDIA={'.png','.jpg','.jpeg','.webp','.gif','.mp4','.webm','.txt','.md','.pdf','.csv','.json','.docx','.xlsx','.pptx','.zip'}
PROJECT_FIELDS={'id','title','version','todo','entries','created','updated','exports'}
ENTRY_FIELDS={'id','title','description','notes','version','date','kind','public','source','excerpt','file_name','file_status'}

def now():return datetime.now(ZoneInfo('Asia/Tokyo')).isoformat(timespec='seconds')
def text(value,limit):
    if not isinstance(value,str) or len(value)>limit or '\x00' in value:raise ValueError('文字类型无效或超过长度限制')
    return value
def ordinary(path):
    path=Path(path).absolute()
    for p in (path,*path.parents):
        if p.is_symlink() or getattr(p,'is_junction',lambda:False)():raise ValueError('不读取链接文件或目录')
    if not path.is_file() or path.stat().st_nlink!=1:raise ValueError('素材原件不可用或不是普通文件')
    return path
def fingerprint(path):
    path=ordinary(path);st=path.stat()
    if st.st_size>MAX_FILE:raise ValueError('单个素材最多100MiB')
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        count=0
        for part in iter(lambda:stream.read(1024*1024),b''):
            count+=len(part)
            if count>MAX_FILE:raise ValueError('素材读取时超过100MiB限制')
            digest.update(part)
    end=path.stat()
    if (st.st_size,st.st_mtime_ns,st.st_ino)!=(end.st_size,end.st_mtime_ns,end.st_ino):raise ValueError('素材读取时发生变化，请重新选择')
    return {'size':st.st_size,'mtime':st.st_mtime_ns,'sha256':digest.hexdigest()}

class SiteMaterials:
    def __init__(self,data_dir):
        self.root=Path(data_dir)/'site-materials';self.path=self.root/'projects.json';self.lock=threading.RLock()
    def _load(self):
        if not self.path.exists():return {'version':1,'projects':[]}
        if self.path.is_symlink() or self.path.stat().st_size>MAX_METADATA_BYTES:raise ValueError('素材档案数据异常')
        data=json.loads(self.path.read_text(encoding='utf-8-sig'))
        if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('projects'),list):raise ValueError('素材档案格式无效')
        return data
    @staticmethod
    def _revision(data):return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    def _expect(self,data,revision):
        if revision!=self._revision(data):raise ValueError('档案已变化，请刷新后重新编辑；当前草稿尚未保存')
    def _store(self,data):
        if len(json.dumps(data,ensure_ascii=False,indent=2).encode('utf-8'))>MAX_METADATA_BYTES:raise ValueError('素材档案容量达到8MiB上限，请减少长文本；原档案保持不变')
        atomic_json(self.path,data);return self._view(data)
    def _find(self,data,identifier):
        row=next((p for p in data['projects'] if p['id']==identifier),None)
        if row is None:raise ValueError('项目不存在，请刷新')
        return row
    def _view(self,data):
        view=json.loads(json.dumps(data))
        for project in view['projects']:
            for entry in project['entries']:
                ref=entry.pop('_reference',None)
                entry['file_name']=ref['name'] if ref else ''
                entry['file_status']='none'
                if ref:
                    try:
                        path=ordinary(ref['path']);st=path.stat()
                        entry['file_status']='ready' if (st.st_size,st.st_mtime_ns)==(ref['size'],ref['mtime']) else 'changed'
                    except (OSError,ValueError):entry['file_status']='missing'
        return dict(revision=self._revision(data),projects=view['projects'])
    def listing(self):
        with self.lock:return self._view(self._load())
    def create(self,title,revision):
        with self.lock:
            data=self._load();self._expect(data,revision);title=text(title,120).strip()
            if not title:raise ValueError('请填写项目名称')
            if len(data['projects'])>=100:raise ValueError('最多100个项目')
            data['projects'].append(dict(id=uuid.uuid4().hex,title=title,version='',todo='',entries=[],created=now(),updated=now(),exports=[]))
            return self._store(data)
    def add_entry(self,identifier,revision,title='新条目',description='',source='',excerpt='',path=None,expected_sha256=None):
        with self.lock:
            data=self._load();self._expect(data,revision);project=self._find(data,identifier)
            if len(project['entries'])>=200:raise ValueError('每项目最多200个条目')
            entry=dict(id=uuid.uuid4().hex,title=text(title,200),description=text(description,6000),source=text(source,1000),excerpt=text(excerpt,2000),
                       notes='',version=project['version'],date=now()[:10],kind='update',public=False)
            if path is not None:
                path=ordinary(path)
                if path.suffix.lower() not in MEDIA:raise ValueError('此格式不能加入网站素材，请选择图片、录屏、文档或成果包')
                # Only native pickers / existing owner resolvers call this method; never accept a browser path.
                stamp=fingerprint(path)
                if expected_sha256 is not None and stamp['sha256']!=expected_sha256:raise ValueError('素材原件已变化，请重新查找并选入')
                entry['_reference']=dict(path=str(path),name=path.name,**stamp)
                entry['kind']='step' if path.suffix.lower() in {'.png','.jpg','.jpeg','.webp','.gif','.mp4','.webm'} else 'source'
            project['entries'].append(entry);project['updated']=now();return self._store(data)
    def save(self,project,revision):
        with self.lock:
            if not isinstance(project,dict) or set(project)-PROJECT_FIELDS:raise ValueError('项目字段无效')
            data=self._load();self._expect(data,revision);old=self._find(data,project.get('id'))
            rows=project.get('entries');known={e['id']:e for e in old['entries']}
            if not isinstance(rows,list) or len(rows)>200:raise ValueError('条目列表无效')
            entries=[];seen=set()
            for e in rows:
                if not isinstance(e,dict) or set(e)-ENTRY_FIELDS or e.get('id') not in known or e['id'] in seen:raise ValueError('条目来源无效或重复')
                seen.add(e['id']);item=dict(known[e['id']])
                for field,limit in [('title',200),('description',6000),('notes',6000),('version',100),('date',40)]:item[field]=text(e.get(field,''),limit)
                if e.get('kind') not in ('update','source','step') or type(e.get('public')) is not bool:raise ValueError('条目类型或公开范围无效')
                item.update(kind=e['kind'],public=e['public']);entries.append(item)
            title=text(project.get('title',''),120).strip()
            if not title:raise ValueError('项目名称不能为空')
            old.update(title=title,version=text(project.get('version',''),100),todo=text(project.get('todo',''),6000),entries=entries,updated=now())
            return self._store(data)
    def delete(self,identifier,revision):
        with self.lock:
            data=self._load();self._expect(data,revision);self._find(data,identifier)
            data['projects']=[p for p in data['projects'] if p['id']!=identifier];return self._store(data)
    def _entry(self,data,project_id,entry_id):
        entry=next((e for e in self._find(data,project_id)['entries'] if e['id']==entry_id),None)
        if not entry:raise ValueError('条目不存在')
        return entry
    def preview(self,project_id,entry_id):
        with self.lock:
            entry=self._entry(self._load(),project_id,entry_id);ref=entry.get('_reference')
            if not ref:return dict(kind='text',text=entry['excerpt'] or entry['description'])
            path=ordinary(ref['path'])
            ext=path.suffix.lower();mime={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.gif':'image/gif'}.get(ext)
            limit=10*1024*1024 if mime else 512*1024 if ext in ('.md','.txt','.csv') else 0
            if limit and ref['size']<=limit:
                with path.open('rb') as stream:raw=stream.read(limit+1)
                if len(raw)>limit or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('原件已变化或超过预览限制，请重新选入')
                if mime:return dict(kind='image',url='data:'+mime+';base64,'+base64.b64encode(raw).decode())
                return dict(kind='text',text=raw.decode('utf-8-sig',errors='replace'))
            return dict(kind='file',text='此素材保留原件，使用“打开原件”查看。')
    def open_reference(self,project_id,entry_id,opener):
        with self.lock:
            ref=self._entry(self._load(),project_id,entry_id).get('_reference')
            if not ref:raise ValueError('此条目没有原件')
            path=ordinary(ref['path'])
            if fingerprint(path)['sha256']!=ref['sha256']:raise ValueError('原件已变化，请重新选入')
            opener(str(path));return {'opened':True}
    def export(self,identifier,selected,revision):
        from site_materials_export import export_package
        with self.lock:
            data=self._load();self._expect(data,revision);project=self._find(data,identifier)
            if not isinstance(selected,list) or not selected or len(selected)!=len(set(selected)):raise ValueError('请选择需要导出的公开条目')
            known={e['id']:e for e in project['entries']}
            if any(not isinstance(i,str) or i not in known or not known[i]['public'] for i in selected):raise ValueError('只能导出明确选中的公开条目')
            result=export_package(self.root,project,[e for e in project['entries'] if e['id'] in selected])
            project['exports']=(project['exports']+[dict(id=result['id'],created=now(),count=len(selected))])[-50:]
            self._store(data);return dict(result,snapshot=self._view(data))
    def open_export(self,identifier,export_id,opener):
        with self.lock:
            project=self._find(self._load(),identifier)
            if export_id not in [e['id'] for e in project['exports']]:raise ValueError('导出记录不存在')
            path=self.root/'exports'/export_id
            if not path.is_dir():raise ValueError('导出目录已移动')
            opener(str(path));return {'opened':True}
