import React,{useEffect,useRef,useState} from 'react';
import {ChevronLeft,ChevronRight} from 'lucide-react';
import {PreviewDialog} from './feedback-dialog.jsx';
import {DeliveryPreview,runFilePreview,saveCollaborationFile} from './collaboration-files.jsx';

export const artifactFileKey=({run_id,name})=>JSON.stringify([run_id,name]);

export default function ArtifactReview({files,initialFile,opener,onClose,call,onArtifacts,onConversation,onSelect}){
 const [selected,setSelected]=useState(initialFile);
 const [loaded,setLoaded]=useState(null),[retry,setRetry]=useState(0);
 const [busy,setBusy]=useState(''),[feedback,setFeedback]=useState(null);
 const actionPending=useRef(false),alive=useRef(true);
 const index=Math.max(0,files.findIndex(file=>artifactFileKey(file)===selected));
 const file=files[index],key=artifactFileKey(file);
 const item=loaded?.key===key&&loaded.retry===retry?loaded:null;
 const preview=file.preview||item?.preview;
 const status=feedback?.key===key?feedback:null;
 const multiple=files.length>1;
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 useEffect(()=>{
  if(file.preview||!file.catalogId)return;
  let cancelled=false;
  async function load(){
   try{
    let result;
    if(file.can_preview){
     const data=await call('workstation_artifact_preview',{id:file.catalogId});
     if(data.name!==file.name)throw Error('预览与当前文件不一致，请重试。');
     result={html:data.html};
    }else{
     const run=await call('api_session',{id:file.run_id});
     if(run?.id!==file.run_id)throw Error('预览与当前文件不一致，请重试。');
     result={preview:runFilePreview(run,file.name)};
    }
    if(!cancelled)setLoaded({key,retry,...result});
   }catch(error){if(!cancelled)setLoaded({key,retry,error:error.message});}
  }
  load();
  return()=>{cancelled=true;};
 },[key,retry,file.catalogId,file.can_preview,!!file.preview]);
 function select(next){
  const entry=files.find(candidate=>artifactFileKey(candidate)===next);
  if(!entry)return;
  setFeedback(null);setSelected(next);setRetry(0);
  onSelect?.(entry);
 }
 async function act(action){
  if(actionPending.current)return;
  actionPending.current=true;setBusy(action);setFeedback(null);
  try{
   if(action==='download'){
    const data=await call('api_collaboration_file',{id:file.run_id,name:file.name});
    if(data.name!==file.name)throw Error('文件名与当前成果不一致，请重新打开后再试。');
    saveCollaborationFile(data);
    if(alive.current)setFeedback({key,text:'已提交保存请求'});
   }else{
    await call('api_collaboration_open_file',{id:file.run_id,name:file.name});
   }
  }catch(error){if(alive.current)setFeedback({key,text:error.message,error:true});}
  finally{actionPending.current=false;if(alive.current)setBusy('');}
 }
 const controls=<div className="artifact-review-controls">
  {multiple&&<div className="artifact-review-switch">
   <button className="station-button" aria-label="上一份文件" disabled={index===0} onClick={()=>select(artifactFileKey(files[index-1]))}><ChevronLeft size={16}/></button>
   <select aria-label="选择本轮文件" value={key} onChange={event=>select(event.target.value)}>
    {files.map((entry,i)=><option key={artifactFileKey(entry)} value={artifactFileKey(entry)}>{i+1}. {entry.label}</option>)}
   </select>
   <button className="station-button" aria-label="下一份文件" disabled={index===files.length-1} onClick={()=>select(artifactFileKey(files[index+1]))}><ChevronRight size={16}/></button>
  </div>}
  <p className="artifact-review-name"><span>{file.name}</span>{multiple&&<span>{index+1} / {files.length}</span>}</p>
 </div>;
 const actions=dismiss=><div className="artifact-review-actions">
  {onConversation&&<button className="station-button" disabled={!!busy} onClick={()=>dismiss(()=>onConversation(file))}>回到对话中的任务</button>}
  {onArtifacts&&<button className="station-button" disabled={!!busy} onClick={()=>dismiss(()=>onArtifacts(file))}>在成果页查看</button>}
  {file.can_open!==false&&<button className="station-button" disabled={!!busy} onClick={()=>act('open')}>本机打开</button>}
  <button className="station-button station-primary" disabled={!!busy} onClick={()=>act('download')}>{busy==='download'?'正在保存…':'保存当前文件'}</button>
 </div>;
 return <PreviewDialog title="本轮文件" opener={opener} onClose={onClose} controls={controls} actions={actions}
  status={status?<span className={status.error?'ws-error':'ws-muted'} role={status.error?'alert':'status'}>{status.text}</span>:null}
  srcDoc={item?.html} frameKey={key} frameTitle="成果隔离预览">
  <div className="artifact-review-body" key={key} tabIndex={0}>
   {preview?<><p className="auto-small">打开原件可查看完整版式。</p><DeliveryPreview preview={preview}/></>:
    item?.error?<div className="artifact-review-empty"><p role="alert">{item.error}</p><button className="station-button" onClick={()=>setRetry(value=>value+1)}>重试预览</button></div>:
    file.catalogId&&!item?<p className="artifact-review-empty" role="status">正在读取文件预览…</p>:<p className="artifact-review-empty">这份文件可以保存后查看。</p>}
  </div>
 </PreviewDialog>;
}
