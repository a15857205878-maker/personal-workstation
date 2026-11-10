import sys
"""On-demand static PDF previews. Never changes tasks or original artifacts."""
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from urllib.parse import quote
from uuid import uuid4

from owned_process import OwnedProcessGroup

SUPPORTED={'.pdf','.png','.jpg','.jpeg','.webp','.bmp','.gif','.tif','.tiff',
           '.docx','.pptx','.xlsx','.odt','.odp','.ods','.txt','.md','.csv','.json','.py','.js','.log'}
MAX_BYTES=100*1024*1024


def safe_path(root, path, file=False):
    root=Path(root).absolute();path=Path(path).absolute()
    if not path.is_relative_to(root):raise ValueError('预览路径无效。')
    current=root
    for name in ('',*path.relative_to(root).parts):
        if name:current=current/name
        if current.is_symlink() or getattr(current,'is_junction',lambda:False)():
            raise ValueError('预览不读取链接目录或链接文件。')
    if file and not path.is_file():raise FileNotFoundError('预览文件不存在。')
    return path


def opened_path(stream, fallback):
    if os.name!='nt':
        fd=Path('/proc/self/fd')/str(stream.fileno())
        return fd.resolve() if fd.exists() else fallback.resolve()
    import ctypes
    import msvcrt
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    fn=kernel.GetFinalPathNameByHandleW
    fn.argtypes=[wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD];fn.restype=wintypes.DWORD
    buf=ctypes.create_unicode_buffer(32768)
    length=fn(msvcrt.get_osfhandle(stream.fileno()),buf,len(buf),0)
    if not length or length>=len(buf):raise OSError('无法核实预览原文件位置。')
    value=buf.value
    if value.startswith('\\\\?\\UNC\\'):value='\\\\'+value[8:]
    elif value.startswith('\\\\?\\'):value=value[4:]
    return Path(value)


