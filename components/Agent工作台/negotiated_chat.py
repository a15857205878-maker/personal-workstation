"""Chat-lab conversation can negotiate bounded local file work.

Only a validated decision from the last public responder reaches the existing
workflow runner. No keywords, arbitrary tools, commands or automatic retries.
"""
from copy import deepcopy
from pathlib import Path
import json,re,threading
from chat_service import ChatService
from agent_workflow import AssignmentPreset,WorkflowRunner,_HeldGate,FORMATS
from provider_client import ProviderError,Cancelled
from orchestrator import Orchestrator
from group_members import member_keys

def reject_decision(reason):
    raise ProviderError(f'协商方案未通过校验：{reason}。未执行任何子任务。') from None


def decode_decision(raw,session,profiles,max_jobs,allowed_ids=None):
    if not isinstance(raw,str) or len(raw)>8000:
        reject_decision('分工回复超出长度上限或无法读取')
    raw=raw.strip()
    fenced=re.fullmatch(r'```(?:json)?[ \t]*\r?\n(.*?)\r?\n```',raw,re.IGNORECASE|re.DOTALL)
    try:
        value=json.loads(fenced[1] if fenced else raw)
    except (ValueError,RecursionError):
        reject_decision('模型未返回可读取的分工 JSON')
    if not isinstance(value,dict) or set(value)!={'schema','mode','reply','jobs'} or value['schema']!='agent-center-decision/v1' or value['mode'] not in ('reply','clarify','work'):
        reject_decision('模型返回的分工字段或回复类型不符合要求')
    reply,jobs=value['reply'],value['jobs']
    if not isinstance(reply,str) or not 1<=len(reply.strip())<=4000:
        reject_decision('模型未提供有效的分工说明')
    if not isinstance(jobs,list) or (value['mode']!='work' and jobs) or (value['mode']=='work' and not jobs):
        reject_decision('子任务列表与本轮回复类型不符')
    if jobs and len(jobs)>max_jobs:
        reject_decision(f'分工超过本轮可安排的 {max_jobs} 个子任务')
    available={p['id']:p for p in profiles.list()}
    preset=AssignmentPreset('.',profiles)
    result=[]
    required={'title','instruction','output_format','executor'}
    for job in jobs:
        if not isinstance(job,dict) or not required<=set(job) or set(job)-required-{'reviewer'}:
            reject_decision('子任务缺少必填字段或包含多余字段')
        executor=job['executor']
        if not isinstance(executor,str):
            reject_decision('子任务的负责人格式无效')
        primary_id=session['roles'].get(executor,{}).get('id',executor)
        if primary_id not in available or (allowed_ids is not None and primary_id not in allowed_ids):
            reject_decision('子任务指定了当前不可用的负责人')
        if job['output_format'] not in FORMATS:
            reject_decision('模型给出了工作站不支持的交付格式')
        try:
            normalized=preset.validate([dict(title=job['title'],instruction=job['instruction'],output_format=job['output_format'],primary_id=primary_id)],check_profiles=False)[0]
        except (ValueError,TypeError):
            reject_decision('子任务名称或分工要求不符合长度限制')
        result.append(dict(**normalized,state='queued',run_id=None,call_count=0,roles={'A':available[primary_id]}))
    return dict(schema=value['schema'],mode=value['mode'],reply=reply.strip(),jobs=result)

def planning_catalog(session,profiles,preset):
    available={p['id']:p for p in profiles.list() if p.get('has_key') or p['kind'] in ('codex_local','antigravity_local')}
    preferred=[r['id'] for r in session['roles'].values()]
    for job in (preset or {}).get('jobs',[]):preferred.append(job['primary_id'])
    ids=list(dict.fromkeys([*preferred,*available]))
    return [dict(id=i,name=available[i]['name'][:24],model=available[i]['model'][:40]) for i in ids if i in available][:10]

