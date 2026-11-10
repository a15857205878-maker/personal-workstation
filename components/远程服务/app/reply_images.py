"""Validate and snapshot images attached to an existing conversation."""
from pathlib import Path
import shutil
from bot_tasks import IMAGE_SUFFIXES


def image_names(value):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 10:
        raise ValueError('历史会话每次最多发送10张图片。')
    for name in value:
        if (not isinstance(name, str) or not name or len(name) > 240
                or Path(name).name != name or any(c in name for c in '/\\<>:"|?*')
                or any(ord(c) < 32 for c in name) or Path(name).suffix.lower() not in IMAGE_SUFFIXES):
            raise ValueError('历史会话图片仅支持 PNG、JPEG、WebP，文件名不能包含路径。')
    if len(set(value)) != len(value):
        raise ValueError('同一图片不能重复添加。')
    return list(value)


def checked_image(base, name):
    image_names([name])
    base = Path(base)
    path = base / name
    if (base.is_symlink() or base.is_junction() or base.parent.is_symlink() or base.parent.is_junction()
            or path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(base.resolve())):
        raise ValueError('图片不存在或路径无效，请重新上传。')
    if not 0 < path.stat().st_size <= 100 * 1024 * 1024:
        raise ValueError('图片不能为空，单张最多100 MB。')
    with path.open('rb') as stream:
        head = stream.read(12)
    suffix = path.suffix.lower()
    if not (suffix == '.png' and head.startswith(b'\x89PNG\r\n\x1a\n')
            or suffix in ('.jpg', '.jpeg') and head.startswith(b'\xff\xd8\xff')
            or suffix == '.webp' and head[:4] == b'RIFF' and head[8:12] == b'WEBP'):
        raise ValueError('图片格式与内容不符，请转换为 PNG、JPEG 或 WebP。')
    return path


def snapshot_images(uploads, folder, names):
    sources = [checked_image(uploads, name) for name in names]
    folder.mkdir()
    for name, source in zip(names, sources):
        shutil.copyfile(source, folder / name)
        checked_image(folder, name)


def execution_images(job):
    base = Path(job['output']).parent / 'inputs'
    return [checked_image(base, name) for name in image_names(job.get('attachments'))]
