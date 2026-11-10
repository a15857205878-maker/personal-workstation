"""Isolated metadata backend; never accesses the real desktop or registry."""
from pathlib import Path
from copy import deepcopy

def make_api(base):
    from PIL import Image
    from shortcut_model import ShortcutService
    from icon_studio_api import IconStudioAPI
    base=Path(base);assets=base/'assets/pokemon';assets.mkdir(parents=True,exist_ok=True)
    for name,color in [('original','blue'),('green','green')]:
        if not (assets/(name+'.ico')).exists():Image.new('RGBA',(32,32),color).save(assets/(name+'.ico'),format='ICO')
    imported=base/'fixture-add.png'
    if not imported.exists():Image.new('RGBA',(48,24),(25,125,225,180)).save(imported)
    desktop=base/'fixture-desktop';desktop.mkdir(exist_ok=True);shortcut=desktop/'验收软件.lnk'
    if not shortcut.exists():shortcut.write_bytes(b'isolated shortcut fixture')
    class Backend:
        def __init__(self):self.value=dict(target=str(base/'fixture.exe'),arguments='--keep-arguments',working_directory=str(base),window_style=1,hotkey='',description='fixture',icon=str(assets/'original.ico')+',0')
        def desktop_dirs(self):return [desktop]
        def read_many(self,paths):return [dict(path=str(path),**self.read(path)) for path in paths]
        def read(self,path):return deepcopy(self.value)
        def write_icon(self,path,icon):self.value['icon']=icon;return deepcopy(self.value)
    service=ShortcutService(base,backend=Backend(),asset_root=base/'fixture-cache')
    return IconStudioAPI(base,lambda folder=False,**kwargs:[str(assets if folder else imported)],service=service,collection=assets)
