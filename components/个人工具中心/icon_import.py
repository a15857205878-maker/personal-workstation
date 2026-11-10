"""Import selected icons into a separate library; never edit source resources."""
from pathlib import Path
from io import BytesIO
import hashlib

def import_icons(paths,destination):
    from PIL import Image
    if len(paths)>100:raise ValueError('一次最多添加100个图标')
    result=dict(added=0,existing=0,paths=[],errors=[]);destination=Path(destination)
    for value in paths:
        source=Path(value)
        try:
            if source.suffix.lower() not in ('.ico','.png'):raise ValueError('只支持ICO或PNG文件')
            if not source.is_file() or not 0<source.stat().st_size<=20*1024*1024:raise ValueError('文件不存在、为空或超过20MB')
            raw=source.read_bytes()
            with Image.open(BytesIO(raw)) as image:
                if image.format!=('ICO' if source.suffix.lower()=='.ico' else 'PNG'):raise ValueError('文件内容与扩展名不符')
                if not all(0<n<=4096 for n in image.size):raise ValueError('图标尺寸需在4096像素以内')
                image.load()
                data=raw
                if source.suffix.lower()=='.png':
                    rgba=image.convert('RGBA');side=min(256,max(rgba.size));rgba.thumbnail((side,side),Image.Resampling.LANCZOS)
                    square=Image.new('RGBA',(side,side),(0,0,0,0));square.paste(rgba,((side-rgba.width)//2,(side-rgba.height)//2))
                    buffer=BytesIO();sizes=[(n,n) for n in (16,24,32,48,64,128,256) if n<=side] or [(side,side)]
                    square.save(buffer,format='ICO',sizes=sizes);data=buffer.getvalue()
            name=source.stem[:80]+'-'+hashlib.sha256(raw).hexdigest()[:12]+'.ico';target=destination/name
            if target.exists():
                if target.read_bytes()!=data:raise ValueError('同名新增图标内容不同，原文件已保留')
                result['existing']+=1;result['paths'].append(str(target));continue
            destination.mkdir(parents=True,exist_ok=True)
            created=False
            try:
                with target.open('xb') as stream:created=True;stream.write(data)
            except Exception:
                if created:target.unlink(missing_ok=True)
                raise
            result['added']+=1;result['paths'].append(str(target))
        except Exception as exc:result['errors'].append(dict(name=source.name,message=str(exc)[:240]))
    return result
