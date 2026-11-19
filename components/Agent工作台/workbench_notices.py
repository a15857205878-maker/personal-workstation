"""Bounded local workbench status outbox. No task body, credentials or file contents."""
from pathlib import Path
import json,logging,re,threading,time,uuid
from credential_store import atomic_json
LOCK=threading.RLock()
PHASES={'结果待确认':('waiting','有结果待确认'),'已完成':('done','任务已确认完成'),'失败':('waiting','任务出错，请检查'),'需要检查':('waiting','任务中断，需要检查'),'等待交接':('waiting','请在客户端完成交接'),'completed':('done','协作已完成'),'failed':('waiting','协作出错，请检查'),'interrupted':('waiting','协作中断，需要检查')}
CENTER_PHASES = {
    'prepared': ('waiting', '搭档有分工待确认'),
    'completed': ('done', '搭档成果可验收'),
    'failed': ('waiting', '搭档本轮出错，请检查'),
    'interrupted': ('waiting', '搭档本轮中断，请检查'),
    'starting': None,
    'cancelled': None,
    'accepted': None,
}

def publish_notice(path,source,identifier,status):
    if source not in ('task','collaboration','center') or not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{32}',identifier):return False
    phases = CENTER_PHASES if source == 'center' else PHASES
    if status not in phases:return False
    phase = phases[status]
    try:
        with LOCK:
            path=Path(path)
            if path.exists() and path.stat().st_size>=131072:return False
            data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'version':1,'events':[]}
            if data.get('version')!=1 or not isinstance(data.get('events'),list):return False
            events=data['events'];previous=next((e for e in reversed(events) if e.get('task_id')==identifier and e.get('source')==source),None)
            if previous and previous.get('status')==status:return True
            if source == 'center':
                # The desktop pet may have been closed while the plan progressed.
                # After it comes back, only offer the latest actionable state of the turn.
                replaced='completed' if status=='accepted' else 'prepared'
                if phase is None and (not previous or previous.get('status') != replaced):
                    return True
                events = [event for event in events if not (event.get('source') == source and event.get('task_id') == identifier)]
            if phase is not None:
                kind,label=phase
                events.append(dict(id=uuid.uuid4().hex,source=source,task_id=identifier,status=status,kind=kind,title='工作台 · '+label,at=time.time()))
            atomic_json(path,dict(version=1,events=events[-100:]));return True
    except (OSError,ValueError,TypeError,AttributeError):
        logging.getLogger(__name__).warning('工作台提醒暂未写入，原任务状态不受影响。');return False

def publish_run_notice(path,run):
    target = run.get('notice_target', {'source': 'collaboration', 'id': run['id']})
    if not isinstance(target,dict):
        return False  # An owning turn publishes for its subtasks.
    return publish_notice(path,target.get('source'),target.get('id'),run['status'])
