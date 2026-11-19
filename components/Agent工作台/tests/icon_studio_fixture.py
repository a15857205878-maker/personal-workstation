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


def make_duplicate_api(base):
    """Two same-name links, with a Dock pointing only at the desktop copy."""
    import json
    api=make_api(base);base=Path(base);desktop=base/'fixture-desktop';archive=base/'fixture-archive';archive.mkdir(exist_ok=True)
    paths=[desktop/'龙娘桌宠.lnk',archive/'龙娘桌宠.lnk']
    for path in paths:path.write_bytes(b'isolated named shortcut')
    initial=api.service.backend.value
    class Backend:
        def __init__(self):self.values={Path(p):deepcopy(initial) for p in [desktop/'验收软件.lnk',*paths]}
        def desktop_dirs(self):return [desktop]
        def read(self,path):return deepcopy(self.values[Path(path)])
        def read_many(self,paths):return [dict(path=str(p),**self.read(p)) for p in paths]
        def write_icon(self,path,icon):self.values[Path(path)]['icon']=icon;return self.read(path)
    api.service.backend=Backend();api.service.root.mkdir(parents=True,exist_ok=True)
    dock=base/'fixture-dock.json';dock.write_text(json.dumps({'Items':[{'Path':str(paths[0])}]}),encoding='utf-8')
    (api.service.root/'sources.json').write_text(json.dumps({'shortcut_dirs':[str(archive)],'dock_settings':str(dock)}),encoding='utf-8')
    return api,paths
