"""Read-only center metadata shared by artifacts, overview and the butler.

No engine construction, recovery writes, prompts, provider settings or dispatch.
"""
from pathlib import Path
from datetime import date, datetime
import re
from session_store import SessionStore
from failure_recovery import failure_targets

ACTIVE={'starting','running','stopping'}
FILE_NAME=re.compile(r'协作成果-[a-f0-9]{16}\.(docx|xlsx|pptx|svg)')
def label(value,default=''):
    return value[:160] if isinstance(value,str) else default

def stamp(value):
    try:return datetime.fromisoformat(str(value).replace('Z','+00:00')).timestamp()
    except (ValueError,TypeError,OverflowError):return 0

def _registered_count(data, run):
    count=0
    root=data/'collaboration-artifacts'
    directory=root/run['id']
    if directory.resolve().parent!=root.resolve():
        return 0
    for file in run.get('files') or []:
        if not isinstance(file,dict) or not isinstance(file.get('name'),str) or not FILE_NAME.fullmatch(file['name']):
            continue
        path=directory/file['name']
        try:
            if path.is_file() and not path.is_symlink() and path.resolve().parent==directory.resolve() and 0<path.stat().st_size==file.get('size'):
                count+=1
        except OSError:
            continue
    return count

def review_delivery(data,turn):
    """Return only counts and a timestamp from finished task runs."""
    jobs=turn.get('jobs') or []
    if turn['state']!='completed' or (turn['kind']!='execute' and not jobs):
        return 0,False,0
    runs=[job.get('run') for job in jobs] if jobs else [turn.get('run')]
    runs=[run for run in runs if run and run.get('status')=='completed']
    count=sum(_registered_count(data,run) for run in runs)
    text=any(run.get('output_format','text')=='text' and any(
        step.get('state')=='completed' and str(step.get('content') or '').strip() for step in run.get('steps',[])
    ) for run in runs)
    return count,text,max([stamp(turn.get('at'))]+[stamp(run.get('updated')) for run in runs])

def center_task_link(data_dir,turn_id):
    """Resolve an exact task ID. Titles and display order play no role."""
    if not isinstance(turn_id,str) or not re.fullmatch('[a-f0-9]{32}',turn_id) or data_dir is None:
        raise ValueError('任务编号无效。')
    store=SessionStore(Path(data_dir)/'agent-center/conversations')
    target=None
    for summary in store.list():
        if summary['status']=='corrupt':
            continue
        try:
            session=store.load(summary['id'])
            turns=session.get('turns') or []
            turn=next((turn for turn in turns if turn.get('id')==turn_id and
                       (turn.get('kind')=='execute' or turn.get('jobs'))),None)
        except (OSError,ValueError,AttributeError,TypeError):
            continue
        if turn is None:
            continue
        if target is not None:
            raise ValueError('有多个相同任务编号，请在工作站核对。')
        target=dict(conversation_id=session['id'],turn_id=turn_id,
                    section='delivery' if turn.get('state')=='completed' else 'progress')
    if target is None:
        raise ValueError('原任务已不可用，请在工作站查看。')
    return target

def _today_row(data,session,turn):
    jobs=turn['jobs']
    if turn['kind']!='execute' and not jobs:
        return None
    status=turn['state']
    moment=stamp(turn.get('at'))
    if status=='prepared':
        group='prepared'
        count=0
    elif status in ACTIVE:
        group='active'
        count=0
    elif status=='completed':
        count,text_delivery,delivered_at=review_delivery(data,turn)
        accepted_at=stamp(turn.get('accepted_at'))
        group='accepted' if accepted_at else 'review'
        if not (accepted_at or count or text_delivery):
            return None
        moment=accepted_at or delivered_at
        if not moment or datetime.fromtimestamp(moment).date()!=date.today():
            return None
    else:
        return None
    job_title=label(jobs[0].get('title'),'搭档任务') if jobs else '搭档任务'
    return group,dict(conversation_id=session['id'],turn_id=turn['id'],
                      conversation_title=label(session['title']),title=job_title,
                      job_count=len(jobs) or 1,file_count=count,state=status,at=moment)

