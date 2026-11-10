"""Reuse the desktop pet launcher and existing metadata-only reminder feed."""
from pathlib import Path
import importlib.util
import json
import os

WORKSTATION=Path(__file__).resolve().parent
PET=Path(os.environ.get('AGENT_PET_ROOT',str(WORKSTATION.parent/'agent-desktop-pet')))


class CompanionAdapter:
    def __init__(self,pet_root=PET,workbench_root=WORKSTATION,launcher=None):
        self.pet_root=Path(pet_root);self.workbench_root=Path(workbench_root)
        if launcher is None:
            center=WORKSTATION.parent/'个人工具中心新版'
            spec=importlib.util.spec_from_file_location('_workstation_pet_launcher',center/'pet_launcher.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            import os
            launcher=module.PetLauncher(center/'data/pet_launcher.json',os.startfile)
        self.launcher=launcher

    def status(self):
        result={'launch_ready':False,'workbench_linked':False,'event_count':0,'feed_state':'empty','warnings':[]}
        try:
            entry=self.launcher.entry();result['launch_ready']=bool(entry and Path(entry).is_file())
        except (OSError,ValueError,TypeError):result['warnings'].append('桌宠启动入口需要检查。')
        try:
            link=self.pet_root/'workbench_link.json'
            if link.stat().st_size>4096:raise ValueError()
            root=Path(json.loads(link.read_text(encoding='utf-8'))['workbench_root'])
            result['workbench_linked']=root.is_absolute() and root.resolve()==self.workbench_root.resolve()
        except (OSError,ValueError,KeyError,TypeError):pass
        if not result['workbench_linked']:result['warnings'].append('桌宠连接位置与当前工作站不一致，请检查本机连接配置。')
        feed=self.workbench_root/'data/pet-notices.json'
        try:
            if feed.exists():
                if feed.stat().st_size>131072:raise ValueError()
                value=json.loads(feed.read_text(encoding='utf-8'))
                if value.get('version')!=1 or not isinstance(value.get('events'),list):raise ValueError()
                result['event_count']=len(value['events']);result['feed_state']='ready'
        except (OSError,ValueError,TypeError,AttributeError):
            result['feed_state']='unavailable';result['warnings'].append('任务提醒记录暂不可读，原文件已保留。')
        return result

    def launch(self):
        result=self.launcher.launch()
        if result.get('needs_configuration'):raise ValueError('桌宠启动入口未配置或已移动，请检查现有桌宠安装。')
        return {'action':result.get('action','requested'),'message':'已请求启动桌宠。若已在运行，不会重复创建；隐藏状态可从系统托盘恢复。'}

    def _home_link(self):
        path=self.pet_root/'pet_home_link.py'
        if not path.is_file():raise ValueError('请更新并正常重启原桌宠后，再打开小屋。')
        spec=importlib.util.spec_from_file_location('_workstation_pet_home_link',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def home_status(self):
        try:return self._home_link().read_status(self.pet_root)
        except (OSError,ValueError,ImportError):return {'connected':False,'mode':'unknown'}

    def open_home(self):
        link=self._home_link()
        self.launch()
        identifier=link.request_home(self.pet_root)
        return {'request_id':identifier,'message':'已请求打开小屋，正在等待桌宠确认。'}
