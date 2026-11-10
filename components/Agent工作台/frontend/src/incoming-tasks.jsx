import React,{useState} from 'react';
import {call} from './auto.jsx';

export default function IncomingTasks({disabled,onImport}){
 const [open,setOpen]=useState(false),[tasks,setTasks]=useState([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[copiedId,setCopiedId]=useState(null);
 async function load(){setOpen(true);setBusy(true);setError('');try{setTasks(await call('app_link_pending'));}catch(e){setError(e.message);}finally{setBusy(false);}}
 async function archive(task){if(busy||disabled)return;setBusy(true);setError('');try{await call('app_link_archive',{id:task.id});setTasks(items=>items.filter(t=>t.id!==task.id));}catch(e){setError(e.message);}finally{setBusy(false);}}
 async function receive(task){if(busy||disabled)return;setBusy(true);setError('');try{
  if(copiedId!==task.id){onImport(task);setCopiedId(task.id);}
  await call('app_link_claim',{id:task.id});setTasks(items=>items.filter(t=>t.id!==task.id));setCopiedId(null);setOpen(false);
 }catch(e){setError(e.message);}finally{setBusy(false);}}
 return <div style={{margin:'12px 0'}}><button type="button" className="auto-button" onClick={load} disabled={busy||disabled}>{busy?'读取中…':'接收联动任务'}</button>{open&&<div className="auto-warning" style={{marginTop:10}}><div style={{display:'flex',gap:10,justifyContent:'space-between'}}><strong>联动收件箱</strong><button type="button" className="auto-link" disabled={busy} onClick={()=>setOpen(false)}>收起</button></div><p>导入后由你选择模型并执行。已接收任务会保存在本机，可再次填入。</p>{error&&<p role="alert">{error}</p>}{!busy&&!tasks.length&&!error&&<p>还没有待接收任务，请先在应用联动中保存并送到工作台。</p>}{tasks.map(task=><div key={task.id} style={{margin:'10px 0',overflowWrap:'anywhere'}}><span>{task.received?'已接收 · ':'待接收 · '}{task.title}</span> <button type="button" className="auto-link" disabled={busy||disabled} onClick={()=>receive(task)}>{copiedId===task.id?'确认已导入':'填入任务'}</button>{task.received&&<button type="button" className="auto-link" disabled={busy||disabled} onClick={()=>archive(task)}>归档记录</button>}</div>)}</div>}</div>;
}
