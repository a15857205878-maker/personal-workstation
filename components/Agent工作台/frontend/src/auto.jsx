import {starterTask,taskVoice,collaborationSignals,stepProgress,partnerState,checkedDraft,revisionDraft} from './partner-model.mjs';
import React,{useEffect,useRef,useState} from 'react';
import {isActive,statusLabel,validatePlan,sameModel,canRetry,finalReply,stepLabel,buildProfilePayload} from './auto-model.mjs';
import './auto.css';
import Attachments from './attachments.jsx';
import GenerationHandoff from './handoff.jsx';
import CollaborationFiles,{saveCollaborationFile} from './collaboration-files.jsx';
import useDialog from './use-dialog.js';
import IncomingTasks from './incoming-tasks.jsx';
import {TaskPanel,BriefDialog} from './task-panel.jsx';
import {acceptBrief} from './workspace-transfer.mjs';

export async function call(action,payload={}){
 if(!window.pywebview?.api?.call)throw Error('正在等待本地桌面服务。');
 const result=await window.pywebview.api.call(action,payload);
 if(!result.ok)throw Error(result.error||'操作未完成');
 return result.data;
}
const emptyProfile=()=>({id:'',name:'DeepSeek',kind:'deepseek',base_url:'https://api.deepseek.com',model:'deepseek-flash',api_key:''});
function Usage({usage}){return <span>{usage&&usage.known!==false&&Number.isFinite(usage.prompt_tokens)&&Number.isFinite(usage.completion_tokens)?`输入 ${usage.prompt_tokens.toLocaleString()} / 输出 ${usage.completion_tokens.toLocaleString()} Token`:'Token 用量未返回'}</span>;}
export function Settings({profiles,onProfiles,onRemove,onClose,locked}){
 const [draft,setDraft]=useState(emptyProfile),[busy,setBusy]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState(''),[models,setModels]=useState([]);
 const [clientPath,setClientPath]=useState(''),[antigravity,setAntigravity]=useState(null);
 const [confirmDelete,setConfirmDelete]=useState(false);
 const dialog=useDialog(close,!!busy),first=useRef(null),mounted=useRef(true);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 useEffect(()=>{call('api_local_path').then(value=>{if(mounted.current)setClientPath(value.executable||'');}).catch(()=>{});},[]);
 function close(){if(busy)return;setDraft(emptyProfile());onClose();}
 function choose(id){const p=profiles.find(x=>x.id===id);setDraft(p?{...p,api_key:''}:emptyProfile());setError('');setMessage('');setModels([]);setConfirmDelete(false);}
 function change(key,value){setDraft(d=>({...d,[key]:value}));setError('');setMessage('');setConfirmDelete(false);if(key==='base_url'||key==='model')setModels([]);}
 async function perform(action){
  if(busy||locked)return;setBusy(action);setError('');setMessage('');if(action!=='remove')setConfirmDelete(false);
  try{
   if(action==='antigravity'){
    const result=await call('api_discover_antigravity');if(!mounted.current)return;setAntigravity(result);setModels((result.models||[]).map(m=>m.id));if(result.state==='catalog')setDraft({...emptyProfile(),name:'Antigravity Gemini',kind:'antigravity_local',base_url:'antigravity://local',model:result.models?.find(m=>m.id==='gemini-4-argon-medium')?.id||result.models?.[0]?.id||''});
   }else if(action==='remove'){
    const result=await call('api_profile_delete',{id:draft.id});if(!mounted.current)return;
    onRemove(result.id);setDraft(emptyProfile());setModels([]);setConfirmDelete(false);setMessage('配置已删除，历史会话保留。');
   }else if(action==='path'){
    const value=await call('api_local_path',{executable:clientPath});if(!mounted.current)return;setClientPath(value.executable||'');setMessage('本机路径已保存，仅用于这台电脑。请重新检测。');
   }else if(action==='discover'){
    const result=await call('api_discover_local');if(!mounted.current)return;
    setModels((result.models||[]).map(m=>m.id));setMessage(result.message);
    if(result.state==='catalog')setDraft({...emptyProfile(),name:'本机 Codex',kind:'codex_local',base_url:'codex://local',model:result.models?.[0]?.id||''});
   }else if(action==='save'){
    const payload=buildProfilePayload(draft);setDraft(d=>({...d,api_key:''}));
    if(!draft.name.trim()||!draft.base_url.trim()||!draft.model.trim())throw Error('请填写配置名、接口地址和模型 ID。');
    const p=await call('api_profile_save',payload);if(!mounted.current)return;
    onProfiles(p);setDraft({...p,api_key:''});setMessage('配置已保存。密钥不会回读。');
   }else if(action==='test'){
    const result=await call('api_profile_test',{id:draft.id});if(!mounted.current)return;
    setModels(result.models||[]);setMessage(result.message||'已读取模型列表；这不代表生成能力已验证。');
   }else{
    const p=await call('api_profile_delete_key',{id:draft.id});if(!mounted.current)return;
    onProfiles(p);setDraft({...p,api_key:''});setMessage('已删除此配置的密钥。');
   }
  }catch(e){if(mounted.current)setError(e.message);}finally{if(mounted.current)setBusy('');}
 }
 const local=['codex_local','antigravity_local'].includes(draft.kind),saved=profiles.find(x=>x.id===draft.id),dirty=!!saved&&['name','kind','base_url','model'].some(k=>draft[k]!==saved[k]);
 return <div className="auto-modal-backdrop"><section className="auto-modal" role="dialog" aria-modal="true" aria-labelledby="model-settings-title" ref={dialog}>
  <div className="auto-modal-head"><div><span className="auto-kicker">YOUR MODELS</span><h2 id="model-settings-title">模型设置</h2></div><button className="auto-close" aria-label="关闭模型设置" disabled={!!busy} onClick={close}>×</button></div>
  <div className="auto-modal-body"><p className="auto-description">连接本机已登录的 Codex，或使用你自己的 API 密钥。换一台电脑后重新检测客户端，密钥由使用者自行填写。</p>
  <div className="auto-discovery"><div><strong>本机模型入口</strong><p>检测安装、登录和目录，不发送生成任务。</p></div><button className="auto-button" disabled={!!busy||locked} onClick={()=>perform('discover')}>{busy==='discover'?'正在检测…':'检测本机 Codex'}</button></div>
  <details className="auto-client-path"><summary>没有检测到？手动指定客户端</summary><label className="auto-field">原生 Codex 路径<input aria-label="本机 Codex 路径" value={clientPath} disabled={!!busy||locked} placeholder="完整 codex.exe 路径；留空恢复自动检测" onChange={e=>setClientPath(e.target.value)}/></label><button className="auto-button" disabled={!!busy||locked} onClick={()=>perform('path')}>{busy==='path'?'保存中…':'保存本机路径'}</button><p className="auto-small">只保存在本机 host.json，不随模型配置或会话共享；不支持脚本或命令参数。</p></details>
  <div className="auto-discovery antigravity-discovery"><div><strong>Antigravity · 本机登录</strong><p>读取官方 CLI 的可用模型，不发送生成任务。</p>{antigravity&&<p role="status" data-state={antigravity.state}>{antigravity.message}</p>}<a href="https://antigravity.google/docs/getting-started?tab=cli" target="_blank" rel="noreferrer">官方 CLI 安装说明</a></div><button className="auto-button" disabled={!!busy||locked} onClick={()=>perform('antigravity')}>{busy==='antigravity'?'正在检查…':'检查 Antigravity'}</button></div>
  {locked&&<div className="auto-warning">协作运行中，结束后可修改配置或测试连接。</div>}
  <label className="auto-field">已保存配置<select ref={first} value={draft.id} disabled={!!busy||locked} onChange={e=>choose(e.target.value)}><option value="">＋ 新建配置</option>{profiles.map(p=><option key={p.id} value={p.id}>{p.name} · {p.model}{['codex_local','antigravity_local'].includes(p.kind)?' · 本机登录':p.has_key?' · 已配置密钥':' · 缺少密钥'}</option>)}</select></label>
  <div className="auto-form-grid"><label className="auto-field">配置名<input value={draft.name} disabled={!!busy||locked} onChange={e=>change('name',e.target.value)}/></label><label className="auto-field">服务商类型<select aria-label="通道类型" value={draft.kind} disabled={!!busy||locked} onChange={e=>{setDraft({...emptyProfile(),name:e.target.value==='antigravity_local'?'Antigravity Gemini':e.target.value==='codex_local'?'本机 Codex':'API 配置',kind:e.target.value,base_url:e.target.value==='antigravity_local'?'antigravity://local':e.target.value==='codex_local'?'codex://local':'https://api.deepseek.com',model:''});setModels([]);setMessage('');setError('');}}><option value="deepseek">DeepSeek API</option><option value="compatible">兼容 API 接口</option><option value="codex_local">本机 Codex</option><option value="antigravity_local">本机 Antigravity</option></select></label></div>
  {!local&&<label className="auto-field">接口地址<input aria-label="接口地址" type="url" value={draft.base_url} disabled={!!busy||locked} spellCheck={false} onChange={e=>change('base_url',e.target.value)}/></label>}
  <label className="auto-field">模型 ID<input aria-label="模型 ID" value={draft.model} list="auto-model-options" disabled={!!busy||locked} spellCheck={false} onChange={e=>change('model',e.target.value)}/><datalist id="auto-model-options">{models.map(m=><option key={m} value={m}/>)}</datalist></label>
  {!local&&<label className="auto-field">API 密钥 <span>{saved?.has_key?'已配置 · 留空保留；更换地址需输入新密钥':'尚未配置'}</span><input aria-label="API 密钥" type="password" autoComplete="new-password" value={draft.api_key} disabled={!!busy||locked} placeholder={saved?.has_key?'不会显示已保存的密钥':'输入你自己的 API 密钥'} onChange={e=>change('api_key',e.target.value)}/></label>}
  <p className="auto-small">{local?'由对应本机客户端管理登录，不读取或复制登录令牌。模型目录不代表生成权限。Antigravity 仅文字回复，目标输出长度非硬 Token 上限。':'密钥由使用者手填，不从其他应用提取。保存后测试连接可读取模型列表，也可手填实际模型 ID。'} 检测与连接测试均不发起生成。</p>
  {error&&<div className="auto-warning" role="alert">{error}</div>}{message&&<div className="auto-feedback" role="status">{message}</div>}
  {confirmDelete&&saved&&<div className="auto-warning" role="group" aria-label="删除配置确认"><p>删除“{saved.name} · {saved.model}”及其已保存密钥？历史仍可回看；关联任务如需重新运行，请选择其他配置新建会话。</p><div className="profile-delete-confirm"><button className="auto-button" disabled={!!busy} onClick={()=>setConfirmDelete(false)}>取消</button><button className="auto-button auto-danger-text" disabled={locked||!!busy} onClick={()=>perform('remove')}>{busy==='remove'?'删除中…':'确认删除配置'}</button></div></div>}
  </div><div className="auto-modal-actions"><button className="auto-button auto-danger-text" disabled={locked||!!busy||!saved} onClick={()=>{setConfirmDelete(true);setError('');setMessage('');requestAnimationFrame(()=>dialog.current?.querySelector('[aria-label="删除配置确认"]')?.scrollIntoView({block:'nearest'}));}}>删除配置</button><button className="auto-button auto-danger-text" disabled={locked||!!busy||!saved?.has_key} onClick={()=>perform('delete')}>{busy==='delete'?'删除中…':'删除密钥'}</button><div><button className="auto-button" disabled={locked||!!busy||!draft.id||dirty||!!draft.api_key} onClick={()=>perform('test')}>{busy==='test'?'连接测试中…':'测试连接'}</button><button className="auto-button auto-primary" disabled={locked||!!busy} onClick={()=>perform('save')}>{busy==='save'?'保存中…':'保存配置'}</button></div></div>
 </section></div>;
}

