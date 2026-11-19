import React,{useEffect,useRef,useState} from 'react';
import {call} from './auto.jsx';
import Attachments from './attachments.jsx';
import './quick.css';
export default function Quick(){
 const [text,setText]=useState(''),[items,setItems]=useState([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[hotkey,setHotkey]=useState(false);
 const [attachmentBusy,setAttachmentBusy]=useState(false);
 const field=useRef(null),nonce=useRef(crypto.randomUUID()),lock=useRef(false);
 useEffect(()=>{document.documentElement.dataset.theme='coastal';let live=true;async function init(){try{const info=await call('api_quick_info');if(live)setHotkey(info.hotkey);}catch(e){if(live)setError(e.message);}}if(window.pywebview?.api?.call)init();else window.addEventListener('pywebviewready',init,{once:true});const escape=e=>{if(e.key==='Escape')call('api_quick_hide').catch(()=>{});};document.addEventListener('keydown',escape);field.current?.focus();return()=>{live=false;document.removeEventListener('keydown',escape);window.removeEventListener('pywebviewready',init);};},[]);
 function change(fn){nonce.current=crypto.randomUUID();setNotice('');fn();}
 async function send(){if(lock.current||attachmentBusy||!text.trim())return;lock.current=true;setBusy(true);setError('');try{await call('api_quick_submit',{request_id:nonce.current,mode:'work',text,attachments:items.map(i=>i.id)});setText('');setItems([]);nonce.current=crypto.randomUUID();setNotice('已送入搭档待接收区，尚未执行。');await call('api_quick_hide');}catch(e){setError(e.message);}finally{lock.current=false;setBusy(false);}}
 return <main className="quick-shell"><header className="quick-head"><div className="pywebview-drag-region"><b>快速交办</b></div><button type="button" onClick={()=>call('api_main_open').catch(e=>setError(e.message))}>大窗口</button><button type="button" aria-label="隐藏快捷栏" onClick={()=>call('api_quick_hide').catch(()=>{})}>×</button></header>
 <div className="quick-body"><p className="quick-notice">可选快捷栏：只送到搭档待接收区，核对后再放入当前会话，不自动执行。</p>
 <textarea ref={field} aria-label="快捷指令" placeholder="想做什么？直接输入指令…" rows="2" value={text} maxLength={8000} disabled={busy} onChange={e=>change(()=>setText(e.target.value))} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();send();}}}/>
 <Attachments compact onBusyChange={setAttachmentBusy} surface="quick" items={items} disabled={busy} onChange={v=>change(()=>setItems(v))}/>
 {error&&<p className="quick-error" role="alert">{error}</p>}{notice&&<p className="quick-notice" role="status">{notice}</p>}<footer><span>Enter 发送 · Esc 隐藏</span><button className="quick-primary" disabled={busy||attachmentBusy||!text.trim()} onClick={send}>{busy?'正在交接…':'送入草稿 →'}</button></footer></div></main>;
}
