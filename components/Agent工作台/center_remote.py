"""Narrow paired-phone contract over the same desktop center; no second store."""
import base64,re,uuid
from agent_workflow import FORMATS
FIELDS={'center_bootstrap':set(),'center_get':{'id','history_limit'},'center_create':{'primary_id','reviewer_id','third_id'},'center_send':{'id','text','target','rounds'},'center_stop':{'id','turn_id'},'center_artifact':{'id','run_id','name'},'center_retry':{'id','turn_id','item'}}
FIELDS.update(center_results=set(),center_today=set(),center_prepare={'id','text','jobs'},
              center_draft={'id','text'},center_edit_plan={'id','turn_id','plan_revision','jobs'},
              center_confirm={'id','turn_id','plan_revision'},center_cancel_plan={'id','turn_id'},center_accept={'id','turn_id'})
FIELDS['center_manage']={'id','title','archived'}
FIELDS['center_retry']={'id','turn_id','item'}
READS={'center_results','center_today','center_bootstrap','center_get','center_artifact'}
REQUIRED={**{k:{'id'} for k in FIELDS},'center_bootstrap':set(),'center_results':set(),'center_create':{'primary_id','reviewer_id'},'center_send':{'id','text'},'center_artifact':{'id','run_id','name'},'center_retry':{'id','turn_id','item'},'center_prepare':{'id','text','jobs'},'center_confirm':{'id','turn_id'},'center_cancel_plan':{'id','turn_id'}}
JOB_FIELDS={'title','instruction','output_format','primary_id'}
REQUIRED.update(center_today=set(),center_draft={'id','text'},center_edit_plan=FIELDS['center_edit_plan'],center_accept=FIELDS['center_accept'])


def validate_jobs(jobs):
    if not isinstance(jobs,list) or not 1<=len(jobs)<=4:
        raise ValueError('分工需要 1 到 4 个子任务')
    for job in jobs:
        if not isinstance(job,dict) or set(job)!=JOB_FIELDS or not all(isinstance(v,str) for v in job.values()):
            raise ValueError('分工字段无效')
        if not 1<=len(job['title'].strip())<=60 or len(job['instruction'])>1000 or job['output_format'] not in FORMATS or not re.fullmatch('[a-f0-9]{32}',job['primary_id']):
            raise ValueError('请核对任务名称、负责人、交付格式和具体要求')


def fields(value,names):return {k:v for k,v in value.items() if k in names.split()}
def roles(value):return {s:fields(p,'id name model kind') for s,p in (value or {}).items() if s in ('A','B','C')}
def public_run(run):
    if not isinstance(run,dict):return None
    result=fields(run,'id status error call_count seconds_left');result['roles']=roles(run.get('roles'))
    for key in ('messages','steps'):
        result[key]=[fields(row,'id seat model stage state content error at usage') for row in run.get(key,[]) if row.get('seat') in ('U','A','B','C')]
    result['files']=[fields(f,'name size format') for f in run.get('files',[])]
    return result
def public_session(session,history_limit=12):
    result=fields(session,'id title status call_count call_limit error updated archived');result['roles']=roles(session.get('roles'));result['turns']=[]
    turns=session.get('turns',[]);result['history_omitted']=max(0,len(turns)-history_limit)
    for turn in turns[-history_limit:]:
        row=fields(turn,'id kind text state at error report call_count target discussion_rounds retry_label output_format drafted draft_reply draft_model plan_revision phase accepted_at');row['retry_of']=fields(turn.get('retry_of',{}),'turn_id item');row['failures']=[fields(f,'item label code title hint detail retryable blocked_reason') for f in turn.get('failures',[])];row['run']=public_run(turn.get('run'));row['jobs']=[]
        if turn.get('drafted') and turn['state']=='prepared':
            row['job_plan']=[fields(job,'title instruction output_format primary_id') for job in turn.get('job_plan') or []]
        for job in turn.get('jobs',[]):
            j=fields(job,'title state error instruction output_format');j['roles']=roles(job.get('roles'));j['run']=public_run(job.get('run'));row['jobs'].append(j)
        result['turns'].append(row)
    return result
