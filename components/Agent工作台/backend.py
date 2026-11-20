"""One registered bridge for bounded API handoff and manual room operations."""
from copy import deepcopy
from pathlib import Path
import json,os,threading,uuid
from room_store import RoomStore,DEFAULT_ROOM
from runner import RoomRunner

class Bridge:
    def __init__(self,root=DEFAULT_ROOM,executor=None,opener=None,data_dir=None,api_client=None):
        self.store=RoomStore(root);self.executor=executor or RoomRunner(root);self.opener=opener or os.startfile
        self._command_lock=threading.Lock();self._state_lock=threading.Lock();self._job=None
        self._data_dir=Path(data_dir) if data_dir is not None else Path(__file__).parent/'data'
        self._api_client=api_client;self._auto=None;self._auto_init=threading.Lock();self.export_saver=None
        from member_identity import IdentityStore
        self.identities=IdentityStore(self._data_dir);self.identity_picker=None
        self.ui_actions={};self.quick_window=None;self.attachment_picker=None;self._attachments=None;self._attachment_lock=threading.Lock()
        self._station=None;self._station_init=threading.Lock();self.station_window=None
        self._workstation=None;self._workstation_init=threading.Lock()
        from appearance_store import AppearanceStore
        self.appearance=AppearanceStore(self._data_dir/'appearance.json')
    @property
    def attachments(self):
        if self._attachments is None:
            from task_station.attachments import AttachmentStore
            self._attachments=AttachmentStore(self._data_dir/'station/attachments')
        return self._attachments
    def _attachment_pick(self,p):
        if not self._attachment_lock.acquire(blocking=False):raise ValueError('另一个附件选择正在处理，请稍候。')
        try:
            if self.attachment_picker:paths=self.attachment_picker()
            else:
                import webview
                window=self.quick_window if p.get('surface')=='quick' and self.quick_window else self.station_window
                if window is None:raise ValueError('窗口尚未就绪。')
                paths=window.create_file_dialog(webview.FileDialog.OPEN,allow_multiple=True,file_types=('资料 (*.txt;*.md;*.csv;*.tsv;*.json;*.log;*.docx;*.pptx;*.xlsx;*.pdf;*.png;*.jpg;*.jpeg;*.bmp;*.webp)',))
            if not paths:return dict(items=[],errors=[])
            if len(paths)>5:raise ValueError('一次最多选择5个附件。')
            items=[];errors=[]
            for path in paths:
                try:items.append(self.attachments.add(path,image_asset=p.get('purpose')=='presentation'))
                except (ValueError,OSError) as exc:errors.append(Path(path).name+'：'+str(exc))
            return dict(items=items,errors=errors)
        finally:self._attachment_lock.release()
    def busy(self):return self._command_lock.locked() or self._attachment_lock.locked() or bool(self._workstation and self._workstation.busy())
    def close_workstation(self):
        if self._workstation:self._workstation.close()
    def call(self,action,payload=None):
        try:
            if action in ('api_example_task','api_example_document'):
                if payload is not None and (not isinstance(payload,dict) or payload):
                    raise ValueError('示例入口不接收参数')
                from first_run_example import document,task
                return dict(ok=True,data=task() if action=='api_example_task' else document())
            if isinstance(action,str) and action.startswith('workstation_'):
                if payload is None:payload={}
                if not isinstance(payload,dict) or len(json.dumps(payload,ensure_ascii=False))>262144:raise ValueError('工作站参数无效或过大')
                with self._workstation_init:
                    if self._workstation is None:
                        from workstation_core import WorkstationCore
                        self._workstation=WorkstationCore(self)
                return dict(ok=True,data=self._workstation.call(action,payload))
            if action in ('api_attachment_pick','api_attachment_bundle','api_quick_submit','api_quick_open','api_quick_hide','api_main_open','api_quick_info','api_window_action'):
                if payload is None:payload={}
                if not isinstance(payload,dict) or len(json.dumps(payload,ensure_ascii=False))>32768:raise ValueError('参数无效或过大')
                if action=='api_attachment_pick':data=self._attachment_pick(payload)
                elif action=='api_attachment_bundle':data=self.attachments.bundle(payload.get('ids',[]))
                else:
                    handler=self.ui_actions.get(action)
                    if handler is None:raise ValueError('桌面快捷通道尚未就绪。')
                    data=handler(payload)
                return dict(ok=True,data=data)
            if isinstance(action,str) and action.startswith('station_'):
                allowed={'quota','quota_open','catalog','list','get','create','submit','cancel','archive','restore','delete','handoff','copy_prompt','import_result','save_text','export_document','export_spreadsheet','complete','open_folder','open_file','settings','save_settings','set_execution_mode','preview_animation','save_templates','review_draft','ppt_draft'}
                method=action[8:]
                if method not in allowed:raise ValueError('不支持的任务操作')
                if payload is None:payload={}
                if not isinstance(payload,dict) or len(json.dumps(payload,ensure_ascii=False).encode('utf-8'))>262144:raise ValueError('任务参数无效或过大')
                with self._station_init:
                    if self._station is None:
                        from task_station.host import Bridge as StationBridge
                        self._station=StationBridge(self._data_dir/'station',execution_gate=self._command_lock)
                    self._station.window=self.station_window
                return self._station.call(method,payload)
            room_actions=('app_link_open','app_link_pending','app_link_claim','app_link_archive','snapshot','start_command','command_status','read_document','open_folder')
            api_actions=('api_bootstrap','api_status','api_session','api_start','api_retry','api_stop','api_note','api_profile_save','api_profile_delete_key','api_profile_delete','api_profile_test','api_discover_local','api_local_path')
            api_actions+=('api_collaboration_file','api_collaboration_open_file')
            api_actions+=('api_chat_bootstrap','api_chat_create','api_chat_delete','api_chat_send','api_chat_status','api_chat_stop','api_chat_discuss','api_chat_memory','api_chat_memory_save','api_chat_memory_delete','api_chat_memory_clear')
            api_actions+=('api_chat_continue','api_chat_export','api_chat_export_save')
            api_actions+=('api_center_bootstrap','api_center_create','api_center_status','api_center_send','api_center_confirm','api_center_stop')
            api_actions+=('api_center_preset_save','api_center_manage','api_center_retry','api_center_accept')
            api_actions+=('api_center_draft','api_center_edit_plan')
            api_actions+=('api_center_identity_get','api_center_identity_save','api_center_identity_pick')
            api_actions+=('api_center_memory','api_center_memory_save','api_center_memory_delete','api_center_memory_clear')
            api_actions+=('api_appearance_get','api_appearance_save','api_antigravity_status','api_discover_antigravity')
            if not isinstance(action,str) or action not in room_actions+api_actions:raise ValueError('不支持的操作')
            if payload is None:payload={}
            if not isinstance(payload,dict) or len(json.dumps(payload,ensure_ascii=False))>32768:raise ValueError('参数无效或过大')
            if action.startswith('app_link_'):
                from app_link_client import open_hub,api
                base=Path(__file__).resolve().parent
                if action=='app_link_open':return dict(ok=True,data=open_hub(base))
                if action=='app_link_archive':return dict(ok=True,data=api(base,'archive',{'id':payload.get('id')}))
                if action=='app_link_claim':
                    if self.busy():raise ValueError('工作台正在执行任务，请稍后接收。')
                    return dict(ok=True,data=api(base,'claim',{'id':payload.get('id')}))
                return dict(ok=True,data=api(base,'pending'))
            if action.startswith('api_center_identity_'):
                if action=='api_center_identity_get':
                    if payload:raise ValueError('成员资料读取不接收参数')
                    return dict(ok=True,data=self.identities.get())
                if not self._command_lock.acquire(blocking=False):raise ValueError('模型或本地操作进行中，请结束后修改成员资料')
                try:
                    if action=='api_center_identity_pick':
                        if payload:raise ValueError('头像选择不接收路径参数')
                        if self.identity_picker:paths=self.identity_picker()
                        else:
                            import webview
                            if self.station_window is None:raise ValueError('窗口尚未就绪')
                            paths=self.station_window.create_file_dialog(webview.FileDialog.OPEN,allow_multiple=False,file_types=('头像图片 (*.png;*.jpg;*.jpeg;*.webp)',))
                        if not paths:return dict(ok=True,data=dict(cancelled=True))
                        from member_identity import import_avatar
                        return dict(ok=True,data=dict(cancelled=False,avatar=import_avatar(paths[0])))
                    if set(payload)!={'id','nickname','avatar'}:raise ValueError('成员资料参数无效')
                    from credential_store import ProfileStore
                    identifier=payload['id']
                    if identifier!='user' and identifier not in {p['id'] for p in ProfileStore(self._data_dir).list()}:
                        if not (payload['nickname']=='' and payload['avatar']=='' and isinstance(identifier,str) and identifier in self.identities.get()['items']):
                            raise ValueError('模型配置不存在，请重新选择成员')
                    return dict(ok=True,data=self.identities.save(identifier,payload['nickname'],payload['avatar']))
                finally:self._command_lock.release()
            if action=='api_antigravity_status':
                if payload:raise ValueError('Antigravity 安装检查不接收参数')
                from antigravity_probe import snapshot
                return dict(ok=True,data=snapshot())
            if action=='api_appearance_get':
                if payload:raise ValueError('界面偏好读取不接收参数')
                return dict(ok=True,data=self.appearance.get())
            if action=='api_appearance_save':
                if not payload or not set(payload)<= {'theme','color_scheme','chat_background','background_strength'}:raise ValueError('界面偏好参数无效')
                if any(value is None for value in payload.values()):raise ValueError('界面偏好参数无效')
                values=self.appearance.save(**payload)
                handler=self.ui_actions.get('appearance_changed')
                if handler:handler(values)
                return dict(ok=True,data=values)
            if action in api_actions:
                with self._auto_init:
                    if self._auto is None:
                        from auto_service import AutoService
                        self._auto=AutoService(self._data_dir,self.store,self._command_lock,self._api_client)
                if action=='api_chat_export_save':
                    if self.export_saver is None:raise ValueError('保存窗口尚未就绪')
                    export=self._auto.chat.export(payload)
                    return dict(ok=True,data=dict(saved=bool(self.export_saver(export['filename'],export['text']))))
                if action=='api_collaboration_open_file':
                    from collaboration_files import artifact_path
                    run=self._auto.sessions.load(payload.get('id'));path=artifact_path(self._data_dir,run,payload.get('name'))
                    self.opener(str(path));return dict(ok=True,data={'name':path.name})
                return dict(ok=True,data=self._auto.call(action,payload))
            return dict(ok=True,data=getattr(self,'_'+action)(payload))
        except (ValueError,OSError,TypeError,KeyError,UnicodeError) as exc:return dict(ok=False,error=str(exc) or '操作失败')
        except Exception:return dict(ok=False,error='操作未完成，请刷新后重试')
    def _api_active(self):return (self._auto is not None and (self._auto.engine.busy() or self._auto.chat.busy() or self._auto.center.busy())) or bool(self._station and self._station.service.jobs)
    def _stop_api(self):
        if self._station:
            for identifier in list(self._station.service.jobs):
                try:self._station.service.call('cancel',{'id':identifier})
                except ValueError:pass
        if self._auto:
            if self._auto.engine.busy():self._auto.engine.stop('用户关闭窗口')
            if self._auto.chat.busy():self._auto.chat.stop('用户关闭窗口')
            if self._auto.center.busy():self._auto.center.stop_all('用户关闭窗口')
    def close_station(self):
        if self._station:self._station.service.close()
    def _snapshot(self,payload):return self.store.snapshot()
    def _read_document(self,payload):return self.store.read_document(payload.get('kind'),payload.get('name',''))
    def _open_folder(self,payload):
        kind=payload.get('kind','room')
        if kind not in ('room','card','drafts'):raise ValueError('不支持的目录')
        path=self.store.path(kind)
        if not path.is_dir():raise ValueError('目录不存在')
        self.opener(str(path));return dict(message='已打开目录')
    def _command_status(self,payload):
        with self._state_lock:return deepcopy(self._job)
    def _arguments(self,payload):
        command=payload.get('command')
        if command not in ('next','bake','card','status','--check'):raise ValueError('不支持的房间命令')
        arguments=[command]
        if command in ('next','card','bake'):
            current=self.store.snapshot()
            if payload.get('revision')!=current['revision']:raise ValueError('房间已更新，请先刷新，再执行操作')
            if command in ('next','card'):
                seat=payload.get('seat')
                if not isinstance(seat,str) or seat not in {s['id'] for s in current['seats']}:raise ValueError('非法席位')
                arguments.append(seat)
            if command=='card':
                count=payload.get('count',6)
                if type(count) is not int or not 1<=count<=2000:raise ValueError('消息条数须为 1–2000 的整数')
                arguments.extend(['-n',str(count)])
        return arguments
    def _start_command(self,payload):
        if not self._command_lock.acquire(blocking=False):raise ValueError('已有命令正在执行，请稍候')
        try:
            # Validation is part of the critical section, not a pre-lock snapshot.
            arguments=self._arguments(payload)
            job=dict(id=uuid.uuid4().hex,command='room '+' '.join(arguments),state='running',output='',exit_code=None)
            with self._state_lock:self._job=job
            def execute():
                try:
                    result=self.executor(arguments)
                    result=dict(**result,state='completed' if result['exit_code']==0 else 'failed')
                except Exception as exc:result=dict(state='failed',exit_code=-1,output=str(exc))
                finally:
                    with self._state_lock:self._job.update(result)
                    self._command_lock.release()
            threading.Thread(target=execute,name='agent-room-command',daemon=False).start()
            return deepcopy(job)
        except Exception:self._command_lock.release();raise
