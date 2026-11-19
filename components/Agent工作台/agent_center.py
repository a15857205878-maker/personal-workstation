"""A continuous public conversation over the existing bounded model engines.

The center owns user turns and immutable references, not a second task engine.
No dispatch occurs during status reads or recovery.
"""
from copy import deepcopy
from pathlib import Path
import re,threading,uuid
from session_store import SessionStore,now
from seat_styles import styles_for
from group_members import member_keys,validate_target
from failure_recovery import failure_targets,retry_history
from chat_service import ChatService
from orchestrator import Orchestrator
from agent_workflow import AssignmentPreset,WorkflowRunner
from negotiated_chat import NegotiatedChat
from workbench_notices import publish_notice

ACTIVE=('starting','running','stopping')

def sync_draft_phase(turn):
    if not turn.get('drafted'):return
    if turn['state']=='prepared':turn['phase']='awaiting_confirmation'
    elif turn['state'] in ACTIVE:turn['phase']='working' if turn.get('job_plan') else 'planning'
    else:turn['phase']='finished'

def bounded_context(turns):
    entries=[];clipped=0
    def add(label,text):
        nonlocal clipped
        if len(text)>1800:clipped+=1
        entries.append(label+text[:1800]+('\n[内容过长，仅引用前1800字]' if len(text)>1800 else ''))
    for turn in turns:
        if turn['state']=='prepared':continue
        add('用户（'+turn['kind']+'）：\n',turn['text'])
        runs=([turn.get('run') or {}] if turn['kind']=='chat' else [])+([job.get('run') or {} for job in turn['jobs']] if turn.get('jobs') else ([] if turn['kind']=='chat' else [turn.get('run') or {}]))
        for run in runs:
            for row in run.get('messages' if 'messages' in run else 'steps',[]):
                if row.get('seat') not in ('A','B','C') or row.get('state')!='completed':continue
                add(f"{row['seat']}席 · {row.get('model','')} · {row.get('stage','讨论')}的公开回复：\n",row['content'])
            if run.get('files'):add('已生成文件（仅元数据）：\n','、'.join(f['name'] for f in run['files']))
        if turn.get('draft_reply'):add('龙娘拟分工回复：\n',turn['draft_reply'])
        if turn.get('report'):add('工作站实际执行汇报：\n',turn['report'])
    selected=[];size=0
    for entry in reversed(entries):
        if len(selected)>=12 or size+len(entry)>6000:break
        selected.append(entry);size+=len(entry)
    return list(reversed(selected)),len(entries)-len(selected)+clipped