def dispatch(gateway,action,p):
    call=gateway._call
    if action in ('center_create','center_send','center_manage','center_retry','center_prepare','center_draft') and call('api_center_bootstrap',{}).get('busy'):
        raise ValueError('center_busy')
    if action=='center_bootstrap':
        boot=call('api_center_bootstrap',{});ids={r['id'] for r in boot['profiles']};identities=call('api_center_identity_get',{})['items']
        return dict(version=1,task_handoff=True,dragon_planning=True,profiles=[dict(**fields(r,'id name model kind'),available=bool(r.get('has_key') or not r.get('requires_key',True))) for r in boot['profiles']],
                    sessions=[fields(r,'id title status call_count call_limit updated archived') for r in boot['sessions']],busy=boot['busy'],
                    identities={k:v for k,v in identities.items() if k in ids or k=='user'},appearance=fields(call('api_appearance_get',{}),'color_scheme chat_background background_strength'),call_limit=30)
    if action=='center_results':return results(call)
    if action=='center_today':
        from center_index import read_center
        index=read_center(gateway.data_dir,include_today=True)
        return dict(today=index['today'],partial=bool(index['warnings']))
    if action=='center_accept':return call('api_center_accept',{'id':p['id'],'turn_id':p['turn_id']})
    if action=='center_draft':return public_session(call('api_center_draft',dict(**p,request_id=uuid.uuid4().hex)))
    if action=='center_edit_plan':return public_session(call('api_center_edit_plan',p))
    if action=='center_get':return public_session(call('api_center_status',{'id':p['id']}),p.get('history_limit',12))
    if action=='center_retry':return public_session(call('api_center_retry',dict(**p,request_id=uuid.uuid4().hex)))
    if action=='center_manage':return public_session(call('api_center_manage',p))
    if action=='center_create':return public_session(call('api_center_create',p))
    if action=='center_send':return public_session(call('api_center_send',dict(**p,kind='chat',request_id=uuid.uuid4().hex)))
    if action=='center_prepare':
        session=call('api_center_status',{'id':p['id']})
        members={profile['id'] for profile in session['roles'].values()}
        if any(job['primary_id'] not in members for job in p['jobs']):
            raise ValueError('手机分工请从当前会话选择负责人')
        return public_session(call('api_center_send',dict(**p,kind='execute',request_id=uuid.uuid4().hex)))
    if action=='center_confirm':
        return public_session(call('api_center_confirm',{'id':p['id'],'request_id':p['turn_id'],**fields(p,'plan_revision')}))
    if action=='center_cancel_plan':
        return public_session(call('api_center_stop',{'id':p['id'],'prepared_id':p['turn_id']}))
    if action=='center_stop':return public_session(call('api_center_stop',p))
    if action=='center_artifact':
        session=call('api_center_status',{'id':p['id']});runs=[]
        for t in session.get('turns',[]):runs.extend([t.get('run')]+[j.get('run') for j in t.get('jobs',[])])
        run=next((r for r in runs if r and r.get('id')==p['run_id']),None)
        if not run or not any(f.get('name')==p['name'] for f in run.get('files',[])):raise ValueError('artifact_not_in_center')
        data=call('api_collaboration_file',{'id':run['id'],'name':p['name']});raw=base64.b64decode(data['content_base64'],validate=True)
        if data['name']!=p['name'] or not 0<len(raw)<=10*1024*1024:raise ValueError('artifact_size_limit')
        return dict(name=data['name'],size=len(raw),content_base64=data['content_base64'])
    raise ValueError('unknown_action')


def results(call):
    """Bounded read-only phone index. Registered files only; downloads revalidate membership."""
    rows=[s for s in call('api_center_bootstrap',{}).get('sessions',[]) if not s.get('archived')]
    items=[];warnings=[];limited=len(rows)>24
    for summary in rows[:24]:
        try:
            session=call('api_center_status',{'id':summary['id']})
            turns=session.get('turns',[]);limited=limited or len(turns)>60
            seen=set()
            for turn in turns[-60:]:
                runs=[(turn.get('run'),None)]+[(j.get('run'),j) for j in turn.get('jobs',[])[:4]]
                for run,job in runs:
                    if not run or not run.get('id') or run['id'] in seen:continue
                    seen.add(run['id']);owner=(run.get('roles') or {}).get('A') or {}
                    for file in run.get('files',[])[:12]:
                        name=file.get('name')
                        if not isinstance(name,str) or not name or len(name)>200 or '/' in name or chr(92) in name or name in ('.','..'):continue
                        if len(items)>=240:limited=True;break
                        items.append(dict(conversation_id=session['id'],conversation_title=str(session.get('title','群聊'))[:160],turn_id=turn['id'],run_id=run['id'],name=name,size=file.get('size',0),format=str(file.get('format',''))[:16],owner=str(owner.get('name','成员'))[:160],status=str(run.get('status','unknown'))[:40],job_title=str((job or {}).get('title',''))[:160]))
        except (ValueError,OSError,KeyError,TypeError,AttributeError):
            if not warnings:warnings.append('部分会话暂不可读，已保留可用成果，请回电脑核对。')
    return dict(items=items,warnings=warnings,limited=limited,scope='最近24个未归档群聊，每群最近60轮，最多240个登记文件。')
