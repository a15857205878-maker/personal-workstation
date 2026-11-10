"""Read-only projection of the desktop pet's existing daily affinity record."""
from pathlib import Path
import json
import os
PET_BUDDY=Path(os.environ.get('AGENT_PET_ROOT',str(Path(__file__).resolve().parent.parent/'agent-desktop-pet')))/'pet_buddy.json'
def read_companion(day,path=None):
    path=Path(path) if path else PET_BUDDY
    unknown=dict(available=False,affinity=0,active_days=0)
    try:
        if not path.is_file() or path.stat().st_size>65536:return unknown
        raw=json.loads(path.read_text(encoding='utf-8-sig'));value=raw.get('interaction')
        if raw.get('version')!=1 or not isinstance(value,dict):return unknown
        affinity=value.get('affinity',0);days=value.get('active_days',0)
        if type(affinity) is not int or type(days) is not int or not 0<=affinity<=100 or not 0<=days<=1000000:return unknown
        return dict(available=True,affinity=affinity if value.get('date')==day else 0,active_days=days)
    except (OSError,ValueError,TypeError,AttributeError):return unknown
