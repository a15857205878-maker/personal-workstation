import React,{useEffect,useLayoutEffect,useRef,useState} from 'react';
import {ListChecks} from 'lucide-react';
import AutoWorkspace,{call,Settings} from './auto.jsx';
import CenterTurn from './center-turn.jsx';
import TaskProgress from './task-progress.jsx';
import ChatAvatar from './chat-avatar.jsx';
import MemberIdentityDialog from './member-identity-dialog.jsx';
import ConversationManager from './conversation-manager.jsx';
import {conversationBlock} from './conversation-operations.mjs';
import {displayMember,displayRoles} from './member-identity.mjs';
import {responseOptions,memberNames} from './group-members.mjs';
import Attachments from './attachments.jsx';
import SeatStyle from './seat-style.jsx';
import MemoryPanel from './memory-panel.jsx';
const labCall=(action,payload)=>call(action.replace('api_chat_memory','api_center_memory'),payload);
import './agent-center.css';
import ChatSeparator from './chat-separator.jsx';
import {inputHeight} from './chat-geometry.mjs';

import {taskTone} from './feedback-status.mjs';
import {ConversationStart,ConversationStarters} from './partner-start.jsx';
import {isTaskTurn,taskNeedsAttention,turnFileCount,turnHasDelivery} from './center-replies.mjs';
const labels={prepared:'等待确认',starting:'正在启动',running:'进行中',stopping:'正在停止',completed:'已完成',failed:'失败，未自动重试',interrupted:'已中断',cancelled:'已取消',queued:'待执行',skipped:'未发送'};
const formats=[['text','文字'],['docx','文档 DOCX'],['xlsx','表格 XLSX'],['pptx','演示 PPTX'],['svg','绘图 SVG 示意图']];
const id=()=>crypto.randomUUID().replaceAll('-','');
const active=s=>['starting','running','stopping'].includes(s?.status);
const defaultJob=(a,b)=>({title:'文档整理',instruction:'按总任务要求整理可交付正文。',output_format:'docx',primary_id:a||''});
const modelLabel=p=>p?`${p.name} · ${p.model}`:'配置不可用';

function Assignments({jobs,onChange,profiles,disabled}){
 const change=(i,k,v)=>onChange(jobs.map((job,n)=>n===i?{...job,[k]:v}:job));
 return <div className="center-assignments">{jobs.map((job,i)=><fieldset key={i} disabled={disabled}><legend>子任务 {i+1}</legend><div className="center-job-grid"><label>名称<input value={job.title} maxLength={60} onChange={e=>change(i,'title',e.target.value)}/></label><label>交付<select value={job.output_format} onChange={e=>change(i,'output_format',e.target.value)}>{formats.map(([v,n])=><option key={v} value={v}>{n}</option>)}</select></label>{[['primary_id','负责人']].map(([key,name])=><label key={key}>{name}<select value={job[key]} onChange={e=>change(i,key,e.target.value)}><option value="">选择模型</option>{profiles.map(p=><option key={p.id} value={p.id}>{modelLabel(p)}</option>)}</select></label>)}</div><label>这一步要做什么<textarea value={job.instruction} maxLength={1000} onChange={e=>change(i,'instruction',e.target.value)} placeholder="可补充分工要求；总任务和前序实际成果会一起传入"/></label><button className="auto-link" disabled={disabled||jobs.length===1} onClick={()=>onChange(jobs.filter((_,n)=>n!==i))}>移除子任务</button></fieldset>)}<button className="auto-button" disabled={disabled||jobs.length>=4} onClick={()=>onChange([...jobs,{...defaultJob(profiles[0]?.id,profiles[1]?.id),title:'绘图',output_format:'svg',instruction:'把总任务的关键信息绘成清晰的SVG示意图。'}])}>＋ 增加子任务</button><p className="auto-small">每个子任务由一名负责人直接完成，不设审核位。绘图目前生成 SVG 示意图，照片类图片通道尚未接入。最多4步，失败即停止后续步骤。</p></div>;
}

