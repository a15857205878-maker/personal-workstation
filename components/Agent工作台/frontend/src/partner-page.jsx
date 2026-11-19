import React,{useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {PanelLeftClose,PanelLeftOpen,Search,SlidersHorizontal} from 'lucide-react';
import {desktopCall} from './workstation-pages.jsx';
import {sessionEmbedUrl,previewUrl} from './partner-model.mjs';
import {PreviewDialog} from './feedback-dialog.jsx';
import {filterConversations} from './conversation-operations.mjs';
import ThemePicker from './theme-picker.jsx';

const receiverOrigin='http://127.0.0.1:8765';
const singleModels={codex:'Codex',deepseek:'DeepSeek'};
const emptyCollaboration={rows:[],active:'',ready:false,locked:true,creationLocked:true};

function HistoryRail({single,collaboration,dual,open,closeControl,onClose,onSingleAction,onPickSingle,onPickCollaboration}){
 const [searchOpen,setSearchOpen]=useState(false);
 const [query,setQuery]=useState(''),[scope,setScope]=useState('active');
 const search=useRef(null),sentQuery=useRef('');
 useEffect(()=>{if(searchOpen&&open)search.current?.focus();},[open,searchOpen]);
 function sendSearch(value){
  if(!single||single.busy||sentQuery.current===value)return;
  sentQuery.current=value;
  onSingleAction('search',value);
 }
 useEffect(()=>{
  if(!single){sentQuery.current='';return;}
  if(single.busy)return;
  const timer=setTimeout(()=>sendSearch(query.trim()),250);
  return()=>clearTimeout(timer);
 },[query,!!single,single?.busy]);
 const modelGroups=Object.entries(single?.groups||{});
 const q=query.trim().toLocaleLowerCase();
 const singleRows=modelGroups.flatMap(([model,group])=>group.rows.filter(row=>row.title.toLocaleLowerCase().includes(q)).map(row=>({...row,model})))
  .sort((left,right)=>(right.updated||0)-(left.updated||0));
 const collaborationRows=filterConversations(collaboration.rows,query,scope);
 return <section className="center-history" aria-label="会话列表" id="partner-conversations" data-open={open||undefined} hidden={!open}
  onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();onClose();}}}>
  <div className="center-history-head"><strong>会话</strong>
   <button className="auto-button center-history-new" title={dual?'新建协作会话':'新建单模型会话'} disabled={dual?collaboration.creationLocked:!single||single.busy} onClick={()=>dual?onPickCollaboration():onSingleAction('new')}>＋ 新建</button>
   <div className="center-history-actions">
    <button className="auto-button" aria-label="搜索与筛选" aria-expanded={searchOpen} onClick={()=>setSearchOpen(value=>!value)}><Search size={15}/></button>
    <button ref={closeControl} className="auto-button" aria-label="收起会话列表" onClick={onClose}><PanelLeftClose size={16}/></button>
   </div>
  </div>
  <div className="center-history-filters" hidden={!searchOpen}>
   <form className="single-history-search" onSubmit={event=>{event.preventDefault();sendSearch(query.trim());}}>
    <input ref={search} aria-label="搜索会话名称" placeholder="搜索会话" maxLength={120} value={query} onChange={event=>setQuery(event.target.value)}/>
    <button className="auto-button" type="submit">搜索</button>
   </form>
   <label className="single-history-model"><span>协作</span><select aria-label="会话列表范围" value={scope} onChange={event=>setScope(event.target.value)}><option value="active">未归档</option><option value="archived">已归档</option><option value="all">全部</option></select></label>
   {single&&<label className="single-history-model"><span>模型</span><select aria-label="单模型选择" value={single.model} disabled={single.busy} onChange={event=>onSingleAction('model',event.target.value)}><option value="codex">Codex</option><option value="deepseek">DeepSeek</option></select></label>}
  </div>
  {!searchOpen&&(q||scope!=='active')&&<button className="auto-link center-clear-history-filter" onClick={()=>{setQuery('');setScope('active');}}>清除筛选</button>}
  <details className="partner-history-group" open>
   <summary>单模型</summary>
   <div className="center-history-items partner-history-rows">
    {singleRows.map(row=>{const current=!dual&&row.key===single.active;return <button key={row.model+':'+row.key} title={row.title} className={'center-session'+(current?' is-current':'')} aria-current={current?'true':undefined} disabled={single.busy&&row.key!==single.active} onClick={()=>onPickSingle(row)}><strong>{row.title}</strong><small>{singleModels[row.model]}</small></button>;})}
    {!singleRows.length&&<p className="auto-small" role="status">{!single?'连接会话服务后显示记录':modelGroups.some(([,group])=>group.loading)?'正在读取会话…':q?'没有匹配的会话':'还没有会话'}</p>}
    {modelGroups.filter(([,group])=>group.more&&!group.loading).map(([model])=><button key={model} className="auto-link partner-history-more" disabled={single.busy} onClick={()=>onSingleAction('more',model)}>更多 {singleModels[model]} 会话</button>)}
   </div>
  </details>
  <details className="partner-history-group" open>
   <summary>协作中心</summary>
   <div className="center-history-items partner-history-rows">
    {collaborationRows.map(row=>{const current=dual&&row.id===collaboration.active;return <button key={row.id} title={row.title} className={'center-session'+(current?' is-current':'')} aria-current={current?'true':undefined} disabled={collaboration.locked&&row.id!==collaboration.active} onClick={()=>onPickCollaboration(row.id)}><strong>{row.title}</strong>{row.archived&&<small>已归档</small>}</button>;})}
    {!collaborationRows.length&&<p className="auto-small" role="status">{!collaboration.ready?'正在读取会话…':q||scope!=='active'?'没有匹配的会话':'还没有会话'}</p>}
   </div>
  </details>
 </section>;
}

