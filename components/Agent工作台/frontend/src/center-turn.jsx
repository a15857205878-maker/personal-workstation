import React,{useRef,useState} from 'react';
import CollaborationFiles,{runFilePreview,saveCollaborationFile} from './collaboration-files.jsx';
import ArtifactReview,{artifactFileKey} from './artifact-review.jsx';
import {call} from './auto.jsx';
import {replyBlocks,groupMessages,finalTaskStep,hasTaskDelivery,isTaskTurn,taskNeedsAttention,turnFileCount} from './center-replies.mjs';
import ChatAvatar from './chat-avatar.jsx';
import DragonMark from './dragon-mark.jsx';
import {displayMember,displayRoles} from './member-identity.mjs';
import {taskTone} from './feedback-status.mjs';

const states={prepared:'待确认',queued:'待执行',starting:'准备中',running:'进行中',stopping:'停止中',completed:'完成',failed:'失败',cancelled:'已取消',interrupted:'已中断',skipped:'未执行'};
const model=p=>p?.name||'模型未配置';
const inline=text=>text.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/g).map((s,i)=>s.startsWith('**')&&s.endsWith('**')?<strong key={i}>{s.slice(2,-2)}</strong>:s.startsWith('`')&&s.endsWith('`')?<code key={i}>{s.slice(1,-1)}</code>:s);
function Content({text}){return <div className="center-content">{replyBlocks(text).map((b,i)=>b.type==='code'?<pre key={i}><code>{b.text}</code></pre>:b.type==='heading'?<h4 key={i}>{inline(b.text)}</h4>:b.type==='list'?React.createElement(b.ordered?'ol':'ul',{key:i},b.items.map((s,j)=><li key={j}>{inline(s)}</li>)):<p key={i}>{inline(b.text)}</p>)}</div>;}
export function TaskMessage({row,roles,onRemember,groupMember=false}){
 if(!row)return null;
 const at=row.at&&new Date(row.at),time=at&&!Number.isNaN(at.getTime())?at.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'';
 return <article className="center-reply center-group-message" data-member={groupMember?row.seat:undefined}>
  <ChatAvatar member={groupMember?row.seat:'task'} name={model(roles?.[row.seat])} avatar={roles?.[row.seat]?.avatar}/>
  <div className="center-reply-main"><div className="center-speaker"><strong>{model(roles?.[row.seat])}</strong>{time&&<time dateTime={row.at}>{time}</time>}{row.state==='running'&&<small>正在接话…</small>}</div>
   <div className="center-message-bubble">
    {row.content?.trim().startsWith('<svg')?<details><summary>查看绘图源码</summary><pre>{row.content}</pre></details>:<Content text={row.content||(['failed','cancelled'].includes(row.state)?'没有完整回复。':'正在整理回复…')}/>}

   </div>
   <details className="center-message-meta"><summary>更多</summary><small>{roles?.[row.seat]?.source_name||roles?.[row.seat]?.name} · {row.model||roles?.[row.seat]?.model}{!groupMember&&` · ${row.stage||'执行'} · ${states[row.state]||row.state}`}</small>{onRemember&&row.state==='completed'&&<button className="auto-link" onClick={()=>onRemember(row)}>记住这条</button>}</details>
  </div>
 </article>;
}
function Discussion({run,onRemember,collapsed=false,identities}){
 if(!run)return null;
 const rows=groupMessages(run),remember=row=>onRemember?.({scope:row.seat,kind:'preference',text:'',source:{chat_id:run.id,message_id:row.id,seat:row.seat,excerpt:row.content.slice(0,500),title:run.title?.slice(0,100)||'群聊'}});
 const content=<div className="center-group-replies">{rows.map(row=><TaskMessage key={row.id} row={row} roles={displayRoles(run.roles,identities)} groupMember onRemember={onRemember?remember:null}/>)}</div>;
 return collapsed&&rows.length>0?<details className="center-discussion center-production-discussion"><summary>制作前讨论 · {rows.length} 条发言</summary>{content}</details>:content;
}
function Result({job,onError,identities,tile=false}){
 const [busy,setBusy]=useState(false),inflight=useRef(false);
 const run=job.run,final=finalTaskStep(run);
 async function openFile(name,save=false){
  if(inflight.current)return;
  inflight.current=true;setBusy(true);
  try{
   const result=await call(save?'api_collaboration_file':'api_collaboration_open_file',{id:run.id,name});
   if(save)saveCollaborationFile(result);
  }catch(e){onError(e.message);}
  finally{inflight.current=false;setBusy(false);}
 }
 return <section className={"center-job-result"+(tile?" center-result-tile":"")}><h3 title={job.title}>{job.title}</h3><small className="center-result-owner">{model(displayMember(run.roles?.A,identities))}</small>
  {run.files?.length?<CollaborationFiles compact tile={tile} title={job.title} session={run} disabled={busy} onOpen={openFile} onDownload={name=>openFile(name,true)}/>:final&&<Content text={final.content}/>}
 </section>;
}
export default function CenterTurn({turn,visible,onProgress,onError,onRemember,identities={},onArtifacts,onAccept,reviewBusy}){
 const [review,setReview]=useState(null);
 const jobs=turn.jobs||[],work=!!jobs.length;
 const isTask=isTaskTurn(turn);
 const prepared=turn.state==='prepared';
 const needsAttention=taskNeedsAttention(turn);
 const fileCount=turnFileCount(turn);
 const runs=work?jobs:[{run:turn.run,title:'结果'}];
 const deliveries=runs.filter(({run})=>hasTaskDelivery(run));
 const files=runs.flatMap(({run,title})=>(run?.files||[]).map(file=>({...file,run_id:run.id,label:title+' · '+(file.format?.toUpperCase()||file.name),preview:runFilePreview(run,file.name)})));
 function openArtifacts(file){onArtifacts?.(file,files.map(({run_id,name})=>({run_id,name})));}
 function browseFiles(event){
  if(files.length)setReview({files,initialFile:artifactFileKey(files[0]),opener:event.currentTarget});
 }
 return <section className="center-turn" data-turn-id={turn.id} tabIndex={-1}><div className="center-user-row"><article className="center-user"><span className="partner-speaker-label">{(identities.user?.nickname||'你')+(turn.kind==='execute'?' · 交办任务':'')}</span><p>{turn.text}</p></article><ChatAvatar member="user" name={identities.user?.nickname||"你"} avatar={identities.user?.avatar}/></div>
  {!isTask&&(turn.kind==='chat'||turn.kind==='discuss')&&<Discussion run={turn.run} onRemember={onRemember} identities={identities}/>}
  {turn.draft_reply&&<article className="center-reply center-group-message" data-member="A">
   <DragonMark/><div className="center-reply-main">
    <div className="center-speaker"><strong>龙娘 · 分工建议</strong>{turn.draft_model&&<small>{turn.draft_model}</small>}</div>
    <div className="center-message-bubble"><Content text={turn.draft_reply}/></div>
   </div>
  </article>}
  {(prepared||needsAttention)&&<div className="center-task-notice">
   <span className="feedback-status" data-tone={taskTone(prepared?'prepared':'failed')}>{prepared?'分工待确认':turn.failures?.some(failure=>failure.code==='plan_rejected')?'未生成分工':isTask?'任务需要查看':'回复需要查看'}</span>
   <button className="auto-button" onClick={event=>onProgress(turn.id,event.currentTarget)}>{prepared?'查看分工':'查看详情'}</button>
  </div>}
  {isTask&&<div className="center-collaboration">
   {!!deliveries.length&&<section className="center-task-delivery" data-task-section="delivery" tabIndex={-1}>
    <div className="center-delivery-header"><h3 className="center-delivery-heading">{fileCount?`本轮成果 · ${fileCount} 份文件`:'本轮结果'}</h3>
     <div className="center-delivery-actions">
     {turn.accepted_at?<span className="feedback-status" data-tone="ready">已确认完成</span>:
      onAccept&&turn.state==='completed'&&<button type="button" className="auto-button" disabled={reviewBusy} onClick={()=>onAccept(turn.id)}>确认完成</button>}
     {fileCount>0&&<button className="auto-button center-browse-files" aria-haspopup="dialog" onClick={browseFiles}>浏览本轮文件</button>}
     </div>
    </div>
    {work?<div className="center-results-grid" aria-label="本轮成果">{deliveries.map(job=><Result key={job.run.id} job={job} onError={onError} identities={identities} tile/>)}</div>:<Result job={deliveries[0]} onError={onError} identities={identities}/>}
    {fileCount>0&&onArtifacts&&<button className="auto-link center-turn-artifacts" onClick={()=>openArtifacts()}>在成果中心查看本轮文件</button>}
    {visible&&review&&<ArtifactReview {...review} call={call} onClose={()=>setReview(null)} onArtifacts={onArtifacts?file=>{setReview(null);openArtifacts(file);}:undefined}/>}
   </section>}
   {turn.kind==='chat'&&<Discussion run={turn.run} onRemember={onRemember} identities={identities} collapsed/>}
  </div>}
  {!isTask&&fileCount>0&&onArtifacts&&<button className="auto-link center-turn-artifacts" onClick={()=>openArtifacts()}>在成果中心查看本轮文件</button>}
 </section>;
}
