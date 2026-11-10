"""Explicit photo snapshots for a single collaboration. No URLs or model paths."""
from pathlib import Path
from io import BytesIO
import hashlib,re,warnings
from PIL import Image,ImageOps

def image_bytes(raw):
 if not 0<len(raw)<=10*1024*1024:raise ValueError('图片需在10MiB以内')
 try:
  with warnings.catch_warnings():
   warnings.simplefilter('error',Image.DecompressionBombWarning)
   with Image.open(BytesIO(raw)) as image:
    if image.format not in ('PNG','JPEG','WEBP','BMP') or image.width*image.height>24000000 or getattr(image,'n_frames',1)!=1:raise ValueError('请选择静态PNG/JPEG/WebP/BMP，最多2400万像素')
    image.load();image=ImageOps.exif_transpose(image);image.thumbnail((1600,1600))
    if image.mode in ('RGBA','LA') or 'transparency' in image.info:
     rgba=image.convert('RGBA');base=Image.new('RGB',image.size,'white');base.paste(rgba,mask=rgba.getchannel('A'));image=base
    else:image=image.convert('RGB')
    out=BytesIO();image.save(out,format='JPEG',quality=88,optimize=True)
    return {'data':out.getvalue(),'width':image.width,'height':image.height,'extension':'jpg'}
 except (OSError,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:raise ValueError('配图损坏或尺寸过大，请换一张静态图片') from exc

def validate_ids(ids):
 if not isinstance(ids,list) or len(ids)>5 or any(not isinstance(v,str) or not re.fullmatch('[a-f0-9]{32}',v) for v in ids) or len(set(ids))!=len(ids):raise ValueError('配图编号无效，最多5张且不可重复')

def media_dir(data_dir,identifier,create=False):
 from collaboration_files import _directory
 folder=_directory(data_dir,identifier,create)/'media'
 if folder.is_symlink() or getattr(folder,'is_junction',lambda:False)():raise ValueError('配图目录不能为链接')
 if create:folder.mkdir(exist_ok=True)
 return folder

def prepare_assets(data_dir,identifier,ids):
 from .attachments import AttachmentStore
 validate_ids(ids)
 if not ids:return []
 root=Path(data_dir);store=AttachmentStore(root/'station/attachments');bundle=store.bundle(ids);manifest=[]
 folder=media_dir(root,identifier,True)
 for row in bundle['items']:
  if row['kind']!='image_asset':raise ValueError('请在PPTX模式重新添加图片作为配图')
  original=store.root/row['id']/('original'+row['suffix'])
  with original.open('rb') as f:raw=f.read(10*1024*1024+1)
  if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('配图原件已变化，请重新添加')
  asset=image_bytes(raw)
  digest=hashlib.sha256(asset['data']).hexdigest();name=row['id']+'-'+digest[:16]+'.jpg';path=folder/name
  if path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise ValueError('配图文件不能为链接')
  if path.exists():
   if path.read_bytes()!=asset['data']:raise ValueError('配图快照已变化')
  else:
   with path.open('xb') as f:f.write(asset['data'])
  manifest.append({'id':row['id'],'name':row['name'],'file':name,'width':asset['width'],'height':asset['height'],'sha256':digest})
 return manifest

def load_assets(data_dir,identifier,manifest):
 if not isinstance(manifest,list) or len(manifest)>5:raise ValueError('配图清单无效')
 folder=media_dir(data_dir,identifier);result={}
 for row in manifest:
  if not isinstance(row,dict) or not re.fullmatch('[a-f0-9]{32}',str(row.get('id',''))) or not re.fullmatch(row['id']+r'-[a-f0-9]{16}\.jpg',str(row.get('file',''))):raise ValueError('配图快照编号无效')
  path=folder/row['file']
  if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=4*1024*1024:raise ValueError('配图快照不存在或无效')
  raw=path.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=row.get('sha256'):raise ValueError('配图快照已变化，请重新添加')
  result[row['id']]={'data':raw,'width':row['width'],'height':row['height'],'extension':'jpg'}
 return result
