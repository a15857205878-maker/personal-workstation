"""Fixed public metadata for a paired phone; never exports task records."""
import math
import time
import json
from pathlib import Path

SCOPE = '最近100个未归档任务与最近100个协作记录'

def public_pet_activity(value, now=None):
    now=time.time() if now is None else now
    if not isinstance(value,dict):return {'available':False}
    at=value.get('observed_at');changed=value.get('changed_at')
    if value.get('available') is not True or type(at) not in (float,int) or not math.isfinite(at) or not 0<=now-at<=12:return {'available':False}
    if value.get('scene') not in ('room','home','plaza','orchard','desktop') or value.get('pose') not in ('back','turn','relax','rest','front','sit') or value.get('phase') not in ('stable','switching','paused'):return {'available':False}
    return dict(available=True,scene=value['scene'],pose=value['pose'],night=value.get('night') is True,automatic=value.get('automatic') is True,held=value.get('held') is True,phase=value['phase'],observed_at=at,changed_at=changed if type(changed) in (float,int) and math.isfinite(changed) and 0<=changed<=at else at)

def read_public_pet_activity(pet_root=None, now=None):
    if pet_root is None:
        from companion_adapter import PET
        pet_root=PET
    try:
        path=Path(pet_root)/'pet-activity.status.json'
        if path.stat().st_size>4096:return {'available':False}
        return public_pet_activity(json.loads(path.read_text(encoding='utf8')),now)
    except (OSError,ValueError,UnicodeError):return {'available':False}

def public_room_status(snapshot, now=None, pet_activity=None):
    now = time.time() if now is None else now
    value = snapshot if isinstance(snapshot, dict) else {}
    source = value.get('counts') if isinstance(value.get('counts'), dict) else {}
    counts = {key: source.get(key) for key in ('tasks', 'collaborations', 'active', 'attention')}
    at = value.get('observed_at')
    valid_time = type(at) in (int, float) and math.isfinite(at) and 0 <= now-at <= 15
    ready = (value.get('overview_state') == 'ready' and valid_time
             and all(type(n) is int and 0 <= n <= 200 for n in counts.values()))
    done = []
    for row in value.get('notices', []) if isinstance(value.get('notices'), list) else []:
        if not isinstance(row, dict) or row.get('kind') != 'done':
            continue
        t = row.get('at')
        if type(t) in (int, float) and math.isfinite(t) and 0 <= now-t <= 60:
            done.append(t)
    result=dict(version=1, observed_at=at if valid_time else None,
                overview_state='ready' if ready else 'unavailable',
                counts=counts if ready else dict.fromkeys(counts),
                recent_completed_at=max(done) if ready and done else None,
                scope=SCOPE, preview_kind='static')
    if pet_activity is not None:result['pet_activity']=public_pet_activity(pet_activity,now)
    return result
