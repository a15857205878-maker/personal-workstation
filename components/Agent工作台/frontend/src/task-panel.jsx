import React,{useState,useId} from 'react';
import useDialog from './use-dialog.js';
import {acceptBrief} from './workspace-transfer.mjs';
export function TaskPanel({title,onClose,blocked=false,children,drawer=false}){
 const heading=useId(),ref=useDialog(onClose,blocked);
 return <div className={'station-modal-backdrop'+(drawer?' station-drawer-backdrop':'')} onMouseDown={e=>{if(e.target===e.currentTarget&&!blocked)onClose();}}><section className={'station-modal'+(drawer?' station-drawer':'')} role="dialog" aria-modal="true" aria-labelledby={heading} ref={ref}><div className="station-modal-head"><h2 id={heading}>{title}</h2><button className="station-button" disabled={blocked} onClick={onClose}>关闭</button></div><div className="station-modal-body">{children}</div></section></div>;
}
export function BriefDialog({title,text,limit,hasExisting=false,locked=false,onClose,onUse}){
 const [draft,setDraft]=useState(text||''),[replace,setReplace]=useState(false),[error,setError]=useState('');
 async function copy(){try{await navigator.clipboard.writeText(draft);setError('已复制，可以自行粘贴。');}catch{setError('请选中需求文字后按Ctrl+C复制。');}}
 function use(){try{acceptBrief(draft,limit);if(hasExisting&&!replace)throw Error('请勾选确认替换，或复制后手动粘贴。');onUse(draft,replace);}catch(e){setError(e.message);}}
 return <TaskPanel title={title} onClose={onClose}><p className="station-hint">检查并编辑后再填入；只传递文字，不启动模型，也不发送给服务商。</p><label className="station-field"><span>待交接的任务需求</span><textarea className="workspace-transfer-text" rows="12" value={draft} onChange={e=>setDraft(e.target.value)} disabled={locked}/></label><p className="station-hint">{draft.length} / {limit} 字符；超出时请手动精简，不会截断。</p>{hasExisting&&<label className="workspace-replace"><input type="checkbox" checked={replace} disabled={locked} onChange={e=>setReplace(e.target.checked)}/>确认替换当前未发布草稿（原输入会被替换，已保存会话不受影响）</label>}{locked&&<p className="station-warning">当前正在执行或处理操作，结束后可接收。可先关闭此窗口，返回协作页停止或等待；现有输入保持不变。</p>}{error&&<p className="station-warning" role="status">{error}</p>}<div className="station-actions"><button className="station-button" onClick={copy}>复制需求</button><button className="station-button station-primary" disabled={locked||!draft.trim()||draft.length>limit||(hasExisting&&!replace)} onClick={use}>确认填入草稿</button></div></TaskPanel>;
}
