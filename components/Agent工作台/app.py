"""On-demand native WebView shell for the local room workbench."""
from pathlib import Path
import argparse,ctypes,json,logging,os,shutil,sys,tempfile,threading,time,traceback
BASE=Path(__file__).resolve().parent
CENTER=BASE.parent/'个人工具中心新版'
sys.path.insert(0,str(CENTER/'vendor'))
from backend import Bridge
from room_store import DEFAULT_ROOM
sys.path.append(str(CENTER))
from singleton import SingleInstance
from bridge_boundary import install_boundary
from desktop_chrome import WindowControls, show_workstation

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--quick',action='store_true');parser.add_argument('--background',action='store_true');parser.add_argument('--ui-smoke',action='store_true');parser.add_argument('--smoke-result');parser.add_argument('--smoke-shots',type=Path);parser.add_argument('--room',type=Path,default=DEFAULT_ROOM);args=parser.parse_args()
    import webview
    # Explicit user downloads use WebView's native SaveFileDialog.
    webview.settings['ALLOW_DOWNLOADS']=True
    install_boundary();temp=None
    root=args.room
    if args.ui_smoke:
        temp=tempfile.TemporaryDirectory(prefix='workbench-ui-');root=Path(temp.name)
        for folder in ('room/messages','card','drafts','persona','bin'):(root/folder).mkdir(parents=True,exist_ok=True)
        for relative in ('PROTOCOL.md','persona/conductor.md','room/brief.md','room/turn.md'):
            shutil.copy2(args.room/relative,root/relative)
        for path in (args.room/'bin').glob('*.ps1'):shutil.copy2(path,root/'bin'/path.name)
    from quick_window import QuickWindow,request_quick
    if args.quick and not args.ui_smoke and request_quick(BASE):return
    quick=None;remote_gateway=None
    bridge=None
    holder={};ready=threading.Event();close_pending=threading.Event()
    def show():
        if ready.wait(10):
            try:show_workstation(holder['window'])
            except Exception:logging.exception('Cannot show workbench')
    instance=SingleInstance(BASE if not temp else root,show)
    try:
        if not instance.acquire(notify=not args.background):
            if args.quick:
                for _ in range(20):
                    if request_quick(BASE):break
                    time.sleep(.2)
            return
        bridge=Bridge(root,data_dir=root/'app-data' if temp else BASE/'data')
        bridge.companion_ui_ready=ready
        bridge._room_surface_visible=not (args.background or args.quick)
        if temp:
            from workstation_core import WorkstationCore,ToolProcess
            from town_adapter import TownAdapter
            tool_fixture=root/'tools-fixture'
            for folder in ('个人工具中心/data','个人工具中心新版/data','游戏管家/data'):(tool_fixture/folder).mkdir(parents=True,exist_ok=True)
            bridge._workstation=WorkstationCore(bridge,tools=ToolProcess(lambda:holder.get('window'),test_root=tool_fixture))
            bridge._workstation.town=TownAdapter(base=root/'town-fixture')
            from remote_surface import RemoteSurface
            def remote_offline(url):raise OSError('isolated UI fixture')
            tailscale_fixture=root/'tailscale-ipn.exe';tailscale_fixture.write_bytes(b'UI fixture, never execute')
            bridge._workstation.remote=RemoteSurface(root/'remote-fixture',fetch=remote_offline,tailscale_path=tailscale_fixture,opener=lambda path:None)
            from companion_adapter import CompanionAdapter
            from types import SimpleNamespace
            pet_fixture=root/'pet-fixture';pet_fixture.mkdir()
            (pet_fixture/'workbench_link.json').write_text(json.dumps({'workbench_root':str(root/'app-data')}),encoding='utf-8')
            pet_entry=pet_fixture/'pet.lnk';pet_entry.write_bytes(b'isolated fixture, never execute')
            fixture_launcher=SimpleNamespace(entry=lambda:pet_entry,launch=lambda:{'action':'requested'})
            bridge._workstation.companion=CompanionAdapter(pet_fixture,root/'app-data',launcher=fixture_launcher)
            from companion_room import RoomPresence
            bridge._workstation._room=RoomPresence(pet_fixture)
            image=pet_fixture/'web/appearances/dragon/01-idle.png';image.parent.mkdir(parents=True)
            shutil.copy2(BASE/'examples/neutral.png',image)
        if not args.ui_smoke:
            try:
                from remote_gateway import RemoteGateway
                remote_gateway=RemoteGateway(bridge,BASE/'data').start()
            except Exception:
                logging.warning('Remote gateway unavailable; desktop remains usable')
            from app_link_client import start_heartbeat
            start_heartbeat(BASE)
        entry=BASE/'frontend/dist/index.html'
        if not entry.is_file():raise RuntimeError('工作台前端尚未构建')
        window=webview.create_window('Agent 工作台',str(entry),width=1320,height=860,min_size=(850,640),hidden=args.quick or args.background,background_color='#edf3f9',text_select=True,frameless=True,easy_drag=False)
        chrome=WindowControls(window).install(bridge)
        from workstation_tray import WorkstationTray
        chrome.tray=WorkstationTray(window,BASE/'assets/station.ico')
        window.events.closed+=chrome.tray.dispose
        holder['window']=window;window.expose(bridge.call);window.events.loaded+=lambda:ready.set()
        bridge.station_window=window
        quick=QuickWindow(BASE,bridge,window,ready,enable_signal=not args.ui_smoke)
        bridge.ui_actions['appearance_changed']=lambda values:(chrome.theme_changed(values),quick.sync_appearance())
        if args.quick:window.events.loaded+=lambda:threading.Thread(target=quick.open,daemon=True).start()
        def save_export(filename,text):
            selection=window.create_file_dialog(webview.FileDialog.SAVE,save_filename=filename,file_types=('JSON (*.json)',))
            if not selection:return False
            target=Path(selection if isinstance(selection,str) else selection[0])
            target.write_text(text,encoding='utf-8');return True
        bridge.export_saver=save_export
        def pause_town():
            if bridge._workstation is None:return True
            try:bridge._workstation.town.close();return True
            except Exception:
                logging.exception('Town state could not be saved before close')
                return ctypes.windll.user32.MessageBoxW(0,'小镇状态未能保存，可能已被另一个窗口修改。\n是否保留磁盘上已有存档并退出？本窗口未保存的小镇状态将不会写入。\n选择“否”可留在工作站检查。','小镇存档需要检查',0x134)==6
        def closing():
            if bridge._api_active():
                if close_pending.is_set():return False
                answer=ctypes.windll.user32.MessageBoxW(0,'模型仍在回复。是否停止并关闭？\n选择“否”可继续等待。已发送请求可能仍由服务商计费。','Agent 工作台',0x24)
                if answer==6:
                    close_pending.set();bridge._stop_api()
                    def after_stop():
                        while bridge.busy():time.sleep(.1)
                        if pause_town():window.destroy()
                        else:close_pending.clear()
                    threading.Thread(target=after_stop,name='close-after-model-stop',daemon=True).start()
                return False
            if bridge.busy():
                ctypes.windll.user32.MessageBoxW(0,'本地操作正在执行，请稍候再关闭。','Agent 工作台',0x40);return False
            if not pause_town():return False
            if quick:quick.close()
            return True
        window.events.closing+=closing
        def smoke():
            if args.background:
                try:
                    if not ready.wait(25):raise RuntimeError('background page not ready')
                    result={'hidden':not bool(window.native.Visible),'roomSurfaceVisible':bridge._room_surface_visible,'navigationReady':ready.is_set(),'townBootstrap':bridge.call('workstation_town_call',{'action':'bootstrap','payload':{}}).get('ok') is True}
                    if args.smoke_result:Path(args.smoke_result).write_text(json.dumps(result),encoding='utf8')
                finally:window.destroy()
                return
            result={};done=threading.Event()
            try:
                window.events.loaded.wait(25);time.sleep(1)
                def receive(value):result.update(value);done.set()
                script="""(async()=>{const r=await window.pywebview.api.call('snapshot',{});return {bridge:r.ok,mode:r.data?.mode,holder:r.data?.turn?.holder,title:document.title,body:document.body.innerText,rootChildren:document.querySelector('#root').childElementCount,overflow:document.documentElement.scrollWidth>innerWidth}})()"""
                checks=BASE/'tests/single_window_smoke.js'
                if checks.is_file():script='(async()=>{const baseline=await '+script+';const checks=await '+checks.read_text(encoding='utf-8')+';return {...baseline,...checks};})()'
                window.evaluate_js(script,callback=receive)
                if not done.wait(50):raise RuntimeError('原生界面没有返回验证结果')
                if not result.get('error'):
                    result['icon_studio_same_native_window']=len(webview.windows)==1
                    start_x,start_y=window.x,window.y
                    drag_script="""(()=>{const target=document.querySelector('.app-breadcrumb-drag strong');target.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,clientX:100,clientY:64}));window.dispatchEvent(new MouseEvent('mousemove',{screenX:%d,screenY:%d}));window.dispatchEvent(new MouseEvent('mouseup'));return true;})()""" % (start_x+145,start_y+89)
                    try:
                        window.evaluate_js(drag_script)
                        for _ in range(30):
                            if abs(window.x-start_x)>5 or abs(window.y-start_y)>5:break
                            time.sleep(.05)
                        result['native_breadcrumb_drag_moves_window']=abs(window.x-start_x)>5 or abs(window.y-start_y)>5
                        if not result['native_breadcrumb_drag_moves_window']:raise RuntimeError('路径栏拖动未移动原生窗口')
                    finally:window.move(start_x,start_y)
                    if window.evaluate_js('document.documentElement.dataset.colorScheme')!='dark':
                        window.evaluate_js("document.querySelector('.theme-scheme-toggle').click()")
                    for _ in range(60):
                        if window.evaluate_js('document.documentElement.dataset.colorScheme')=='dark':break
                        time.sleep(.05)
                    quick.open()
                    if not quick.window.events.loaded.wait(15):raise RuntimeError('快捷栏主题验收启动超时')
                    for _ in range(60):
                        if quick.window.evaluate_js('document.documentElement.dataset.colorScheme')=='dark':break
                        time.sleep(.05)
                    else:raise RuntimeError('快捷栏首次加载未采用已保存深色主题')
                    result['quick_first_open_dark']=True
                    for scheme in ('dark','light'):
                        if window.evaluate_js('document.documentElement.dataset.colorScheme')!=scheme:
                            window.evaluate_js("document.querySelector('.theme-scheme-toggle').click()")
                        for _ in range(60):
                            if quick.window.evaluate_js('document.documentElement.dataset.colorScheme')==scheme:break
                            time.sleep(.05)
                        else:raise RuntimeError('快捷栏主题未同步')
                        result['quick_'+scheme+'_background']=quick.window.evaluate_js("getComputedStyle(document.querySelector('.quick-shell')).backgroundColor")
                        if args.smoke_shots:
                            sys.path.insert(0,str(BASE/'tests'))
                            from native_theme_capture import capture
                            capture(quick.window,args.smoke_shots/('quick-'+scheme+'.png'))
                    result['quick_theme_sync']=True;quick.hide()
                    chrome.action({'action':'toggle_maximize'});time.sleep(.35)
                    result['native_maximize']=chrome.state()['maximized']
                    chrome.action({'action':'toggle_maximize'});time.sleep(.25)
                    result['native_restore']=not chrome.state()['maximized']
                    chrome.action({'action':'minimize'});time.sleep(.2)
                    result['native_minimize']=str(window.native.WindowState)=='Minimized'
                    window.restore();time.sleep(.25)
                    get=ctypes.windll.user32.GetWindowLongPtrW
                    get.argtypes=[ctypes.c_void_p,ctypes.c_int];get.restype=ctypes.c_ssize_t
                    style=get(int(window.native.Handle.ToInt64()),-16)
                    result['native_caption_removed']=not bool(style & 0x00C00000)
                    result['native_resize_frame']=bool(style & 0x00040000)
                probe=BASE/'tests/layout_probe.js'
                if probe.is_file() and not result.get('error'):
                    for label,width,height in [('compact',850,700),('desktop',1320,860)]:
                        window.resize(width,height);time.sleep(.3);done.clear()
                        def layout_receive(value,key=label):result[key+'_layout']=value;done.set()
                        window.evaluate_js(probe.read_text(encoding='utf-8'),callback=layout_receive)
                        if not done.wait(18):raise RuntimeError('布局尺寸验收超时：'+label)
                if args.smoke_shots and not result.get('error'):
                    sys.path.insert(0,str(BASE/'tests'))
                    from native_theme_capture import capture
                    window.resize(1320,860);time.sleep(.3)
                    window.evaluate_js("document.querySelector('.app-nav-item[aria-label=个人管家]')?.click()")
                    time.sleep(.5)
                    for scheme in ('dark','light'):
                        if window.evaluate_js("document.documentElement.dataset.colorScheme")!=scheme:
                            window.evaluate_js("document.querySelector('.theme-scheme-toggle')?.click()")
                        for _ in range(60):
                            if window.evaluate_js("document.documentElement.dataset.colorScheme")==scheme:break
                            time.sleep(.05)
                        else:raise RuntimeError('主题截图等待切换超时')
                        time.sleep(.3)
                        capture(window,args.smoke_shots/(scheme+'-personal-center.png'))
            except Exception as exc:result['error']=str(exc)
            finally:
                if args.smoke_result:Path(args.smoke_result).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                window.destroy()
        webview.start(smoke if args.ui_smoke else None,gui='edgechromium',debug=False,private_mode=True,storage_path=str((root if temp else BASE)/'data/webview'))
    finally:
        if remote_gateway:remote_gateway.close()
        if quick:quick.close()
        try:
            if bridge is not None:
                bridge._stop_api()
                bridge.close_station()
                bridge.close_workstation()
        except Exception:
            logging.exception('Workstation tool cleanup did not complete')
        finally:
            instance.close()
            if temp:temp.cleanup()

if __name__=='__main__':
    try:main()
    except Exception as exc:
        if sys.stderr:traceback.print_exc()
        if '--ui-smoke' not in sys.argv and '--background' not in sys.argv:ctypes.windll.user32.MessageBoxW(0,str(exc),'Agent 工作台启动失败',0x10)
        raise SystemExit(1)
