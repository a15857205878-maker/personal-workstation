"""Read-only front-end product tickets and explicit app-owned WebView screenshots."""
from pathlib import Path,PurePosixPath
import secrets,threading,time,mimetypes,re,subprocess,sys,os,tempfile,struct
from urllib.parse import quote
from artifact_preview import safe_path,opened_path

CSP="sandbox allow-scripts; default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
EXTENSIONS={'.html','.css','.js','.mjs','.json','.png','.jpg','.jpeg','.gif','.svg','.webp','.ico','.woff','.woff2','.ttf','.map'}
def frontend_entry(workspace):
    workspace=Path(workspace);root=None
    for relative in ('frontend/dist','frontend/build','frontend'):
     candidate=safe_path(workspace,workspace/relative)
     entry=safe_path(workspace,candidate/'index.html')
     if entry.is_file():root=candidate;break
    if root is None:raise ValueError('没有可直接打开的index.html，请先构建网页成品。')
    entry=safe_path(root,root/'index.html',file=True)
    if entry.stat().st_size>2*1024*1024:raise ValueError('网页入口超过2MiB。')
    text=entry.read_text(encoding='utf-8',errors='replace')
    if re.search(r'(?:src|href)\s*=\s*["\'][^"\']*(?:/@vite/client|\.(?:jsx|tsx|ts)(?:[?"\']))',text,re.I) or '%PUBLIC_URL%' in text:raise ValueError('这是未构建的前端源码，请先构建再打开。')
    return root

class WebProducts:
 def __init__(self,tasks):self.tasks=tasks;self.tickets={};self.lock=threading.RLock();self.capture_lock=threading.Lock()
 def entry_root(self,identifier):
  task=self.tasks.get(identifier)
  if task.get('agent')!='codex-deepseek-code' or task.get('project_kind','web')!='web':raise ValueError('仅网页设计项目支持成品预览。')
  if task.get('status') in ('queued','running'):raise ValueError('项目尚在执行，请完成或停止后再预览。')
  return frontend_entry(self.tasks.workspace(identifier))
 def prepare(self,identifier):
  root=self.entry_root(identifier)
  now=time.monotonic()
  with self.lock:
   self.tickets={k:v for k,v in self.tickets.items() if v['expires']>now}
   if len(self.tickets)>=64:self.tickets.pop(next(iter(self.tickets)))
   token=secrets.token_hex(24);self.tickets[token]={'id':identifier,'root':root,'expires':now+1800}
  return {'url':'/web-product/'+token+'/index.html','expires_seconds':1800,'notice':'只预览前端成品，不启动项目后端；依赖接口的功能可能暂不可用。'}
 def asset(self,token,name):
  with self.lock:ticket=self.tickets.get(token)
  if not ticket or ticket['expires']<=time.monotonic():raise ValueError('预览链接已失效，请重新打开项目预览。')
  parts=PurePosixPath(name).parts
  if not name or name.startswith('/') or '\\' in name or ':' in name or any(p.lower() in ('..','node_modules') or p.startswith('.') for p in parts):raise ValueError('无效的前端资源。')
  workspace=self.tasks.workspace(ticket['id']);root=safe_path(workspace,ticket['root']);path=safe_path(root,root/name,file=True)
  if path.suffix.lower() not in EXTENSIONS or path.stat().st_size>8*1024*1024:raise ValueError('不支持的前端资源或文件过大。')
  with path.open('rb') as stream:
   if os.path.normcase(str(opened_path(stream,path)))!=os.path.normcase(str(path.absolute())):raise ValueError('前端文件位置已改变。')
   data=stream.read(8*1024*1024+1)
  if len(data)>8*1024*1024:raise ValueError('前端资源过大。')
  if path.suffix.lower() in ('.html','.css'):
   text=data.decode('utf-8',errors='replace');prefix='/web-product/'+token+'/'
   text=re.sub(r'((?:src|href)\s*=\s*["\'])/(?!/)',lambda m:m[1]+prefix,text,flags=re.I)
   text=re.sub(r'(url\(\s*["\']?)/(?!/)',lambda m:m[1]+prefix,text,flags=re.I)
   data=text.encode('utf-8')
  mime={'.js':'application/javascript','.mjs':'application/javascript','.css':'text/css','.html':'text/html'}.get(path.suffix.lower(),mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
  return data,mime
 def screenshot_path(self,identifier):
  task=self.tasks.get(identifier)
  if task.get('agent')!='codex-deepseek-code' or not task.get('web_screenshot'):raise ValueError('尚未生成网页截图。')
  return safe_path(self.tasks.root,self.tasks.data/identifier/'web-screenshot.png',file=True)
 def screenshot(self,identifier,base):
  if not self.capture_lock.acquire(blocking=False):raise ValueError('已有截图正在生成，请稍后再试。')
  try:
   receipt=self.prepare(identifier)
   metadata=safe_path(self.tasks.root,self.tasks.data/identifier);metadata.mkdir(parents=True,exist_ok=True)
   output=safe_path(self.tasks.root,metadata/'web-screenshot.png')
   with tempfile.TemporaryDirectory(prefix='.web-capture-',dir=metadata) as private:
    temporary=Path(private)/'capture.png'
    command=[sys.executable,str(Path(__file__).with_name('web_product_capture.py')),'--url',base+receipt['url'],'--output',str(temporary)]
    from owned_process import OwnedProcessGroup
    process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:group=OwnedProcessGroup(process)
    except Exception:
     process.kill();process.wait();raise ValueError('无法管理截图进程，未继续。') from None
    try:
     try:code=process.wait(timeout=35)
     except subprocess.TimeoutExpired:raise ValueError('截图超时；源码保留，可稍后重试。') from None
     if code!=0:raise ValueError('本机WebView未能生成截图；请确认Windows会话与WebView2可用。')
     safe_path(metadata,temporary,file=True)
     with temporary.open('rb') as stream:
      if os.path.normcase(str(opened_path(stream,temporary)))!=os.path.normcase(str(temporary.absolute())):raise ValueError('截图位置已改变。')
      header=stream.read(24)
      if len(header)!=24 or header[:8]!=b'\x89PNG\r\n\x1a\n' or header[12:16]!=b'IHDR':raise ValueError('未生成有效PNG。')
      width,height=struct.unpack('>II',header[16:24])
      if not 0<width<=4096 or not 0<height<=4096 or os.fstat(stream.fileno()).st_size>32*1024*1024:raise ValueError('截图尺寸或大小超限。')
     safe_path(self.tasks.root,output);temporary.replace(output)
     self.tasks.update(identifier,web_screenshot=True)
     return {'url':'/api/web-product/screenshot?id='+identifier,'message':'网页视口截图已保存；此图不代表后端功能已验收。'}
    finally:
     group.terminate();group.close()
     if process.poll() is None:process.kill()
     process.wait(timeout=5)
  finally:self.capture_lock.release()