function Center({visible,pendingSetup,onSetupHandled,pendingBrief,onBriefHandled,onLegacy,pendingConversation,onConversationHandled,onTurnArtifacts,historyVisible,historyIntent,onHistoryState,onHistoryIntentHandled}){
 const [profiles,setProfiles]=useState([]),[sessions,setSessions]=useState([]),[session,setSession]=useState(null),[ready,setReady]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(''),[globalBusy,setGlobalBusy]=useState(false),[settings,setSettings]=useState(false),[creating,setCreating]=useState(false);
 const [statusError,setStatusError]=useState('');
 const [a,setA]=useState(''),[b,setB]=useState(''),[c,setC]=useState(''),[jobs,setJobs]=useState([]),[presetName,setPresetName]=useState('我的分工'),[preset,setPreset]=useState(null),[drafts,setDrafts]=useState({}),[assignments,setAssignments]=useState(false),[draftAttachments,setDraftAttachments]=useState({}),[attachmentBusy,setAttachmentBusy]=useState(false);
 const [managing,setManaging]=useState(false);
 const [manual,setManual]=useState(false),[identities,setIdentities]=useState({}),[identityTarget,setIdentityTarget]=useState(null);
 const [styles,setStyles]=useState({A:{preset:'lele',text:''},B:{preset:'jingshui',text:''},C:{preset:'conductor',text:''}}),[memorySeed,setMemorySeed]=useState(null),[target,setTarget]=useState('AB'),[rounds,setRounds]=useState(1);
 const focusTurn=useRef(null),draftInput=useRef(null),focusDraftForSession=useRef(null),navigationInFlight=useRef(null);
 const [progressId,setProgressId]=useState(null);
 const progressButton=useRef(null),progressOpener=useRef(null);
 const [progressGeometry,setProgressGeometry]=useState(null);
 const [inputSize,setInputSize]=useState(72),[height,setHeight]=useState(800);
 const main=useRef(null);
 useEffect(()=>{const observer=new ResizeObserver(()=>{const h=main.current?.clientHeight;if(h>0){setHeight(h);setInputSize(v=>inputHeight(v,h));}});if(main.current)observer.observe(main.current);return()=>observer.disconnect();},[]);
 const retryAttempts=useRef(new Map());
 const current=useRef(null),alive=useRef(true),locked=useRef(false),attempt=useRef(null),feed=useRef(null),nearBottom=useRef(true);
 const displayError=error||statusError;
 const draftKey=session?.id||'new',text=drafts[draftKey]||'',running=active(session),prepared=session?.turns?.find(t=>t.state==='prepared');
 const attachments=draftAttachments[draftKey]||[];
 const setAttachments=items=>setDraftAttachments(old=>({...old,[draftKey]:items}));
 const latestTurn=session?.turns?.at(-1);
 const currentTurn=prepared||(running?latestTurn:null);
 const taskRunning=running&&isTaskTurn(currentTurn);
 const readyTurn=!currentTurn&&isTaskTurn(latestTurn)&&turnHasDelivery(latestTurn)?latestTurn:null;
 const progressTurns=(session?.turns||[]).slice().reverse().filter(turn=>turn.id===currentTurn?.id||isTaskTurn(turn)||taskNeedsAttention(turn)||turn.retry_of);
 const progressDefault=currentTurn||progressTurns[0];
 const progressTone=prepared?'prepared':running?session.status:taskNeedsAttention(progressDefault)?'failed':'';
 const progressHint=prepared?'待确认':running?labels[session.status]:progressTone?'需要查看':'';
 const historyLocked=!!(busy||running||prepared||attachmentBusy);
 const creationLocked=historyLocked||globalBusy;
 useEffect(()=>onHistoryState?.({rows:sessions,active:session?.id||'',ready,locked:historyLocked,creationLocked}),[sessions,session?.id,ready,historyLocked,creationLocked,onHistoryState]);
 const canReturnToDraft=!text.trim()&&!attachments.length&&!pendingBrief&&!attachmentBusy;
 const canRestorePlanningInput=canReturnToDraft&&!manual&&!historyLocked&&!session?.archived;
 const displaySeats=displayRoles(session?.roles,identities);
 const sendBlock=conversationBlock(session,target,rounds,manual,jobs.length||1);
 const startMembers=[['A',a],['B',b],...(c?[['C',c]]:[])].map(([seat,identifier])=>({seat,profile:profiles.find(profile=>profile.id===identifier)}));
 const starterDisabled=!!(text.trim()||attachments.length||manual||running||prepared||busy||globalBusy||attachmentBusy||session?.archived||sendBlock);
 const setText=value=>setDrafts(old=>({...old,[draftKey]:typeof value==='function'?value(old[draftKey]||''):value}));
 function remember(s){if(!s)return;setSessions(old=>[{id:s.id,title:s.title,status:s.status,call_count:s.call_count,call_limit:s.call_limit,archived:!!s.archived},...old.filter(x=>x.id!==s.id)]);}
 async function bootstrap(initial=false){
  const data=await call('api_center_bootstrap');if(!alive.current)return;
  if(initial)call('api_center_identity_get').then(v=>{if(alive.current)setIdentities(v.items||{});}).catch(e=>{if(alive.current)setNotice(e.message);});
  const available=data.profiles||[];
  const hasProfile=identifier=>available.some(profile=>profile.id===identifier);
  setProfiles(available);setSessions(data.sessions||[]);setGlobalBusy(data.busy);setPreset(data.preset);
  if(data.preset_error)setError(data.preset_error);
  setC(old=>initial?available[2]?.id||'':hasProfile(old)?old:'');
  setA(old=>hasProfile(old)?old:available[0]?.id||'');
  setB(old=>hasProfile(old)?old:available[1]?.id||available[0]?.id||'');
  setJobs(old=>old.length?old:data.preset?.jobs||[defaultJob(data.profiles?.[0]?.id,data.profiles?.[1]?.id)]);
  const recent=data.sessions?.find(s=>s.status!=='corrupt'&&!s.archived);
  if(initial&&recent){try{const selected=await call('api_center_status',{id:recent.id});if(alive.current&&!current.current){current.current=selected.id;setSession(selected);setTarget(Object.keys(selected.roles).join(''));}}catch(e){if(alive.current)setError('旧协作无法打开，可直接新建：'+e.message);}}
  if(alive.current)setReady(true);
 }
 useEffect(()=>{alive.current=true;const init=()=>bootstrap(true).catch(e=>alive.current&&setError(e.message));if(window.pywebview?.api?.call)init();else window.addEventListener('pywebviewready',init,{once:true});return()=>{alive.current=false;window.removeEventListener('pywebviewready',init);};},[]);
 useEffect(()=>{if((!visible&&!historyVisible)||!ready)return;let cancelled=false,inflight=false;let tick=0;
  async function poll(){
   if(cancelled||inflight||locked.current)return;
   inflight=true;const selected=current.current;
   try{
    if(selected){
     const s=await call('api_center_status',{id:selected});
     if(!cancelled&&current.current===selected){setSession(s);remember(s);}
    }
    if(++tick%5===0)await bootstrap();
    if(!cancelled&&current.current===selected)setStatusError('');
   }catch(e){
    if(!cancelled&&current.current===selected)setStatusError('状态读取失败：'+e.message);
   }finally{inflight=false;}
  }
  const timer=setInterval(poll,800);return()=>{cancelled=true;clearInterval(timer);};
 },[visible,historyVisible,ready]);
 useEffect(()=>{if(visible&&pendingSetup&&pendingSetup.section!=='options'){setSettings(true);onSetupHandled?.();}},[visible,pendingSetup?.id]);
 useEffect(()=>{if(!visible)setProgressId(null);},[visible]);
 useEffect(()=>{
  if(!visible)return;
  const pending=focusTurn.current;
  if(pending&&focusRecord(pending.id,pending.section,pending.file)){focusTurn.current=null;return;}
  if(session?.turns?.length&&nearBottom.current&&feed.current)feed.current.scrollTop=feed.current.scrollHeight;
 },[visible,session,creating]);
 useLayoutEffect(()=>{
  if(!focusDraftForSession.current||focusDraftForSession.current!==session?.id||creating||busy)return;
  focusDraftForSession.current=null;
  if(visible)draftInput.current?.focus({preventScroll:true});
 },[visible,session?.id,creating,busy]);
 useEffect(()=>{
  if(!visible||!ready||!pendingConversation||navigationInFlight.current===pendingConversation.nonce)return;
  const {id,turn_id,section,file,fromToday}=pendingConversation;
  if(fromToday&&(locked.current||attachmentBusy))return;
  if(locked.current||id!==current.current&&!fromToday&&(running||prepared||attachmentBusy)){setNotice('当前会话还有进行中的操作，请处理后再从原入口打开。');onConversationHandled?.();return;}
  const requested=turn_id?{id:turn_id,section,file}:null;
  if(id===current.current){
   focusTurn.current=requested;
   setCreating(false);
   if(turn_id&&focusRecord(turn_id,section,file))focusTurn.current=null;
   else if(turn_id&&!session?.turns?.some(turn=>turn.id===turn_id)){focusTurn.current=null;setNotice('这条任务记录已不可用，请刷新今日事务。');}
   onConversationHandled?.();return;
  }
  const nonce=pendingConversation.nonce;
  navigationInFlight.current=nonce;
  open(id,{guardCurrent:!fromToday,requested}).then(()=>{
   if(navigationInFlight.current===nonce)onConversationHandled?.(nonce);
  });
 },[visible,ready,pendingConversation?.nonce,busy,attachmentBusy]);
 useEffect(()=>{
  if(!visible||!ready||!historyIntent||pendingConversation||locked.current)return;
  const {id:identifier,nonce}=historyIntent;
  if(!identifier){
   if(!creationLocked){setCreating(true);setManual(false);setAssignments(false);}
  }else if(identifier===current.current){
   setCreating(false);
  }else if(!historyLocked){
   open(identifier,{guardCurrent:true});
  }
  onHistoryIntentHandled?.(nonce);
 },[visible,ready,historyIntent?.nonce,pendingConversation?.nonce,historyLocked,creationLocked]);
 function focusRecord(turnId,section,file){
  if(section==='progress'&&session?.turns?.some(turn=>turn.id===turnId)&&!creating){
   openProgress(turnId);
   return true;
  }
  const row=feed.current?.querySelector('[data-turn-id="'+turnId+'"]');
  if(!row?.getClientRects().length)return false;
  const match=file&&[...row.querySelectorAll('[data-artifact-run]')].find(node=>node.dataset.artifactRun===file.run_id&&node.dataset.artifactName===file.name);
  const element=match||(section?[...row.querySelectorAll('[data-task-section]')].find(node=>node.dataset.taskSection===section)||row:row);
  if(match)(match.closest('.center-job-result')||match).scrollIntoView({block:'center'});
  else element.scrollIntoView({block:section?'start':'center'});
  element.focus({preventScroll:true});
  nearBottom.current=false;
  return true;
 }
 async function action(name,fn){if(locked.current)return;locked.current=true;setBusy(name);setError('');setNotice('');try{await fn();}catch(e){if(alive.current)setError(e.message);}finally{locked.current=false;if(alive.current)setBusy('');}}
 async function open(identifier,{guardCurrent=false,requested=null}={}){await action('open',async()=>{if(guardCurrent&&current.current&&current.current!==identifier){const previous=await call('api_center_status',{id:current.current});if(active(previous)||previous.turns?.some(t=>t.state==='prepared')){setSession(previous);remember(previous);setNotice('当前会话还有进行中的操作或待确认分工，请处理后再打开其他记录。');return;}}const s=await call('api_center_status',{id:identifier});if(requested&&!s.turns.some(turn=>turn.id===requested.id)){setNotice('这条任务记录已不可用，请刷新今日事务。');requested=null;}focusTurn.current=requested;current.current=s.id;setProgressId(null);setSession(s);setTarget(Object.keys(s.roles).join(''));setRounds(1);setManual(false);setAssignments(false);attempt.current=null;setCreating(false);nearBottom.current=!requested;});}
 async function create(){await action('create',async()=>{const s=await call('api_center_create',{primary_id:a,reviewer_id:b,...(c?{third_id:c}:{}),seat_styles:Object.fromEntries(Object.entries(styles).filter(([seat])=>seat!=='C'||c))});current.current=s.id;focusDraftForSession.current=s.id;setSession(s);remember(s);setTarget(Object.keys(s.roles).join(''));setRounds(1);setManual(false);setAssignments(false);setCreating(false);attempt.current=null;nearBottom.current=true;});}
 function beginTask(){
  setManual(true);setAssignments(true);
  setJobs(old=>old.map(job=>job.primary_id?job:{...job,primary_id:session.roles.A.id}));
  draftInput.current?.focus({preventScroll:true});
 }
 function openProgress(turnId,opener=progressButton.current){
  progressOpener.current=opener;
  setProgressId(turnId||'');
 }
 function restorePlanningInput(turn){
  if(!canRestorePlanningInput)return;
  setText(previous=>previous.trim()?previous:turn.text);
  setManual(false);
  setAssignments(false);
  setProgressId(null);
  requestAnimationFrame(()=>draftInput.current?.focus({preventScroll:true}));
 }
 function useStarter(value){
  if(starterDisabled)return;
  setText(previous=>previous.trim()?previous:value);
  draftInput.current?.focus({preventScroll:true});
 }
 async function send(drafting=false){
  const kind=drafting?'draft':manual?'execute':'chat';
  if(!session||!text.trim()||attachmentBusy||busy||running||prepared||globalBusy||(drafting?(session.archived||session.call_limit-session.call_count<2):sendBlock))return;
  if(attachments.length){setError('请先将附件识别文字加入输入，或移除附件。');return;}
  if(kind!=='execute'&&text.trim().length>4000){setError('讨论消息最多4000字，可缩短或切换分工执行。');return;}
  const signature=JSON.stringify({id:session.id,kind,text:text.trim(),...(drafting?{}:kind==='execute'?{jobs}:{target,rounds})});
  if(attempt.current?.signature!==signature)attempt.current={signature,request_id:id()};
  await action('send',async()=>{
   const request=attempt.current.request_id;
   const payload=JSON.parse(signature);
   if(drafting)delete payload.kind;
   const s=await call(drafting?'api_center_draft':'api_center_send',{...payload,request_id:request});
   if(current.current!==s.id)return;
   if(kind==='execute'){
    if(s.turns.some(turn=>turn.id===request&&turn.state==='prepared'))openProgress(request);
    setAssignments(false);setManual(false);
   }
   if(drafting)openProgress(request);
   setSession(s);remember(s);setText('');attempt.current=null;nearBottom.current=true;
  });
 }
 async function retry(turn,failure){const key=JSON.stringify([session.id,turn.id,failure.item]);if(!retryAttempts.current.has(key))retryAttempts.current.set(key,id());await action('retry',async()=>{const request=retryAttempts.current.get(key);const value=await call('api_center_retry',{id:session.id,turn_id:turn.id,item:failure.item,request_id:request});setSession(value);remember(value);if(value.turns.some(item=>item.id===request))setProgressId(request);nearBottom.current=true;});}
 async function confirm(turn){await action('confirm',async()=>{const s=await call('api_center_confirm',{id:session.id,request_id:turn.id,...(turn.drafted?{plan_revision:turn.plan_revision}:{})});setSession(s);remember(s);setManual(false);});}
 async function saveDraft(turnId,version,jobs){
  let saved=false;
  await action('edit',async()=>{const result=await call('api_center_edit_plan',{id:session.id,turn_id:turnId,plan_revision:version,jobs});setSession(result);remember(result);saved=true;});
  return saved;
 }
 async function accept(turnId){await action('accept',async()=>{
  const receipt=await call('api_center_accept',{id:session.id,turn_id:turnId});
  setSession(current=>current?.id===receipt.conversation_id?{...current,turns:current.turns.map(turn=>turn.id===receipt.turn_id?{...turn,accepted_at:receipt.accepted_at}:turn)}:current);
 });}
 async function cancelPlan(turn,restore=false){
  if(restore&&(!canReturnToDraft||!turn.job_plan?.length))return;
  await action('stop',async()=>{
   const s=await call('api_center_stop',{id:session.id,prepared_id:turn.id});
   setSession(s);remember(s);setManual(false);
   if(!restore)return;
   if(!s.turns.some(item=>item.id===turn.id&&item.state==='cancelled'&&!item.call_count)){
    setNotice('分工状态已更新，请核对当前记录。');return;
   }
   setText(turn.text);setJobs(turn.job_plan.map(job=>({...job})));
   setProgressId(null);
   focusDraftForSession.current=s.id;
   setManual(true);setAssignments(true);
  });
 }
 async function stop(){await action('stop',async()=>{const s=await call('api_center_stop',{id:session.id,...(currentTurn?{turn_id:currentTurn.id}:{})});setSession(s);remember(s);setManual(false);});}
 async function savePreset(){await action('preset',async()=>{const value=await call('api_center_preset_save',{name:presetName,jobs});setPreset(value);setNotice('分工预设已保存；每次执行前仍可修改。');});}
 async function manage(changes){await action('manage',async()=>{const value=await call('api_center_manage',{id:session.id,...changes});setSession(value);remember(value);setManaging(false);});}
 function updateProfile(p){setProfiles(old=>[...old.filter(x=>x.id!==p.id),p]);setA(old=>old||p.id);setB(old=>old||p.id);}
 return <div className="agent-center center-single-rail">
 <section ref={main} className="center-main" aria-label="搭档群聊">
 <header className="center-heading">
  <div className="center-heading-title"><strong>{session?.title||'搭档群聊'}</strong>{session&&<p>{memberNames(displayRoles(session.roles,identities))}</p>}</div>
  <div className="center-heading-actions">
   {readyTurn&&!creating&&<button className="auto-button center-task-jump" onClick={()=>focusRecord(readyTurn.id,'delivery')}>{turnFileCount(readyTurn)?'查看本轮成果':'查看本轮结果'}</button>}
   {session&&!creating&&<button ref={progressButton} className="auto-button center-progress-toggle" aria-haspopup="dialog" onClick={event=>openProgress(progressDefault?.id,event.currentTarget)}>
    <ListChecks size={15} aria-hidden="true"/><span>任务进度</span>{progressHint&&<span className="feedback-status" data-tone={taskTone(progressTone)}>{progressHint}</span>}
   </button>}
   <details className="center-settings-menu"><summary>群聊设置</summary><button className="auto-button" disabled={!session||!!busy||running||!!prepared||globalBusy} onClick={()=>setManaging(true)}>会话管理</button><button className="auto-button" onClick={()=>setMemorySeed({})}>长期记忆</button><button className="auto-button" onClick={()=>setSettings(true)}>模型连接</button><button className="auto-button" onClick={onLegacy}>原高级协作</button><small>点击成员资料可更换头像和昵称。</small></details>
  </div>
 </header>
 {sendBlock&&session&&!creating&&!prepared&&!running&&<p className="auto-warning" role="status">{sendBlock}</p>}{displayError&&progressId===null&&<div className="auto-warning" role="alert">{displayError}</div>}{notice&&progressId===null&&<p role="status">{notice}</p>}
 {(!session||creating)&&<ConversationStart ready={ready} error={error} loading={!!busy||globalBusy}
  hasProfiles={profiles.length>0} members={startMembers} onCreate={create} onModels={()=>setSettings(true)}
  onRetry={()=>action('bootstrap',()=>bootstrap(true))} onBack={session?()=>setCreating(false):undefined}>
  <div className="center-job-grid">{[[a,setA,'聊天成员 A'],[b,setB,'聊天成员 B'],[c,setC,'聊天成员 C（可选）']].map(([value,setter,label])=><label key={label}>{label}<select aria-label={label} value={value} disabled={!!busy||globalBusy} onChange={e=>setter(e.target.value)}><option value="">{label.includes('C')?'不加入第三位':'选择模型'}</option>{profiles.map(p=><option key={p.id} value={p.id}>{modelLabel(p)}</option>)}</select></label>)}</div>
  <details className="center-lab-settings"><summary>成员表达风格</summary><div className="center-job-grid">{(c?['A','B','C']:['A','B']).map(seat=><SeatStyle key={seat} chat seat={seat} style={styles[seat]} locked={!!busy||globalBusy} onChange={patch=>setStyles(old=>({...old,[seat]:{...old[seat],...patch}}))}/>)}</div></details>
 </ConversationStart>}
 {!creating&&session&&<><details className="center-members"><summary>成员资料 · {Object.keys(session.roles).length} 人</summary><div className="center-member-strip" aria-label="当前群聊成员">{Object.entries(session.roles).map(([seat,p])=><span key={seat}><button className="center-member-edit" aria-label={`编辑 ${displayMember(p,identities).name} 的资料`} disabled={!!busy||running||globalBusy} onClick={()=>setIdentityTarget(p.id)}><ChatAvatar member={seat} name={displayMember(p,identities).name} avatar={identities[p.id]?.avatar}/><span><strong>{displayMember(p,identities).name}</strong><small>{p.model}</small></span></button></span>)}<button className="auto-button center-my-identity" disabled={!!busy||running||globalBusy} onClick={()=>setIdentityTarget('user')}>我的资料</button></div></details>
 <div className="center-chat-area">
 <div ref={feed} className="center-feed" onScroll={()=>{const el=feed.current;nearBottom.current=el.scrollHeight-el.scrollTop-el.clientHeight<90;}}>{!session.turns.length&&!session.archived&&<ConversationStarters disabled={starterDisabled} onChoose={useStarter}/>}
 {session.turns.map(turn=><CenterTurn key={turn.id} turn={turn} visible={visible} onProgress={openProgress} onAccept={session.archived?undefined:accept} reviewBusy={!!busy}
  onError={setError} onRemember={setMemorySeed} identities={identities} onArtifacts={(file,files)=>onTurnArtifacts?.({conversation_id:session.id,turn_id:turn.id,files,file:file&&{run_id:file.run_id,name:file.name}})}/>)}</div>
 {visible&&progressId!==null&&<TaskProgress session={session} turns={progressTurns} selected={progressId} onSelect={setProgressId}
  geometry={progressGeometry} onGeometry={setProgressGeometry}
  onSaveDraft={saveDraft} renderEditor={(items,setItems,disabled)=><Assignments jobs={items} onChange={setItems} profiles={profiles} disabled={disabled}/>}
  onRestorePlanningInput={canRestorePlanningInput?restorePlanningInput:undefined}
  opener={progressOpener.current} onClose={()=>setProgressId(null)} onDelivery={turnId=>requestAnimationFrame(()=>focusRecord(turnId,'delivery'))}
  activeId={currentTurn?.id} busy={busy} globalBusy={globalBusy} identities={identities} error={displayError} notice={notice}
  onConfirm={confirm} onEdit={canReturnToDraft?item=>cancelPlan(item,true):undefined} onCancel={cancelPlan} onStop={stop} onRetry={retry}
  retryBlocked={running||!!prepared||!!session.archived||session.call_count>=session.call_limit}/>}
 </div>
 {!prepared&&!taskRunning&&<ChatSeparator axis="height" className="center-input-resize" label="调整聊天与输入区大小" value={inputSize} min={48} max={inputHeight(300,height)} onChange={v=>setInputSize(inputHeight(v,main.current?.clientHeight))} onReset={()=>setInputSize(inputHeight(72,main.current?.clientHeight))}/>}
 <div className="center-composer" data-task-draft={manual&&!attachments.length&&!attachmentBusy||undefined} hidden={!!prepared||taskRunning}>{pendingBrief&&<div className="center-plan"><strong>待接收的任务需求</strong><p>{pendingBrief.text}</p><button className="auto-button" disabled={!!busy||running||!!prepared||!!text.trim()} onClick={()=>{setText(pendingBrief.text);beginTask();onBriefHandled?.();}}>放入输入框，继续检查</button><button className="auto-button" onClick={onBriefHandled}>暂不接收</button>{text.trim()&&<p>先处理已有输入，再接收新需求。</p>}</div>}
 <div className="center-composer-options center-group-tools">
  <label className="center-response-picker"><span>谁来回复</span><select aria-label="群聊回应对象" value={target}
   disabled={manual||!!busy||running||!!prepared} onChange={e=>{setTarget(e.target.value);if(e.target.value.length===1)setRounds(1);}}>
   {responseOptions(displaySeats).map(([v,n],index)=><option key={v} value={v}>{index===0?'所有搭档':n}</option>)}
  </select></label>
  <details className="center-group-settings"><summary>回复轮数{rounds>1?` · ${rounds} 轮`:''}</summary><label>接话轮数<select aria-label="群聊轮数" value={rounds} disabled={manual||!!busy||running||!!prepared||target.length===1} onChange={e=>setRounds(Number(e.target.value))}>{[1,2,4,6].map(n=><option key={n} value={n}>{n} 轮</option>)}</select></label><p className="auto-small">本轮接话最多 {target.length*rounds} 次，剩余 {session.call_limit-session.call_count} 次。每位成员每轮回应一次，文件交付另计。</p></details>
  <button className="auto-button" aria-expanded={assignments} disabled={!!busy||running||!!prepared||attachmentBusy} onClick={()=>{if(manual)setAssignments(!assignments);else beginTask();}}>{manual?(assignments?'收起分工':'展开分工'):'交办任务'}</button>
  {manual&&<><span className="center-manual-hint">本轮使用指定分工</span><button className="auto-link" disabled={!!busy||running||!!prepared||attachmentBusy} onClick={()=>{setManual(false);setAssignments(false);}}>取消指定</button></>}
  {running&&<button className="auto-button" disabled={!!busy} onClick={stop}>停止本轮</button>}
 </div>
 <label className="center-input-label"><span className="center-compose-label">{manual?'这次任务的目标':'发给搭档们'}</span><textarea ref={draftInput} style={{height:inputSize}} aria-label="协作输入" onKeyDown={e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'&&!e.nativeEvent.isComposing){e.preventDefault();send();}}} placeholder={manual?'写下要交付的成果…':'给搭档发消息…'} maxLength={manual?8000:4000} disabled={!!busy||running||!!prepared||attachmentBusy||!!session.archived} value={text} onChange={e=>setText(e.target.value)}/></label>
 {assignments&&<div className="center-assignment-editor">
  <h3>分工与交付</h3>
  <Assignments jobs={jobs} onChange={setJobs} profiles={profiles} disabled={!!busy||running||!!prepared}/>
  <details className="center-task-presets"><summary>分工预设</summary><label>预设名称<input value={presetName} maxLength={60} onChange={e=>setPresetName(e.target.value)}/></label><div className="center-composer-options"><button className="auto-button" disabled={!!busy||running||!!prepared} onClick={savePreset}>保存为我的分工预设</button><button className="auto-button" disabled={!preset||!!busy||running||!!prepared} onClick={()=>{setJobs(preset.jobs);setPresetName(preset.name);}}>使用已保存预设</button></div></details>
 </div>}
 <div className="studio-composer-actions">
 <div className="center-attachment"><Attachments key={draftKey} compact composer items={attachments} onChange={setAttachments} disabled={!!busy||running||!!prepared||!!session.archived} onBusyChange={setAttachmentBusy} onInsert={async extra=>{if(text.length+extra.length+2>(manual?8000:4000))throw Error('加入后的文字超过本轮上限，请缩短资料。');setText(old=>old?old+'\n\n'+extra:extra);}}/></div>
 <div className="center-send-row"><small>{prepared?'请确认或取消上面的分工计划':running?'成员正在接话或完成任务，随时可停止。':attachments.length?'核对资料后，把识别文字加入草稿。':manual?'本轮使用指定分工，检查后确认执行；取消指定可回到群聊。':'Ctrl + Enter 发送'}</small>
 {!manual&&<button className="auto-button center-dragon-draft" title="由当前会话的主搭档模型拟稿，确认后执行" disabled={!!busy||running||!!prepared||!text.trim()||attachmentBusy||attachments.length>0||globalBusy||session.archived||session.call_limit-session.call_count<2} onClick={()=>send(true)}>请龙娘拟分工</button>}
 <button className="auto-button auto-primary" disabled={!!busy||running||!!prepared||!text.trim()||attachmentBusy||attachments.length>0||globalBusy||!!sendBlock} onClick={()=>send()}>{busy==='send'?'提交中…':manual?'检查分工':'发送'}</button></div>
 </div></div></>}

 </section>
 {managing&&session&&<ConversationManager key={session.id} session={session} busy={!!busy||running||globalBusy} error={error} onClose={()=>setManaging(false)} onSave={manage}/>}
 {identityTarget!==null&&<MemberIdentityDialog key={identityTarget} identifier={identityTarget} profile={profiles.find(p=>p.id===identityTarget)} seat={Object.keys(session?.roles||{}).find(s=>session.roles[s].id===identityTarget)||'user'} value={identities[identityTarget]} orphans={Object.entries(identities).filter(([key])=>key!=='user'&&!profiles.some(p=>p.id===key))} locked={running||globalBusy} onClose={()=>setIdentityTarget(null)} onSaved={setIdentities}/>}
 {memorySeed!==null&&<MemoryPanel seed={memorySeed} apiCall={labCall} onClose={()=>setMemorySeed(null)} onUpdated={()=>{}} locked={running||globalBusy}/>}
 {settings&&<Settings profiles={profiles} onProfiles={updateProfile} onRemove={identifier=>setProfiles(old=>old.filter(p=>p.id!==identifier))} onClose={()=>{setSettings(false);bootstrap().catch(e=>setError(e.message));}} locked={running||globalBusy}/>}
 </div>;
}

export default function AgentPartner(props){
 const [legacy,setLegacy]=useState(false);
 useEffect(()=>{if(props.historyIntent||props.pendingConversation||props.pendingBrief)setLegacy(false);else if(props.pendingSetup?.section==='options')setLegacy(true);else if(props.pendingSetup)setLegacy(false);},[props.pendingSetup?.id,props.pendingBrief?.id,props.pendingConversation?.nonce,props.historyIntent?.nonce]);
 return <div className="center-partner"><div className="center-unified" hidden={legacy}><Center {...props} visible={props.visible&&!legacy} pendingSetup={legacy?null:props.pendingSetup} onLegacy={()=>setLegacy(true)}/></div>{legacy&&<div className="center-legacy-toolbar"><button className="auto-button" onClick={()=>setLegacy(false)}>← 返回统一协作对话</button><span>原高级功能与记录兼容入口</span></div>}<div hidden={!legacy}><AutoWorkspace {...props} pendingSetup={legacy?props.pendingSetup:null} pendingBrief={null} visible={props.visible&&legacy}/></div></div>;
}
