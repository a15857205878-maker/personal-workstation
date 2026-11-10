"""Apply current task choices in memory, retaining custom suffixes and old records."""
import copy,json
from pathlib import Path

def load_catalog(saved,packaged):
 defaults=json.loads(Path(packaged).read_text(encoding='utf-8-sig'))
 saved=Path(saved)
 value=json.loads(saved.read_text(encoding='utf-8-sig')) if saved.exists() else copy.deepcopy(defaults)
 mapping={t['id']:t for t in defaults['tasks']}
 for kind in ('text','pptx','xlsx','research','image','animation'):
  new=mapping[kind];old=next((t for t in value['tasks'] if t['id']==kind),None)
  if old is None:value['tasks'].append(copy.deepcopy(new));continue
  old['agents']=copy.deepcopy(new['agents'])
  if old.get('default_role_ref') not in [a['role_ref'] for a in old['agents']]:old['default_role_ref']=new['default_role_ref']
  old['label']=new['label']
 return value
