"""Metadata-only desktop artifact index; sources do not grant remote file access."""
from pathlib import Path
from html import escape
from html.parser import HTMLParser
import hashlib,json,os,threading,uuid
from credential_store import atomic_json

OPEN={'.docx','.xlsx','.pptx','.pdf','.txt','.md','.csv','.tsv','.png','.jpg','.jpeg','.webp','.gif','.mp4','.webm','.zip'}
PREVIEW={'.html','.htm','.svg'}
SHOW=OPEN|PREVIEW|{'.json','.py','.js','.css'}

def linked(path):return path.is_symlink() or getattr(path,'is_junction',lambda:False)()
def checked(path,root):
 path=Path(path);root=Path(root)
 if linked(root) or not path.resolve().is_relative_to(root.resolve()):raise ValueError('成果路径已改变，请重新选择来源')
 for p in (path,*path.parents):
  if linked(p):raise ValueError('成果来源包含链接，请选择实际文件目录')
 if not path.is_file():raise ValueError('文件已移动或删除，请刷新成果')
 return path

class _StaticHTML(HTMLParser):
 tags=set('div span p h1 h2 h3 h4 h5 h6 header footer main section article aside nav ul ol li dl dt dd table thead tbody tr th td br hr b strong i em small pre code blockquote style title svg g path rect circle ellipse line polyline polygon text tspan defs lineargradient radialgradient stop clippath mask pattern use img figure figcaption'.split())
 def __init__(self):super().__init__(convert_charrefs=True);self.out=[];self.blocked=0;self.style=False
 def handle_starttag(self,tag,attrs):
  if tag in ('script','iframe','object','foreignobject'):self.blocked+=1;return
  if self.blocked or tag not in self.tags:return
  safe=[]
  for key,value in attrs:
   value=value or ''
   if key.startswith('on') or key in ('action','formaction','target','srcdoc','xml:base'):continue
   if key in ('href','xlink:href') and not value.startswith('#'):continue
   if key in ('src','srcset') and not (key=='src' and value.startswith(('data:image/png;base64,','data:image/jpeg;base64,','data:image/webp;base64,','data:image/gif;base64,'))):continue
   safe.append(' '+key+'="'+escape(value,quote=True)+'"')
  self.out.append('<'+tag+''.join(safe)+'>');self.style=tag=='style'
 def handle_startendtag(self,tag,attrs):self.handle_starttag(tag,attrs);self.handle_endtag(tag)
 def handle_endtag(self,tag):
  if tag in ('script','iframe','object','foreignobject'):
   self.blocked=max(0,self.blocked-1);return
  if not self.blocked and tag in self.tags:self.out.append('</'+tag+'>')
  if tag=='style':self.style=False
 def handle_data(self,text):
  if not self.blocked:self.out.append(text if self.style else escape(text))

def isolated_html(raw):
 try:
  from task_station.generation_channels import animation_html
  return animation_html(raw)
 except ValueError:
  parser=_StaticHTML();parser.feed(raw)
  policy="default-src 'none'; style-src 'unsafe-inline'; img-src data:; script-src 'none'; base-uri 'none'; form-action 'none'"
  return '<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="'+policy+'"></head><body>'+''.join(parser.out)+'</body></html>'

