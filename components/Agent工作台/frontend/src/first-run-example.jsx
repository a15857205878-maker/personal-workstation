import React,{useEffect,useId,useLayoutEffect,useReducer,useRef,useState} from 'react';
import {FileText,ListChecks,X} from 'lucide-react';
import ArtifactReview,{artifactFileKey} from './artifact-review.jsx';
import ChatAvatar from './chat-avatar.jsx';
import {examplePhase,exampleTurn} from './first-run-flow.mjs';
import TaskProgress from './task-progress.jsx';
import './first-run-example.css';

export default function FirstRunExample({opener,onClose,onConnect,call}){
 const title=useId(),shell=useRef(null),heading=useRef(null),task=useRef(null);
 const taskOpener=useRef(null);
 const [sample,setSample]=useState(null),[error,setError]=useState(''),[attempt,setAttempt]=useState(0);
 const [phase,advance]=useReducer(examplePhase,'prepared');
 const [progress,setProgress]=useState(false),[geometry,setGeometry]=useState(null);
 const [review,setReview]=useState(null),[returned,setReturned]=useState(false);

 useLayoutEffect(()=>{
  const dialog=shell.current;
  dialog.showModal();heading.current.focus({preventScroll:true});
  return()=>{
   if(dialog.open)dialog.close();
   if(opener?.isConnected&&opener.getClientRects().length)opener.focus({preventScroll:true});
  };
 },[opener]);
 useEffect(()=>{
  let current=true;
  call('api_example_task').then(value=>{if(current)setSample(value);})
   .catch(reason=>{if(current)setError(reason.message);});
  return()=>{current=false;};
 },[attempt,call]);
 useEffect(()=>{
  if(phase!=='organizing'&&phase!=='writing')return;
  const timer=setTimeout(()=>advance('step'),phase==='organizing'?1250:1100);
  return()=>clearTimeout(timer);
 },[phase]);

 function showProgress(event){
  taskOpener.current=event.currentTarget;
  setProgress(true);
 }
 function returnToTask(){
  setReview(null);setReturned(true);
  requestAnimationFrame(()=>task.current?.focus({preventScroll:false}));
 }
 function restart(event){
  setReturned(false);advance('restart');showProgress(event);
 }

 const turn=sample&&exampleTurn(sample,phase);
 const run=phase==='completed'&&turn?.jobs.find(job=>job.run)?.run;
 const file=run&&{...run.files[0],run_id:run.id,label:'本周三步工作计划 · DOCX',preview:run.artifact_preview,can_open:false};
 async function getFile(action,payload){
  if(action!=='api_collaboration_file'||payload.id!==file?.run_id||payload.name!==sample.file_name){
   throw Error('请从当前示例的预览保存 Word 文件。');
  }
  return call('api_example_document');
 }

 return <dialog className="first-run-example" ref={shell} aria-labelledby={title} onCancel={event=>{
  if(event.target===event.currentTarget){event.preventDefault();onClose();}
 }}>
  <header className="first-run-header">
   <div><h2 id={title} ref={heading} tabIndex={-1}>体验示例任务</h2>
    <p>用内置样例走完一次分工、进度和 Word 交付。</p></div>
   <button type="button" className="auto-button" aria-label="退出示例" onClick={onClose}><X size={17}/></button>
  </header>
  {sample?<div className="center-chat-area first-run-body">
   <div className="center-feed first-run-feed">
    <section ref={task} className="first-run-task" tabIndex={-1} aria-label="示例对话中的任务">
     <div className="center-user-row">
      <article className="center-user"><span className="partner-speaker-label">你 · 示例需求</span><p>{sample.goal}</p></article>
      <ChatAvatar member="user" name="示例用户"/>
     </div>
     <div className="first-run-exchange">
      <ChatAvatar member="A" name="示例搭档"/>
      <div className="center-message-bubble">
       <strong>示例搭档</strong>
       <p>{phase==='prepared'?'分工已准备好，确认后就能看到两步进度。':
          phase==='completed'?'Word 计划已就绪，可以预览并保存。':
          phase==='cancelled'?'这轮已取消，可以重新体验。':'正在按分工准备示例文件。'}</p>
       {phase!=='cancelled'&&<button type="button" className={'auto-button'+(phase==='prepared'?' auto-primary':'')}
        aria-haspopup="dialog" aria-expanded={progress} onClick={showProgress}>
        <ListChecks size={16} aria-hidden="true"/>{phase==='prepared'?'查看分工':'任务进度'}
       </button>}
       {phase==='cancelled'&&<button type="button" className="auto-button auto-primary" onClick={restart}>重新体验</button>}
      </div>
     </div>
     {file&&<section className="first-run-result" aria-label="示例成果">
      <FileText size={22} aria-hidden="true"/>
      <div><strong>{sample.title}</strong><p>Word · 可编辑表格</p></div>
      <button type="button" className="auto-button auto-primary" aria-haspopup="dialog"
       onClick={event=>{setProgress(false);setReview(event.currentTarget);}}>预览 Word</button>
     </section>}
     {returned&&<p className="first-run-return" role="status">已回到这条示例任务。</p>}
    </section>
   </div>
   {progress&&<TaskProgress example turns={[turn]} selected={turn.id} activeId={turn.id}
    opener={taskOpener.current} onClose={()=>setProgress(false)} geometry={geometry} onGeometry={setGeometry}
    onConfirm={()=>advance('confirm')} onCancel={()=>advance('cancel')} onStop={()=>advance('cancel')}
    onDelivery={returnToTask}/>}
  </div>:<div className="first-run-loading">
   {error?<><p role="alert">{error}</p><button type="button" className="auto-button"
    onClick={()=>{setError('');setAttempt(value=>value+1);}}>重试加载</button></>:
    <p role="status">正在准备示例…</p>}
  </div>}
  <footer className="first-run-footer">
   <span>内置示例 · 0 次模型调用</span>
   {phase==='completed'&&<button type="button" className="auto-button" onClick={onConnect}>连接自己的模型</button>}
  </footer>
  {review&&file&&<ArtifactReview files={[file]} initialFile={artifactFileKey(file)} opener={review}
   call={getFile} onClose={()=>setReview(null)} onConversation={returnToTask}/>}
 </dialog>;
}
