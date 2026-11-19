import React,{useId,useLayoutEffect,useRef,useState} from 'react';
import {ChevronDown,Grip,GripHorizontal,ListChecks,Minus,RotateCcw,X} from 'lucide-react';
import {completionSummary,isTaskTurn,turnHasDelivery} from './center-replies.mjs';
import {TaskMessage} from './center-turn.jsx';
import {displayMember,displayRoles} from './member-identity.mjs';
import {taskTone} from './feedback-status.mjs';
import {useFeedbackDismiss} from './feedback-dialog.jsx';

export const progressLabels={prepared:'待确认',queued:'待执行',starting:'准备中',running:'进行中',stopping:'停止中',completed:'已完成',failed:'失败',cancelled:'已取消',interrupted:'已中断',skipped:'未执行'};
const formats={text:'文字',docx:'DOCX',xlsx:'XLSX',pptx:'PPTX',svg:'SVG'};
const actionStates=['starting','running','stopping'];
const clamp=(n,low,high)=>Math.max(low,Math.min(n,high));
function fitPanel(value,space,collapsed){
 const maxHeight=Math.max(47,space.height-20);
 const width=clamp(value?.width??352,306,Math.min(490,space.width-330));
 const height=clamp(value?.height??410,Math.min(198,maxHeight),maxHeight);
 const top=clamp(value?.top??0,0,Math.max(0,maxHeight-(collapsed?47:height)));
 return {side:value?.side||'right',top,width,height};
}

