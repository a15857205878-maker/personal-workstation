"""Read-only, best-effort adapter for this machine's Codex history format.

This is not the running Codex control channel. All statuses are log observations.
"""
from contextlib import closing
import base64
import copy
import json
from pathlib import Path
import re
import sqlite3
import time


def presentation_text(text):
    """Normalize known app envelopes only; never treat task code as diagnostics."""
    stripped = text.strip()
    for tag in ('external_codex_apps_open_page', 'environment_context'):
        envelope = re.fullmatch(r'<' + tag + r'>([\s\S]*?)</' + tag + r'>', stripped)
        if envelope and ('</' + tag + '>') not in envelope.group(1):
            return ''
    ambient = re.match(r'^<in-app-browser-context\s+source="ambient-ui-state">[\s\S]*?</in-app-browser-context>\s*(?:##? My request:\s*)?', stripped)
    if ambient:
        return stripped[ambient.end():].strip()
    reply = re.fullmatch(r'<send_user_message_question_reply>\s*([\s\S]*?)\s*</send_user_message_question_reply>', stripped)
    if reply:
        try:
            rows = json.loads(reply.group(1))
            if isinstance(rows, list) and rows and all(isinstance(row, dict) and isinstance(row.get('question'), str) and isinstance(row.get('answer'), str) for row in rows):
                return '\n\n'.join(row['question'] + '\n' + row['answer'] for row in rows)
        except ValueError:
            pass
    return text