class ArtifactBrowser:
 def __init__(self,data_dir,opener=None):
  self.data=Path(data_dir) if data_dir is not None else None;self.opener=opener or os.startfile;self.lock=threading.RLock();self.current={}
 def _sources(self):
  if self.data is None:return []
  path=self.data/'artifact-sources.json'
  if not path.exists():return []
  if linked(path) or path.stat().st_size>131072:raise ValueError('成果来源配置异常，原文件保留')
  value=json.loads(path.read_text(encoding='utf-8'))
  if not isinstance(value,list) or len(value)>110:raise ValueError('成果来源配置格式无效')
  for s in value:
   if not isinstance(s,dict) or s.get('kind') not in ('file','folder') or not isinstance(s.get('path'),str) or not isinstance(s.get('id'),str):raise ValueError('成果来源配置格式无效')
  return value
 def add(self,paths,folder=False):
  if self.data is None:raise ValueError('成果设置目录不可用')
  with self.lock:
   sources=self._sources();kind='folder' if folder else 'file';known={os.path.normcase(s['path']) for s in sources}
   for raw in paths:
    p=Path(raw).absolute()
    if linked(p) or (not p.is_dir() if folder else not p.is_file()):raise ValueError('请选择实际的文件或文件夹')
    if os.path.normcase(str(p)) in known:continue
    sources.append({'id':uuid.uuid4().hex,'kind':kind,'path':str(p)});known.add(os.path.normcase(str(p)))
   if sum(s['kind']=='folder' for s in sources)>10 or sum(s['kind']=='file' for s in sources)>100:raise ValueError('最多添加10个文件夹和100个独立文件')
   atomic_json(self.data/'artifact-sources.json',sources)
 def remove(self,identifier):
  with self.lock:
   sources=self._sources()
   if not any(s['id']==identifier for s in sources):raise ValueError('来源已移除，请刷新')
   atomic_json(self.data/'artifact-sources.json',[s for s in sources if s['id']!=identifier])
 def list(self,station_items):
  with self.lock:
   warnings=[];items=[];cache={};seen=set();sources=self._sources()
   from center_index import read_center
   center=read_center(self.data);owners=center['run_owners'];warnings.extend(center['warnings'])
   def add(path,kind,source,title='',owner=None,metadata=None):
    p=Path(path) if path else None;name=p.name if p else metadata['name'];size=metadata.get('size',0) if metadata else 0;mtime=0
    try:
     if p:stat=p.stat();size=stat.st_size;mtime=stat.st_mtime
    except OSError:
     if kind=='center':warnings.append('部分搭档成果文件已移动或缺失，请回原记录核对。')
     return
    key=os.path.normcase(str(p.absolute())) if p else 'station:'+source+':'+name
    if key in seen:return
    seen.add(key)
    identifier=hashlib.sha256((kind+'\0'+source+'\0'+str(path or name)).encode('utf-8')).hexdigest()
    item=dict(id=identifier,name=name,size=size,modified=mtime,source_kind=kind,source_label={'station':'历史任务成果','collaboration':'双模型协作','external':'外部文件','center':'搭档群聊'}[kind],title=title,can_open=Path(name).suffix.lower() in OPEN,can_preview=Path(name).suffix.lower() in PREVIEW)
    if owner:item.update(task_id=owner.get('id'),task_title=title)
    if kind=='center':item.update(owners[owner['id']])
    cache[identifier]=dict(item,path=p,source=source,owner=owner);items.append(item)
   for item in station_items:
    path=Path(item['folder'])/'results'/item['name'] if item.get('folder') else None
    add(path,'station',item['task_id'],item.get('title',''),{'id':item['task_id'],'name':item['name']},item)
   if self.data is not None:
    from session_store import SessionStore
    store=SessionStore(self.data/'sessions')
    for identifier in dict.fromkeys([*owners,*[r['id'] for r in store.list()]]):
     try:
      run=store.load(identifier)
      files=run.get('files') or []
      if not isinstance(files,list):raise ValueError('成果元数据异常')
      for f in files[:100]:
       if not isinstance(f,dict):continue
       name=f.get('name','')
       if not isinstance(name,str) or not name or Path(name).name!=name:continue
       path=self.data/'collaboration-artifacts'/run['id']/name
       add(path,'center' if run['id'] in owners else 'collaboration',run['id'],owners.get(run['id'],{}).get('conversation_title') or run.get('title',''),{'id':run['id'],'name':name})
     except (OSError,ValueError,KeyError,TypeError):warnings.append('部分协作记录暂时无法读取，原文件保持不变。')
   for source in sources:
    p=Path(source['path'])
    try:
     if source['kind']=='file':checked(p,p.parent);add(p,'external',source['id'],'单独添加 · '+p.parent.name)
     else:
      if not p.is_dir() or linked(p):raise ValueError()
      for index,f in enumerate(p.iterdir()):
       if index>=2000:warnings.append(p.name+'条目较多，仅检查前2000项；建议选择更具体的成果目录。');break
       if f.is_file() and not linked(f) and not f.name.startswith('.') and f.suffix.lower() in SHOW:add(f,'external',source['id'],'文件夹 · '+p.name)
    except (OSError,ValueError):warnings.append('外部来源不可用：'+p.name+'，可重新选择或移除来源。')
   items.sort(key=lambda x:x['modified'],reverse=True);items=items[:300];self.current={i['id']:cache[i['id']] for i in items}
   return dict(items=items,sources=[dict(s,label=Path(s['path']).name) for s in sources],warnings=list(dict.fromkeys(warnings)),limit=300,scope='搭档群聊与历史任务/协作最近100条记录 + 已选择的外部文件/文件夹；文件夹仅当前层，最多显示最近300个文件')
 def path(self,identifier):
  with self.lock:
   entry=self.current.get(identifier)
   if entry is None:raise ValueError('成果列表已变化，请刷新后重新选择')
   if entry['source_kind']=='station':
    if self.data is None:raise ValueError('任务目录不可用')
    root=self.data/'station/tasks'/entry['owner']['id']/'results';path=root/entry['owner']['name']
   elif entry['source_kind'] in ('collaboration','center'):
    from session_store import SessionStore
    from collaboration_files import artifact_path
    return artifact_path(self.data,SessionStore(self.data/'sessions').load(entry['owner']['id']),entry['owner']['name'])
   else:
    source=next((s for s in self._sources() if s['id']==entry['source']),None)
    if source is None:raise ValueError('成果来源已移除')
    root=Path(source['path']);path=entry['path']
    if source['kind']=='file':
     if path!=root:raise ValueError('成果路径无效')
     root=root.parent
   return checked(path,root)
 def preview(self,identifier):
  p=self.path(identifier)
  if p.suffix.lower() not in PREVIEW or p.stat().st_size>1000000:raise ValueError('仅支持1MB以内的HTML/SVG隔离预览')
  return {'name':p.name,'html':isolated_html(p.read_text(encoding='utf-8-sig'))}
 def open(self,identifier,locate=False):
  p=self.path(identifier)
  if not locate and p.suffix.lower() not in OPEN:raise ValueError('此类型请使用隔离预览或定位文件夹后自行检查')
  self.opener(str(p.parent if locate else p));return {'opened':True}
