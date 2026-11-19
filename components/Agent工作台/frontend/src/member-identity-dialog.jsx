import React,{useRef,useState,useEffect} from 'react';
import {call} from './auto.jsx';
import ChatAvatar from './chat-avatar.jsx';
import useDialog from './use-dialog.js';

export default function MemberIdentityDialog({identifier,profile,seat,value={},orphans=[],locked,onClose,onSaved}){
 const [nickname,setNickname]=useState(value.nickname||''),[avatar,setAvatar]=useState(value.avatar||''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const mounted=useRef(true);useEffect(()=>()=>{mounted.current=false;},[]);
 const dialog=useDialog(onClose,busy),original=identifier==='user'?'你':profile?.source_name||profile?.name||'成员';
 async function pick(){
  if(busy||locked)return;setBusy(true);setError('');
  try{const result=await call('api_center_identity_pick');if(mounted.current&&!result.cancelled)setAvatar(result.avatar);}
  catch(e){if(mounted.current)setError(e.message);}finally{if(mounted.current)setBusy(false);}
 }
 async function save(e){
  e.preventDefault();if(busy||locked)return;setBusy(true);setError('');
  try{const result=await call('api_center_identity_save',{id:identifier,nickname:nickname.trim(),avatar});if(mounted.current){onSaved(result.items);onClose();}}
  catch(e){if(mounted.current)setError(e.message);}finally{if(mounted.current)setBusy(false);}
 }
 async function resetOld(id){
  if(busy||locked)return;setBusy(true);setError('');
  try{const result=await call('api_center_identity_save',{id,nickname:'',avatar:''});if(mounted.current)onSaved(result.items);}
  catch(e){if(mounted.current)setError(e.message);}finally{if(mounted.current)setBusy(false);}
 }
 return <div className="auto-modal-backdrop"><section className="auto-modal identity-dialog" ref={dialog} role="dialog" aria-modal="true" aria-labelledby="identity-title">
  <header className="auto-modal-head"><h2 id="identity-title">头像与昵称</h2><button className="auto-close" disabled={busy} aria-label="关闭成员资料" onClick={onClose}>×</button></header>
  <form onSubmit={save}><div className="auto-modal-body">
   <div className="identity-preview"><ChatAvatar member={seat||'user'} name={nickname.trim()||original} avatar={avatar}/><div><strong>{nickname.trim()||original}</strong><small>{identifier==='user'?'你的群聊资料':original+' · '+profile?.model}</small></div></div>
   <label className="auto-field">昵称<input aria-label="成员昵称" value={nickname} maxLength={24} placeholder={original} disabled={busy||locked} onChange={e=>setNickname(e.target.value)}/></label>
   <div className="identity-avatar-actions"><button className="auto-button" type="button" disabled={busy||locked} onClick={pick}>{busy?'处理中…':'从本机选择头像'}</button><button className="auto-button" type="button" disabled={busy||locked||!avatar} onClick={()=>setAvatar('')}>使用默认头像</button></div>
   <p className="auto-small">PNG、JPEG、WebP，最多10MB。图片居中裁成方形；原图保留，不会发给模型。</p>
   <p className="auto-small">跨群聊保存，只改变显示；模型和原始记录保持原样。昵称留空会恢复默认名称。</p>
   {!!orphans.length&&<details className="identity-orphans"><summary>已移除模型的资料（{orphans.length}）</summary><p className="auto-small">可恢复其默认显示以腾出位置，旧聊天仍保留。</p>{orphans.map(([id,row])=><button className="auto-button" type="button" key={id} disabled={busy||locked} onClick={()=>resetOld(id)}>恢复 {row.nickname||'旧成员'} 默认资料</button>)}</details>}
   {error&&<p className="auto-warning" role="alert">{error}</p>}
  </div><footer className="auto-modal-actions"><button className="auto-button" type="button" disabled={busy||locked} onClick={()=>{setNickname('');setAvatar('');}}>恢复全部默认</button><div><button className="auto-button" type="button" disabled={busy} onClick={onClose}>取消</button><button className="auto-button auto-primary" type="submit" disabled={busy||locked}>保存资料</button></div></footer></form>
 </section></div>;
}
