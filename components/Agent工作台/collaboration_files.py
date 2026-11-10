"""Typed collaboration delivery contracts and bounded immutable local artifacts."""
from pathlib import Path
import hashlib,re,base64
from task_station.spreadsheet_export import CONTRACT as SHEET_CONTRACT,spreadsheet_bytes,parse as parse_sheets,Formulas,col
from task_station.presentation_export import CONTRACT as SLIDE_CONTRACT,presentation_bytes,parse as parse_slides
from task_station.document_export import document_bytes

class DeliveryContentError(ValueError):
 pass

FORMATS=('text','docx','xlsx','pptx')
MIME={'xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation','docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
def output_format(payload):
 value=payload.get('output_format','text')
 if value not in FORMATS:raise ValueError('交付格式只支持文字、DOCX、XLSX或PPTX')
 return value

def delivery_instruction(fmt,seat,stage):
 if fmt=='text':return ''
 contract={'xlsx':SHEET_CONTRACT,'pptx':SLIDE_CONTRACT,'docx':'以可直接排版的正文交付，不编造下载链接。工作站会把最终修订生成DOCX文件。'}[fmt]
 role=('审查前一席实际内容，重点检查数据、公式、遗漏与协议边界；列出具体修订意见，不声称已打开文件或完成视觉验收。' if seat=='B' else '制作完整可交付内容。修订阶段须按审查意见返回完整最终内容，不能只给差异、摘要或说明。')
 if seat=='B':contract='以下为A席应遵守的交付协议，供你检查；你只返回审查意见：\n'+contract
 return '\n本任务交付'+fmt.upper()+'真实文件：'+role+'宿主在最终修订后生成文件，不由你操作Office。以下交付协议优先于席位块或表达风格；A席只返回协议内容，B席使用文字审查。\n'+contract

def _directory(data_dir,identifier,create=False):
 if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('成果会话ID无效')
 root=Path(data_dir).resolve();folder=root/'collaboration-artifacts'/identifier
 for part in (root/'collaboration-artifacts',folder):
  if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()) or not part.resolve().is_relative_to(root):raise ValueError('成果目录路径异常')
 if create:folder.mkdir(parents=True,exist_ok=True)
 return folder

def create_artifact(data_dir,run):
 fmt=output_format(run)
 if fmt=='text':return [],None
 final=next((step['content'] for step in reversed(run['steps']) if step['seat']=='A' and step['stage']=='修订' and step['state']=='completed'),None)
 if not final:raise DeliveryContentError('没有完整最终修订，未生成文件')
 try:
  if fmt=='xlsx':
   raw=spreadsheet_bytes(final);sheets=parse_sheets(final);preview={'type':'xlsx','sheets':[]}
   for sheet in sheets:
    formulas=Formulas(sheet);rows=[]
    for r,row in enumerate(sheet['rows'][:20],2):rows.append([formulas.value(col(c)+str(r)) if isinstance(cell,dict) else cell for c,cell in enumerate(row,1)])
    preview['sheets'].append({'name':sheet['name'],'columns':sheet['columns'],'rows':rows,'total_rows':len(sheet['rows'])})
  elif fmt=='pptx':
   from task_station.presentation_assets import load_assets
   assets=load_assets(data_dir,run['id'],run.get('image_assets',[]))
   raw=presentation_bytes(final,assets);preview={'type':'pptx',**parse_slides(final),'image_count':len(assets)}
  else:raw=document_bytes(final);preview={'type':'docx','text':final[:12000]}
 except (ValueError,RecursionError) as error:raise DeliveryContentError('文件生成失败：'+str(error)) from None
 if not 0<len(raw)<=8*1024*1024:raise DeliveryContentError('文件生成大小超出8MiB上限')
 digest=hashlib.sha256(raw).hexdigest();name='协作成果-'+digest[:16]+'.'+fmt;path=_directory(data_dir,run['id'],True)/name
 if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):raise ValueError('成果文件不能为链接')
 if path.exists():
  if path.read_bytes()!=raw:raise ValueError('已有同名文件内容不同，未覆盖')
 else:
  with path.open('xb') as stream:
   try:stream.write(raw)
   except Exception:
    stream.close();path.unlink(missing_ok=True);raise
 return [{'name':name,'size':len(raw),'sha256':digest,'format':fmt}],preview

def artifact_path(data_dir,run,name):
 metadata=next((f for f in run.get('files',[]) if f.get('name')==name),None)
 if not metadata or not isinstance(name,str) or not re.fullmatch(r'协作成果-[a-f0-9]{16}\.(?:docx|xlsx|pptx)',name):raise ValueError('成果不存在或文件名无效')
 folder=_directory(data_dir,run['id']);path=folder/name
 if path.is_symlink() or not path.is_file() or path.resolve().parent!=folder.resolve() or not 0<path.stat().st_size<=8*1024*1024:raise ValueError('成果文件缺失或路径异常')
 raw=path.read_bytes()
 if len(raw)!=metadata.get('size') or hashlib.sha256(raw).hexdigest()!=metadata.get('sha256'):raise ValueError('成果文件已变化，请在电脑核对原件')
 return path

def read_artifact(data_dir,run,name):
 path=artifact_path(data_dir,run,name);return {'name':name,'mime':MIME[path.suffix[1:]],'content_base64':base64.b64encode(path.read_bytes()).decode('ascii')}
