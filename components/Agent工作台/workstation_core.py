"""Unified PC surface over the existing workbench and isolated tool adapter."""
from pathlib import Path
import importlib.util
import json
import os
import queue
import subprocess
import sys
import threading
import time
from workstation_zones import catalog, split_tools, validate_module, AREA

TOOL_ACTIONS=frozenset(('icon_studio','bootstrap','game_list','game_favorite','game_save','game_add','game_add_tool','game_open','materials_choose','materials_open','pick_files','pick_output','pack_previous','pack_start','pack_materials','job_status','job_open','wheel_get','wheel_save','wheel_add','wheel_import','wheel_draw','steam_open'))
INTEGRATION=Path(os.environ.get('WORKSTATION_INTEGRATION_ROOT', str(Path(__file__).resolve().parent.parent / '个人应用联动')))

class ToolProcess:
    def __init__(self,window=lambda:None,test_root=None):
        self.window=window;self.test_root=test_root;self.process=None;self.lock=threading.RLock();self.jobs={};self.active=False;self.responses=queue.Queue();self.pending=False;self.closed=False;self.disconnected=False
    def _start(self):
        if self.process and self.process.poll() is None:return
        executable=Path(sys.executable)
        if executable.name.lower()=='pythonw.exe':executable=executable.with_name('python.exe')
        env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
        env.pop('PC_WORKSTATION_TEST_ROOT',None)
        if self.test_root:env['PC_WORKSTATION_TEST_ROOT']=str(Path(self.test_root).resolve())
        self.process=subprocess.Popen([str(executable),str(Path(__file__).with_name('tool_worker.py'))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',env=env,bufsize=1,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        self.responses=queue.Queue();responses=self.responses;process=self.process
        def read_responses():
            try:
                while True:
                    line=process.stdout.readline(16*1024*1024+1)
                    if not isinstance(line,str) or not line or len(line)>16*1024*1024:
                        responses.put(None);return
                    responses.put(line)
            except (OSError,ValueError):responses.put(None)
        threading.Thread(target=read_responses,name='pc-tool-responses',daemon=True).start()
    def _track(self,data):
        if isinstance(data,dict) and isinstance(data.get('job'),dict):self.jobs[data['job']['id']]=data['job']
    def _disconnect(self):
        self.disconnected=True;self.pending=False
        for job in self.jobs.values():
            if job.get('status') in ('queued','running'):job.update(status='uncertain',error='工具连接中断，请先核对输出；未自动重发。')
    def _recover(self):
        if not self.pending:return
        try:line=self.responses.get_nowait()
        except queue.Empty:return
        if not line:
            self._disconnect();return
        if line:
            try:
                value=json.loads(line)
                if value.get('event')=='dialog':
                    self.process.stdin.write('{"selection":null}\n');self.process.stdin.flush()
                    return
                self._track(value.get('data',{}))
            except OSError:
                self.disconnected=True
                for job in self.jobs.values():
                    if job.get('status') in ('queued','running'):job.update(status='uncertain',error='工具连接中断，请先核对输出；未自动重发。')
                if self.process and self.process.poll() is None:return
            except (ValueError,AttributeError):self._disconnect()
        self.pending=False
    def call(self,action,payload):
        if action=='open_module':validate_module(payload)
        elif action not in TOOL_ACTIONS:raise ValueError('不支持的工具操作')
        with self.lock:
            if self.closed:raise ValueError('工具服务正在退出，不能再接收新操作。')
            if self.disconnected:raise ValueError('工具连接已中断，请先核对上一项输出并重新打开工作台；未自动重发。')
            if self.pending:
                self._recover()
                raise ValueError('上一项工具操作回执尚需核对，请刷新记录；未重复执行。')
            self.active=True
            try:
                self._start();self.process.stdin.write(json.dumps({'action':action,'payload':payload},ensure_ascii=False)+'\n');self.process.stdin.flush()
                while True:
                    try:line=self.responses.get(timeout=60)
                    except queue.Empty:
                        self.pending=True
                        raise ValueError('工具回执超时，请先检查工具记录；未自动重发。') from None
                    if not line:
                        self._disconnect();raise ValueError('工具连接已中断，上一项操作回执未确认；请核对输出并重新打开工作站，未自动重发。')
                    try:
                        value=json.loads(line)
                        if not isinstance(value,dict):raise ValueError()
                    except (ValueError,TypeError):
                        self._disconnect();raise ValueError('工具响应格式无效，操作回执未确认；请核对输出并重新打开工作站。') from None
                    if value.get('event')=='dialog':
                        window=self.window()
                        if window is None:selection=None
                        else:
                            try:selection=window.create_file_dialog(value['kind'],**value.get('options',{}))
                            except Exception:selection=None
                        self.process.stdin.write(json.dumps({'selection':selection},ensure_ascii=False)+'\n');self.process.stdin.flush();continue
                    if not value.get('ok'):raise ValueError(value.get('error','工具操作未完成'))
                    data=value.get('data',{})
                    self._track(data)
                    return data
            except OSError:
                self._disconnect();raise ValueError('工具连接已中断，请核对上一项输出并重新打开工作站；未自动重发。') from None
            finally:self.active=False
    def busy(self):
        if self.active:return True
        self._recover()
        if self.disconnected:return bool(self.process and self.process.poll() is None)
        if self.pending:return True
        if self.process and self.process.poll() is not None:
            for job in self.jobs.values():
                if job.get('status') in ('queued','running'):job.update(status='uncertain',error='工具服务已断开，请检查输出文件，未自动重试。')
            return False
        for identifier,job in list(self.jobs.items()):
            if job.get('status') in ('queued','running'):
                try:self.call('job_status',{'id':identifier})
                except ValueError:return bool(self.pending or self.active or any(j.get('status') in ('queued','running') for j in self.jobs.values()))
        return any(j.get('status') in ('queued','running') for j in self.jobs.values())
    def close(self):
        with self.lock:
            self.closed=True;process=self.process;deferred=False
            def finish_after_exit():
                process.wait()
                for pipe in (process.stdin,process.stdout):
                    if pipe:
                        try:pipe.close()
                        except (OSError,ValueError):pass
            try:
                if process and process.poll() is None:
                    process.stdin.write('{"action":"__close__"}\n');process.stdin.flush()
                    try:process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        deferred=True
                        threading.Thread(target=finish_after_exit,name='pc-tool-graceful-cleanup',daemon=True).start()
            finally:
                if process and not deferred and process.poll() is None:
                    deferred=True
                    threading.Thread(target=finish_after_exit,name='pc-tool-graceful-cleanup',daemon=True).start()
                if process and not deferred:
                    for pipe in (process.stdin,process.stdout):
                        if pipe:
                            try:pipe.close()
                            except (OSError,ValueError):pass
                self.process=None

class WorkstationCore:
    def __init__(self,bridge,tools=None,integration_root=INTEGRATION,town=None):
        self.bridge=bridge;self.tools=tools or ToolProcess(lambda:bridge.station_window);self.integration_root=Path(integration_root)
        from town_adapter import TownAdapter
        self.town=town if town is not None else TownAdapter()
        self._remote_init=threading.Lock()
        self._companion_init=threading.Lock()
        self._room=None;self._room_init=threading.Lock()
        self._artifact_browser=None;self._artifact_init=threading.Lock();self._artifact_dialog=threading.Lock()
    @property
    def artifact_browser(self):
        with self._artifact_init:
            if self._artifact_browser is None:
                from artifact_browser import ArtifactBrowser
                self._artifact_browser=ArtifactBrowser(getattr(self.bridge,'_data_dir',None),opener=getattr(self.bridge,'opener',None))
            return self._artifact_browser
    def _read(self,action,payload,errors):
        result=self.bridge.call(action,payload)
        if not result.get('ok'):
            errors.append(result.get('error','读取失败'));return None
        return result.get('data')
    def overview(self,*,include_today=False):
        from center_index import read_center
        from session_store import SessionStore
        data_dir=getattr(self.bridge,'_data_dir',None);current=read_center(data_dir,include_today=include_today)
        errors=[];tasks=self._read('station_list',{},errors) or []
        sessions=[r for r in SessionStore(Path(data_dir)/'sessions').list() if r['id'] not in current['run_owners']] if data_dir is not None else []
        counts=dict(current['counts'],tasks=len(tasks),collaborations=len(sessions))
        result=dict(tasks=tasks,collaborations=sessions,conversations=current['rows'],counts=counts,scope=current['scope'],limit=100,center_available=not current['warnings'],center_run_ids=list(current['run_owners']),history_scope='旧任务与高级协作仅作历史参考，不计入当前搭档状态',history_warnings=errors,warnings=current['warnings'],errors=current['warnings'])
        if include_today:result['today']=current['today']
        return result
    def artifacts(self):
        errors=[];items=[]
        rows=self._read('station_list',{},errors) or []
        for summary in rows:
            task=self._read('station_get',{'id':summary['id']},errors)
            if not task:continue
            for file in task.get('files',[]):
                items.append({'task_id':task['id'],'title':task['title'],'task_title':task['title'],'name':file['name'],'size':file['size'],'folder':task.get('folder')})
        result=self.artifact_browser.list(items);result['warnings']=errors+result['warnings'];result['errors']=errors;return result
    def call(self,action,payload):
        if action.startswith('workstation_materials_'):
            with self._artifact_init:
                if not hasattr(self,'_materials'):
                    from site_materials_api import MaterialsAPI
                    self._materials=MaterialsAPI(self)
            return self._materials.call(action.removeprefix('workstation_materials_'),payload)
        if action=='workstation_leisure_status':
            if payload:raise ValueError('休闲概况只接受空参数。')
            from reading_room import ReadingRoom
            try:reading=ReadingRoom(self.bridge._data_dir).overview()
            except (ValueError,OSError):reading=dict(counts=None,resume=None,warnings=['书房概况暂不可读，原文件和设置已保留。'])
            return dict(reading=reading,focus=self.town.focus_summary())
        if action.startswith('workstation_reading_'):
            from reading_room import ReadingRoom
            with self._artifact_init:
                if not hasattr(self,'_reading'):self._reading=ReadingRoom(self.bridge._data_dir)
            operation=action.removeprefix('workstation_reading_')
            if operation=='list':
                if payload:raise ValueError('书库列表不接受额外参数。')
                return self._reading.listing()
            if operation=='import':
                if set(payload)-{'kind'} or payload.get('kind','book') not in ('book','audio'):raise ValueError('导入类型无效。')
                if self.bridge.station_window is None:raise ValueError('请在电脑工作站选择文件。')
                if not self._artifact_dialog.acquire(blocking=False):raise ValueError('已有文件选择窗口打开。')
                try:
                    import webview
                    kind=payload.get('kind','book')
                    selected=self.bridge.station_window.create_file_dialog(webview.FileDialog.OPEN,allow_multiple=True,file_types=(('读物 (*.txt;*.md;*.pdf)' if kind=='book' else '音频 (*.mp3;*.wav;*.ogg;*.m4a)'),))
                    if not selected:return dict(self._reading.listing(),cancelled=True)
                    return self._reading.import_paths(list(selected or []),kind)
                finally:self._artifact_dialog.release()
            if operation in ('read','open'):
                if set(payload)!={'id'}:raise ValueError('只能通过书库编号读取。')
                return self._reading.read(payload['id']) if operation=='read' else self._reading.open_copy(payload['id'],self.bridge.opener)
            if operation=='export_notes':
                if set(payload)!={'id'}:raise ValueError('笔记导出只接受书库编号。')
                return self._reading.export_notes(payload['id'])
            if operation=='preferences':
                if payload:raise ValueError('读取偏好不接受额外参数。')
                return self._reading.preferences()
            if operation=='preferences_save':return self._reading.preferences_save(payload)
            if operation=='update':return self._reading.update(payload)
            raise ValueError('未知书房操作。')
        if action=='workstation_butler_status':
            if payload:raise ValueError('个人管家只读接口不接收额外参数。')
            from butler_center import ButlerCenter
            return dict(ButlerCenter(data_dir=self.bridge._data_dir).snapshot(self.overview(include_today=True)),observed_at=time.time(),focus=self.town.focus_summary())
        if action in ('workstation_room_view','workstation_room_enter','workstation_room_heartbeat','workstation_room_leave'):
            fields={'token'} if action in ('workstation_room_heartbeat','workstation_room_leave') else set()
            if set(payload)!=fields or (fields and (not isinstance(payload['token'],str) or len(payload['token'])!=32)):
                raise ValueError('房间仅接受固定的显示交接参数。')
            with self._room_init:
                if self._room is None:
                    from companion_room import RoomPresence
                    self._room=RoomPresence()
            if action=='workstation_room_view':return dict(image=self._room.portrait(),**self.town.room_layout())
            if action=='workstation_room_leave':return self._room.leave(payload['token'])
            if not getattr(self.bridge,'_room_surface_visible',True):
                self._room.leave();raise ValueError('工作站已隐藏，请重新打开房间。')
            return self._room.enter() if action=='workstation_room_enter' else self._room.heartbeat(payload['token'])
        if action in ('workstation_companion_status','workstation_companion_launch','workstation_companion_home','workstation_companion_home_status'):
            if payload:raise ValueError('桌宠入口不接收自定义参数。')
            with self._companion_init:
                if not hasattr(self,'companion'):
                    from companion_adapter import CompanionAdapter
                    self.companion=CompanionAdapter()
            if action=='workstation_companion_home':return self.companion.open_home()
            if action=='workstation_companion_home_status':return self.companion.home_status()
            return self.companion.launch() if action=='workstation_companion_launch' else self.companion.status()
        if action in ('workstation_overview','workstation_artifacts','workstation_diagnostics') and payload:
            raise ValueError('此只读接口不接收额外参数。')
        if action in ('workstation_file_library_status','workstation_file_library_open','workstation_file_library_choose'):
            if payload:raise ValueError('请用电脑文件夹选择框设置共享目录，不接收路径参数。')
            from remote_surface import RemoteSurface
            with self._remote_init:
                if not hasattr(self,'remote'):self.remote=RemoteSurface()
            return self.remote.file_library(open_folder=action=='workstation_file_library_open',choose_folder=action=='workstation_file_library_choose',window=self.bridge.station_window)
        if action in ('workstation_file_roots','workstation_file_root_add','workstation_file_root_remove'):
            from remote_surface import RemoteSurface
            with self._remote_init:
                if not hasattr(self,'remote'):self.remote=RemoteSurface()
            return self.remote.file_roots({'workstation_file_roots':'list','workstation_file_root_add':'add','workstation_file_root_remove':'remove'}[action],self.bridge.station_window,payload)
        if action in ('workstation_remote_status','workstation_remote_start','workstation_tailscale_open'):
            if payload:raise ValueError('远程入口不接收自定义参数。')
            from remote_surface import RemoteSurface
            with self._remote_init:
                if not hasattr(self,'remote'):self.remote=RemoteSurface()
            if action=='workstation_tailscale_open':return self.remote.open_tailscale()
            return self.remote.start() if action=='workstation_remote_start' else self.remote.status()
        if action=='workstation_focus_status':
            if payload:raise ValueError('专注摘要不接收额外参数。')
            return self.town.focus_summary()
        if action=='workstation_town_call':
            if set(payload)-{'action','payload'} or not isinstance(payload.get('payload',{}),dict):raise ValueError('小镇参数无效')
            return self.town.call(payload.get('action'),payload.get('payload',{}))
        if action=='workstation_zones':
            if payload:raise ValueError('分区目录不接收额外参数。')
            return catalog()
        if action=='workstation_open_module':
            if set(payload)-{'id','zone'}:raise ValueError('模块参数无效。')
            identifier=validate_module({'id':payload.get('id')})
            if payload.get('zone',AREA[identifier])!=AREA[identifier]:raise ValueError('模块不属于该分区。')
            return self.tools.call('open_module',{'id':identifier})
        if action=='workstation_overview':return self.overview()
        if action=='workstation_artifacts':return self.artifacts()
        if action in ('workstation_artifact_add_files','workstation_artifact_add_folder'):
            if payload:raise ValueError('请通过本机文件选择窗口添加成果来源')
            if self.bridge.station_window is None:raise ValueError('请在电脑工作站中选择文件')
            import webview
            if not self._artifact_dialog.acquire(blocking=False):raise ValueError('已有成果选择窗口打开')
            try:
                folder=action.endswith('_folder')
                selection=self.bridge.station_window.create_file_dialog(webview.FileDialog.FOLDER if folder else webview.FileDialog.OPEN,allow_multiple=not folder)
                if selection:self.artifact_browser.add([selection] if isinstance(selection,str) else selection,folder)
            finally:self._artifact_dialog.release()
            return self.artifacts()
        if action in ('workstation_artifact_open','workstation_artifact_locate','workstation_artifact_preview','workstation_artifact_source_remove'):
            if set(payload)!={'id'} or not isinstance(payload['id'],str):raise ValueError('成果编号无效')
            identifier=payload['id']
            if action.endswith('_source_remove'):self.artifact_browser.remove(identifier);return self.artifacts()
            if action.endswith('_preview'):return self.artifact_browser.preview(identifier)
            return self.artifact_browser.open(identifier,locate=action.endswith('_locate'))

        if action=='workstation_tools':
            if set(payload)-{'zone'}:raise ValueError('工具目录参数无效。')
            if 'zone' in payload and payload['zone'] not in ('work','leisure','shared'):raise ValueError('未知功能分区。')
            data=self.tools.call('bootstrap',{})
            return split_tools(data,payload['zone']) if 'zone' in payload else data
        if action=='workstation_tool_call':
            if set(payload)-{'action','payload'} or not isinstance(payload.get('payload',{}),dict):raise ValueError('工具参数无效')
            return self.tools.call(payload.get('action'),payload.get('payload',{}))
        if action=='workstation_diagnostics':
            try:
                path=self.integration_root/'ecosystem.py';spec=importlib.util.spec_from_file_location('pc_ecosystem',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                registry=json.loads((self.integration_root/'registry.json').read_text(encoding='utf-8'))
                config=json.loads((self.integration_root/'navigation_config.json').read_text(encoding='utf-8'))
                tree=json.loads(Path(config['index']).read_text(encoding='utf-8'))
                return module.inspect_ecosystem(registry['projects'],tree)
            except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
                raise ValueError('本机维护模块尚未就绪，请检查工作站的本机接入配置。') from None
        raise ValueError('不支持的工作站操作')
    def busy(self):return self.tools.busy()
    def close(self):
        if self._room is not None:self._room.leave()
        try:self.town.close()
        finally:self.tools.close()

Core=WorkstationCore
