"""Read-only filename search and bounded downloads from PC-selected folders."""
from pathlib import Path
import hashlib,json,os,re,secrets,threading,time,stat

PRIVATE_DIRS={'.ssh','.aws','.azure','.codex','.dsh','.git','node_modules','venv','.venv','__pycache__','appdata','$recycle.bin','system volume information'}
PRIVATE_FILES={'pairing.json','runtime.json','connections.json','credentials.json','secrets.json','id_rsa','id_ed25519'}

def private(name):
    value=name.casefold()
    return value in PRIVATE_FILES or value.startswith('.env') or value.endswith(('.pem','.key','.pfx','.p12'))

def safe(root,path):
    root=Path(root).absolute();path=Path(path).absolute()
    if not path.is_relative_to(root):raise ValueError('文件不在已选择目录内。')
    current=Path(path.anchor)
    for part in path.parts[1:]:
        current=current/part
        if current.is_symlink() or getattr(current,'is_junction',lambda:False)():raise ValueError('不读取链接文件或目录。')
    return path

class ComputerFiles:
    def __init__(self,root):
        self.root=Path(root);self.config=self.root/'computer-file-roots.json';self.lock=threading.RLock();self._tickets={};self.ttl=600;self._search_slots=threading.BoundedSemaphore(2)
    def _load(self):
        if not self.config.exists():return {'version':1,'roots':[]}
        if self.config.is_symlink() or self.config.stat().st_size>20000:raise ValueError('文件查找配置无效。')
        data=json.loads(self.config.read_text(encoding='utf-8-sig'))
        if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('roots'),list) or len(data['roots'])>8:raise ValueError('文件查找配置无效。')
        for row in data['roots']:
            if not isinstance(row,dict) or not re.fullmatch('[a-f0-9]{32}',row.get('id','')) or not isinstance(row.get('path'),str) or not Path(row['path']).is_absolute():raise ValueError('文件查找配置无效。')
        return data
    @staticmethod
    def _revision(data):return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    def local_roots(self):
        data=self._load();return {'roots':data['roots'],'revision':self._revision(data),'library_id':data.get('library_id')}
    def _save(self,data):
        self.root.mkdir(parents=True,exist_ok=True);temporary=self.config.with_suffix('.tmp');temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(self.config)
        return self.local_roots()
    def add_root(self,path):
        path=Path(path).absolute();safe(path,path)
        if not path.is_dir() or path==Path(path.anchor) or path==Path.home() or any(p.casefold() in PRIVATE_DIRS for p in path.parts):raise ValueError('请选择具体的普通文件夹，不选择整个磁盘、用户根目录或认证目录。')
        with self.lock:
            data=self._load()
            if any(os.path.normcase(row['path'])==os.path.normcase(str(path)) for row in data['roots']):return self.local_roots()
            if len(data['roots'])>=8:raise ValueError('最多添加8个查找目录。')
            data['roots'].append({'id':secrets.token_hex(16),'label':path.name,'path':str(path)})
            return self._save(data)
    def set_library(self,path):
        with self.lock:
            self.add_root(path);data=self._load();absolute=str(Path(path).absolute());row=next(row for row in data['roots'] if os.path.normcase(row['path'])==os.path.normcase(absolute));data['library_id']=row['id'];return self._save(data)
    def library_files(self,query=''):
        if not self._search_slots.acquire(blocking=False):raise ValueError('文件库繁忙，请稍后重试。')
        try:return self._search(query,library=True)
        finally:self._search_slots.release()
    def library_content(self,query):
        if not self._search_slots.acquire(blocking=False):raise ValueError('文件库繁忙，请稍后重试。')
        try:
            # Keep ticket/config mutation and content resolution within one snapshot.
            with self.lock:
                import importlib.util
                spec=importlib.util.spec_from_file_location('personal_pc_content',Path(__file__).with_name('pc_content.py'))
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                return module.search(self,query)
        finally:self._search_slots.release()
    def remove_root(self,identifier):
        with self.lock:
            data=self._load();data['roots']=[row for row in data['roots'] if row['id']!=identifier];return self._save(data)
    def search(self,query):
        if not self._search_slots.acquire(blocking=False):raise ValueError('文件查找繁忙，请稍后重试。')
        try:return self._search(query)
        finally:self._search_slots.release()
    def _search(self,query,library=False,limit=50):
        if not isinstance(query,str) or not (0 if library else 1)<=len(query.strip())<=120 or re.search(r'[\\/:\x00-\x1f]',query) or '..' in query:raise ValueError('请输入文件名关键词，不输入电脑路径。')
        query=query.strip().casefold();tokens=query.split();data=self._load();revision=self._revision(data);now=time.time();deadline=time.monotonic()+3;items=[];seen=0;limited=False;unavailable=0
        roots=[row for row in data['roots'] if row['id']==data.get('library_id')] if library else data['roots']
        with self.lock:
            self._tickets={k:v for k,v in self._tickets.items() if now-v['time']<self.ttl}
        for row in roots:
            root=Path(row['path']);stack=[(root,0)]
            try:safe(root,root)
            except (ValueError,OSError):unavailable+=1;continue
            if not root.is_dir():unavailable+=1;continue
            while stack:
                directory,depth=stack.pop()
                if seen>=20000 or time.monotonic()>deadline or len(items)>=limit:limited=True;break
                try:
                    safe(root,directory)
                    with os.scandir(directory) as entries:
                        for entry in entries:
                            seen+=1
                            if seen>=20000 or time.monotonic()>deadline or len(items)>=limit:limited=True;break
                            if entry.is_symlink() or getattr(Path(entry.path),'is_junction',lambda:False)():continue
                            if entry.is_dir(follow_symlinks=False):
                                if entry.name.casefold() in PRIVATE_DIRS or entry.name.startswith('.'):continue
                                if depth<12:stack.append((Path(entry.path),depth+1))
                                else:limited=True
                                continue
                            if private(entry.name) or not entry.is_file(follow_symlinks=False) or not all(t in entry.name.casefold() for t in tokens):continue
                            path=Path(entry.path);st=path.stat(follow_symlinks=False)
                            if st.st_nlink>1:continue
                            ticket=secrets.token_hex(16)
                            with self.lock:
                                if len(self._tickets)>=512:self._tickets.pop(next(iter(self._tickets)))
                                self._tickets[ticket]={'root':row['id'],'path':str(path),'revision':revision,'time':now,'size':st.st_size,'mtime':st.st_mtime_ns,'ino':st.st_ino,'dev':st.st_dev}
                            items.append({'id':ticket,'name':entry.name,'folder':row['label'],'relative':path.relative_to(root).as_posix(),'size':st.st_size,'modified':st.st_mtime,'downloadable':st.st_size<=100*1024*1024})
                except (OSError,ValueError):unavailable+=1
            if limited and (seen>=20000 or time.monotonic()>deadline or len(items)>=limit):break
        return {'roots':[{'id':row['id'],'label':row['label']} for row in roots],'files':items,'limited':limited,'unavailable':unavailable,'query':query}
    def open_file(self,identifier):
        with self.lock:ticket=dict(self._tickets.get(identifier,{}) if isinstance(identifier,str) else {})
        data=self._load()
        if not ticket or time.time()-ticket['time']>=self.ttl or ticket['revision']!=self._revision(data):raise ValueError('结果已过期或范围已变化，请重新查找。')
        row=next((row for row in data['roots'] if row['id']==ticket['root']),None)
        if not row:raise ValueError('目录已取消，请重新查找。')
        path=safe(Path(row['path']),Path(ticket['path']))
        if private(path.name):raise ValueError('该文件不提供下载。')
        stream=path.open('rb')
        try:
            import importlib.util
            spec=importlib.util.spec_from_file_location('personal_pc_file_handle',Path(__file__).with_name('pc_file_handle.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            actual=module.opened_path(stream,path);st=os.fstat(stream.fileno())
            if os.path.normcase(str(actual))!=os.path.normcase(str(path)) or not actual.is_relative_to(Path(row['path'])):raise ValueError('文件位置已改变，请重新查找。')
            if (st.st_size,st.st_mtime_ns,st.st_ino,st.st_dev)!=(ticket['size'],ticket['mtime'],ticket['ino'],ticket['dev']):raise ValueError('文件已变化，请重新查找。')
            if st.st_nlink>1:raise ValueError('不读取硬链接文件。')
            if not stat.S_ISREG(st.st_mode):raise ValueError('不是普通文件。')
            if st.st_size>100*1024*1024:raise ValueError('文件超过100MiB，请在电脑取用。')
            return stream
        except Exception:
            stream.close();raise
