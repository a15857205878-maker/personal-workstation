"""Channel-neutral new-task receiver; no historical conversation binding."""
from pathlib import Path

IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp'}
UNSUPPORTED_IMAGES = {'.heic', '.heif', '.gif', '.bmp', '.tif', '.tiff', '.avif', '.svg'}
DEFAULT_GOAL = '请查看并说明所附图片内容'


def create_bot_task(manager, payload):
    if not isinstance(payload, dict):
        raise ValueError('消息格式不正确')
    text = payload.get('text', '')
    attachments = payload.get('attachments', [])
    mode = payload.get('mode', 'task')
    agent = payload.get('agent', 'codex')
    if not isinstance(agent,str) or agent not in ('codex','deepseek-flash','codex-deepseek-code'):
        raise ValueError('请选择Codex或DeepSeek Flash。')
    if agent=='codex-deepseek-code' and (mode!='task' or attachments or set(payload)-{'text','attachments','mode','agent','request_id','project_kind','reference_url'}):
        raise ValueError('代码协作只支持专用目录新项目，不接受附件、目录参数或只读审查。')
    if agent == 'deepseek-flash' and mode != 'task':
        raise ValueError('Flash首版仅支持新任务；只读审查请选择Codex。')
    if not isinstance(text, str) or len(text) > 20000:
        raise ValueError('文字最多 20000 字')
    if mode not in ('task', 'review'):
        raise ValueError('请选择新任务或审查附件')
    if not isinstance(attachments, list) or len(attachments) > 10:
        raise ValueError('最多选择 10 个附件')
    if mode == 'review' and not attachments:
        raise ValueError('请先添加需要审查的附件')
    for name in attachments:
        if not isinstance(name, str) or Path(name).name != name or '/' in name or '\\' in name:
            raise ValueError('附件名称无效')
        suffix = Path(name).suffix.lower()
        if suffix in UNSUPPORTED_IMAGES:
            raise ValueError('这类图片暂不支持直接看图，请转换为 PNG、JPEG 或 WebP 后发送')
        if suffix in IMAGE_SUFFIXES:
            path = manager.uploads / name
            if path.is_symlink() or not path.is_file():
                raise ValueError('图片不存在，请重新上传')
            with path.open('rb') as stream:
                head = stream.read(12)
            valid = (suffix == '.png' and head.startswith(b'\x89PNG\r\n\x1a\n') or
                     suffix in {'.jpg', '.jpeg'} and head.startswith(b'\xff\xd8\xff') or
                     suffix == '.webp' and head[:4] == b'RIFF' and head[8:12] == b'WEBP')
            if not valid:
                raise ValueError('图片格式与文件内容不符，请重新导出图片')
    if not text.strip():
        if not attachments:
            raise ValueError('请输入文字或添加图片')
        text = ('请只读审查所附材料，列出问题、依据与改进建议' if mode == 'review' else
                DEFAULT_GOAL if all(Path(n).suffix.lower() in IMAGE_SUFFIXES for n in attachments)
                else '请阅读并说明所附材料内容')
    options={k:payload[k] for k in ('project_kind','reference_url') if k in payload} if agent=='codex-deepseek-code' else {}
    return manager.create({'goal': text, 'attachments': attachments, 'agent': agent,
                           'mode': mode, 'client_id': payload.get('request_id'),**options})
