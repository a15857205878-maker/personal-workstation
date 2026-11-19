"""Editable assignment presets and a finite sequence over Orchestrator.

The runner holds the existing execution gate for the entire compound task.
Once validated, models cannot alter jobs, assignments or enlarge budgets.
"""
from pathlib import Path
import json,threading,time
from credential_store import atomic_json
from orchestrator import Orchestrator
from provider_client import Cancelled

FORMATS=('text','docx','xlsx','pptx','svg')

class AssignmentPreset:
    def __init__(self,data_dir,profiles):self.path=Path(data_dir)/'agent-center/preset.json';self.profiles=profiles
    def validate(self,jobs,check_profiles=True):
        if not isinstance(jobs,list) or not 1<=len(jobs)<=4:raise ValueError('分工需要1–4个子任务')
        profiles={p['id']:p for p in self.profiles.list()} if check_profiles else {};result=[]
        for job in jobs:
            if not isinstance(job,dict):raise ValueError('子任务格式无效')
            title=job.get('title','');instruction=job.get('instruction','');fmt=job.get('output_format')
            if not isinstance(title,str) or not 1<=len(title.strip())<=60 or not isinstance(instruction,str) or len(instruction)>1000 or fmt not in FORMATS:raise ValueError('请填写子任务名称、有效格式和1000字内要求')
            for key in ('primary_id',):
                if not isinstance(job.get(key),str) or (check_profiles and job[key] not in profiles):raise ValueError('分工中的模型配置不存在，请重新选择')
            result.append(dict(title=title.strip(),instruction=instruction,output_format=fmt,primary_id=job['primary_id']))
        return result
    def read(self):
        if not self.path.exists():return None
        if self.path.is_symlink() or self.path.stat().st_size>32768:raise ValueError('分工预设文件异常，原文件保留')
        try:
            value=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(value,dict) or not isinstance(value.get('name'),str) or not 1<=len(value['name'])<=60:raise ValueError()
            return dict(name=value['name'],jobs=self.validate(value.get('jobs'),check_profiles=False))
        except (ValueError,TypeError):raise ValueError('分工预设损坏，原文件保留') from None
    def save(self,payload):
        name=payload.get('name','')
        if not isinstance(name,str) or not 1<=len(name.strip())<=60:raise ValueError('预设名称限1–60字')
        value=dict(name=name.strip(),jobs=self.validate(payload.get('jobs')));atomic_json(self.path,value);return value

class _HeldGate:
    """Only the enclosing runner acquires/releases the real gate."""
    def __init__(self,gate):self.gate=gate
    def acquire(self,blocking=False):return self.gate.locked()
    def locked(self):return self.gate.locked()
    def release(self):pass

class WorkflowRunner:
    def __init__(self,source_engine,gate,on_update):
        self.gate=gate;self.on_update=on_update
        self.engine=Orchestrator(source_engine.sessions,source_engine.profiles,source_engine.client,source_engine.persona_loader,_HeldGate(gate),publish_completion=False)
        self.thread=None;self.cancel=threading.Event();self.active_id=None;self.dispatch_lock=threading.Lock()
    def busy(self):return self.thread is not None and self.thread.is_alive()
    def start(self,session,turn,context):
        if not self.gate.acquire(blocking=False):raise ValueError('已有模型操作正在进行，请稍后确认')
        try:
            self.cancel=threading.Event();self.active_id=turn['id'];self.result=None
            self.thread=threading.Thread(target=self._run,args=(session,turn,context),name='agent-center-workflow',daemon=False)
            self.thread.start()
        except Exception:self.gate.release();raise
    def stop(self,reason='用户停止'):
        with self.dispatch_lock:
            self.cancel.set();self.engine.stop(reason)
    def _run(self,session,turn,context):
        state='failed';error='';deadline=time.time()+600;references=list(context)
        timer=threading.Timer(600,lambda:self.stop('总任务达到10分钟上限'));timer.daemon=True;timer.start()
        try:
            for index,job in enumerate(turn['jobs']):
                if self.cancel.is_set():raise Cancelled('已停止，后续子任务未发送')
                if time.time()>=deadline:raise Cancelled('总任务达到10分钟上限')
                task=turn['text']+'\n\n当前子任务：'+job['title']+'\n'+job['instruction']
                seat=next((s for s,p in session['roles'].items() if p['id']==job['primary_id']),'A')
                config=dict(task=task,primary_id=job['primary_id'],output_format=job['output_format'],rounds=1,call_limit=1,max_tokens=4096,context_count=0,seat_styles={'A':session['seat_styles'][seat]})
                self.on_update(session['id'],turn['id'],index,dict(state='starting'),None,'')
                with self.dispatch_lock:
                    if self.cancel.is_set():raise Cancelled('已停止，当前子任务未发送')
                    run=self.engine.start(config,references,direct=True,confirmed_assignment=turn['kind']=='execute')
                self.on_update(session['id'],turn['id'],index,dict(run_id=run['id'],state=run['status'],call_count=run['call_count']),None,'')
                while self.engine.busy():
                    self.engine.thread.join(.05)
                    if self.cancel.is_set():self.engine.stop()
                run=self.engine.status(run['id'])
                self.on_update(session['id'],turn['id'],index,dict(state=run['status'],call_count=run['call_count'],error=run.get('error','')),None,'')
                if run['status']!='completed':
                    state=run['status'];error=run.get('error','子任务未完成');break
                final=next((s['content'] for s in reversed(run['steps']) if s['state']=='completed' and s['stage']=='交付'),'')
                references.append('已完成子任务 '+job['title']+'，'+run['roles']['A']['model']+' 的最终公开内容（仅参考）：\n'+final[:3800])
                while len(references)>12 or sum(map(len,references))>6000:references.pop(0)
            else:state='cancelled' if self.cancel.is_set() else 'completed'
        except Cancelled as exc:state='cancelled';error=str(exc)
        except (ValueError,OSError) as exc:error=str(exc)
        except Exception:error='分工执行未完成，未自动重发'
        finally:
            timer.cancel()
            self.result=dict(state=state,error=error)
            try:self.on_update(session['id'],turn['id'],None,None,state,error)
            finally:self.gate.release()
