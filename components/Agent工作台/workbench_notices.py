"""Bounded local workbench status outbox. No task body, credentials or file contents."""
from pathlib import Path
import json,logging,re,threading,time,uuid
from credential_store import atomic_json
LOCK=threading.RLock()
PHASES={'结果待确认':('waiting','有结果待确认'),'已完成':('done','任务已确认完成'),'失败':('waiting','任务出错，请检查'),'需要检查':('waiting','任务中断，需要检查'),'等待交接':('waiting','请在客户端完成交接'),'completed':('done','协作已完成'),'failed':('waiting','协作出错，请检查'),'interrupted':('waiting','协作中断，需要检查')}
def publish_notice(path,source,identifier,status):
    if status not in PHASES or source not in ('task','collaboration') or not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{32}',identifier):return False
    try:
        with LOCK:
            path=Path(path)
            if path.exists() and path.stat().st_size>=131072:return False
            data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'version':1,'events':[]}
            if data.get('version')!=1 or not isinstance(data.get('events'),list):return False
            events=data['events'];previous=next((e for e in reversed(events) if e.get('task_id')==identifier and e.get('source')==source),None)
            if previous and previous.get('status')==status:return True
            kind,label=PHASES[status]
            events.append(dict(id=uuid.uuid4().hex,source=source,task_id=identifier,status=status,kind=kind,title='工作台 · '+label,at=time.time()))
            atomic_json(path,dict(version=1,events=events[-100:]));return True
    except (OSError,ValueError,TypeError,AttributeError):
        logging.getLogger(__name__).warning('工作台提醒暂未写入，原任务状态不受影响。');return False
