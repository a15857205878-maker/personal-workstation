"""Small UI-only preferences, independent of credentials and conversations."""
import json,threading
from pathlib import Path
from credential_store import atomic_json

class AppearanceStore:
    THEMES=('mint','blue','lavender','apricot','coastal')
    SCHEMES=('light','dark')
    BACKGROUNDS=('auto','coast','aurora','garden','observatory','none')
    @staticmethod
    def valid_strength(value):return type(value) is int and 0<=value<=60
    def __init__(self,path):self.path=Path(path);self.lock=threading.RLock()
    def get(self):
        with self.lock:
            try:
                if self.path.stat().st_size>4096:raise ValueError()
                value=json.loads(self.path.read_text(encoding='utf-8'))
                return dict(theme=value['theme'] if value['theme'] in self.THEMES else 'mint',color_scheme=value.get('color_scheme') if value.get('color_scheme') in self.SCHEMES else 'light',chat_background=value.get('chat_background') if value.get('chat_background') in self.BACKGROUNDS else 'auto',background_strength=value.get('background_strength') if self.valid_strength(value.get('background_strength')) else 35)
            except (OSError,ValueError,KeyError,TypeError):return dict(theme='mint',color_scheme='light',chat_background='auto',background_strength=35)
    def save(self,theme=None,color_scheme=None,chat_background=None,background_strength=None):
        if all(v is None for v in (theme,color_scheme,chat_background,background_strength)):raise ValueError('请选择界面配色或深浅主题')
        if theme is not None and (not isinstance(theme,str) or theme not in self.THEMES):raise ValueError('配色选项无效')
        if color_scheme is not None and (not isinstance(color_scheme,str) or color_scheme not in self.SCHEMES):raise ValueError('深浅主题选项无效')
        if chat_background is not None and (not isinstance(chat_background,str) or chat_background not in self.BACKGROUNDS):raise ValueError('背景选项无效')
        if background_strength is not None and not self.valid_strength(background_strength):raise ValueError('背景强度须为0–60的整数')
        with self.lock:
            values=self.get()
            if theme is not None:values['theme']=theme
            if color_scheme is not None:values['color_scheme']=color_scheme
            if chat_background is not None:values['chat_background']=chat_background
            if background_strength is not None:values['background_strength']=background_strength
            atomic_json(self.path,values);return values