class PreviewService:
    def __init__(self,tasks,converter=None,start_worker=True):
        self.tasks=tasks;self.root=tasks.root/'任务预览'
        safe_path(tasks.root,self.root);self.root.mkdir(exist_ok=True)
        self.converter=converter or self._convert
        self.jobs={};self.lock=threading.RLock();self.queue=queue.Queue()
        self.stop=threading.Event();self.worker=None
        # Interrupted conversions are never silently replayed on service restart.
        for state in self.root.glob('[a-f0-9]'*64+'/state.json'):
            try:
                job=self._load(state.parent.name)
                if job['status'] in ('queued','converting'):
                    job.update(status='failed',message='接收服务曾重启，请返回成果列表重新点击PDF预览。')
                    self._save(job)
            except (OSError,ValueError,KeyError):continue
        if start_worker:
            self.worker=threading.Thread(target=self._work,daemon=True);self.worker.start()

    def _directory(self,key):
        if not isinstance(key,str) or not re.fullmatch('[a-f0-9]{64}',key):raise ValueError('预览编号无效。')
        return safe_path(self.root,self.root/key)

    def _save(self,job):
        directory=self._directory(job['id']);directory.mkdir(exist_ok=True)
        safe_path(self.root,directory/'state.json')
        temp=directory/('state-'+uuid4().hex+'.tmp')
        temp.write_text(json.dumps(job,ensure_ascii=False),encoding='utf-8')
        os.replace(temp,directory/'state.json');self.jobs[job['id']]=job

    def _load(self,key):
        if key in self.jobs:return self.jobs[key]
        file=safe_path(self.root,self._directory(key)/'state.json',file=True)
        try:job=json.loads(file.read_text(encoding='utf-8'))
        except (ValueError,UnicodeError) as e:raise ValueError('预览记录损坏，请重新预览原文件。') from e
        if (job.get('id')!=key or job.get('status') not in ('queued','converting','ready','failed')
                or not re.fullmatch('attempt-[a-f0-9]{32}',job.get('attempt',''))
                or not isinstance(job.get('source'),str) or Path(job['source']).name!=job['source']
                or not job['source'].startswith('source.')
                or type(job.get('pages')) is not int or not 0<=job['pages']<=100
                or not isinstance(job.get('title'),str) or not isinstance(job.get('path'),str)
                or job.get('owner','native') not in ('native','workbench')
                or job.get('workbench_kind','task') not in ('task','collaboration')
                or not isinstance(job.get('task_id'),str) or not re.fullmatch('[a-f0-9]{32}',job['task_id'])):
            raise ValueError('预览记录无效。')
        self.jobs[key]=job;return job

    def _public(self,job):
        key=job['id']
        return {'id':key,'status':job['status'],'pages':job.get('pages',0),'title':job['title'],
                'message':job.get('message',''),'viewer_url':'/preview-viewer?preview_id='+key,
                'pdf_url':'/preview/'+key+'/document.pdf',
                'original_url':('/api/workbench-artifact?id='+quote(job['task_id'],safe='')+'&name='+quote(job['path'],safe='')+('&kind=collaboration' if job.get('workbench_kind')=='collaboration' else '')) if job.get('owner')=='workbench' else '/artifact/'+quote(job['task_id'],safe='')+'/'+quote(job['path'],safe='/')}

    def create(self,task_id,name):
        if not isinstance(name,str) or '\\' in name:raise ValueError('成果路径无效。')
        self.tasks.artifact_path(task_id,name) # Must be in the registered artifact list.
        workspace=self.tasks.workspace(task_id).absolute()
        source=safe_path(workspace,workspace/name,file=True)
        if source.suffix.lower() not in SUPPORTED:raise ValueError('该格式暂不支持PDF预览，请下载原文件。')
        before=source.stat()
        if not 0<before.st_size<=MAX_BYTES:raise ValueError('空文件或超过100MB的文件不能预览。')
        with self.lock,tempfile.TemporaryDirectory(prefix='.snapshot-',dir=self.root) as tmp:
            if self.stop.is_set():raise ValueError('接收器正在关闭，请稍后重试。')
            snapshot=Path(tmp)/('source'+source.suffix.lower());digest=hashlib.sha256()
            with source.open('rb') as src,snapshot.open('wb') as dst:
                actual=opened_path(src,source)
                if os.path.normcase(str(actual))!=os.path.normcase(str(source)):
                    raise ValueError('成果位置已变化，请刷新后重试。')
                total=0
                while chunk:=src.read(1024*1024):
                    total+=len(chunk)
                    if total>MAX_BYTES:raise ValueError('成果正在更新或超过100MB，请稍后重试。')
                    digest.update(chunk);dst.write(chunk)
                after=source.stat()
            if (before.st_dev,before.st_ino,before.st_mtime_ns,before.st_size)!=(after.st_dev,after.st_ino,after.st_mtime_ns,after.st_size):
                raise ValueError('成果正在更新，请稍后重新预览。')
            return self._enqueue(task_id,name,snapshot,digest.hexdigest())

    def create_bytes(self,task_id,name,raw,kind='task'):
        # Caller obtains bytes through the original owned-artifact gateway.
        if kind not in ('task','collaboration'):raise ValueError('成果来源无效。')
        if not isinstance(task_id,str) or not re.fullmatch('[a-f0-9]{32}',task_id):raise ValueError('任务编号无效。')
        if not isinstance(name,str) or not name or Path(name).name!=name or '/' in name or '\\' in name or len(name)>240:raise ValueError('成果名称无效。')
        if Path(name).suffix.lower() not in SUPPORTED:raise ValueError('此格式请下载原文件，暂不支持预览。')
        if not isinstance(raw,bytes) or not 0<len(raw)<=10*1024*1024:raise ValueError('文件为空或超过手机10MiB上限，请在电脑查看。')
        with self.lock,tempfile.TemporaryDirectory(prefix='.snapshot-',dir=self.root) as tmp:
            if self.stop.is_set():raise ValueError('接收器正在关闭。')
            snapshot=Path(tmp)/('source'+Path(name).suffix.lower());snapshot.write_bytes(raw)
            return self._enqueue(task_id,name,snapshot,hashlib.sha256(raw).hexdigest(),'workbench',kind)

    def _enqueue(self,task_id,name,snapshot,content_hash,owner='native',kind='task'):
        key=hashlib.sha256((('collaboration-pdf-v1' if owner=='workbench' and kind=='collaboration' else 'workbench-pdf-v1' if owner=='workbench' else 'static-pdf-v1')+'\0'+task_id+'\0'+name+'\0'+content_hash).encode()).hexdigest()
        directory=self._directory(key)
        try:existing=self._load(key)
        except (FileNotFoundError,ValueError):existing=None
        if existing and existing['status']=='ready':
            try:valid=self._fingerprints(existing,existing['pages'])==existing.get('signatures')
            except (OSError,ValueError):valid=False
            if not valid:
                existing.update(status='failed',message='预览缓存不完整，正在重新生成。')
                self._save(existing)
        if existing and existing['status'] in ('queued','converting','ready'):
            return self._public(existing)
        if sum(j['status'] in ('queued','converting') for j in self.jobs.values())>=8:
            raise ValueError('预览队列已满，请稍后再试。')
        directory.mkdir(exist_ok=True)
        attempt='attempt-'+uuid4().hex
        out=safe_path(self.root,directory/attempt);out.mkdir()
        shutil.copyfile(snapshot,out/snapshot.name)
        job={'id':key,'task_id':task_id,'path':name,'title':Path(name).name,'attempt':attempt,
             'source':snapshot.name,'owner':owner,'workbench_kind':kind,'status':'queued','message':'正在等待生成PDF预览。','pages':0}
        self._save(job);self.queue.put(key)
        return self._public(job)

    def get(self,key):
        with self.lock:return self._public(self._load(key))

    def asset(self,key,name):
        with self.lock:
            job=self._load(key)
            if job['status']!='ready':raise FileNotFoundError('PDF预览尚未生成。')
            if name!='document.pdf':
                match=re.fullmatch('page-([1-9][0-9]{0,2})\\.png',name)
                if not match or not 1<=int(match[1])<=job.get('pages',0):raise FileNotFoundError('预览页面不存在。')
            return safe_path(self.root,self._directory(key)/job['attempt']/name,file=True)

    def _fingerprints(self,job,pages):
        if type(pages) is not int or not 1<=pages<=100:raise ValueError('预览页数无效。')
        out=self._directory(job['id'])/job['attempt'];result={};total=0
        for name in ['document.pdf',*(f'page-{n}.png' for n in range(1,pages+1))]:
            path=safe_path(self.root,out/name,file=True);size=path.stat().st_size
            if not 0<size<=MAX_BYTES:raise ValueError('预览文件大小无效。')
            with path.open('rb') as stream:
                magic=b'%PDF-' if name.endswith('.pdf') else bytes.fromhex('89504e470d0a1a0a')
                if stream.read(len(magic))!=magic:raise ValueError('预览文件内容无效。')
                stream.seek(0);digest=hashlib.file_digest(stream,'sha256').hexdigest()
            total+=size
            if total>300*1024*1024:raise ValueError('预览文件总大小超限。')
            result[name]={'size':size,'sha256':digest}
        return result

    def _work(self):
        while not self.stop.is_set():
            try:key=self.queue.get(timeout=.2)
            except queue.Empty:continue
            try:
                with self.lock:
                    job=self._load(key);job.update(status='converting',message='正在生成静态PDF预览。');self._save(job)
                    out=self._directory(key)/job['attempt']
                try:
                    result=self.converter(safe_path(self.root,out/job['source'],file=True),out,self.stop)
                    pages=result.get('pages')
                    if type(pages) is not int or not 1<=pages<=100:raise ValueError('预览页数无效或超过100页。')
                    signatures=self._fingerprints(job,pages)
                    with self.lock:job.update(status='ready',message='静态PDF预览已就绪。',pages=pages,signatures=signatures);self._save(job)
                except Exception as error:
                    message=str(error) if isinstance(error,PreviewError) else 'PDF预览生成失败，请下载原文件；可返回成果列表重新预览。'
                    with self.lock:job.update(status='failed',message=message);self._save(job)
            finally:self.queue.task_done()

    def _convert(self,source,out,stop):
        runtime=Path(sys.executable)
        if not runtime.is_file():raise PreviewError('PDF转换运行环境不可用，请下载原文件。')
        process=subprocess.Popen([str(runtime),str(Path(__file__).with_name('preview_worker.py')),str(source),str(out)],
                                 stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),start_new_session=os.name!='nt')
        group=None
        try:
            group=OwnedProcessGroup(process);deadline=time.monotonic()+180
            while True:
                if stop.is_set() or time.monotonic()>deadline:
                    raise PreviewError('转换已停止或超过3分钟，请下载原文件。')
                try:stdout,_=process.communicate(timeout=.25);break
                except subprocess.TimeoutExpired:continue
            try:result=json.loads(stdout)
            except (ValueError,UnicodeError):raise PreviewError('转换未完成，请下载原文件后查看。')
            if process.returncode:raise PreviewError(result.get('error','转换失败，请下载原文件。'))
            return result
        finally:
            if group:group.close()
            elif process.poll() is None:process.kill()
            if process.poll() is None:process.wait(timeout=5)
            if process.stdout:process.stdout.close()

    def close(self):
        self.stop.set()
        if self.worker:self.worker.join(timeout=8)


class PreviewError(Exception):pass
