"""Personal-center butler: local metadata, no pet/renderer/SDK dependency."""
from pathlib import Path
import json,math,re

LABELS={'结果待确认':'有结果待确认','已完成':'任务已确认完成','失败':'任务出错，请检查','需要检查':'任务中断，需要检查','等待交接':'请在客户端完成交接','completed':'协作已完成','failed':'协作出错，请检查','interrupted':'协作中断，需要检查'}

class ButlerCenter:
    def __init__(self,root=None,*,data_dir=None):self.path=(Path(data_dir) if data_dir is not None else Path(root)/'data')/'pet-notices.json'
    def snapshot(self,overview):
        counts={key:max(0,min(200,value)) if type(value) is int else 0 for key in ('tasks','collaborations','active','attention') for value in [overview.get('counts',{}).get(key,0)]}
        notices=[];state='empty';warnings=[]
        overview_state='unavailable' if overview.get('warnings') or overview.get('errors') else 'ready'
        if overview_state!='ready':
            counts={key:None for key in counts}
            warnings.append('部分工作概况暂不可读，计数显示为未知；请稍后刷新或检查工作区。')
        try:
            if self.path.exists():
                if self.path.stat().st_size>131072:raise ValueError('oversize')
                data=json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('events'),list):raise ValueError('format')
                state='ready';seen=set()
                for row in reversed(data['events'][-100:]):
                    if not isinstance(row,dict) or row.get('source') not in ('task','collaboration') or row.get('status') not in LABELS:continue
                    if not all(isinstance(row.get(key),str) and re.fullmatch('[a-f0-9]{32}',row[key]) for key in ('id','task_id')):continue
                    if row['id'] in seen:continue
                    seen.add(row['id']);at=row.get('at',0)
                    notices.append(dict(id=row['id'],label=LABELS[row['status']],source='独立任务' if row['source']=='task' else '双模型协作',kind='done' if row['status'] in ('已完成','completed') else 'waiting',page='tasks' if row['source']=='task' else 'work',at=at if type(at) in (float,int) and math.isfinite(at) else 0))
        except (OSError,ValueError,TypeError):
            state='unavailable';warnings.append('近期提醒暂不可读，原始记录已保留。')
        return dict(version=1,overview_state=overview_state,counts=counts,scope='最近100个未归档任务与最近100个协作记录',notices=notices,feed_state=state,warnings=warnings,independent_of_pet=True)