def read_center(data_dir,*,include_today=False):
    result=dict(rows=[],run_owners={},warnings=[],counts=dict(conversations=0,active=0,attention=0,deliveries=0),scope='最近100个搭档群聊；当前计数不含归档，成果为已登记文件')
    today={key:[] for key in ('prepared','active','review','accepted')}
    if include_today:result['today']={key:{'count':0,'items':[]} for key in today}
    if data_dir is None:return result
    data=Path(data_dir);store=SessionStore(data/'agent-center/conversations');cache={};identities={}
    try:
        from member_identity import IdentityStore
        identities=IdentityStore(data).get()['items']
    except ValueError:result['warnings'].append('成员显示资料暂不可读，使用原模型名称。')
    def load(base,identifier):
        key=(base,identifier)
        if key not in cache:cache[key]=SessionStore(data/base).load(identifier)
        return cache[key]
    for summary in store.list():
        partial=False
        try:
            session=store.load(summary['id']);turns=session['turns']
            if not isinstance(turns,list) or len(turns)>60 or not isinstance(session.get('roles'),dict):raise ValueError()
            if type(session.get('archived',False)) is not bool:raise ValueError()
            files=set();last_turn={};active=False;prepared=False
            hydrated=[]
            for source in turns:
                turn=dict(source);turn['jobs']=[dict(j) for j in source.get('jobs',[])];hydrated.append(turn)
                if len(turn['jobs'])>4:raise ValueError()
                references=[]
                if turn.get('run_id') and turn['kind'] in ('chat','discuss'):
                    references.append(('agent-center/negotiations' if turn['kind']=='chat' else 'agent-center/chats',turn['run_id'],turn,None))
                if turn['jobs']:
                    references.extend(('sessions',j['run_id'],j,j) for j in turn['jobs'] if j.get('run_id'))
                elif turn['kind']=='execute' and turn.get('run_id'):references.append(('sessions',turn['run_id'],turn,None))
                for base,rid,target,job in references:
                    try:
                        run=load(base,rid);target['run']=run
                        if turn['kind']=='discuss' or turn['kind']=='execute' and not turn['jobs']:
                            state=run['status']
                            if state=='idle':state='completed' if any(m.get('seat')=='U' for m in run.get('messages',[])) else 'interrupted'
                            turn.update(state=state,call_count=run.get('call_count',turn.get('call_count',0)),error=run.get('error',''))
                        if base!='sessions':continue
                        profile=(job or {}).get('roles',{}).get('A') or run.get('roles',{}).get('A') or {}
                        owner_name=label(identities.get(profile.get('id'),{}).get('nickname') or profile.get('name'),'模型')
                        info=dict(conversation_id=session['id'],conversation_title=session['title'],conversation_archived=session.get('archived',False),turn_id=turn['id'],run_id=rid,job_title=label((job or {}).get('title'),'结果') or '结果',owner_name=owner_name,owner_model=label(profile.get('model')),is_retry=bool(turn.get('retry_of')))
                        result['run_owners'].setdefault(rid,info)
                        metadata=run.get('files') or []
                        if not isinstance(metadata,list):raise ValueError()
                        for f in metadata:
                            if isinstance(f,dict) and isinstance(f.get('name'),str) and FILE_NAME.fullmatch(f['name']):files.add((rid,f['name']))
                    except (ValueError,OSError,KeyError,TypeError):partial=True
            last_turn=hydrated[-1] if hydrated else {}
            active=any(t['state'] in ACTIVE for t in hydrated)
            projected={**session,'turns':hydrated}
            # A failed attempt remains historical, but successful linked recovery resolves attention.
            def unresolved(turn,seen):
                if turn['id'] in seen:return True
                if turn['state']=='interrupted':return True
                if turn['state']!='failed':return False
                targets=failure_targets(projected,turn)
                if not targets:return True
                # A rejected draft never started work. Older attempts stay in the conversation.
                if turn['id']!=last_turn.get('id') and all(f['code']=='plan_rejected' for f in targets):
                    return False
                for f in targets:
                    origin=dict(turn_id=turn['id'],item=f['item'])
                    attempts=[t for t in hydrated if t.get('retry_of')==origin]
                    if not attempts:return True
                    attempt=attempts[-1]
                    if attempt['state'] in ACTIVE:continue
                    if attempt['state']=='completed':continue
                    if attempt['state']=='failed' and not unresolved(attempt,seen|{turn['id']}):continue
                    return True
                return False
            pending=[t for t in hydrated if t['state']=='prepared' or unresolved(t,set())]
            attention=partial or bool(pending)
            focused=next((t for t in reversed(hydrated) if t['state'] in ACTIVE),pending[-1] if pending else last_turn)
            state='running' if active else 'attention' if attention else last_turn.get('state','idle')
            row=dict(id=session['id'],title=session['title'],archived=session.get('archived',False),status=state,updated=session['updated'],at=stamp(session['updated']),turn_id=focused.get('id'),needs_attention=attention,call_count=sum(t.get('call_count',0) for t in hydrated),file_count=len(files),partial=partial,can_open=True)
            if include_today and not row['archived']:
                for turn in hydrated:
                    item=_today_row(data,session,turn)
                    if item:
                        group,record=item
                        today[group].append(record)
        except (OSError,ValueError,KeyError,TypeError,AttributeError):
            row=dict(id=summary['id'],title=summary['title'],archived=False,status='attention',updated=summary['updated'],at=stamp(summary['updated']),turn_id=None,call_count=0,file_count=0,partial=True,can_open=False);partial=True
        if partial:result['warnings'].append('部分搭档或子运行记录暂不可读，已保留可用记录；请回原会话核对。')
        result['rows'].append(row)
        if not row['archived']:
            c=result['counts'];c['conversations']+=1;c['active']+=int(row['status']=='running');c['attention']+=int(row.get('needs_attention',False) or row['partial']);c['deliveries']+=row['file_count']
    result['warnings']=list(dict.fromkeys(result['warnings']))
    if include_today:
        result['today']={key:{'count':len(rows),'items':sorted(rows,key=lambda row:row['at'],reverse=True)[:12]} for key,rows in today.items()}
    return result