class AgentCenter:
    def __init__(self,data_dir,profiles,client,gate,engine,lab=None):
        self.notice_path=Path(data_dir)/'pet-notices.json'
        self.sessions=SessionStore(Path(data_dir)/'agent-center/conversations',summary_fields=('archived',))
        self.chat=ChatService(data_dir,profiles,client,gate,session_dir=Path(data_dir)/'agent-center/chats',allow_third=True)
        self.profiles=profiles;self.gate=gate;self.engine=engine;self.lock=threading.RLock()
        self.preset=AssignmentPreset(data_dir,profiles);self.workflow=WorkflowRunner(engine,gate,self._workflow_update)
        if lab:self.chat.memory=lab.memory
        self.agent=NegotiatedChat(data_dir,profiles,client,gate,engine,self.chat.memory,self._agent_update,self._workflow_update)
        self.chat.memory_sources=[self.chat.sessions,self.agent.chat.sessions]+([lab.sessions] if lab else [])
        for summary in self.sessions.list():
            if summary['status']=='corrupt':continue
            session=self.sessions.load(summary['id']);interrupted=[];jobs_changed=False
            for turn in session['turns']:
                if (turn['state']=='starting' and not turn.get('run_id')) or ((turn.get('jobs') or turn.get('drafted') or turn['kind']=='chat') and turn['state'] in ACTIVE):
                    turn.update(state='interrupted',error='上次启动结果未确认，未自动重发')
                    interrupted.append(turn)
                if turn['state']!='interrupted':continue
                for job in turn.get('jobs',[]):
                    if job.get('run_id'):continue
                    if job['state']=='queued':
                        job.update(state='skipped',error='上次运行中断，此子任务未发送')
                        jobs_changed=True
                    elif job['state']=='starting':
                        job.update(state='interrupted',error='上次子任务启动结果未确认')
                        jobs_changed=True
            if interrupted or jobs_changed:
                self._save(session)
                for turn in interrupted:
                    if turn['kind']=='execute' or turn.get('jobs'):
                        self._notice(turn)
    def _notice(self,turn):
        publish_notice(self.notice_path,'center',turn['id'],turn['state'])
    def busy(self):return self.chat.busy() or self.workflow.busy() or self.agent.busy()
    def stop_all(self,reason='用户关闭窗口'):
        if self.chat.busy():self.chat.stop(reason)
        if self.workflow.busy():self.workflow.stop(reason)
        if self.agent.busy():self.agent.stop(reason)
    def call(self,action,payload):
        with self.lock:
            if action in ('api_center_memory','api_center_memory_save','api_center_memory_delete','api_center_memory_clear'):return self.chat.call(action.replace('api_center_','api_chat_'),payload)
            if action=='api_center_bootstrap':
                preset=None;error=''
                try:preset=self.preset.read()
                except (OSError,ValueError):error='分工预设无法读取，原文件保留；可重新填写并显式保存。'
                return dict(profiles=self.profiles.list(),sessions=self.sessions.list(),busy=self.gate.locked(),call_limit=30,preset=preset,preset_error=error,context_limits=dict(characters=6000,entries=12,entry_characters=1800))
            if action=='api_center_preset_save':return self.preset.save(payload)
            if action=='api_center_create':return self.create(payload)
            if action=='api_center_manage':return self.manage(payload)
            if action=='api_center_retry':return self.retry(payload)
            if action=='api_center_status':return self.status(payload.get('id'))
            if action=='api_center_send':return self.send(payload)
            if action=='api_center_draft':
                if set(payload)!={'id','text','request_id'}:raise ValueError('拟分工参数无效')
                return self.send({**payload,'kind':'execute'},drafting=True)
            if action=='api_center_edit_plan':return self.edit_plan(payload)
            if action=='api_center_confirm':return self.confirm(payload)
            if action=='api_center_accept':return self.accept(payload)
            if action=='api_center_stop':return self.stop(payload)
            raise ValueError('不支持的协作中心操作')
    def create(self,payload):
        if not self.gate.acquire(blocking=False):raise ValueError('已有模型正在运行，请等待或停止后再新建')
        try:
            available={p['id']:p for p in self.profiles.list()};roles={}
            for seat,key in member_keys(payload):
                if payload.get(key) not in available:raise ValueError('请选择已保存的模型配置')
                roles[seat]=available[payload[key]]
            session=dict(id=uuid.uuid4().hex,title='新的协作',status='idle',updated=now(),started=now(),roles=roles,
                         seat_styles=styles_for(payload,seats=tuple(roles)),turns=[],steps=[],call_count=0,call_limit=30,error='')
            self.sessions.save(session);return session
        finally:self.gate.release()
    def _snapshot(self,identifier):
        session=self.sessions.load(identifier);changed=False
        for turn in session['turns']:
            if turn.get('drafted') and turn.get('planning_run_id') and not turn.get('negotiation_calls'):
                try:
                    service=self.agent.chat
                    run_id=turn['planning_run_id']
                    run=service.status(run_id) if service.busy() and service.run and service.run['id']==run_id else service.sessions.load(run_id)
                    if run['call_count']:
                        turn['negotiation_calls']=run['call_count'];changed=True
                except (OSError,ValueError):
                    pass
            if turn['kind']=='chat' and turn.get('run_id'):
                try:
                    service=self.agent.chat
                    run=service.status(turn['run_id']) if service.busy() and service.run and service.run['id']==turn['run_id'] else service.sessions.load(turn['run_id'])
                    turn['run']=run
                    if turn.get('negotiation_calls',0)!=run['call_count']:turn['negotiation_calls']=run['call_count'];changed=True
                except (OSError,ValueError):turn.update(state='interrupted',error='协商记录不可用，未自动重发');changed=True
            if turn.get('jobs'):
                for job in turn['jobs']:
                    if not job.get('run_id'):continue
                    try:
                        service=self.agent.workflow.engine if turn['kind']=='chat' else self.workflow.engine
                        run=service.status(job['run_id']) if service.busy() and service.run and service.run['id']==job['run_id'] else service.sessions.load(job['run_id'])
                        job['run']=run
                        if (job['state'],job.get('call_count',0))!=(run['status'],run['call_count']):job.update(state=run['status'],call_count=run['call_count']);changed=True
                    except (OSError,ValueError):
                        job.update(state='interrupted',error='原运行记录不可用，未自动重发')
                        turn.update(state='interrupted',error='部分子任务记录不可用，未自动重发');changed=True
                count=sum(j.get('call_count',0) for j in turn['jobs'])+turn.get('negotiation_calls',0)
                if turn.get('call_count',0)!=count:turn['call_count']=count;changed=True
                continue
            if turn['kind']=='chat' or turn.get('drafted'):
                if turn.get('call_count',0)!=turn.get('negotiation_calls',0):turn['call_count']=turn.get('negotiation_calls',0);changed=True
                continue
            if not turn.get('run_id'):continue
            service=self.chat if turn['kind']=='discuss' else self.engine
            try:
                run=service.status(turn['run_id']) if service.busy() and service.run and service.run['id']==turn['run_id'] else service.sessions.load(turn['run_id'])
                state=run['status'];count=run['call_count'];error=run.get('error','')
                if state=='idle':
                    state='completed' if any(m.get('seat')=='U' for m in run.get('messages',[])) else 'interrupted'
                turn['run']=run
            except (OSError,ValueError):
                state='interrupted';count=turn.get('call_count',0);error='原运行记录不可用，未自动重发'
            if (turn['state'],turn.get('call_count',0),turn.get('error',''))!=(state,count,error):
                turn.update(state=state,call_count=count,error=error);changed=True
        count=sum(t.get('call_count',0) for t in session['turns'])
        state=next((t['state'] for t in reversed(session['turns']) if t['state'] in (*ACTIVE,'prepared')),'idle')
        if session['call_count']!=count or session['status']!=state:session.update(call_count=count,status=state);changed=True
        if changed:self._save(session)
        for turn in session['turns']:
            sync_draft_phase(turn)
            turn['failures']=failure_targets(session,turn)
        return session
    def accept(self,payload):
        if not isinstance(payload,dict) or set(payload)!={'id','turn_id'} or not isinstance(payload['turn_id'],str) or not re.fullmatch('[a-f0-9]{32}',payload['turn_id']):
            raise ValueError('验收任务编号无效。')
        from center_index import review_delivery
        session=self._snapshot(payload['id'])
        turn=next((item for item in session['turns'] if item['id']==payload['turn_id']),None)
        if not turn or session.get('archived'):
            raise ValueError('任务已不可验收，请刷新今日事务。')
        if not turn.get('accepted_at'):
            count,text,_=review_delivery(self.notice_path.parent,turn)
            if not count and not text:
                raise ValueError('这项任务还没有可验收的交付。')
            turn['accepted_at']=now()
            self._save(session)
        publish_notice(self.notice_path,'center',turn['id'],'accepted')
        return dict(conversation_id=session['id'],turn_id=turn['id'],accepted_at=turn['accepted_at'])

    def retry(self,payload):
        if not isinstance(payload,dict) or set(payload)!={'id','turn_id','item','request_id'}:raise ValueError('重试参数无效')
        request=payload['request_id']
        if not isinstance(request,str) or not re.fullmatch('[a-f0-9]{32}',request):raise ValueError('重试编号无效')
        session=self._snapshot(payload['id']);source=next((t for t in session['turns'] if t['id']==payload['turn_id']),None)
        origin=dict(turn_id=payload['turn_id'],item=payload['item'])
        previous=next((t for t in session['turns'] if t['id']==request),None)
        if previous:
            if previous.get('retry_of')!=origin:raise ValueError('重试编号已用于其他内容')
            return session
        if session.get('archived') or session['status'] in (*ACTIVE,'prepared') or self.gate.locked():raise ValueError('请先恢复会话或结束当前操作')
        if len(session['turns'])>=60 or session['call_count']>=session['call_limit']:raise ValueError('本会话已达上限，请新建会话')
        target=next((f for f in (source or {}).get('failures',[]) if f['item']==payload['item'] and f['retryable']),None)
        if not target:raise ValueError('此项没有可重试的明确失败记录，或已有重试，请核对后续记录')
        retry_history(session['turns'],origin)
        self._check_roles(session)
        turn=dict(id=request,kind='discuss',text=source['text'],output_format='text',job_plan=None,target='A',discussion_rounds=1,execution_mode='direct',state='prepared',at=now(),call_count=0,run_id=None,error='',retry_of=origin,retry_label=target['label'])
        if payload['item'].startswith('message:'):
            row=next(m for m in source['run']['messages'] if 'message:'+m['id']==payload['item']);turn['target']=row['seat']
        else:
            job=source['jobs'][int(payload['item'][4:])] if payload['item'].startswith('job:') else dict(title='结果',instruction='',output_format=source['output_format'],primary_id=source['run']['roles']['A']['id'],roles={'A':source['run']['roles']['A']})
            self._check_roles(session,list(job['roles'].values()))
            plan=self.preset.validate([job])[0]
            turn.update(kind='execute',jobs=[dict(**plan,roles=deepcopy(job['roles']),state='queued',run_id=None,call_count=0)],job_plan=[plan])
            Orchestrator.validate(dict(task=turn['text']+'\n\n当前子任务：'+job['title']+'\n'+job['instruction'],output_format=job['output_format'],rounds=1,call_limit=1),direct=True)
        session['turns'].append(turn);self._save(session);self._launch(session,turn)
        return self._snapshot(session['id'])
    def manage(self,payload):
        if not isinstance(payload,dict) or 'id' not in payload or not 2<=len(payload)<=3 or set(payload)-{'id','title','archived'}:
            raise ValueError('会话管理参数无效')
        if 'title' in payload:
            title=payload['title']
            if not isinstance(title,str) or not 1<=len(title.strip())<=60 or any(ord(c)<32 or ord(c)==127 for c in title):raise ValueError('会话名称请输入1–60字，不含换行')
        if 'archived' in payload and type(payload['archived']) is not bool:raise ValueError('归档状态无效')
        if not self.gate.acquire(blocking=False):raise ValueError('有模型正在运行，请结束后管理会话')
        try:
            session=self._snapshot(payload['id'])
            if session['status'] in (*ACTIVE,'prepared'):raise ValueError('请先结束当前回复或处理待确认分工')
            if 'title' in payload:session.update(title=payload['title'].strip(),custom_title=True)
            if 'archived' in payload:session['archived']=payload['archived']
            self._save(session);return session
        finally:self.gate.release()
    def _save(self,session):
        value=deepcopy(session)
        for turn in value['turns']:
            sync_draft_phase(turn)
            turn.pop('failures',None)
            turn.pop('run',None)
            for job in turn.get('jobs',[]):job.pop('run',None)
        self.sessions.save(value)
    def status(self,identifier):return self._snapshot(identifier)
    def _check_roles(self,session,extra=()):
        available={p['id']:p for p in self.profiles.list()}
        for role in [*session['roles'].values(),*extra]:
            current=available.get(role['id'])
            if current is None or any(current[k]!=role[k] for k in ('kind','model','base_url')):
                raise ValueError('此对话的模型配置已改变，请新建协作以保留真实模型身份')
    def _queued_jobs(self,plan,text):
        available={p['id']:p for p in self.profiles.list()}
        for job in plan:
            Orchestrator.validate(dict(task=text+'\n\n当前子任务：'+job['title']+'\n'+job['instruction'],output_format=job['output_format'],rounds=1,call_limit=1),direct=True)
        return [dict(**job,state='queued',run_id=None,call_count=0,roles={'A':available[job['primary_id']]}) for job in plan]

    def send(self,payload,*,drafting=False):
        session=self._snapshot(payload.get('id'));kind=payload.get('kind');text=payload.get('text');request=payload.get('request_id')
        if kind not in ('chat','discuss','execute'):raise ValueError('请选择聊天、只讨论或指定分工')
        if not isinstance(text,str) or not 1<=len(text.strip())<=(8000 if kind=='execute' else 4000):raise ValueError('聊天限4000字，指定执行限8000字，内容不能为空')
        if not isinstance(request,str) or not re.fullmatch('[a-f0-9]{32}',request):raise ValueError('提交标识无效')
        output=payload.get('output_format','text') if kind=='execute' else 'text'
        jobs=self.preset.validate(payload['jobs']) if kind=='execute' and 'jobs' in payload else None
        target='A' if drafting else payload.get('target',''.join(session['roles'])) if kind in ('chat','discuss') else 'AB';rounds=payload.get('rounds',1) if kind in ('chat','discuss') else 1
        validate_target(target,session['roles'],rounds)
        signature=dict(kind=kind,text=text.strip(),output_format=output,job_plan=jobs,target=target,discussion_rounds=rounds)
        previous=next((t for t in session['turns'] if t['id']==request),None)
        if previous:
            if bool(previous.get('drafted'))!=drafting or any(previous.get(k)!=v for k,v in signature.items() if not drafting or k!='job_plan'):raise ValueError('提交标识已使用，请重新发送')
            return session
        if session['status'] in (*ACTIVE,'prepared'):raise ValueError('请先处理当前回复或待确认的任务')
        if session.get('archived'):raise ValueError('会话已归档，请先在会话管理中恢复')
        if self.gate.locked():raise ValueError('其他模型操作正在进行，请稍后发送')
        if len(session['turns'])>=60:raise ValueError('本对话已达60条输入，请新建协作')
        self._check_roles(session)
        required=2 if drafting else len(target)*rounds if kind in ('chat','discuss') else len(jobs or [1])
        if session['call_count']+required>session['call_limit']:raise ValueError('本对话剩余调用次数不足，请新建协作')
        if kind=='execute':Orchestrator.validate(dict(task=text,output_format=output,rounds=1,call_limit=1),direct=True)
        turn=dict(id=request,**signature,execution_mode='direct',state='prepared',at=now(),call_count=0,run_id=None,error='')
        if drafting:turn.update(drafted=True,phase='planning')
        if jobs:
            turn['jobs']=self._queued_jobs(jobs,text.strip())
        session['turns'].append(turn)
        if session['title']=='新的协作' and not session.get('custom_title'):session['title']=text.strip()[:45]
        if drafting or kind in ('chat','discuss'):self._launch(session,turn,drafting=drafting)
        else:
            self._save(session);self._notice(turn)
        return self._snapshot(session['id'])
    def _check_plan_revision(self,turn,payload):
        if turn.get('drafted') and (type(payload.get('plan_revision')) is not int or payload['plan_revision']!=turn.get('plan_revision')):
            raise ValueError('分工已更新，请刷新并核对最新草案。')

    def edit_plan(self,payload):
        if set(payload)!={'id','turn_id','jobs','plan_revision'}:raise ValueError('修改分工参数无效')
        session=self._snapshot(payload['id'])
        turn=next((item for item in session['turns'] if item['id']==payload['turn_id']),None)
        if not turn or not turn.get('drafted') or turn['state']!='prepared' or session.get('archived'):
            raise ValueError('该草案已不可修改，请刷新核对。')
        self._check_plan_revision(turn,payload)
        plan=self.preset.validate(payload['jobs'])
        if session['call_count']+len(plan)>session['call_limit']:raise ValueError('剩余调用次数不足，请减少子任务。')
        if plan!=turn['job_plan']:
            turn.update(job_plan=plan,jobs=self._queued_jobs(plan,turn['text']),plan_revision=turn['plan_revision']+1)
            self._save(session)
        return self._snapshot(session['id'])

    def confirm(self,payload):
        session=self._snapshot(payload.get('id'))
        turn=next((t for t in session['turns'] if t['id']==payload.get('request_id')),None)
        if turn is None or turn['kind']!='execute':raise ValueError('待确认任务不存在')
        if turn['state']!='prepared':return session
        self._check_plan_revision(turn,payload)
        if self.gate.locked():raise ValueError('其他模型操作正在进行，请稍后确认')
        self._check_roles(session,[role for job in turn.get('jobs',[]) for role in job['roles'].values()])
        if session['call_count']+len(turn.get('jobs') or [1])>session['call_limit']:raise ValueError('剩余调用次数不足，请新建协作')
        self._launch(session,turn);return self._snapshot(session['id'])
    def _launch(self,session,turn,*,drafting=False):
        history=session['turns'][:-1]
        if turn.get('retry_of'):history=retry_history(history,turn['retry_of'])
        context,omitted=bounded_context(history)
        turn.update(state='starting',context_omitted=omitted);session['status']='starting';self._save(session)
        if turn['kind']=='execute':self._notice(turn)
        config={key:session['roles'][seat]['id'] for seat,key in member_keys({'third_id':session['roles'].get('C')})};config['seat_styles']=session['seat_styles']
        try:
            if drafting or turn['kind']=='chat':
                try:preset=self.preset.read()
                except (OSError,ValueError):preset=None
                self.agent.start(session,turn,context,preset);return
            elif turn.get('jobs'):
                self.workflow.start(session,turn,context);return
            elif turn['kind']=='discuss':
                chat=self.chat.create(config)
                # Persist ownership before invoking: a crash can never lose a submitted run reference.
                turn['run_id']=chat['id'];self._save(session)
                run=self.chat.send(dict(id=chat['id'],text=turn['text'],target=turn.get('target','AB')),rounds=turn.get('discussion_rounds',1),reference_context=context,concise=True)
            else:
                config.pop('third_id',None)
                config['seat_styles']={s:session['seat_styles'][s] for s in ('A','B')}
                run=self.engine.start(dict(**config,task=turn['text'],output_format=turn['output_format'],rounds=1,call_limit=1,max_tokens=4096,context_count=0),context,direct=True,center_turn_id=turn['id'])
                turn['run_id']=run['id']
            turn.update(state=run['status'],call_count=run['call_count']);self._save(session)
        except Exception:
            turn.update(state='failed',error='启动未完成，请检查连接；本条不会自动重发');self._save(session)
            if turn['kind']=='execute':self._notice(turn)
            raise
    def stop(self,payload):
        session=self._snapshot(payload.get('id'))
        prepared_id=payload.get('prepared_id')
        turn_id=payload.get('turn_id')
        turns=session['turns']
        if prepared_id is not None:
            turns=[t for t in turns if t['id']==prepared_id and t['state']=='prepared' and t['kind']=='execute']
        elif turn_id is not None:
            turns=[t for t in turns if t['id']==turn_id and t['state'] in ACTIVE]
        if not turns:return session
        cancelled_plans=[]
        for turn in turns:
            if turn['state']=='prepared':
                turn.update(state='cancelled',error='已取消草案，未执行子任务' if turn.get('drafted') else '已取消，未调用模型')
                cancelled_plans.append(turn)
                for job in turn.get('jobs',[]):job.update(state='skipped',error='已取消，未发送')
            elif turn['state'] in ACTIVE:
                if (turn['kind']=='chat' or turn.get('drafted')) and self.agent.active_id==turn['id'] and self.agent.busy():
                    self.agent.stop();turn['state']='stopping';continue
                if turn.get('jobs') and self.workflow.active_id==turn['id']:
                    self.workflow.stop();turn['state']='stopping';continue
                service=self.chat if turn['kind']=='discuss' else self.engine
                if service.run and service.run['id']==turn.get('run_id'):service.stop()
        self._save(session)
        for turn in cancelled_plans:self._notice(turn)
        return self._snapshot(session['id'])
    def _workflow_update(self,identifier,turn_id,index,update,state,error):
        with self.lock:
            session=self.sessions.load(identifier);turn=next(t for t in session['turns'] if t['id']==turn_id)
            if index is not None:
                turn['jobs'][index].update(update)
                if index==0 and update.get('run_id') and turn['kind']!='chat':turn['run_id']=update['run_id']
            if state:
                turn.update(state=state,error=error)
                for job in turn['jobs']:
                    if job['state'] in ('queued','starting'):job.update(state='skipped',error='此前步骤未完成，未发送')
            else:turn['state']='stopping' if (self.agent.workflow if turn['kind']=='chat' else self.workflow).cancel.is_set() else 'running'
            if turn['kind']=='chat' and state:turn['state']='running'  # Parent still owns gate and must build the actual report.
            turn['call_count']=sum(j.get('call_count',0) for j in turn['jobs'])+turn.get('negotiation_calls',0)
            session['call_count']=sum(t.get('call_count',0) for t in session['turns']);session['status']='idle' if state else turn['state']
            self._save(session)
            if state and turn['kind']!='chat':self._notice(turn)
    def _agent_update(self,identifier,turn_id,patch):
        with self.lock:
            session=self.sessions.load(identifier);turn=next(t for t in session['turns'] if t['id']==turn_id)
            build=patch.pop('build_report',False)
            if turn.get('drafted'):
                if 'run_id' in patch:patch['planning_run_id']=patch.pop('run_id')
                if turn['state']=='stopping' and patch.get('state') in ('prepared','completed'):
                    patch=dict(state='cancelled',phase='finished',error='已停止拟分工',negotiation_calls=patch['negotiation_calls'])
                elif turn['state']=='stopping' and patch.get('state')=='running':
                    patch['state']='stopping'
            turn.update(patch)
            if build:
                lines=['本轮执行回报（工作站实际回执）：']
                for job in turn.get('jobs',[]):
                    names=[]
                    if job.get('run_id'):
                        try:
                            run=self.engine.sessions.load(job['run_id']);job.update(state=run['status'],call_count=run['call_count']);names=[f['name'] for f in run.get('files',[])]
                        except (OSError,ValueError):job['state']='interrupted'
                    label={'completed':'已完成','failed':'失败','cancelled':'已取消','skipped':'未执行','queued':'未执行','starting':'未确认启动','interrupted':'记录不可用'}.get(job['state'],'未完成')
                    lines.append(job['title']+'：'+label+('；文件：'+'、'.join(names) if names else '；无已验证文件'))
                turn['report']='\n'.join(lines)
            turn['call_count']=turn.get('negotiation_calls',0)+sum(j.get('call_count',0) for j in turn.get('jobs',[]))
            session['call_count']=sum(t.get('call_count',0) for t in session['turns']);session['status']=turn['state'] if turn['state'] in (*ACTIVE,'prepared') else 'idle'
            self._save(session)
            if 'state' in patch and (turn.get('jobs') or turn.get('drafted') and turn['state']=='failed') and turn['state'] not in ACTIVE:self._notice(turn)
