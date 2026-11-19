"""Versioned local butler contract: aggregate status and fixed UI navigation only."""
import json
import time
from desktop_chrome import show_workstation

PAGES={'leisure':'休闲','reading':'书房与放松','icons':'图标换装台','overview':'工作概览','partner':'搭档','work':'双模型协作','pack':'资料与打包',
       'chat':'聊天实验室','games':'游戏资料库','wheel':'休闲轮盘','town':'小镇与专注',
       'remote':'远程','artifacts':'成果','companion':'个人管家','settings':'设置与维护','quick':'快捷指令'}

class DesktopAssistant:
    def __init__(self,bridge):self.bridge=bridge
    def status(self):
        result=self.bridge.call('workstation_overview',{})
        if not result.get('ok'):raise ValueError('工作站状态暂不可读，请在电脑端检查。')
        counts=result.get('data',{}).get('counts',{})
        values={key:max(0,min(10000,value)) if type(value) is int else 0 for key in ('tasks','collaborations','active','attention','conversations','deliveries') for value in [counts.get(key,0)]}
        ready=getattr(self.bridge,'companion_ui_ready',None)
        try:focus=self.bridge.call('workstation_focus_status',{})
        except Exception:focus={'ok':False}
        f=focus.get('data') if focus.get('ok') else None
        f={k:f.get(k) for k in ('kind','remaining','duration','observed_at')} if isinstance(f,dict) and f.get('kind') in ('running','paused','idle','unknown') else None
        return {'version':1,'checked_at':time.time(),'navigation_ready':bool(ready and ready.is_set()),'counts':values,'focus':f,'scope':result.get('data',{}).get('scope','当前搭档状态'),'pages':dict(PAGES)}
    def open(self,payload):
        if isinstance(payload,dict) and set(payload)=={'turn_id'}:
            from center_index import center_task_link
            target=center_task_link(getattr(self.bridge,'_data_dir',None),payload['turn_id'])
            self._show({'kind':'center_turn',**target})
            return {'opened':True,'page':'work','turn_id':target['turn_id']}
        if not isinstance(payload,dict) or set(payload)!={'page'} or not isinstance(payload['page'],str) or payload['page'] not in {*PAGES,'tasks'}:
            raise ValueError('只允许打开已登记的工作站功能。')
        page='artifacts' if payload['page']=='tasks' else payload['page']
        if page=='quick':
            result=self.bridge.call('api_quick_open',{})
            if not result.get('ok'):raise ValueError('快捷指令暂未就绪，请在电脑端检查。')
        else:
            self._show({'kind':'navigate','page':page})
        return {'opened':True,'page':page,'label':PAGES[page]}

    def _show(self,event):
        window=self.bridge.station_window
        if window is None:raise ValueError('工作站界面尚未就绪，请稍后重试。')
        if window.evaluate_js('window.workbenchReceive?.('+json.dumps(event,ensure_ascii=False)+')') is not True:
            raise ValueError('工作站尚未确认页面切换，请在电脑端查看。')
        show_workstation(window)
