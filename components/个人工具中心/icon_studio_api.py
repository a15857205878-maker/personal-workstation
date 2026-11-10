"""In-window adapter over the existing icon service, with snapshot-bound IDs."""
from pathlib import Path
from io import BytesIO
import base64,hashlib,uuid
from shortcut_model import ShortcutService
from pokemon_assets import find_collection
from icon_import import import_icons

def identifier(kind,path):return hashlib.sha256((kind+str(path)).encode('utf-8')).hexdigest()[:24]

def png(image):
    if image is None:return None
    buffer=BytesIO();image.convert('RGBA').save(buffer,format='PNG');return 'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode('ascii')

class IconStudioAPI:
    def __init__(self,base,picker,service=None,collection=None):
        self.base=Path(base);self.picker=picker;self.service=service or ShortcutService(base)
        self.collection=Path(collection) if collection is not None else find_collection(base)
        self.added=self.base/'data/icon_studio/imported-icons';self.targets={};self.assets={};self.revision=None
    def snapshot(self,**extra):
        self.targets={identifier('target',item['path']):item for item in self.service.scan()}
        assets={}
        for source,folder in (('原素材',self.collection),('新增',self.added)):
            if folder:
                for path in sorted(folder.glob('*.ico')):assets[identifier('asset',path)]=dict(path=path,source=source)
        self.assets=assets;self.revision=uuid.uuid4().hex
        return dict(revision=self.revision,targets=[dict(id=key,name=item.get('name') or Path(item['path']).stem,path=item['path'],kind=item.get('kind','shortcut'),editable=item.get('editable',True)) for key,item in self.targets.items()],assets=[dict(id=key,name=item['path'].stem,source=item['source']) for key,item in self.assets.items()],collection=str(self.collection) if self.collection else '',added_collection=str(self.added),**extra)
    def _refresh(self,message,**extra):
        try:return self.snapshot(message=message,**extra)
        except Exception:
            self.revision=None;self.targets={};self.assets={}
            return dict(revision=None,targets=[],assets=[],collection=str(self.collection or ''),added_collection=str(self.added),message=message,refresh_required=True,warnings=['操作回执已保存，但列表刷新未完成；请点击刷新核对，不要重复执行。'],**extra)
    def _target(self,value):
        if not isinstance(value,str) or value not in self.targets:raise ValueError('快捷方式不在当前列表，请刷新')
        return self.targets[value]
    def _asset(self,value):
        if not isinstance(value,str) or value not in self.assets:raise ValueError('图标不在当前素材列表，请刷新')
        return self.assets[value]['path']
    def call(self,p):
        fields={'load':{'action'},'choose_collection':{'action'},'import':{'action'},'preview':{'action','revision','target','asset'},'apply':{'action','revision','target','asset'},'restore':{'action','revision','target'},'restore_all':{'action','revision'}}
        if not isinstance(p,dict) or not isinstance(p.get('action'),str) or p['action'] not in fields or set(p)!=fields[p['action']]:raise ValueError('换装台参数无效')
        action=p['action']
        if 'revision' in p and (not self.revision or p['revision']!=self.revision):raise ValueError('列表已更新，请重新预览后操作')
        if action=='load':return self.snapshot()
        if action=='choose_collection':
            chosen=self.picker(folder=True)
            if not chosen:return self.snapshot(message='已取消，素材目录保持不变。')
            folder=Path(chosen if isinstance(chosen,str) else chosen[0])
            if not folder.is_dir():raise ValueError('所选素材文件夹不存在')
            self.collection=folder;return self.snapshot(message='已读取所选文件夹，未移动或修改素材。')
        if action=='import':
            chosen=self.picker(multiple=True,file_types=('ICO或PNG (*.ico;*.png)',))
            if not chosen:return self.snapshot(message='已取消添加。')
            result=import_icons([chosen] if isinstance(chosen,str) else chosen,self.added)
            selected=identifier('asset',Path(result['paths'][0])) if result['paths'] else None
            return self._refresh(f"已添加 {result['added']} 个，已存在 {result['existing']} 个；原素材未改动。",import_errors=result['errors'],preferred_asset=selected)
        if action=='restore_all':
            result=self.service.restore_all();errors=[row for row in result if row.get('status')=='failed']
            return self._refresh(f'已完成还原 {len(result)-len(errors)} 项，未完成 {len(errors)} 项。',operation_errors=[str(row.get('message','还原未完成')) for row in errors])
        item=self._target(p['target'])
        if action=='preview':
            from PIL import Image
            from win_icons import shortcut_image
            asset=self._asset(p['asset']);errors=[];current=proposed=None
            try:current=png(shortcut_image(item,128))
            except Exception:errors.append('当前图标暂无法预览；快捷方式不会被自动修改。')
            try:
                with Image.open(asset) as image:
                    image.load();image.thumbnail((128,128));proposed=png(image)
            except Exception:errors.append('所选素材暂无法预览，请换一个图标。')
            return dict(current=current,proposed=proposed,warnings=errors)
        if not item.get('editable',True):raise ValueError('特殊应用入口暂不支持换装或还原')
        if action=='apply':self.service.apply(item['path'],self._asset(p['asset']),item)
        else:self.service.restore(item['path'])
        return self._refresh('已应用并保留原还原记录。' if action=='apply' else '已还原选中项。')