class CodexSessionReader:
    def __init__(self, home=None):
        self.home = Path(home) if home else Path.home()/'.codex'
        self.cache = {}
        self.history_cache = {}
        self.generation_cache = {}

    def _generation_calls(self,path,end,stat):
        """Small source-only provenance index; never parse large tool outputs here."""
        key=(str(path),stat.st_mtime_ns,stat.st_size,end)
        if key in self.generation_cache:return set(self.generation_cache[key])
        calls=set();start=max(0,end-64*1024*1024)
        with path.open('rb') as stream:
            stream.seek(start)
            if start:
                while stream.tell()<end:
                    chunk=stream.readline(min(128*1024,end-stream.tell()))
                    if chunk.endswith(b'\n') or not chunk:break
            while stream.tell()<end:
                line=stream.readline(min(128*1024+1,end-stream.tell()))
                if len(line)>128*1024:
                    while not line.endswith(b'\n') and stream.tell()<end:
                        line=stream.readline(min(128*1024,end-stream.tell()))
                    continue
                if b'custom_tool_call' not in line or b'image_gen__imagegen' not in line:continue
                try:value=json.loads(line)
                except (ValueError,UnicodeError):continue
                self._generated_message(value,0,calls)
        if len(self.generation_cache)>=16:self.generation_cache.clear()
        self.generation_cache[key]=set(calls)
        return calls

    @staticmethod
    def _generation_call(code):
        """Accept only a standalone generation call, never arbitrary exec source."""
        if not isinstance(code,str):return False
        code=re.sub(r'^\s*// @exec: [^\r\n]*\r?\n','',code,count=1)
        match=re.fullmatch(r'\s*(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*await\s+tools\.image_gen__imagegen\(\s*(\{[\s\S]*\})\s*\)\s*;\s*generatedImage\(\s*\1\s*\)\s*;?\s*',code)
        if not match:return False
        # Permit literal JSON plus unquoted JS object keys, no expressions/calls.
        literal=re.sub(r'("(?:\\.|[^"\\])*")|\b([A-Za-z_][\w]*)\s*:',
                       lambda m:m[1] if m[1] else json.dumps(m[2])+':',match[2])
        try:args=json.loads(literal)
        except ValueError:return False
        return (isinstance(args,dict) and set(args)<=
                {'prompt','transparent_background','referenced_image_paths','num_last_images_to_include'})

    @staticmethod
    def _image_bytes(item):
        if not isinstance(item,dict) or item.get('type')!='input_image':raise ValueError('图片格式无效')
        url=item.get('image_url')
        if not isinstance(url,str) or len(url)>16*1024*1024:raise ValueError('图片过大')
        header,separator,encoded=url.partition(',')
        mime=header.removeprefix('data:').removesuffix(';base64')
        if not separator or header!='data:'+mime+';base64' or mime not in ('image/png','image/jpeg','image/webp'):
            raise ValueError('图片格式无效')
        data=base64.b64decode(encoded,validate=True)
        valid=(mime=='image/png' and data.startswith(b'\x89PNG\r\n\x1a\n') or
               mime=='image/jpeg' and data.startswith(b'\xff\xd8\xff') or
               mime=='image/webp' and data.startswith(b'RIFF') and data[8:12]==b'WEBP')
        if not valid:raise ValueError('图片内容无效')
        return data,mime

    def _generated_message(self,value,offset,calls):
        if not isinstance(value,dict) or value.get('type')!='response_item':return None
        p=value.get('payload',{})
        if not isinstance(p,dict):return None
        if p.get('type')=='custom_tool_call':
            code=p.get('input','')
            if (p.get('name')=='exec' and self._generation_call(code) and isinstance(p.get('call_id'),str)):
                calls.add(p['call_id'])
            return None
        if p.get('type')!='custom_tool_call_output' or p.get('call_id') not in calls:return None
        content=p.get('output');images=[]
        if not isinstance(content,list):return None
        for index,item in enumerate(content[:100]):
            try:
                data,mime=self._image_bytes(item)
            except (ValueError,TypeError):continue
            images.append({'index':index,'mime':mime,'size':len(data)})
        if not images:return None
        return {'id':str(offset),'role':'assistant','text':'生成的图片','time':value.get('timestamp',''),
                'truncated':False,'images':images}

    def generated_image(self,session_id,offset,index):
        if type(offset) is not int or offset<0 or type(index) is not int or not 0<=index<100:
            raise ValueError('图片标识无效')
        rows=self._rows(session_id,1)
        if not rows:raise KeyError('会话不存在')
        path=self._log_path(rows[0])
        with path.open('rb') as stream:
            if offset:
                stream.seek(offset-1)
                if stream.read(1)!=b'\n':raise FileNotFoundError('图片记录不存在')
            stream.seek(offset);line=stream.readline(16*1024*1024+1)
        if len(line)>16*1024*1024:raise ValueError('图片记录过大')
        # Revalidate generation-call provenance in this exact session/page.
        page=self.history(session_id,before=offset+len(line))
        found=next((m for m in page['messages'] if m['id']==str(offset) and
                    any(i['index']==index for i in m.get('images',[]))),None)
        if not found:raise FileNotFoundError('图片记录不存在')
        value=json.loads(line)
        return self._image_bytes(value['payload']['output'][index])

    def _database(self):
        files = list(self.home.glob('state_*.sqlite'))
        if not files:
            raise FileNotFoundError('未找到本机 Codex 会话索引，请先在电脑打开 Codex。')
        return max(files, key=lambda p:p.stat().st_mtime)

    def _rows(self, session_id=None, limit=20, offset=0, search=''):
        with closing(sqlite3.connect(self._database().as_uri()+'?mode=ro', uri=True, timeout=2)) as db:
            db.row_factory=sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            cols={r[1] for r in db.execute('PRAGMA table_info(threads)')}
            required={'id','title','cwd','updated_at','rollout_path','archived'}
            if not required.issubset(cols):
                raise ValueError('此版本 Codex 的本地索引结构尚未适配。')
            label="COALESCE(NULLIF(TRIM(name),''),title) AS title" if 'name' in cols else 'title'
            sql='SELECT id,'+label+',cwd,updated_at,rollout_path FROM threads WHERE archived=0'
            values=[]
            if 'thread_source' in cols:
                sql+=" AND (thread_source IS NULL OR thread_source NOT IN ('guardian_review','subagent','review'))"
            if 'source' in cols:
                sql+=' AND (source IS NULL OR source NOT LIKE ?)';values.append('%"subagent"%')
            if 'agent_role' in cols:
                sql+=' AND agent_role IS NULL'
            if session_id is not None:
                sql+=' AND id=?';values.append(session_id)
            if search:
                field="COALESCE(NULLIF(TRIM(name),''),title,'')" if 'name' in cols else "COALESCE(title,'')"
                sql+=' AND instr(lower('+field+'),lower(?))>0';values.append(search)
            sql+=' ORDER BY updated_at DESC,id DESC LIMIT ? OFFSET ?';values.extend([limit,offset])
            return [dict(r) for r in db.execute(sql,values)]

    def session_page(self, limit=20, offset=0, search=''):
        if not isinstance(limit,int) or not 1 <= limit <= 50 or not isinstance(offset,int) or offset < 0:
            raise ValueError('会话分页参数无效')
        if not isinstance(search,str) or len(search)>300:
            raise ValueError('搜索文字最多 300 字')
        rows=self._rows(limit=limit+1,offset=offset,search=search.strip())
        return {'sessions':[{'id':r['id'],'title':r['title'] or '未命名会话','updated':r['updated_at']}
                            for r in rows[:limit]],
                'next_offset':offset+limit if len(rows)>limit else None}

    def get(self, session_id):
        rows=self._rows(session_id,1)
        if not rows:raise KeyError('会话不存在或已归档，请重新列出会话。')
        r=rows[0]
        return {'id':r['id'],'title':r['title'] or '未命名会话','cwd':r['cwd'],'updated':r['updated_at']}

    def sessions(self):
        result=[]
        for r in self._rows():
            item={'id':r['id'],'title':r['title'] or '未命名会话','cwd':r['cwd'],'updated':r['updated_at']}
            try:
                progress=self._read_log(r)
                item.update(status=progress['status'],status_hint=progress['status_hint'])
            except (OSError, ValueError):
                item.update(status='unknown',status_hint='暂时无法读取会话记录')
            item['number']=len(result)+1
            result.append(item)
        return result

    def progress(self, session_id):
        rows=self._rows(session_id,1)
        if not rows:raise KeyError('绑定会话不存在或已归档。')
        row=rows[0]
        return {'id':row['id'],'title':row['title'] or '未命名会话','cwd':row['cwd'],
                'observed_at':time.time(),**self._read_log(row)}

    def _log_path(self, row):
        name=row['rollout_path']
        if name.startswith('\\\\?\\'):name=name[4:]
        path=Path(name).resolve()
        roots=[(self.home/'sessions').resolve(),(self.home/'archived_sessions').resolve()]
        if not any(path.is_relative_to(root) for root in roots):
            raise ValueError('会话日志路径不在允许的 Codex 会话目录中。')
        return path

    @staticmethod
    def _public_message(value, offset):
        if not isinstance(value,dict) or value.get('type')!='response_item':return None
        payload=value.get('payload')
        if not isinstance(payload,dict) or payload.get('type')!='message':return None
        role=payload.get('role')
        if role not in ('user','assistant'):return None
        public={'commentary','final','final_answer'}
        if role=='assistant' and payload.get('phase') not in public and payload.get('channel') not in public:return None
        content=payload.get('content')
        if not isinstance(content,list):return None
        parts=[]
        for item in content:
            if not isinstance(item,dict):continue
            if item.get('type') in ('input_text','output_text') and isinstance(item.get('text'),str):parts.append(item['text'])
            elif item.get('type') in ('input_image','image_url','image'):parts.append('［图片附件，历史预览不加载原图］')
        text='\n'.join(parts)
        if role == 'user':
            text = presentation_text(text)
        if not text.strip():return None
        return {'id':str(offset),'role':role,'text':text[:12000],
                'time':value.get('timestamp',''),'truncated':len(text)>12000}

    def history(self, session_id, before=None, limit=50):
        rows=self._rows(session_id,1)
        if not rows:raise KeyError('会话不存在或已归档。')
        if not isinstance(limit,int) or not 1<=limit<=50:raise ValueError('历史分页大小无效')
        row=rows[0];path=self._log_path(row);stat=path.stat();size=stat.st_size
        if before is not None and (not isinstance(before,int) or not 0<=before<=size):
            raise ValueError('历史游标无效或日志已变化，请重新选择会话')
        end=size if before is None else before
        cache_key=(str(path),stat.st_mtime_ns,size,end,limit)
        if cache_key in self.history_cache:
            result=copy.deepcopy(self.history_cache[cache_key]);result.update(observed_at=time.time(),**{
                k:v for k,v in self._read_log(row).items() if k in ('status','status_hint')})
            return result
        start=max(0,end-16*1024*1024);messages=[];calls=self._generation_calls(path,end,stat)
        with path.open('rb') as stream:
            stream.seek(start)
            if start:stream.readline(end-start)
            scan_start=stream.tell()
            while stream.tell()<end:
                position=stream.tell();line=stream.readline(end-position)
                if not line:break
                try:value=json.loads(line)
                except (ValueError,UnicodeError):continue
                message=self._public_message(value,position) or self._generated_message(value,position,calls)
                if message:messages.append(message)
        if len(messages)>limit:
            messages=messages[-limit:];cursor=int(messages[0]['id'])
        else:cursor=(scan_start if scan_start<end else start) if start else None
        state=self._read_log(row)
        result={'id':row['id'],'title':row['title'] or '未命名会话','messages':messages,
                'next_before':cursor if cursor else None,'scan_limited':start>0,
                'observed_at':time.time(),'status':state['status'],'status_hint':state['status_hint']}
        if len(self.history_cache)>=16:self.history_cache.clear()
        self.history_cache[cache_key]=copy.deepcopy(result)
        return result

    def _read_log(self, row):
        path=self._log_path(row)
        stat=path.stat()
        cache_key=(str(path),stat.st_mtime_ns,stat.st_size)
        cached=self.cache.get(row['id'])
        if cached and cached[0]==cache_key:
            result=dict(cached[1])
        else:
            events=[];status='unknown';end=min(stat.st_size,1024*1024);truncated=stat.st_size>end
            with path.open('rb') as f:
                f.seek(stat.st_size-end)
                if truncated:f.readline()
                for line in f:
                    try:v=json.loads(line)
                    except (ValueError,UnicodeError):continue
                    if not isinstance(v,dict):continue
                    p=v.get('payload')
                    if not isinstance(p,dict):continue
                    outer=v.get('type');kind=p.get('type');stamp=v.get('timestamp','')
                    if outer=='event_msg':
                        if kind=='task_started':status='running'
                        elif kind in ('task_complete','task_completed'):status='completed'
                        elif kind=='turn_aborted':status='interrupted'
                        elif kind=='task_failed':status='failed'
                    if outer=='response_item' and kind=='message' and p.get('role')=='assistant':
                        if p.get('phase') not in ('commentary','final','final_answer') and p.get('channel') not in ('commentary','final','final_answer'):continue
                        content=p.get('content',[])
                        if not isinstance(content,list):continue
                        text='\n'.join(x.get('text','') for x in content if isinstance(x,dict) and x.get('type')=='output_text' and isinstance(x.get('text'),str))
                        if text.strip():events.append({'kind':'message','text':text[:12000],'time':stamp})
                    elif outer=='response_item' and kind in ('custom_tool_call','function_call'):
                        tool=p.get('name')
                        if isinstance(tool,str):events.append({'kind':'tool','text':'工具调用：'+tool[:100],'time':stamp})
                    # Reasoning, raw command bodies, tool outputs and embedded data
                    # deliberately never enter the public Bot response.
            result={'status':status,'events':events[-60:],'truncated':truncated or len(events)>60}
            if len(self.cache)>40:self.cache.clear()
            self.cache[row['id']]=(cache_key,result)
            result=dict(result)
        if result['status']=='running' and time.time()-stat.st_mtime>120:
            result['status']='unconfirmed'
        hints={'running':'日志显示本轮已开始；非执行器实时状态','completed':'日志记录本轮已结束','interrupted':'日志记录本轮被中断','failed':'日志记录执行失败','unknown':'记录不足，无法确认当前状态','unconfirmed':'近期无日志更新，是否仍在执行待确认'}
        result['status_hint']=hints[result['status']]
        return result