export default function AutoWorkspace({visible=true,pendingBrief,onBriefHandled,onToIndependent,pendingSetup,onSetupHandled}){
 const [profiles,setProfiles]=useState([]),[sessions,setSessions]=useState([]),[session,setSession]=useState(null),[view,setView]=useState(null),[ready,setReady]=useState(false),[settings,setSettings]=useState(false),[busy,setBusy]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState(''),[note,setNote]=useState('');
 const [plan,setPlan]=useState({task:'',primary_id:'',reviewer_id:'',rounds:1,call_limit:9,max_tokens:1024,context_count:0,persona:'conductor',output_format:'text'});

 const [attachmentBusy,setAttachmentBusy]=useState(false);
 const [attachments,setAttachments]=useState([]);
 const [drawer,setDrawer]=useState('');
 useEffect(()=>{if(!visible||!ready||!pendingSetup)return;if(pendingSetup.section==='options'){setSettings(false);setDrawer('options');}else{setDrawer('');setSettings(true);}onSetupHandled?.();},[visible,ready,pendingSetup?.id]);
 const [checked,setChecked]=useState(null),[revision,setRevision]=useState(''),[includeGoal,setIncludeGoal]=useState(false),[includeResult,setIncludeResult]=useState(false);
 const alive=useRef(true),pollTimer=useRef(null),copyArea=useRef(null),loadSequence=useRef(0),actionLock=useRef(false);
 const active=isActive(session),display=view||session,history=!!view;
 useEffect(()=>{setRevision('');setIncludeGoal(false);setIncludeResult(false);},[display?.id]);
 function setField(k,v){setPlan(p=>({...p,[k]:v}));}

 function remember(s){if(!s)return;setSessions(list=>[{id:s.id,title:s.title||s.task,status:s.status,updated:new Date().toISOString(),call_count:s.call_count,call_limit:s.call_limit},...list.filter(x=>x.id!==s.id)]);}
 async function bootstrap(){try{const data=await call('api_bootstrap');if(!alive.current)return;setProfiles(data.profiles||[]);setSessions(data.sessions||[]);setSession(data.active);setPlan(p=>({...p,context_count:data.room_available===false?0:p.context_count,primary_id:p.primary_id||(data.profiles?.[0]?.id||''),reviewer_id:p.reviewer_id||(data.profiles?.[1]?.id||data.profiles?.[0]?.id||'')}));setReady(true);setError('');}catch(e){if(alive.current)setError(e.message);}}
 useEffect(()=>{alive.current=true;const init=()=>bootstrap();if(window.pywebview?.api?.call)init();else window.addEventListener('pywebviewready',init,{once:true});return()=>{alive.current=false;loadSequence.current++;clearTimeout(pollTimer.current);window.removeEventListener('pywebviewready',init);};},[]);
 useEffect(()=>{
  if(!visible||!ready||active)return;let stopped=false,inflight=false;
  async function syncRemote(){
   if(stopped||inflight||actionLock.current||document.visibilityState==='hidden')return;inflight=true;
   try{const data=await call('api_bootstrap');if(stopped||!alive.current)return;setSessions(data.sessions||[]);if(isActive(data.active)){setSession(data.active);setNotice('手机或其他入口的协作正在执行，已同步当前状态。');}}catch{}finally{inflight=false;}
  }
  syncRemote();const timer=setInterval(syncRemote,5000);
  return()=>{stopped=true;clearInterval(timer);};
 },[visible,ready,active]);
 useEffect(()=>{
  if(!active)return;let cancelled=false;
  async function poll(){try{const s=await call('api_status',{id:session.id});if(cancelled||!alive.current)return;if(s){setSession(s);remember(s);}setError('');}catch(e){if(!cancelled&&alive.current)setError('状态读取失败：'+e.message);}finally{if(!cancelled&&alive.current)pollTimer.current=setTimeout(poll,600);}}
  pollTimer.current=setTimeout(poll,500);return()=>{cancelled=true;clearTimeout(pollTimer.current);};
 },[active,session?.id]);
 async function action(name,fn){if(actionLock.current)return;actionLock.current=true;setBusy(name);setError('');setNotice('');try{await fn();}catch(e){if(alive.current)setError(e.message);}finally{actionLock.current=false;if(alive.current)setBusy('');}}
 function removeProfile(id){setProfiles(list=>list.filter(p=>p.id!==id));setPlan(p=>({...p,primary_id:p.primary_id===id?'':p.primary_id,reviewer_id:p.reviewer_id===id?'':p.reviewer_id}));}
 function updateProfile(p){setProfiles(list=>[...list.filter(x=>x.id!==p.id),p]);setPlan(v=>({...v,primary_id:v.primary_id||p.id,reviewer_id:v.reviewer_id||p.id}));}
 async function start(draft=plan,images=attachments){if(attachmentBusy){setError('附件识别完成后再开始。');return;}if(images.some(v=>v.kind!=='image_asset')){setError('请先将附件识别文字加入需求，或移除文字附件，再开始协作。');return;}if(images.length&&draft.output_format!=='pptx'){setError('配图仅用于PPTX，请选择PPTX或移除配图。');return;}const message=validatePlan(draft,profiles);if(message){setError(message);return;}await action('start',async()=>{const s=await call('api_start',{...draft,...(images.length?{image_ids:images.map(v=>v.id)}:{}),task:draft.task.trim(),rounds:Number(draft.rounds),max_tokens:Number(draft.max_tokens),context_count:Number(draft.context_count)});if(!alive.current)return;loadSequence.current++;setView(null);setSession(s);remember(s);setNote('');setRevision('');setChecked(null);setPlan(draft);setAttachments(images);});}
 function checkTask(draft=plan,images=attachments){
  if(active||actionLock.current||attachmentBusy)return;
  const validation=validatePlan(draft,profiles);if(validation){setError(validation);return;}
  if(images.some(v=>v.kind!=='image_asset')){setError('请先将附件识别文字加入需求，或移除文字附件。');return;}
  if(images.length&&draft.output_format!=='pptx'){setError('配图仅用于PPTX，请选择PPTX或移除配图。');return;}
  setError('');setChecked(checkedDraft(draft,images));
 }
 function checkRevision(){try{checkTask(revisionDraft(display,revision,plan,{goal:includeGoal,result:includeResult}),[]);}catch(e){setError(e.message);}}
 async function reopen(id){const seq=++loadSequence.current;await action('history',async()=>{const s=await call('api_session',{id});if(alive.current&&seq===loadSequence.current)setView(s);});}
 async function copy(text){try{await navigator.clipboard.writeText(text);setNotice('已复制回复。');}catch{if(copyArea.current){copyArea.current.value=text;copyArea.current.focus();copyArea.current.select();try{if(document.execCommand('copy')){setNotice('已复制回复。');return;}}catch{}setNotice('自动复制不可用，回复已选中，请按 Ctrl+C。');}}}
 const A=profiles.find(p=>p.id===plan.primary_id),B=profiles.find(p=>p.id===plan.reviewer_id),validation=validatePlan(plan,profiles),final=finalReply(display);
 function exportBrief(text){try{onToIndependent({text:acceptBrief(text,24000)});}catch(e){setError(e.message);}}
 const progress=stepProgress(display);
 return <div className={"auto-shell partner-auto partner-state-"+partnerState(display,history)}>
  <main className="auto-main"><header className="auto-header"><div className="partner-header-actions"><button className="auto-button" disabled={!!busy} onClick={()=>setDrawer('history')}>历史 · {sessions.length}</button><button className="auto-button" onClick={()=>setDrawer('options')}>设置</button><button className="auto-button" disabled={active||!!busy||attachmentBusy} onClick={()=>{loadSequence.current++;setView(null);setSession(null);setAttachments([]);setPlan(p=>({...p,task:''}));setRevision('');setNote('');setError('');setNotice('');}}>新建任务</button></div></header>
   {error&&<div className="auto-warning" role="alert">{error}{!ready&&window.pywebview?.api?.call&&<button className="auto-link" onClick={bootstrap}>重新连接</button>}</div>}
   <div className="auto-layout"><section className="auto-compose auto-panel" hidden={!!display}><div className="auto-panel-heading"><div><span className="auto-kicker">THE BRIEF</span><h2>想一起解决什么？</h2></div><span className="auto-pill">{({docx:'Word交付',xlsx:'Excel交付',pptx:'PPTX交付'})[plan.output_format]||'文字协作'}</span></div>

    <label className="auto-task-label" htmlFor="auto-task">具体要求</label><textarea id="auto-task" aria-label="任务" className="auto-task" placeholder="例如：帮我把这个想法整理成一份简短方案，并检查遗漏。" value={plan.task} disabled={active||!!busy} onChange={e=>setField('task',e.target.value)}/>

    <div className="partner-draft-options"><label className="auto-field auto-output-format"><span>交付形式</span><select aria-label="协作交付形式" value={plan.output_format||'text'} disabled={active||!!busy} onChange={e=>setField('output_format',e.target.value)}><option value="text">对话与文字结论</option><option value="docx">Word 文档 · DOCX</option><option value="xlsx">Excel 表格 · XLSX</option><option value="pptx">演示文稿 · PPTX（实验）</option></select></label>
    {plan.output_format&&plan.output_format!=='text'&&<div className="partner-delivery-hint"><p className="auto-small">{plan.output_format==='pptx'?'需要配图时先添加图片；生成后可下载原件。':'生成后可下载原件。'}</p></div>}
    <div className="auto-brief-summary"><span>{A&&B?'执行与审查已就绪':'请在协作选项中选择模型'} · {plan.rounds} 轮协作</span><button className="auto-button" onClick={()=>setDrawer('options')}>协作选项</button></div>
    </div>
    <Attachments purpose={plan.output_format==='pptx'?'presentation':''} onBusyChange={setAttachmentBusy} items={attachments} onChange={setAttachments} disabled={active||!!busy} onInsert={text=>{const next=[plan.task,text].filter(Boolean).join('\n\n');acceptBrief(next,8000);setPlan(p=>({...p,task:next}));}}/>
    <div className="auto-start-row"><span>{!ready?'等待本地桌面服务…':active?'当前协作结束后，可开始新任务。':validation||'检查后会显示摘要，确认执行才会发送给模型。'}</span><button className="auto-button auto-primary" disabled={!ready||active||!!busy||attachmentBusy||attachments.some(v=>v.kind!=='image_asset')||!!validation} onClick={()=>checkTask()}>{busy==='start'?'正在开始…':'检查任务'} <span>→</span></button></div>

   </section>
   <section className="auto-observe auto-panel"><div className="auto-panel-heading"><div><span className="auto-kicker">TASK PROGRESS</span><h2>{history?'会话回看':'协作进度与结果'}</h2></div><span className={'auto-pill '+(active&&!history?'auto-live':'')}>{history?'历史记录':statusLabel(display?.status)}</span></div>
    {history&&<div className="auto-history-banner">正在查看已保存会话，原始回复只读。<button className="auto-link" onClick={()=>{loadSequence.current++;setView(null);}}>返回当前协作 →</button></div>}
    {display?<><div className="auto-session-brief"><span className="partner-avatar" data-person="user" aria-hidden="true"/><small className="partner-speaker-label">你</small><h3 title={display.task}>{display.title||display.task}</h3>{!!display.image_assets?.length&&<ul className="partner-sent-attachments" aria-label="已发送附件，只读">{display.image_assets.map(asset=><li key={asset.id||asset.name}>{asset.name} · 已发送配图</li>)}</ul>}<details className="conversation-details"><summary>完整目标与模型</summary><p>{display.task}</p><div className="auto-session-roles">{['A','B'].map(seat=><span key={seat}><b>{seat} · {seat==='A'?'主执行':'审查'}</b> {display.roles?.[seat]?.name} / {display.roles?.[seat]?.model}</span>)}</div>{sameModel(display.roles?.A,display.roles?.B)&&<small>同一模型、不同角色</small>}</details></div>
    <div className="partner-status-message" role="note" aria-label="搭档任务状态"><span className="partner-avatar" data-person="assistant" aria-hidden="true"/><div><small className="partner-speaker-label">搭档 · {history?'历史状态':'任务状态'}</small><p>{taskVoice(display)}</p></div></div>
    {display.error&&<div className="auto-warning" role="alert">{display.error}</div>}

    {display.status==='completed'&&display.output_format&&display.output_format!=='text'&&!display.files?.length&&<p className="auto-warning" role="status">模型内容已完成，但尚无可用成果文件。可展开过程核对内容；仅在原接口允许时手动重试文件生成。</p>}
    <CollaborationFiles session={display} disabled={!!busy} onDownload={name=>action('download-file',async()=>{saveCollaborationFile(await call('api_collaboration_file',{id:display.id,name}));setNotice('已请求保存原件副本；请在保存窗口选择位置。');})} onOpen={name=>action('open-file',async()=>{await call('api_collaboration_open_file',{id:display.id,name});setNotice('已请求本机软件打开原文件。');})}/>
    <ol className="partner-step-signals" aria-label="本轮协作步骤">{collaborationSignals(display).map(s=><li key={s.label} data-state={s.state} aria-current={s.state==='running'?'step':undefined}><span className="partner-signal-dot" aria-hidden="true"/><strong>{s.label}</strong><small>{s.text}</small></li>)}</ol>
    <details className="partner-execution-details" open={isActive(display)}><summary>{isActive(display)?'任务进度':'预算与执行详情'} · {statusLabel(display.status)}</summary><div className="auto-progress"><div><strong>{display.stage||statusLabel(display.status)}</strong><span>已完成 {progress.completed}/{progress.total||'—'} 步</span></div><progress aria-label="已完成协作步骤" value={progress.completed} max={progress.total||1}/><details className="conversation-details"><summary>预算与用量</summary><p>已尝试 {display.call_count}/{display.call_limit} 次{isActive(display)&&!history?` · 剩余 ${Math.max(0,Math.ceil(display.seconds_left||0))} 秒`:''}</p><small><Usage usage={display.usage}/></small></details></div></details>
    {!history&&active&&<div className="auto-stop-zone"><button className="auto-button auto-stop" disabled={busy==='stop'||display.status==='stopping'} onClick={()=>action('stop',async()=>{const s=await call('api_stop');if(alive.current&&s){setSession(s);remember(s);}})}>{display.status==='stopping'?'正在停止…':'停止协作'}</button><p>停止后不再发起下一次请求。已发送请求可能仍由服务商计费。</p></div>}
    <details className="partner-process"><summary>制作与审查记录 · {(display.steps||[]).length} 条</summary><div className="auto-transcript">{(display.steps||[]).map(step=><article className={'auto-message role-'+step.seat} key={step.id}><div className="auto-message-head"><b className="auto-seat">{step.seat}</b><div><strong>{step.seat==='A'?'主执行':'审查'} · {step.stage}</strong><span>第 {step.round} 轮协作</span></div><span className={'auto-step-state '+step.state}>{stepLabel(step)}</span></div><details className="auto-structured-reply" open={!display.output_format||display.output_format==='text'||step.seat==='B'}><summary>{display.output_format&&display.output_format!=='text'&&step.seat==='A'?'制作数据（展开查看）':'公开回复'}</summary><p className="auto-message-content">{step.content||(step.state==='running'?'等待服务商返回公开回复…':'未收到公开回复。')}</p></details>{step.error&&<p className="auto-step-error">{step.error}</p>}<details className="auto-message-details conversation-details"><summary>执行详情</summary><div className="auto-message-meta"><span>{step.model} · {step.provider}{Number.isFinite(step.seconds)?` · ${step.seconds}s`:''}</span><Usage usage={step.usage}/></div></details><button className="auto-link auto-message-copy" disabled={!step.content} onClick={()=>copy(step.content)}>复制回复</button></article>)}</div></details>
    {final&&(!display.output_format||display.output_format==='text')&&<div className="auto-final"><span className="auto-kicker">COMPLETED REVISION · A</span><h3>最后修订</h3><p>{final.content}</p><button className="auto-link" onClick={()=>copy(final.content)}>复制完整修订 →</button>{onToIndependent&&<button className="auto-button" onClick={()=>exportBrief(final.content)}>将修订稿作为任务需求</button>}</div>}
    {final&&(!display.output_format||display.output_format==='text')&&<GenerationHandoff key={display.id} session={display} onCopy={copy}/>}
    {canRetry(display)&&<div className="auto-retry"><p>{history?'重新打开的中断任务可由你手动重试。':display.delivery_retry==='export'?'内容已完成，可重试文件生成，不会再次调用模型。':display.delivery_retry==='content'?'文件内容未通过校验，可重新请求最终修订。':'交接已暂停，可手动重试失败步骤。'} 使用原有调用次数和首次开始的截止时间；不会重置预算。</p><button className="auto-button" disabled={!!busy||active} onClick={()=>action('retry',async()=>{const s=await call('api_retry',{id:display.id});if(alive.current){loadSequence.current++;setSession(s);setView(null);remember(s);}})}>手动重试</button></div>}
    {!!display.notes?.length&&<details className="auto-notes"><summary>用户意见 · {display.notes.length} 条</summary>{display.notes.map((n,i)=><p key={i}>{n.text}</p>)}</details>}
    </>:<div className="partner-welcome"><h1>今天，一起完成什么？</h1><p>说出目标，我们从这里开始。</p><div className="partner-templates">{[['docx','文档'],['xlsx','Excel'],['pptx','PPTX'],['web','网页']].map(([id,label])=><button className="auto-button" key={id} onClick={()=>{if(id==='web'){setNotice('网页/代码执行请切换单模型原会话，在原会话内选择已有代码协作入口。这里仅提供文件/文字协作。');return;}setPlan(p=>({...p,output_format:id,task:starterTask(id,p.task)}));}}><i className={'partner-icon partner-icon-'+id} aria-hidden="true"/>{label}</button>)}</div><p className="auto-small">模板是交付形式；尚未发送任何模型任务。</p>{sessions.slice(0,3).map(s=><button key={s.id} className="partner-recent" onClick={()=>reopen(s.id)}><strong>{s.title||'未命名任务'}</strong><span>{statusLabel(s.status)} · 查看记录 →</span></button>)}</div>}
    {notice&&<div className="auto-feedback" role="status">{notice}</div>}<textarea ref={copyArea} className="auto-copy-fallback" aria-label="复制备用文本" readOnly tabIndex="-1"/>
    <footer className="auto-observe-footer"><span className="auto-local-dot"/> 公开回复按原文展示 · 未完成内容不作为最终结果</footer>
   </section>
   {display&&<section className="partner-reply auto-panel">{history?<p>历史记录只读。原模型回复、附件与成果保持原样。{active?<button className="auto-button" onClick={()=>{loadSequence.current++;setView(null);}}>返回进行中的任务</button>:<button className="auto-button" onClick={()=>{loadSequence.current++;setSession(display);setView(null);setRevision('');setNotice('原记录保持不变，修改会新建一轮并再次确认。');}}>准备新一轮修改</button>}</p>:active?<form onSubmit={e=>{e.preventDefault();if(!note.trim()||display.status!=='running')return;action('note',async()=>{const result=await call('api_note',{text:note.trim()});if(alive.current){setNote('');setNotice(result.message||'补充已加入下一次交接。');}});}}><label htmlFor="partner-note">补充这次任务的要求</label><textarea id="partner-note" value={note} maxLength={1000} disabled={!!busy||display.status!=='running'} placeholder="仅补充文字要求，在下一次交接时送达…" onChange={e=>setNote(e.target.value)}/><div className="partner-composer-actions"><small>附件保持只读 · 不替换原任务</small><button className="auto-button auto-primary" disabled={!!busy||!note.trim()||display.status!=='running'}>补充要求</button></div></form>:<div><label htmlFor="partner-revision">说说想调整哪里</label><textarea id="partner-revision" value={revision} maxLength={6000} disabled={!!busy} placeholder="填写新一轮的修改要求…" onChange={e=>setRevision(e.target.value)}/><div className="partner-context-choices"><label><input type="checkbox" checked={includeGoal} onChange={e=>setIncludeGoal(e.target.checked)}/>带入原目标</label><label><input type="checkbox" checked={includeResult} onChange={e=>setIncludeResult(e.target.checked)}/>带入原公开成果摘录</label></div><div className="partner-composer-actions"><small>新建一轮，原成果保留 · 模型和预算可在设置核对</small><button className="auto-button auto-primary" disabled={!!busy||!revision.trim()} onClick={checkRevision}>检查修改</button></div></div>}</section>}
   </div>
  </main>{visible&&checked&&<TaskPanel title="确认本轮任务" blocked={!!busy} onClose={()=>{if(!busy)setChecked(null);}}><p className="auto-feedback">检查已完成，尚未执行。确认后才发送任务给以下模型。</p>{error&&<p className="auto-warning" role="alert">{error}</p>}<dl className="partner-confirm"><dt>目标</dt><dd>{checked.plan.task}</dd><dt>方式</dt><dd>双模型 · 制作 → 审查 → 修订</dd><dt>主执行</dt><dd>{profiles.find(p=>p.id===checked.plan.primary_id)?.name} · {profiles.find(p=>p.id===checked.plan.primary_id)?.model}</dd><dt>审查</dt><dd>{profiles.find(p=>p.id===checked.plan.reviewer_id)?.name} · {profiles.find(p=>p.id===checked.plan.reviewer_id)?.model}</dd><dt>交付</dt><dd>{({text:'公开文字',docx:'Word · DOCX',xlsx:'Excel · XLSX',pptx:'PPTX'})[checked.plan.output_format||'text']}</dd><dt>材料</dt><dd>{checked.attachments.map(a=>a.name).join('、')||'无新附件；不自动附加原件'}</dd><dt>位置与限制</dt><dd>沿用个人工作站原协作成果目录；最多 {checked.plan.call_limit} 次请求 · {checked.plan.rounds} 轮 · 10分钟。原历史预算与成果不变。</dd></dl><div className="partner-composer-actions"><button className="auto-button" disabled={!!busy} onClick={()=>setChecked(null)}>返回编辑</button><button className="auto-button auto-primary" disabled={!!busy||active} onClick={()=>start(checked.plan,checked.attachments)}>{busy==='start'?'正在提交…':'确认执行'}</button></div></TaskPanel>}
 {visible&&drawer==='history'&&<TaskPanel title="协作历史" drawer onClose={()=>setDrawer('')}><button className="auto-button" onClick={()=>setDrawer('incoming')}>联动收件箱</button><div className="auto-history">{sessions.length?sessions.map(s=><button key={s.id} disabled={!!busy} onClick={()=>{reopen(s.id);setDrawer('');}}><strong>{s.title||'未命名任务'}</strong><span>{statusLabel(s.status)} · {s.call_count}/{s.call_limit} 次</span></button>):<p>已保存协作会显示在这里。</p>}</div></TaskPanel>}
 {visible&&drawer==='options' &&!pendingBrief&&<TaskPanel title="协作选项" drawer onClose={()=>setDrawer('')}>{plan.output_format&&plan.output_format!=='text'&&<details className="conversation-details"><summary>文件交付说明与当前能力</summary><p className="auto-small">A 制作 → B 审查 → A 修订 → 本地生成文件。沿用当前预算；内容较多时可在协作选项调整输出上限。{plan.output_format==='pptx'?' PPTX支持1–12页封面、图文和卡片版式。需要配图时先添加照片，文字可编辑；暂不含图表和动画。':''}</p></details>}<p className="auto-small">两席使用固定的执行与审查职责。性格模板请在群聊实验中使用。</p>    <div className="auto-roles">{[['A','主执行模型','primary_id'],['B','审查模型','reviewer_id']].map(([seat,label,key])=><div className={'auto-role role-'+seat} key={seat}><span className="auto-role-top"><b>{seat}</b><span>{label}<small>{seat==='A'?'提出方案 · 根据审查修订':'独立审查 · 指出问题'}</small></span></span><select aria-label={label} disabled={active||!!busy} value={plan[key]} onChange={e=>setField(key,e.target.value)}><option value="">选择模型配置</option>{profiles.map(p=><option key={p.id} value={p.id}>{p.name} · {p.model}{p.kind==='codex_local'?' · 本机':p.has_key?'':' · 未配密钥'}</option>)}</select><small className="auto-endpoint">{profiles.find(p=>p.id===plan[key])?.base_url||'先在模型设置中添加配置'}</small></div>)}</div>
    {sameModel(A,B)&&<div className="auto-same">同一模型、不同角色 · 两个席位分别生成真实回复</div>}
    {!profiles.length&&<button className="auto-setup" onClick={()=>{setDrawer('');setSettings(true);}}>添加自己的模型与密钥 <span>→</span></button>}
    <div className="auto-options"><label className="auto-field">总请求上限<select aria-label="总请求上限" value={plan.call_limit} disabled={active||!!busy} onChange={e=>setField('call_limit',Number(e.target.value))}>{[3,6,9,15,30].map(n=><option key={n} value={n}>{n} 次</option>)}</select></label><label className="auto-field">轮数<input aria-label="轮数" type="number" min="1" max="10" value={plan.rounds} disabled={active||!!busy} onChange={e=>setField('rounds',e.target.value)}/></label><label className="auto-field">API 单次最大输出 Token<input aria-label="单次最大输出 Token" type="number" min="128" max="4096" value={plan.max_tokens} disabled={active||!!busy} onChange={e=>setField('max_tokens',e.target.value)}/></label></div>
    <p className="auto-small">两席仅围绕本次任务、已完成回复和你的补充意见协作。本机 Codex 的输出 Token 由客户端管理；Token 设置仅适用于 API。每次公开回复仍有字符限制。</p>
    <div className="auto-budget"><span className="auto-budget-icon">↔</span><div><strong>最多 {plan.call_limit} 次尝试 · 10 分钟</strong><p>当前计划 {Number(plan.rounds)>=1&&Number(plan.rounds)<=10?Number(plan.rounds)*3:'—'} 次生成请求：A 提案 → B 审查 → A 修订。达到上限自动结束，手动重试也计入总预算。</p></div></div>
    {onToIndependent&&<div className="station-actions"><button className="auto-button" disabled={!plan.task.trim()||!!busy||attachmentBusy||attachments.length>0} title={attachments.length?'请先将附件识别文字加入需求':''} onClick={()=>exportBrief(plan.task)}>转为独立任务草稿</button><button className="auto-button" disabled={!plan.task.trim()} onClick={()=>copy(plan.task)}>复制当前需求</button></div>}
<div className="station-actions"><button className="auto-button" onClick={()=>{setDrawer('');setSettings(true);}}>模型连接设置</button><button className="auto-button auto-primary" onClick={()=>setDrawer('')}>完成</button></div></TaskPanel>}
 {visible&&drawer==='incoming'&&!pendingBrief&&<TaskPanel title="联动收件箱" drawer onClose={()=>setDrawer('')}>    <IncomingTasks disabled={active||!!busy} onImport={task=>{if(actionLock.current||active)throw Error('当前任务结束后再接收。');if(plan.task.trim())throw Error('当前输入框已有需求，请先保存或清空，再导入新任务。');if(!task||typeof task.text!=='string'||!task.text.trim()||task.text.length>8000)throw Error('联动任务格式无效。');setPlan(p=>({...p,task:task.text}));loadSequence.current++;setView(null);setSession(null);setNotice('任务已填入，请检查需求、选择模型后再开始协作。');}}/></TaskPanel>}
 {visible&&settings&&<Settings profiles={profiles} onProfiles={updateProfile} onRemove={removeProfile} onClose={()=>setSettings(false)} locked={active}/>}
 {visible&&pendingBrief&&<BriefDialog key={pendingBrief.id} title="独立任务 → 高级协作" text={pendingBrief.text} limit={8000} hasExisting={!!plan.task.trim()||attachments.length>0} locked={active||!!busy||attachmentBusy} onClose={onBriefHandled} onUse={(text,replace)=>{if(actionLock.current||active)throw Error('当前协作结束后再接收。');if(plan.task.trim()&&!replace)throw Error('请先确认替换现有需求。');setPlan(p=>({...p,task:acceptBrief(text,8000)}));loadSequence.current++;setView(null);setSession(null);setAttachments([]);setDrawer('');onBriefHandled();setNotice('独立任务需求已填入，请检查模型与预算后点击“检查任务”；尚未启动模型。');}}/>}
 </div>;
}