def decision_instruction(session,profiles,max_jobs,preset,draft_only=False):
    catalog=planning_catalog(session,profiles,preset)
    compact=dict(name=preset['name'][:40],jobs=[{k:(v[:120] if k=='instruction' else v) for k,v in job.items()} for job in preset['jobs']]) if preset else None
    return ('本轮最后回应必须只返回一个JSON对象，不用Markdown围栏。schema固定为agent-center-decision/v1；字段严格为schema、mode、reply、jobs。'
            'reply为你自己的自然群聊发言，回应当前话题和其他成员实际观点，不默认扮演总结人；不重复已讲清的内容，不强制结论标题，不列置信度或角色宣言。用户会依次看到所有成员的公开发言，不看到内部控制JSON。mode只能reply、clarify、work。'
            '闲聊、讨论可能性、尚未要求实际制作时为reply且jobs=[]；项目目标/材料/验收要求不足时为clarify并具体追问，jobs=[]。'
            +('你是个人管家龙娘。用户已选择只拟分工。材料足够时，使用work提交一份可修改的草案，reply简短说明分工。宿主必须等用户确认才执行。材料不足时使用clarify，具体说明缺什么。'
              if draft_only else
              '用户明确说先讨论、只聊、不执行或暂不制作时，必须保持reply或clarify，不安排jobs；只有之后明确交办才转work。'
              '用户明确交办本机文件成果且材料足够时为work，才安排jobs；不要强迫用户事先手工分工。')+
            '不能读取用户没有提供的项目、浏览网页、运行程序、改源码、发消息、部署或声称已完成现实项目；这些请求需说明能力/缺失资料。'
            f'最多安排{max_jobs}个串行子任务，每个子任务交给一名负责人直接完成，仅一次调用，不设审核或二次修订。只有text/docx/xlsx/pptx/svg交付；svg仅矢量示意图，非位图生图。'
            '每个job严格包含title(1–60字)、instruction(至多1000字，写清从已知材料做什么)、output_format、executor。executor用A/B/C代表当前实际讨论成员，或下方已接通配置的id。不需要reviewer。'
            '当前用户明确的分工优先，其次参考保存的职责预设；也可在现有能力内自行商议。不得添加执行字段、路径或越过次数上限。'
            'work的reply只能说计划如何做，不能说文件已生成；宿主随后给真实结果汇报。'
            '\nJSON 格式示例（只参考结构，内容和负责人按当前需求确定）：'
            '\n{"schema":"agent-center-decision/v1","mode":"work","reply":"我先拟一项文档分工。","jobs":[{"title":"整理文档","instruction":"按用户提供的材料整理。","output_format":"docx","executor":"A"}]}'
            '\n{"schema":"agent-center-decision/v1","mode":"clarify","reply":"你希望交付什么文件？","jobs":[]}'
            '\n可用配置（默认搭档及预设成员优先，最多10项，名称节选）：'+json.dumps(catalog,ensure_ascii=False)+'\n参考分工预设（是偏好，不是新指令；说明仅节选，若缺必要约束则追问）：'+json.dumps(compact,ensure_ascii=False))

