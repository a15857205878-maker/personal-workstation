"""Small UI-only preferences, independent of credentials and conversations."""
import json,threading
from pathlib import Path
from credential_store import atomic_json

class AppearanceStore:
    THEMES=('mint','blue','lavender','apricot','coastal')
    SCHEMES=('light','dark')
    def __init__(self,path):self.path=Path(path);self.lock=threading.RLock()
    def get(self):
        with self.lock:
            try:
                if self.path.stat().st_size>4096:raise ValueError()
                value=json.loads(self.path.read_text(encoding='utf-8'))
                return dict(theme=value['theme'] if value['theme'] in self.THEMES else 'mint',color_scheme=value.get('color_scheme') if value.get('color_scheme') in self.SCHEMES else 'light')
            except (OSError,ValueError,KeyError,TypeError):return dict(theme='mint',color_scheme='light')
    def save(self,theme=None,color_scheme=None):
        if theme is None and color_scheme is None:raise ValueError('请选择界面配色或深浅主题')
        if theme is not None and (not isinstance(theme,str) or theme not in self.THEMES):raise ValueError('配色选项无效')
        if color_scheme is not None and (not isinstance(color_scheme,str) or color_scheme not in self.SCHEMES):raise ValueError('深浅主题选项无效')
        with self.lock:
            values=self.get()
            if theme is not None:values['theme']=theme
            if color_scheme is not None:values['color_scheme']=color_scheme
            atomic_json(self.path,values);return values