export default function TaskProgress({session,turns,selected,onSelect,opener,onClose,onDelivery,activeId,busy,globalBusy,onConfirm,onEdit,onCancel,onStop,onRetry,retryBlocked,identities,error,notice,geometry,onGeometry,onSaveDraft,onRestorePlanningInput,renderEditor}){
 const title=useId(),dialog=useRef(null),closeButton=useRef(null);
 const [collapsed,setCollapsed]=useState(false),[space,setSpace]=useState({width:0,height:0});
 const [editor,setEditor]=useState(null);
 const pointer=useRef(null);
 const compact=space.width<665;
 const box=fitPanel(geometry,space,collapsed);
 const dismiss=useFeedbackDismiss(dialog);
 useLayoutEffect(()=>{
  const area=dialog.current.parentElement;
  const measure=()=>{
   const {clientWidth:width,clientHeight:height}=area;
   setSpace(old=>old.width===width&&old.height===height?old:{width,height});
  };
  measure();
  const observer=new ResizeObserver(measure);
  observer.observe(area);
  return()=>observer.disconnect();
 },[]);
 useLayoutEffect(()=>{
  const panel=dialog.current;panel.show();
  (panel.querySelector('.center-approval .auto-primary:not(:disabled)')||closeButton.current).focus({preventScroll:true});
  return ()=>{
   if(panel.open)panel.close();
   if(opener?.isConnected&&opener.getClientRects().length)opener.focus({preventScroll:true});
  };
 },[opener]);
 const turn=turns.find(item=>item.id===selected)||turns[0];
 const prepared=turn?.state==='prepared',task=isTaskTurn(turn),jobs=turn?.jobs||[];
 const planningRejected=turn?.failures?.some(failure=>failure.code==='plan_rejected');
 const editing=prepared&&turn.id===editor?.id;
 const running=turn?.id===activeId&&actionStates.includes(turn?.state);
 const done=jobs.filter(job=>(job.run?.status||job.state)==='completed').length;
 const fileJobs=jobs.length?jobs:task&&turn?.run?[{title:'执行记录',run:turn.run}]:[];
 function close(){dismiss(onClose);}
 function jump(){dismiss(()=>{onClose();onDelivery(turn.id);});}
 function shift(base,kind,dx,dy,side=base.side){
  const adjusted=kind==='move'?{...base,side,top:base.top+dy}:
   {...base,width:base.width+dx,height:base.height+dy};
  onGeometry(fitPanel(adjusted,space,collapsed));
 }
 function grip(kind){
  return {
   onPointerDown:event=>{
    if(event.button!==0)return;
    const area=dialog.current.parentElement.getBoundingClientRect();
    pointer.current={id:event.pointerId,x:event.clientX,y:event.clientY,midpoint:area.left+area.width/2,box};
    event.currentTarget.setPointerCapture(event.pointerId);event.currentTarget.focus({preventScroll:true});
   },
   onPointerMove:event=>{
    const start=pointer.current;
    if(start?.id!==event.pointerId)return;
    const side=event.clientX<start.midpoint?'left':'right';
    shift(start.box,kind,event.clientX-start.x,event.clientY-start.y,side);
   },
   onLostPointerCapture:()=>{pointer.current=null;},
   onKeyDown:event=>{
    const offsets={ArrowLeft:[-16,0],ArrowRight:[16,0],ArrowUp:[0,-16],ArrowDown:[0,16]};
    if(!offsets[event.key])return;
    event.preventDefault();
    const [x,y]=offsets[event.key],side=x<0?'left':x>0?'right':box.side;
    shift(box,kind,x,y,side);
   },
  };
 }
 return <dialog className="task-progress-panel" data-modeless="" data-collapsed={collapsed||undefined} data-compact={compact||undefined} data-side={box.side} ref={dialog} data-feedback-dialog aria-labelledby={title}
  style={compact?undefined:{width:box.width,height:collapsed?undefined:box.height,marginTop:box.top+10}}
  onCancel={event=>{event.preventDefault();close();}}
  onKeyDown={event=>{if(event.key==='Escape'&&!event.defaultPrevented){event.preventDefault();event.stopPropagation();close();}}}>
  <div className="task-progress-inner">
   <header>
    <div className="task-progress-title"><ListChecks size={17} aria-hidden="true"/><h2 id={title}>任务进度</h2>{collapsed&&turn&&<span className="feedback-status" data-tone={taskTone(turn.state)}>{progressLabels[turn.state]}</span>}</div>
    <div className="task-window-actions">
     {!compact&&<button className="auto-button task-window-drag" aria-label="移动任务浮窗" title="拖到左侧或右侧，或用方向键移动" {...grip('move')}><GripHorizontal size={17}/></button>}
     {!compact&&<button className="auto-button" aria-label="恢复浮窗位置和大小" title="恢复位置和大小" onClick={()=>onGeometry(null)}><RotateCcw size={14}/></button>}
     <button className="auto-button" aria-label={collapsed?'展开任务进度':'折叠任务进度'} aria-expanded={!collapsed} onClick={()=>setCollapsed(value=>!value)}>{collapsed?<ChevronDown size={17}/>:<Minus size={17}/>}</button>
     <button ref={closeButton} className="auto-button" aria-label="关闭任务进度" onClick={close}><X size={18} aria-hidden="true"/></button>
    </div>
   </header>
   <div className="task-progress-body" hidden={collapsed}>
    {error&&<p className="auto-warning" role="alert">{error}</p>}{notice&&<p className="auto-small" role="status">{notice}</p>}
    {!turn?<div className="task-progress-empty"><h3>还没有任务</h3><p>在对话里点「交办任务」后，可以在这里确认分工和查看进度。</p></div>:<>
     {turns.length>1&&<label className="task-progress-choice">选择任务<select aria-label="选择任务" value={turn.id} onChange={event=>onSelect(event.target.value)}>
      {turns.map(item=><option key={item.id} value={item.id}>{progressLabels[item.state]||'已记录'} · {item.text?.trim().slice(0,48)||'协作任务'}</option>)}
     </select></label>}
     <article className="center-plan task-progress-card" data-state={turn.state} key={turn.id}>
      <div className="center-stage-heading"><strong>{prepared?'确认本次分工':'当前记录'}</strong>
       <span className="feedback-status" data-tone={taskTone(turn.state)} role="status">{progressLabels[turn.state]||'已记录'}</span></div>
      <p className="task-progress-goal">{turn.text}</p>
      {turn.phase==='planning'&&running&&<p className="auto-small" role="status">龙娘正在拟分工，草案生成后等你确认。</p>}
      {!prepared&&!planningRejected&&task&&turn.state!=='cancelled'&&(jobs.length?<div className="task-progress-meter">
       <span>已完成 {done}/{jobs.length} 项</span><progress value={done} max={jobs.length} aria-label="已完成子任务数"/>
      </div>:<p className="auto-small">{completionSummary(turn)}</p>)}
      {editing?<>
       {editor.version!==turn.plan_revision&&<p className="auto-warning" role="status">另一端已修改草案。请退出编辑，重新打开最新版本。</p>}
       {renderEditor(editor.jobs,jobs=>setEditor(old=>({...old,jobs})),!!busy)}
       <div className="task-progress-actions task-progress-edit-actions">
        <button className="auto-button auto-primary" disabled={!!busy||editor.version!==turn.plan_revision} onClick={async()=>{if(await onSaveDraft(turn.id,editor.version,editor.jobs))setEditor(null);}}>保存分工</button>
        <button className="auto-button" disabled={!!busy} onClick={()=>setEditor(null)}>退出编辑</button>
       </div>
      </>:!!jobs.length&&<ul className="task-progress-steps">{jobs.map((job,index)=>{
       const state=prepared?'prepared':job.run?.status||job.state;
       const member=displayMember(job.roles?.A,identities);
       return <li key={index}><div><strong>{job.title}</strong><span className="feedback-status" data-tone={taskTone(state)}>{progressLabels[state]||'待更新'}</span></div>
        <small>{member?.name||'模型未配置'}{member?.model&&' · '+member.model}{formats[job.output_format]&&' · '+formats[job.output_format]}</small>
        {prepared&&job.instruction&&<p>{job.instruction}</p>}
        {!prepared&&job.instruction&&<details><summary>分工要求</summary><p>{job.instruction}</p></details>}
       </li>;
      })}</ul>}
      {prepared&&!editing&&<div className="center-approval">
       <p>确认后计划调用模型 {jobs.length||1} 次。</p>
       <div className="task-progress-actions">
        <button className="auto-button auto-primary" disabled={!!busy||globalBusy} onClick={()=>onConfirm(turn)}>确认执行</button>
        {turn.drafted&&turn.job_plan?.length>0&&<button className="auto-button" disabled={!!busy} onClick={()=>setEditor({id:turn.id,version:turn.plan_revision,jobs:turn.job_plan.map(job=>({...job}))})}>修改分工</button>}
        {!turn.drafted&&onEdit&&turn.job_plan?.length>0&&<button className="auto-button" disabled={!!busy} onClick={()=>onEdit(turn)}>返回修改</button>}
        <button className="auto-link" disabled={!!busy} onClick={()=>onCancel(turn)}>取消本次计划</button>
       </div>
      </div>}
      {!prepared&&<div className="task-progress-actions">
       {running&&<button className="auto-button" disabled={!!busy||turn.state==='stopping'} onClick={onStop}>停止本轮</button>}
       {task&&turnHasDelivery(turn)&&<button className="auto-button" onClick={jump}>回到对话中的成果</button>}
      </div>}
     </article>
     {(turn.failures||[]).map(failure=><section className="task-progress-problem" key={failure.item||'unknown'}>
      <strong>{failure.label} · {failure.title}</strong><p>{failure.hint}</p>
      {failure.retryable&&<button className="auto-button" disabled={!!busy||globalBusy||retryBlocked} onClick={()=>onRetry(turn,failure)}>重试这一项</button>}
      {failure.code==='plan_rejected'&&<button type="button" className="auto-button" disabled={!onRestorePlanningInput} title={!onRestorePlanningInput?'请先处理当前草稿或会话':'只填入原文字'} onClick={()=>onRestorePlanningInput?.(turn)}>取回原需求</button>}
      <details><summary>错误详情</summary><p>{failure.detail}</p>{failure.blocked_reason&&<small>{failure.blocked_reason}</small>}</details>
     </section>)}
     {turn.error&&!turn.failures?.length&&<p className="auto-warning" role="alert">{turn.error}</p>}
     {fileJobs.filter(job=>job.run?.steps?.length).map(job=><details className="task-progress-log center-task-process" key={job.run.id}>
      <summary>{jobs.length>1?job.title+' · ':''}执行记录</summary>
      {job.run.steps.map(row=><TaskMessage key={row.id} row={row} roles={displayRoles(job.run.roles,identities)}/>)}
     </details>)}
     <details className="task-progress-log center-turn-meta"><summary>本轮详情{turn.call_count?` · ${turn.call_count} 次调用`:''}</summary>
      <p>本会话已调用 {session.call_count}/{session.call_limit} 次。</p>
      {turn.retry_of&&<p>{turn.retry_label} · 单项重试</p>}
      {turn.context_omitted>0&&<p>历史参考有 {turn.context_omitted} 处省略或节选。</p>}
      {turn.report&&<p>{turn.report}</p>}
      <small>{progressLabels[turn.state]||turn.state}</small>
     </details>
    </>}
   </div>
   {!collapsed&&!compact&&<button className="auto-button task-window-resize" aria-label="调整任务浮窗大小" title="拖动角落，或用方向键调整大小" {...grip('resize')}><Grip size={15}/></button>}
  </div>
 </dialog>;
}
