"""Standalone unified town/focus window; local assets and no legacy-save import."""
from pathlib import Path
from logging.handlers import RotatingFileHandler
import argparse,ctypes,json,logging,sys,tempfile,threading,time,traceback

BASE=Path(__file__).resolve().parent
VENDOR=BASE.parent/'个人工具中心新版/vendor'
sys.path.insert(0,str(VENDOR))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--smoke-test',action='store_true');parser.add_argument('--smoke-result');args=parser.parse_args()
    logs=BASE/'logs';logs.mkdir(parents=True,exist_ok=True)
    handler=RotatingFileHandler(logs/'app.log',maxBytes=700_000,backupCount=2,encoding='utf-8');handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logging.getLogger().setLevel(logging.INFO);logging.getLogger().addHandler(handler)
    import webview
    from bridge_boundary import install_boundary
    from singleton import SingleInstance
    from town_backend import Bridge
    install_boundary();ready=threading.Event();holder={};temporary=None
    def show():
        if ready.wait(10):
            try:holder['window'].restore();holder['window'].show()
            except Exception:logging.exception('Could not restore town window')
    instance=SingleInstance(BASE,show)
    try:
        if not args.smoke_test and not instance.acquire():return
        entry=BASE/'frontend/dist/index.html'
        if not entry.is_file():raise OSError('新版界面尚未构建，请查看使用说明。')
        data_base=BASE
        if args.smoke_test:
            temporary=tempfile.TemporaryDirectory(prefix='town-smoke-',dir=BASE/'tests');data_base=Path(temporary.name)
        logging.info('Preparing town state')
        bridge=Bridge(data_base)
        native=webview.create_window('宝可梦小镇与专注',url=str(entry),width=1280,height=850,min_size=(960,680),background_color='#f7f7ee',text_select=True)
        def close_town():native.destroy()
        native.expose(bridge.call,close_town);holder['window']=native
        def shown():ready.set();logging.info('Town window shown')
        native.events.shown+=shown
        def closing():
            try:bridge._pause_for_close();return True
            except Exception as exc:
                logging.exception('Close save failed')
                ctypes.windll.user32.MessageBoxW(0,'保存未完成，窗口已保留。\n'+str(exc),'小镇进度未保存',0x30);return False
        native.events.closing+=closing
        def smoke():
            output=Path(args.smoke_result or BASE/'tests/ui-smoke.json')
            try:
                native.events.loaded.wait(25);time.sleep(.7)
                event=threading.Event();values={}
                def received(value):values['result']=value;event.set()
                native.evaluate_js("""(async()=>{
                    const r=await window.pywebview.api.call('bootstrap',{});
                    for(let i=0;i<140&&!document.querySelector('iframe')?.contentWindow?.yardScene?.ready;i++)await new Promise(resolve=>setTimeout(resolve,50));
                    const frame=document.querySelector('iframe');if(!frame?.contentWindow?.yardScene?.ready)throw Error('未打开新场景');
                    const yard=frame.contentDocument;yard.querySelector('[data-tool="shop"]').click();
                    for(let i=0;i<80&&!yard.querySelector('#town-sheet h2');i++)await new Promise(resolve=>setTimeout(resolve,50));
                    const shopRendered=yard.querySelector('#town-sheet h2')?.textContent==='杂货铺';
                    for(let i=0;i<100&&frame.contentWindow.yardScene.getState().careBusy;i++)await new Promise(resolve=>setTimeout(resolve,50));yard.querySelector('#town-sheet button')?.click();yard.getElementById('home').click();
                    for(let i=0;i<100&&!document.querySelector('.focus-console');i++)await new Promise(resolve=>setTimeout(resolve,50));
                    return {ok:r.ok,version:r.data?.app?.version,berries:r.data?.town?.berries,shopRendered,focusRendered:!!document.querySelector('.focus-console'),legacyManagerPresent:document.body.innerText.includes('管理小镇')};
                })()""",callback=received)
                if not event.wait(15):raise OSError('前端与桌面接口尚未连接')
                output.write_text(json.dumps(values['result'],ensure_ascii=False,indent=2),encoding='utf-8')
            except Exception as exc:output.write_text(json.dumps(dict(error=str(exc)),ensure_ascii=False),encoding='utf-8')
            finally:native.destroy()
        profile=data_base/'data/webview'
        logging.info('Starting WebView2')
        webview.start(smoke if args.smoke_test else None,gui='edgechromium',http_server=True,debug=False,private_mode=False,storage_path=str(profile),icon=str(BASE/'assets/app.ico'))
    finally:
        instance.close()
        if temporary:
            try:temporary.cleanup()
            except OSError:logging.warning('WebView test cache is temporarily in use; source data is unaffected')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        logging.exception('Town startup failed')
        if sys.stderr is not None:traceback.print_exc()
        if '--smoke-test' not in sys.argv:ctypes.windll.user32.MessageBoxW(0,'小镇暂时无法打开：\n'+str(exc)+'\n详细日志位于新版小镇 logs/app.log。','小镇启动失败',0x10)
        raise SystemExit(1)
