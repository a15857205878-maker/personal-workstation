import React,{useEffect,useRef,useState} from 'react';
import {desktopCall} from './workstation-pages.jsx';
import {sessionEmbedUrl,previewUrl} from './partner-model.mjs';

export default function PartnerPage({visible,forceDual,onNavigate,children}){
 const [choice,setChoice]=useState('single'),[data,setData]=useState(null),[lastUrl,setLastUrl]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[preview,setPreview]=useState('');
 const frame=useRef(null),inflight=useRef(false),alive=useRef(true);
 const dual=forceDual||choice==='dual';
 async function refresh(){if(inflight.current)return;inflight.current=true;setBusy(true);setError('');try{const next=await desktopCall('workstation_remote_status');if(!alive.current)return;setData(next);const url=next.online&&sessionEmbedUrl(next.session_url);if(url)setLastUrl(url);else if(next.online)setError('会话地址不可用，请在连接与设置中检查接收器。');}catch(e){if(alive.current)setError(e.message);}finally{inflight.current=false;if(alive.current)setBusy(false);}}
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 useEffect(()=>{if(!visible)return;const ready=()=>refresh();if(window.pywebview?.api?.call)ready();else window.addEventListener('pywebviewready',ready,{once:true});return()=>window.removeEventListener('pywebviewready',ready);},[visible]);
 function syncTheme(){
  const embed=frame.current,sidebar=document.querySelector('.partner-shell .app-sidebar');
  if(!embed?.contentWindow||!lastUrl)return;
  const rect=embed.getBoundingClientRect(),side=sidebar?.getBoundingClientRect();
  const scenery=side&&rect.width>0?{offset:rect.left-side.left,bottom:side.bottom-rect.bottom}:undefined;
  embed.contentWindow.postMessage({type:'workstation-visual-theme',scheme:document.documentElement.dataset.colorScheme==='dark'?'dark':'light',scenery},'http://127.0.0.1:8765');
 }
 useEffect(()=>{syncTheme();const observer=new MutationObserver(syncTheme);observer.observe(document.documentElement,{attributes:true,attributeFilter:['data-color-scheme']});
  const size=new ResizeObserver(syncTheme);if(frame.current)size.observe(frame.current);const sidebar=document.querySelector('.partner-shell .app-sidebar');if(sidebar)size.observe(sidebar);
  window.addEventListener('resize',syncTheme);return()=>{observer.disconnect();size.disconnect();window.removeEventListener('resize',syncTheme);};},[lastUrl]);
 useEffect(()=>{function message(event){if(event.origin!=='http://127.0.0.1:8765'||event.source!==frame.current?.contentWindow||event.data?.type!=='remote-workstation-navigation')return;const url=previewUrl(event.data.preview,lastUrl);if(url)setPreview(url);}window.addEventListener('message',message);return()=>window.removeEventListener('message',message);},[lastUrl]);
 return <div className="partner-page"><header className="partner-heading"><div className="partner-heading-title"><i className="partner-icon partner-icon-brand" aria-hidden="true"/><strong>搭档</strong></div><div className="partner-model-choice" aria-label="执行方式"><button aria-pressed={!dual} onClick={()=>{setChoice('single');if(forceDual)onNavigate('partner');}}>单模型</button><button aria-pressed={dual} onClick={()=>setChoice('dual')}>双模型</button></div><span className={'partner-connection '+(data?.online?'connected':'')}>{data?.online?'接收器已连接':'接收器未连接'}</span><button className="auto-button" disabled={busy} onClick={refresh}>{busy?'检查中…':'刷新连接'}</button></header>
 {error&&<p className="auto-warning" role="alert">{error}</p>}
 <div className="partner-single" hidden={dual}>{lastUrl?<><p className="partner-session-hint">原会话 · 沿用所选模型的权限、附件与回执{!data?.online?' · 当前离线，已保留输入与页面':''}</p><iframe ref={frame} title="搭档原模型会话" src={lastUrl} onLoad={syncTheme} sandbox="allow-scripts allow-same-origin allow-forms allow-downloads" referrerPolicy="no-referrer"/></>:<div className="partner-welcome"><i className="partner-icon partner-icon-brand" aria-hidden="true"/><h1>今天，一起完成什么？</h1><p>单模型直接继续原模型会话；双模型由执行和审查两席协作。</p><div className="partner-templates">{[['docx','文档'],['xlsx','Excel'],['pptx','PPTX'],['web','网页']].map(([id,label])=><div key={id}><i className={'partner-icon partner-icon-'+id} aria-hidden="true"/><span>{label}</span></div>)}</div><div className="partner-offline"><strong>先连接已有会话服务</strong><p>接收器尚未运行。请到连接页手动点击“启动远程接收器”，再回来刷新。不会自动启动服务或发送任务。</p><button className="auto-button" onClick={()=>onNavigate('remote')}>打开连接与设置</button><button className="auto-button" onClick={()=>setChoice('dual')}>准备双模型任务</button></div></div>}</div>
 <div className="partner-dual" hidden={!dual}>{children(visible&&dual)}</div>
 {preview&&<div className="remote-preview" role="dialog" aria-modal="true" aria-label="搭档文件预览"><header><strong>文件预览</strong><button autoFocus onClick={()=>setPreview('')}>关闭预览</button></header><iframe title="搭档文件预览" src={preview} sandbox="allow-scripts allow-same-origin allow-forms allow-downloads" referrerPolicy="no-referrer"/></div>}
 </div>;
}
