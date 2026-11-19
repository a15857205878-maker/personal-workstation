import React,{useState} from 'react';
import useDialog from './use-dialog.js';
export default function ConversationManager({session,busy,error,onClose,onSave}){
 const [title,setTitle]=useState(session.title),[archived,setArchived]=useState(!!session.archived);
 const dialog=useDialog(onClose,busy);
 const changes={...(title.trim()!==session.title?{title:title.trim()}:{}),...(archived!==!!session.archived?{archived}:{})};
 return <div className="auto-modal-backdrop"><section className="auto-modal conversation-manager" role="dialog" aria-modal="true" aria-labelledby="conversation-title" ref={dialog}>
  <header className="auto-modal-head"><h2 id="conversation-title">会话管理</h2><button className="auto-close" aria-label="关闭会话管理" disabled={busy} onClick={onClose}>×</button></header>
  <form onSubmit={e=>{e.preventDefault();onSave(changes);}}><div className="auto-modal-body">
   <label className="auto-field">会话名称<input aria-label="会话名称" maxLength={60} value={title} disabled={busy} onChange={e=>setTitle(e.target.value)}/></label>
   <label className="conversation-archive"><input aria-label="归档此会话" type="checkbox" checked={archived} disabled={busy} onChange={e=>setArchived(e.target.checked)}/>归档此会话</label>
   <p className="auto-small">归档后保留聊天和成果，暂不继续发送；可切到已归档列表恢复。</p>
   {error&&<p className="auto-warning" role="alert">{error}</p>}
  </div><footer className="auto-modal-actions"><button className="auto-button" type="button" disabled={busy} onClick={onClose}>取消</button><button className="auto-button auto-primary" disabled={busy||!title.trim()||!Object.keys(changes).length}>保存会话设置</button></footer></form>
 </section></div>;
}