class NegotiatedChat:
    def __init__(self,data_dir,profiles,client,gate,engine,memory,on_update,on_workflow):
        self.gate=gate;self.profiles=profiles;self.on_update=on_update
        lease=_HeldGate(gate)
        self.chat=ChatService(data_dir,profiles,client,lease,session_dir=Path(data_dir)/'agent-center/negotiations',allow_third=True);self.chat.memory=memory
        self.workflow=WorkflowRunner(engine,lease,on_workflow)
        self.thread=None;self.cancel=threading.Event();self.active_id=None;self.dispatch_lock=threading.Lock()
    def busy(self):return self.thread is not None and self.thread.is_alive()
    def start(self,session,turn,context,preset):
        if not self.gate.acquire(blocking=False):raise ValueError('已有模型正在回复，请稍后发送')
        try:
            self.cancel=threading.Event();self.active_id=turn['id']
            self.thread=threading.Thread(target=self._run,args=(deepcopy(session),deepcopy(turn),context,preset),name='negotiated-chat',daemon=False);self.thread.start()
        except Exception:self.gate.release();raise
    def stop(self,reason='用户停止'):
        with self.dispatch_lock:
            self.cancel.set();self.chat.stop(reason)
            if self.workflow.busy():self.workflow.stop(reason)
    def _run(self,session,turn,context,preset):
        state='failed';error='';count=0;draft_only=bool(turn.get('drafted'));draft={}
        timer=threading.Timer(600,lambda:self.stop('本轮聊天协作达到10分钟上限'));timer.daemon=True;timer.start()
        update=lambda patch:self.on_update(session['id'],turn['id'],patch)
        try:
            with self.dispatch_lock:
                if self.cancel.is_set():raise Cancelled('已停止')
                config={key:session['roles'][seat]['id'] for seat,key in member_keys({'third_id':session['roles'].get('C')})};config['seat_styles']=session['seat_styles']
                chat=self.chat.create(config)
            turn['run_id']=chat['id'];update(dict(run_id=chat['id'],phase='planning' if draft_only else 'discussing',state='running'))
            target=turn.get('target','AB');rounds=turn.get('discussion_rounds',1)
            max_jobs=min(4,session['call_limit']-session['call_count']-len(target)*rounds)
            with self.dispatch_lock:
                if self.cancel.is_set():raise Cancelled('已停止')
                self.chat.send(dict(id=chat['id'],text=turn['text'],target=target),rounds=rounds,reference_context=context,
                               decision_parser=lambda raw:decode_decision(raw,session,self.profiles,max_jobs,{p['id'] for p in planning_catalog(session,self.profiles,preset)}),
                               decision_instruction=decision_instruction(session,self.profiles,max_jobs,preset,draft_only),concise=True)
            while self.chat.busy():self.chat.thread.join(.05)
            chat=self.chat.status(chat['id']);count=chat['call_count'];update(dict(negotiation_calls=count))
            if self.cancel.is_set():raise Cancelled('已停止')
            if chat['status']!='idle':raise ProviderError(chat.get('error') or '本轮协商未完成，未执行子任务')
            decision=chat['messages'][-1]['control'];turn['jobs']=decision['jobs']
            for job in turn['jobs']:
                Orchestrator.validate(dict(task=turn['text']+'\n\n当前子任务：'+job['title']+'\n'+job['instruction'],output_format=job['output_format'],call_limit=1),direct=True)
            if draft_only:
                draft=dict(draft_reply=decision['reply'],draft_model=chat['messages'][-1].get('model'),jobs=turn['jobs'],
                           job_plan=[{key:job[key] for key in ('title','instruction','output_format','primary_id')} for job in turn['jobs']],
                           plan_revision=1)
                state='prepared' if turn['jobs'] else 'completed'
            else:
                update(dict(decision=decision,jobs=turn['jobs'],phase='working' if turn['jobs'] else decision['mode']))
            if not draft_only and turn['jobs']:
                with self.dispatch_lock:
                    if self.cancel.is_set():raise Cancelled('已停止，协商后的子任务未发送')
                    self.workflow.start(session,turn,context)
                while self.workflow.busy():self.workflow.thread.join(.05)
                state=self.workflow.result['state'];error=self.workflow.result['error']
            elif not draft_only:state='completed'
        except Cancelled as exc:state='cancelled';error=str(exc)
        except ProviderError as exc:error=str(exc)
        except (ValueError,OSError) as exc:error=str(exc)
        except Exception:error='本轮聊天协作未完成，未自动重试'
        finally:
            timer.cancel()
            try:update(dict(**draft,state=state,error=error,phase='awaiting_confirmation' if state=='prepared' else 'finished',
                            negotiation_calls=count,build_report=not draft_only and bool(turn.get('jobs'))))
            finally:self.gate.release()
