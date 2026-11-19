import React,{useEffect,useRef,useState} from 'react';
import {desktopCall} from './workstation-pages.jsx';
import './remote-workspace.css';
import {remoteSurface} from './app-interaction.mjs';

export default function RemoteWorkspace({visible}){
 const [data,setData]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [tab,setTab]=useState('collaboration'),[visited,setVisited]=useState({collaboration:true}),[address,setAddress]=useState('');
 const [lastSurface,setLastSurface]=useState(null);
 const surface=remoteSurface(data,lastSurface);
 const [preview,setPreview]=useState(null),frames=useRef({}),inFlight=useRef(false);
 const [tailscaleBusy,setTailscaleBusy]=useState(false),[notice,setNotice]=useState('');
 const [fileLibrary,setFileLibrary]=useState(null),[fileBusy,setFileBusy]=useState(false);
 async function manageFileLibrary(open=false){
  if(fileBusy)return;setFileBusy(true);setError('');
  try{setFileLibrary(await desktopCall(open==='choose'?'workstation_file_library_choose':open?'workstation_file_library_open':'workstation_file_library_status'));}
  catch(e){setError(e.message);}finally{setFileBusy(false);}
 }
 async function openTailscale(){
  if(inFlight.current)return;
  inFlight.current=true;setTailscaleBusy(true);setError('');setNotice('');
  try{const result=await desktopCall('workstation_tailscale_open');setNotice(result.message);}
  catch(e){setError(e.message);}
  finally{inFlight.current=false;setTailscaleBusy(false);}
 }
 async function refresh(start=false){
  if(inFlight.current)return;
  inFlight.current=true;setBusy(true);setError('');
  try{const next=await desktopCall(start?'workstation_remote_start':'workstation_remote_status');setData(next);if(next.online)setLastSurface(next);}
  catch(e){setError(e.message);}
  finally{inFlight.current=false;setBusy(false);}
 }
 useEffect(()=>{if(!visible)return;const ready=()=>refresh();if(window.pywebview?.api?.call)ready();else window.addEventListener('pywebviewready',ready,{once:true});return()=>window.removeEventListener('pywebviewready',ready);},[visible]);
 const selected=data?.connections?.find(c=>c.address===address)||data?.connections?.[0];
 const syncRemoteTheme=frame=>{
  if(!frame?.contentWindow)return;
  try{const origin=new URL(frame.src).origin;if(origin!=='http://127.0.0.1:8765')return;frame.contentWindow.postMessage({type:'workstation-visual-theme',scheme:document.documentElement.dataset.colorScheme==='dark'?'dark':'light'},origin);}catch{}
 };
 useEffect(()=>{const sync=()=>Object.values(frames.current).forEach(syncRemoteTheme);sync();const observer=new MutationObserver(sync);observer.observe(document.documentElement,{attributes:true,attributeFilter:['data-color-scheme']});return()=>observer.disconnect();},[]);
 function choose(next){setTab(next);setVisited(old=>({...old,[next]:true}));}
 useEffect(()=>{
  const navigate=event=>{
   if(event.origin!=='http://127.0.0.1:8765'||!Object.values(frames.current).some(frame=>frame?.contentWindow===event.source)||event.data?.type!=='remote-workstation-navigation')return;
   if(['sessions','collaboration','transfer'].includes(event.data.page)){choose(event.data.page);return;}
   if(typeof event.data.preview!=='string'||event.data.preview.length>8192||!data?.session_url)return;
   try{const url=new URL(event.data.preview),base=new URL(data.session_url);
    if(url.origin===base.origin&&['/preview-viewer','/file-viewer'].includes(url.pathname)&&url.searchParams.get('token')===base.searchParams.get('token'))setPreview(url.href);
   }catch{}
  };
  window.addEventListener('message',navigate);return()=>window.removeEventListener('message',navigate);
 },[data?.session_url]);
 return <div className="remote-workspace">
  <header className="remote-heading"><div><h1>手机与远程连接</h1><p>扫码连接手机，使用搭档群聊、查看成果和传输文件。</p></div><div className="ws-actions"><button disabled={busy||tailscaleBusy} onClick={openTailscale}>{tailscaleBusy?'正在打开…':'打开 Tailscale'}</button><button disabled={busy||tailscaleBusy} onClick={()=>refresh()}>刷新连接</button>{!data?.online&&<button disabled={busy||tailscaleBusy} onClick={()=>refresh(true)}>启动远程接收器</button>}</div></header>
  {error&&<p role="alert" className="ws-error">{error}</p>}
  {notice&&<p role="status" className="ws-muted">{notice}</p>}
  <div className="remote-status" aria-live="polite">{busy?'正在检查连接…':data?.message||'正在等待桌面服务…'} · 此处检查电脑服务，不代表手机在线 · 工作站网关：{data?.gateway_online?'已连接':'未连接，请正常重启工作站后再检查'}</div>
  <section className="remote-pairing" aria-labelledby="phone-pairing-title">
   <div className="remote-pairing-heading"><div><span className="remote-step">01 · 连接手机</span><h2 id="phone-pairing-title">手机扫码，从这里开始</h2></div><span className={'remote-connection-badge'+(data?.online?' connected':'')}>{data?.online?'接收器已连接':'等待启动接收器'}</span></div>
   <div className="remote-pairing-body">
   {data?.online&&selected?<><div className="remote-qr-box">{selected.qr?<img className="remote-qr" src={selected.qr} alt="手机配对二维码"/>:<p>二维码暂不可用，请刷新连接。</p>}<span>用手机相机扫描</span></div><div className="remote-pairing-guide"><strong>扫码 → 打开手机工作站 → 选择聊天、成果或文件</strong><p>沿用原配对页，在“聊天”内切换搭档群聊或单模型；“成果 / 文件 / 更多”分别查看交付、取用文件和连接说明。原有配对继续有效。</p><label>连接方式 <select aria-label="手机连接方式" value={selected.address} onChange={e=>setAddress(e.target.value)}>{data.connections.map(c=><option key={c.address} value={c.address}>{c.address}</option>)}</select></label><p className="ws-muted">{data.network_state==='connected'?'电脑 Tailscale 已连接；手机端连接及跨网可用性仍需在手机确认。':'同一 Wi-Fi 可直接连接；跨网络时，两端都需要连接 Tailscale。'}</p></div></>:<div className="remote-pairing-empty"><strong>先启动接收器，再用手机扫码</strong><p>点击右上方“启动远程接收器”。连接成功后，二维码会直接显示在这里。</p></div>}
   </div>
   <details className="remote-connection-help"><summary>连接不成功？查看检查步骤</summary><ol><li>确认电脑个人工作站保持打开。</li><li>同一 Wi-Fi 先尝试局域网连接；外出时确认手机和电脑的 Tailscale 都已连接。</li><li>刷新连接，重新扫码。若电脑任务接口显示未连接，正常重开工作站后再检查。</li></ol><p>日常从个人工作站“远程”或原手机配对页进入；旧“远程会话台”窗口仅作兼容入口。接收器独立运行，关闭页面不会停止电脑任务。二维码包含私人配对信息，请勿分享。</p></details>
  </section>
  <details className="remote-connection-help" onToggle={event=>{if(event.currentTarget.open)manageFileLibrary();}}><summary>手机文件库 · 电脑共享文件夹</summary><p>手机直接读取这里的文件，支持图片、文字和 CSV 预览及原件下载。实验结果也可保存到这里；更换目录后，手机重新查找即可。</p><div className="ws-actions"><button disabled={fileBusy} onClick={()=>manageFileLibrary(true)}>打开共享文件夹</button><button disabled={fileBusy} onClick={()=>manageFileLibrary('choose')}>更换共享文件夹</button></div>{fileLibrary&&<p className="ws-muted">{fileLibrary.path} · {fileLibrary.ready?'已接通手机取用':'点击按钮准备文件库'}</p>}</details>
  {surface?<><nav className="remote-tabs" aria-label="远程功能">{[['collaboration','手机工作站'],['sessions','继续电脑会话'],['transfer','文件与文字']].map(([id,label])=><button key={id} aria-current={tab===id?'page':undefined} className={tab===id?'selected':''} onClick={()=>choose(id)}>{label}</button>)}</nav>{!data?.online&&<p role="status" className="remote-offline-notice">连接暂不可用，已保留打开的页面与输入。请刷新连接或启动接收器，恢复后再提交任务。</p>}<div className="remote-content">{[['sessions',surface.session_url,'单模型原会话兼容页'],['collaboration',surface.collaboration_url,'手机工作站：聊天、成果、文件与更多'],['transfer',surface.transfer_url,'远程文件与文字传输']].map(([id,url,title])=>visited[id]&&<iframe key={id} ref={frame=>{frames.current[id]=frame;}} hidden={tab!==id} title={title} onLoad={event=>syncRemoteTheme(event.currentTarget)} src={url+'&desktop_embed=1'} sandbox="allow-scripts allow-same-origin allow-forms allow-downloads" referrerPolicy="no-referrer"/>)}</div></>:<div className="ws-empty">远程接收器未连接。点击“启动远程接收器”即可在当前窗口继续操作。</div>}
  {preview&&<div className="remote-preview" role="dialog" aria-modal="true" aria-label="远程文件预览"><header><strong>文件预览</strong><button autoFocus onClick={()=>setPreview(null)}>关闭预览</button></header><iframe title="远程文件预览" src={preview} sandbox="allow-scripts allow-same-origin allow-forms allow-downloads" referrerPolicy="no-referrer"/></div>}
 </div>;
}
