"""Read-only views of the existing collaboration file protocol."""
from pathlib import Path
from datetime import datetime
import hashlib,re

DEFAULT_ROOM=Path(__file__).resolve().parent/'examples/collab'
MAX_FILE=512*1024

def frontmatter(text,name):
    lines=text.replace('\r\n','\n').replace('\r','\n').split('\n')
    if not lines or lines[0]!='---':raise ValueError(f'{name}: 缺少 frontmatter 起始 ---')
    fields={}
    for index,line in enumerate(lines[1:],1):
        if line=='---':return fields,'\n'.join(lines[index+1:]).strip('\n')
        if not line.strip() or line.lstrip().startswith('#'):continue
        if ':' not in line:raise ValueError(f'{name}: frontmatter 第 {index+1} 行格式错误')
        key,value=line.split(':',1);key=key.strip();value=value.strip()
        if key in fields:raise ValueError(f'{name}: 字段重复 {key}')
        if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):value=value[1:-1]
        fields[key]=value
    raise ValueError(f'{name}: 缺少 frontmatter 结束 ---')

def require(fields,keys,name):
    for key in keys:
        if not fields.get(key,'').strip():raise ValueError(f'{name}: 缺少必填字段 {key}')

class RoomStore:
    def __init__(self,root=DEFAULT_ROOM):self.root=Path(root).resolve()
    def path(self,relative):
        path=(self.root/relative).resolve()
        if not path.is_relative_to(self.root):raise ValueError('拒绝访问房间目录以外的路径')
        return path
    def read(self,relative):
        path=self.path(relative)
        if path.stat().st_size>MAX_FILE:raise ValueError(f'{path.name}: 文件过大，最大 512 KiB')
        return path.read_text(encoding='utf-8-sig')
    def documents(self,kind):
        folder=self.path(kind)
        if not folder.is_dir():return []
        result=[]
        for path in sorted(folder.glob('*.md'),key=lambda p:p.name):
            safe=self.path(f'{kind}/{path.name}')
            if safe.parent!=folder or not safe.is_file():raise ValueError(f'{path.name}: 文档路径越界')
            result.append(dict(name=path.name,size=safe.stat().st_size,modified=datetime.fromtimestamp(safe.stat().st_mtime).isoformat(timespec='seconds')))
        return result
    def read_document(self,kind,name=''):
        fixed={'persona':'persona/conductor.md','protocol':'PROTOCOL.md','log':'room/log.md'}
        if kind in fixed:relative=fixed[kind]
        elif kind in ('drafts','card'):
            if not isinstance(name,str) or name in ('','.','..') or '/' in name or '\\' in name or ':' in name:raise ValueError('文档名称无效')
            if name not in {row['name'] for row in self.documents(kind)}:raise ValueError('文档不存在或不在可读列表中')
            relative=f'{kind}/{name}'
        else:raise ValueError('不支持的文档类型')
        return dict(name=Path(relative).name,text=self.read(relative))
    def snapshot(self):
        digest=hashlib.sha256();total=0
        def read(relative):
            nonlocal total
            value=self.read(relative);total+=len(value.encode('utf-8'))
            if total>12*1024*1024:raise ValueError('房间内容过大，请先归档历史消息')
            digest.update(str(relative).encode());digest.update(b'\0');digest.update(value.encode('utf-8'));digest.update(b'\0')
            return value
        read('PROTOCOL.md');read('persona/conductor.md')
        brief,body=frontmatter(read('room/brief.md'),'brief.md')
        require(brief,('场次','目标','语言','轮次上限'),'brief.md')
        seats={};inside=False
        for line in body.splitlines():
            if not line.strip().startswith('|'):
                if inside:break
                continue
            cells=[s.strip() for s in line.strip().strip('|').split('|')]
            if not inside:
                if cells==['席','模型','职能','接线']:inside=True
                continue
            if all(re.fullmatch(r':?-+:?',x) for x in cells):continue
            if len(cells)!=4 or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*',cells[0]):raise ValueError('brief.md: 无效席位表行')
            if cells[0] in seats:raise ValueError(f'brief.md: 席位重复 {cells[0]}')
            if not cells[1] or not cells[2]:raise ValueError('brief.md: 模型或职能为空')
            seats[cells[0]]=dict(id=cells[0],model=cells[1],role=cells[2],connection=cells[3])
        if not seats:raise ValueError('brief.md: 找不到非空席位表')
        for special,label in (('U','用户'),('SUM','合流')):seats.setdefault(special,dict(id=special,model=label,role=label,connection='手工'))
        turntext=read('room/turn.md');turn={}
        for field,key in (('持权','holder'),('轮次','round'),('自','since')):
            matches=re.findall(r'^'+field+r':[ \t]*([^\r\n]*)',turntext,re.M)
            if len(matches)!=1 or not matches[0].strip():raise ValueError(f'turn.md: 字段 {field} 必须唯一且非空')
            turn[key]=matches[0].strip()
        if turn['holder'] not in seats and turn['holder']!='用户':raise ValueError(f'turn.md: 非法当前持权 {turn["holder"]}')
        if not turn['round'].isdigit() or int(turn['round'])<1:raise ValueError('turn.md: 轮次必须为正整数')
        turn['round']=int(turn['round'])
        messages=[];folder=self.path('room/messages')
        if not folder.is_dir():raise ValueError('room/messages/ 不存在')
        paths=sorted(folder.glob('*.md'),key=lambda p:p.name)
        if len(paths)>2000:raise ValueError('消息超过 2000 条，请先归档')
        for path in paths:
            raw=read(f'room/messages/{path.name}');fields,body=frontmatter(raw,path.name)
            require(fields,('seat','model','role','round','at'),path.name)
            if not path.name.isascii():raise ValueError(f'{path.name}: 文件名必须为 ASCII')
            if not fields['round'].isdigit() or int(fields['round'])<1:raise ValueError(f'{path.name}: round 必须为正整数')
            try:
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})',fields['at']):raise ValueError()
                datetime.fromisoformat(fields['at'])
            except ValueError:raise ValueError(f'{path.name}: at 必须为含时区的 ISO 时间') from None
            messages.append(dict(id=path.name,seat=fields['seat'],model=fields['model'],role=fields['role'],round=int(fields['round']),at=fields['at'],reply_to=fields.get('reply-to',''),body=body,raw=raw))
        return dict(path=str(self.root),mode='manual',revision=digest.hexdigest(),
                    brief=dict(name=brief['场次'],goal=brief['目标'],language=brief['语言'],round_limit=brief['轮次上限']),
                    seats=list(seats.values()),turn=turn,messages=messages,
                    files={kind:self.documents(kind) for kind in ('card','drafts')},refreshed=datetime.now().isoformat(timespec='seconds'))