export default function PartnerPage({visible,forceDual,onNavigate,conversationSlot,children}){
 const [choice,setChoice]=useState('dual'),[data,setData]=useState(null),[lastUrl,setLastUrl]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[preview,setPreview]=useState('');
 const [history,setHistory]=useState(null),[railOpen,setRailOpen]=useState(()=>!window.matchMedia('(max-width:1020px)').matches);
 const [backgroundOpen,setBackgroundOpen]=useState(false),backgroundButton=useRef(null);
 const [collaboration,setCollaboration]=useState(emptyCollaboration),[historyIntent,setHistoryIntent]=useState(null);
 const frame=useRef(null),inflight=useRef(false),alive=useRef(true),railToggle=useRef(null),railClose=useRef(null),historySequence=useRef(0);
 const dual=forceDual||choice==='dual';
 async function refresh(){if(inflight.current)return;inflight.current=true;setBusy(true);setError('');try{const next=await desktopCall('workstation_remote_status');if(!alive.current)return;setData(next);const url=next.online&&sessionEmbedUrl(next.session_url);if(url)setLastUrl(url);else if(next.online)setError('会话地址不可用，请在连接与设置中检查接收器。');}catch(e){if(alive.current)setError(e.message);}finally{inflight.current=false;if(alive.current)setBusy(false);}}
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 useEffect(()=>{
  const media=window.matchMedia('(max-width:1020px)');
  const update=()=>setRailOpen(!media.matches);
  media.addEventListener('change',update);
  return()=>media.removeEventListener('change',update);
 },[]);
 useEffect(()=>{if(!visible)return;const ready=()=>refresh();if(window.pywebview?.api?.call)ready();else window.addEventListener('pywebviewready',ready,{once:true});return()=>window.removeEventListener('pywebviewready',ready);},[visible]);
 function syncTheme(){
  const embed=frame.current,sidebar=document.querySelector('.partner-shell .app-sidebar');
  if(!embed?.contentWindow||!lastUrl)return;
  const rect=embed.getBoundingClientRect(),side=sidebar?.getBoundingClientRect();
  const scenery=side&&rect.width>0?{offset:rect.left-side.left,bottom:side.bottom-rect.bottom}:undefined;
  embed.contentWindow.postMessage({type:'workstation-visual-theme',scheme:document.documentElement.dataset.colorScheme==='dark'?'dark':'light',skin:'messenger',chat_background:document.documentElement.dataset.chatBackground||'auto',background_strength:Number(document.documentElement.dataset.backgroundStrength??35),scenery},'http://127.0.0.1:8765');
 }
 useEffect(()=>{syncTheme();const observer=new MutationObserver(syncTheme);observer.observe(document.documentElement,{attributes:true,attributeFilter:['data-color-scheme','data-chat-background','data-background-strength']});
  const size=new ResizeObserver(syncTheme);if(frame.current)size.observe(frame.current);const sidebar=document.querySelector('.partner-shell .app-sidebar');if(sidebar)size.observe(sidebar);
  window.addEventListener('resize',syncTheme);return()=>{observer.disconnect();size.disconnect();window.removeEventListener('resize',syncTheme);};},[lastUrl]);
 useEffect(()=>{
  if(!visible||dual){setPreview('');return;}
  function message(event){
   if(event.origin!=='http://127.0.0.1:8765'||event.source!==frame.current?.contentWindow||event.data?.type!=='remote-workstation-navigation')return;
   const url=previewUrl(event.data.preview,lastUrl);
   if(url)setPreview(url);
  }
  window.addEventListener('message',message);
  return()=>window.removeEventListener('message',message);
 },[lastUrl,visible,dual]);
 useEffect(()=>{
  function message(event){
   const value=event.data;
   if(event.origin!==receiverOrigin||event.source!==frame.current?.contentWindow||value?.type!=='workstation-single-history')return;
   if(!['codex','deepseek'].includes(value.model))return;
   if(Object.keys(singleModels).some(model=>!Array.isArray(value.groups?.[model]?.rows)||value.groups[model].rows.some(row=>typeof row?.key!=='string'||typeof row.title!=='string')))return;
   setHistory(value);
  }
  window.addEventListener('message',message);
  return()=>window.removeEventListener('message',message);
 },[]);
 function historyAction(action,value){frame.current?.contentWindow?.postMessage({type:'workstation-single-history-action',action,value},receiverOrigin);}
 function loadFrame(){setHistory(null);syncTheme();historyAction('connect');}
 function closeRail(){setRailOpen(false);requestAnimationFrame(()=>railToggle.current?.focus());}
 function openRail(){setRailOpen(true);requestAnimationFrame(()=>railClose.current?.focus());}
 function showMode(mode){setChoice(mode);if(mode==='single'&&forceDual)onNavigate('partner');}
 function hideNarrowRail(){if(window.matchMedia('(max-width:1020px)').matches)setRailOpen(false);}
 function pickSingle(row){showMode('single');historyAction('open',{model:row.model,key:row.key});hideNarrowRail();}
 function pickCollaboration(id){showMode('dual');setHistoryIntent({id,nonce:++historySequence.current});hideNarrowRail();}
 function finishHistoryIntent(nonce){setHistoryIntent(current=>current?.nonce===nonce?null:current);}
 const connected=!!data?.online&&!error;
 const connectionTone=busy?'working':error?'error':connected?'ready':data?'attention':'neutral';
 return <div className="partner-page"><header className="partner-heading">
  <div className="partner-heading-title"><strong>搭档</strong></div>
  <div className="partner-model-choice" role="group" aria-label="执行方式" data-mode={dual?'dual':'single'}>
   <button aria-pressed={!dual} onClick={()=>showMode('single')}>单模型</button>
   <button aria-pressed={dual} onClick={()=>showMode('dual')}>协作中心</button>
  </div>
  {!railOpen&&conversationSlot&&<button ref={railToggle} className="auto-button center-rail-toggle" aria-label="展开会话列表" aria-controls="partner-conversations" aria-expanded={false} onClick={openRail}><PanelLeftOpen size={16}/>会话</button>}
  <button className="auto-button partner-today-entry" onClick={()=>onNavigate('companion')}>今日事务</button>
  <details className="partner-connection-menu">
   <summary aria-label="手机服务连接状态"><span>手机服务</span><span className="feedback-status" data-tone={connectionTone} role="status">{busy?'检查中':error?'连接异常':connected?'已连接':data?'未连接':'待检查'}</span></summary>
   <p>{connected?'手机会话服务已连接':'手机会话服务待确认'}</p>
   <button className="auto-button" disabled={busy} onClick={refresh}>{busy?'检查中…':'刷新连接'}</button>
   <button className="auto-button" onClick={()=>onNavigate('remote')}>手机与远程连接</button>
  </details>
  <button ref={backgroundButton} className="auto-button partner-background-button" aria-label="聊天背景" title="聊天背景" aria-haspopup="dialog" onClick={()=>setBackgroundOpen(true)}><SlidersHorizontal size={16} aria-hidden="true"/></button>
 </header>
 {conversationSlot&&createPortal(<HistoryRail single={history} collaboration={collaboration} dual={dual} open={visible&&railOpen} closeControl={railClose} onClose={closeRail} onSingleAction={historyAction} onPickSingle={pickSingle} onPickCollaboration={pickCollaboration}/>,conversationSlot)}
 {error&&<p className="auto-warning" role="alert">{error}</p>}
 <div className="partner-single" hidden={dual}>{lastUrl?<>{!data?.online&&<p className="partner-session-hint" role="status">当前离线，已保留输入与页面。</p>}<iframe ref={frame} title="搭档原模型会话" src={lastUrl} onLoad={loadFrame} sandbox="allow-scripts allow-same-origin allow-forms allow-downloads" referrerPolicy="no-referrer"/></>:<div className="partner-welcome"><h1>{busy?'正在检查会话连接':'连接单模型会话'}</h1><p>启动接收器后，可继续原来的会话。</p><button className="auto-button" onClick={()=>onNavigate('remote')}>打开连接与设置</button></div>}</div>
 <div className="partner-dual" hidden={!dual}>{children(visible&&dual,{historyVisible:visible,historyIntent,onHistoryState:setCollaboration,onHistoryIntentHandled:finishHistoryIntent})}</div>
 {visible&&!dual&&preview&&<PreviewDialog key={preview} title="搭档文件预览" frameTitle="搭档文件预览" src={preview} opener={frame.current}
  sandbox="allow-scripts allow-same-origin allow-forms allow-downloads" onClose={()=>setPreview('')}/>}
 {visible&&backgroundOpen&&<PreviewDialog title="聊天背景" opener={backgroundButton.current} onClose={()=>setBackgroundOpen(false)}><ThemePicker showBackground/></PreviewDialog>}
 </div>;
}
