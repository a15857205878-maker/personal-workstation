"""Local display preferences, separate from model identities and conversation data."""
from pathlib import Path
import base64,io,json,re,threading
from PIL import Image,ImageOps,UnidentifiedImageError
from credential_store import atomic_json

PREFIX='data:image/webp;base64,'
def import_avatar(path):
    path=Path(path)
    if path.suffix.lower() not in ('.png','.jpg','.jpeg','.webp') or path.stat().st_size>10*1024*1024:
        raise ValueError('请选择10MB以内的PNG、JPEG或WebP图片')
    try:
        with Image.open(path) as source:
            if source.format not in ('PNG','JPEG','WEBP') or source.width*source.height>16000000:
                raise ValueError('图片格式不支持或像素过大（最多1600万像素）')
            source.seek(0)
            avatar=ImageOps.fit(ImageOps.exif_transpose(source).convert('RGBA'),(128,128),method=Image.Resampling.LANCZOS)
            for quality in (85,70,50):
                out=io.BytesIO();avatar.save(out,format='WEBP',quality=quality,method=4,exif=b'',icc_profile=b'')
                value=PREFIX+base64.b64encode(out.getvalue()).decode('ascii')
                if len(value)<=24000:return value
            raise ValueError('图片内容过于复杂，请选择较简单的头像')
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError):raise ValueError('无法读取这张图片，请换一张有效图片') from None

def validate(nickname,avatar):
    if not isinstance(nickname,str) or len(nickname.strip())>24 or any(ord(c)<32 or ord(c)==127 for c in nickname):
        raise ValueError('昵称最多24字，不能包含换行或控制字符')
    if not isinstance(avatar,str) or len(avatar)>24000:raise ValueError('头像内容无效或过大')
    if avatar:
        try:
            if not avatar.startswith(PREFIX):raise ValueError()
            raw=base64.b64decode(avatar[len(PREFIX):],validate=True)
            with Image.open(io.BytesIO(raw)) as im:
                if im.format!='WEBP' or im.size!=(128,128):raise ValueError()
                im.load()
        except (ValueError,OSError,UnidentifiedImageError):raise ValueError('头像格式无效，请通过选择图片重新导入') from None

def valid_id(value):return isinstance(value,str) and (value=='user' or re.fullmatch('[a-f0-9]{32}',value))

class IdentityStore:
    def __init__(self,data_dir):self.path=Path(data_dir)/'member-identities.json';self.lock=threading.RLock()
    def _load(self):
        if not self.path.exists():return {}
        try:
            if self.path.is_symlink() or self.path.stat().st_size>1024*1024:raise ValueError()
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data,dict) or len(data)>33:raise ValueError()
            for key,row in data.items():
                if not valid_id(key) or not isinstance(row,dict) or set(row)!={'nickname','avatar'}:raise ValueError()
                validate(row['nickname'],row['avatar'])
            return data
        except (ValueError,TypeError,KeyError,OSError):raise ValueError('成员资料无法读取，原文件保留，请检查 member-identities.json') from None
    def get(self):
        with self.lock:return dict(items=self._load())
    def save(self,identifier,nickname,avatar):
        if not valid_id(identifier):raise ValueError('成员标识无效')
        validate(nickname,avatar)
        with self.lock:
            data=self._load()
            if nickname.strip() or avatar:data[identifier]=dict(nickname=nickname.strip(),avatar=avatar)
            else:data.pop(identifier,None)
            if len(data)>33:raise ValueError('成员资料最多33项，请先整理')
            atomic_json(self.path,data);return dict(items=data)
