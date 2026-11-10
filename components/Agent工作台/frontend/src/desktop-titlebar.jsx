import React,{useEffect,useRef,useState} from 'react';
import {Command,Minus,Square,Copy,X,PanelBottomClose} from 'lucide-react';
import ThemePicker from './theme-picker.jsx';

// The native shell owns the window. A failed call must never look like success.
export async function windowAction(action){
 const api=window.pywebview?.api;
 if(!api||typeof api.call!=='function')throw Error('原生窗口服务未就绪，请重启工作站。');
 const result=await api.call('api_window_action',{action});
 if(result?.ok===false)throw Error(result.error||'窗口操作未完成，请重试。');
 const data=result?.data??result??{};
 if(data&&typeof data.maximized!=='boolean'&&typeof result?.maximized==='boolean')data.maximized=result.maximized;
 return data;
}

export function maximizedFrom(value,fallback=false){
 return value&&typeof value.maximized==='boolean'?value.maximized:fallback;
}

export default function DesktopTitlebar(){
 const [maximized,setMaximized]=useState(false),[busy,setBusy]=useState(''),[error,setError]=useState('');
 const mounted=useRef(true);
 useEffect(()=>()=>{mounted.current=false;},[]);
 useEffect(()=>{
  let live=true;
  const sync=event=>{if(live)setMaximized(maximizedFrom(event?.detail,false));};
  window.addEventListener('window-workstation-state',sync);
  windowAction('state').then(data=>{if(live)setMaximized(maximizedFrom(data,false));}).catch(()=>{});
  return()=>{live=false;window.removeEventListener('window-workstation-state',sync);};
 },[]);
 async function run(action){
  if(busy)return;
  setBusy(action);setError('');
  try{const data=await windowAction(action);if(mounted.current&&action!=='close')setMaximized(maximizedFrom(data,maximized));}
  catch(e){if(mounted.current)setError(e.message||'窗口操作失败，请重试。');}
  finally{if(mounted.current)setBusy('');}
 }
 const toggle=()=>run('toggle_maximize');
 const maximizeLabel=maximized?'还原窗口':'最大化窗口';
 return <>
  <header className="desktop-titlebar">
   <div className="desktop-drag-region pywebview-drag-region" onDoubleClick={toggle} title="拖动窗口；双击最大化或还原">
    <span className="desktop-brand-mark" aria-hidden="true"><Command size={13}/></span>
    <strong className="desktop-brand-name">个人工作站</strong>
   </div>
   <div className="desktop-titlebar-tools">
    <ThemePicker/>
    <div className="desktop-window-buttons" onDoubleClick={event=>event.stopPropagation()}>
     <button type="button" className="desktop-window-button" aria-label="收起到托盘" title="收起到托盘（后台继续运行）" disabled={!!busy} onClick={()=>run('tray')}><PanelBottomClose size={14} aria-hidden="true"/></button>
     <button type="button" className="desktop-window-button" aria-label="最小化窗口" title="最小化" disabled={!!busy} onClick={()=>run('minimize')}><Minus size={14} aria-hidden="true"/></button>
     <button type="button" className="desktop-window-button" aria-label={maximizeLabel} title={maximizeLabel} disabled={!!busy} onClick={toggle}>{maximized?<Copy size={12} aria-hidden="true"/>:<Square size={12} aria-hidden="true"/>}</button>
     <button type="button" className="desktop-window-button is-close" aria-label="关闭窗口" title="关闭" disabled={!!busy} onClick={()=>run('close')}><X size={14} aria-hidden="true"/></button>
    </div>
   </div>
  </header>
  {error&&<div className="desktop-window-error" role="alert"><span>{error}</span><button type="button" aria-label="关闭提示" onClick={()=>setError('')}>×</button></div>}
 </>;
}
