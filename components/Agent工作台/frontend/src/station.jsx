import {partnerGuidance} from './partner-guidance.mjs';
import React,{useEffect,useRef,useState} from 'react';
import './station.css';
import Attachments from './attachments.jsx';
import ClaudeQuota from './claude-quota.jsx';
import {TaskPanel,BriefDialog} from './task-panel.jsx';
import {advancedBrief,importTask} from './workspace-transfer.mjs';
import {STATUS,normalizeStationData,canStart,canComplete,canHandoff,canReviewRole,initialTaskRole} from './station-model.mjs';

const REVIEWERS=['backend_and_integration','text_1','text_2','frontend'];
const EDITORS=['text_1','text_2'];
const PAGE=100;
const MODE_TASKS=new Set(['text','pptx','xlsx','image','animation','research']);
const EMPTY_PROVIDER={base_url:'',model:'',has_key:false,key:''};
const PROVIDERS={qwen:'千问',gemini:'Gemini',claude:'Claude',kimi:'Kimi'};
const BASE_URLS={qwen:'https://dashscope.aliyuncs.com/compatible-mode/v1',gemini:'https://generativelanguage.googleapis.com/v1beta/openai',claude:'https://api.anthropic.com/v1',kimi:'https://api.moonshot.ai/v1'};
const EMPTY_SETTINGS=Object.fromEntries(Object.keys(PROVIDERS).map(k=>[k,{...EMPTY_PROVIDER,base_url:BASE_URLS[k],image_model:''}]));

function statusLabel(status){return STATUS[status]||status||'未知';}
function fmtTime(value){if(!value)return '—';const date=new Date(value);return Number.isNaN(date.getTime())?String(value):date.toLocaleString('zh-CN',{hour12:false});}
function fmtSize(value){const size=Number(value);if(!Number.isFinite(size))return '大小未知';if(size<1024)return size+' B';if(size<1048576)return (size/1024).toFixed(1)+' KB';return (size/1048576).toFixed(1)+' MB';}
function normalizeSettings(value){return Object.fromEntries(Object.keys(PROVIDERS).map(k=>[k,{base_url:value?.[k]?.base_url||BASE_URLS[k],model:value?.[k]?.model||'',image_model:value?.[k]?.image_model||'',has_key:!!value?.[k]?.has_key,key:''}]));}
async function bridge(method,params={}){
  const api=window.pywebview?.api;
  if(!api||typeof api.call!=='function')throw new Error('正在等待本地桌面服务，请稍候重试。');
  let result;
  try{result=await api.call('station_'+method,params);}catch(e){throw new Error(e?.message||'本地服务调用失败');}
  if(!result||result.ok!==true)throw new Error(result?.error||'操作未完成');
  return normalizeStationData(result.data);
}

export default function StationWorkspace({visible=true,onToAdvanced,pendingTask,onTaskHandled,pendingOpen,onOpenHandled}){
  const [catalog,setCatalog]=useState({tasks:[],roles:{}});
  const [items,setItems]=useState([]);
  const [archived,setArchived]=useState(false);
  const [offset,setOffset]=useState(0);
  const [settings,setSettings]=useState(null);
  const [current,setCurrent]=useState(null);
  const [detailArchived,setDetailArchived]=useState(false);
  const [attachmentBusy,setAttachmentBusy]=useState(false);
  const [attachments,setAttachments]=useState([]);
  const [form,setForm]=useState({task_type:'text',role:'text_claude',execution_mode:'external',instruction:'',materials:'',requirements:''});
  const [suffixes,setSuffixes]=useState({});
  const [settingsOpen,setSettingsOpen]=useState(false);
  const [settingsTab,setSettingsTab]=useState('qwen');
  const [draftSettings,setDraftSettings]=useState(EMPTY_SETTINGS);
  const [suffixDraft,setSuffixDraft]=useState({});
  const [drawer,setDrawer]=useState('');
  const [advancedDraft,setAdvancedDraft]=useState(null);
  const [ready,setReady]=useState(false);
  const [busy,setBusy]=useState('');
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [source,setSource]=useState('');
  const [reviewer,setReviewer]=useState('backend_and_integration');
  const [editor,setEditor]=useState('text_1');
  const [pasteText,setPasteText]=useState('');
  const [reviewRequirements,setReviewRequirements]=useState('');
  const [pptInstruction,setPptInstruction]=useState('');
  const [animationPreview,setAnimationPreview]=useState(null);
  const [deleteId,setDeleteId]=useState('');
  const busyRef=useRef(false),alive=useRef(true);
  useEffect(()=>{if(!visible||!ready||!pendingOpen||busy)return;setArchived(false);setOffset(0);openTask(pendingOpen.id);onOpenHandled();refreshList(false,0).catch(()=>{});},[pendingOpen,visible,ready,busy]);


  const typeLabel=id=>(catalog.tasks.find(task=>task.id===id)?.label||id||'—');
  const roleLabel=ref=>(catalog.roles?.[ref]?.label||ref||'—');
  const suffixOf=id=>suffixes[id]??catalog.tasks.find(task=>task.id===id)?.suffix??'';
  const formMeta=catalog.tasks.find(task=>task.id===form.task_type);
  const formRole=catalog.roles?.[form.role];
  const suffix=suffixOf(form.task_type);
  const previewText=[MODE_TASKS.has(form.task_type)&&`执行方式：${form.execution_mode==='external'?'外部客户端（复制并尝试填入，不自动发送）':'API直接执行'}`,`类别：${formMeta?.label||form.task_type}`,`角色：${formRole?.label||form.role||'未选择'}${formRole?.mode?`（${formRole.mode}）`:''}`,`具体要求：\n${form.instruction||'（未填写）'}`,form.materials&&`资料：\n${form.materials}`,attachments.length&&`附件识别文字：\n${attachments.map(v=>v.name+'\n'+v.text).join('\n\n')}`,form.requirements&&`补充要求：\n${form.requirements}`,suffix&&`交付后缀：\n${suffix}`].filter(Boolean).join('\n\n');

  const currentRole=current?catalog.roles?.[current.role]:null;
  const detailCanRun=currentRole?.can_run===true;
  const startable=canStart(current,detailCanRun,detailArchived);
  const cancellable=!!current&&['queued','running'].includes(current.status);
  const handoffDisabled=!canHandoff(current,detailArchived);
  const completable=canComplete(current,detailArchived);
  const events=current?.events||[];
  const files=current?.files||[];

  const reviewerOptions=REVIEWERS.map(ref=>({ref,role:catalog.roles?.[ref]})).filter(item=>item.role);
  const availableReviewer=reviewerOptions.some(item=>item.ref===reviewer&&canReviewRole(item.role))?reviewer:(reviewerOptions.find(item=>canReviewRole(item.role))?.ref||'');
  const editorOptions=EDITORS.map(ref=>({ref,role:catalog.roles?.[ref]})).filter(item=>canReviewRole(item.role)&&item.ref!==availableReviewer);
  const availableEditor=editorOptions.some(item=>item.ref===editor)?editor:(editorOptions[0]?.ref||'');
  const reviewFiles=files.filter(file=>/\.(txt|md)$/i.test(file?.name||''));
  const sourceOptions=[];
  if(current?.result)sourceOptions.push({value:'result',label:'当前正文'});
  reviewFiles.forEach(file=>sourceOptions.push({value:'file:'+file.name,label:'文件：'+file.name}));
  const reviewSource=sourceOptions.some(option=>option.value===source)?source:(sourceOptions[0]?.value||'');
  const reviewTooLong=reviewSource==='result'&&(current?.result||'').length>9000;
  const reviewReady=!!current&&!detailArchived&&!cancellable&&!!reviewSource&&!!availableReviewer&&!!availableEditor&&availableReviewer!==availableEditor&&!reviewTooLong;

  useEffect(()=>{
    alive.current=true;
    let cancelled=false,inflight=false,timer=null,attempts=0;
    async function boot(){
      if(cancelled||inflight)return;
      if(!window.pywebview?.api?.call){
        setReady(false);
        setError('正在等待本地桌面服务，稍后自动重试…');
        if(attempts++<20)timer=setTimeout(boot,800);
        return;
      }
      inflight=true;
      try{
        const [nextCatalog,nextItems,nextSettings]=await Promise.all([bridge('catalog'),bridge('list',{archived:false,offset:0}),bridge('settings')]);
        if(cancelled)return;
        setCatalog({tasks:Array.isArray(nextCatalog?.tasks)?nextCatalog.tasks:[],roles:nextCatalog?.roles&&typeof nextCatalog.roles==='object'?nextCatalog.roles:{}});
        setItems(Array.isArray(nextItems)?nextItems:[]);
        setArchived(false);setOffset(0);
        const normalized=normalizeSettings(nextSettings);
        setSettings(normalized);setDraftSettings(normalized);
        setReady(true);setError('');
      }catch(e){
        if(cancelled)return;
        setReady(false);setError(e?.message||'本地服务读取失败');
        if(attempts++<2)timer=setTimeout(boot,1200);
      }finally{inflight=false;}
    }
    const wake=()=>{clearTimeout(timer);attempts=0;setError('');boot();};
    boot();
    window.addEventListener('pywebviewready',wake);
    return()=>{cancelled=true;alive.current=false;clearTimeout(timer);window.removeEventListener('pywebviewready',wake);};
  },[]);

  useEffect(()=>{
    if(!visible||!ready)return;let stopped=false,inflight=false;
    async function syncRemote(){
      if(stopped||inflight||busyRef.current||document.visibilityState==='hidden')return;
      inflight=true;
      try{const rows=await bridge('list',{archived,offset});if(!stopped&&alive.current&&Array.isArray(rows))setItems(rows);}catch{}finally{inflight=false;}
    }
    syncRemote();const timer=setInterval(syncRemote,5000);
    return()=>{stopped=true;clearInterval(timer);};
  },[visible,ready,archived,offset]);

  useEffect(()=>{
    if(!current?.id||!['running','queued'].includes(current.status))return;
    let stopped=false,timer=null;
    async function tick(){
      if(stopped)return;
      if(document.visibilityState!=='hidden'){
        try{
          const task=await bridge('get',{id:current.id});
          if(!stopped&&task)setCurrent(previous=>previous&&previous.id===task.id?task:previous);
        }catch(e){if(!stopped)setError('状态刷新失败：'+e.message);}
      }
      if(!stopped)timer=setTimeout(tick,1000);
    }
    timer=setTimeout(tick,1000);
    return()=>{stopped=true;clearTimeout(timer);};
  },[current?.id,current?.status]);

  useEffect(()=>{
    if(!current?.id||!['running','queued'].includes(current.status))return;
    let stopped=false,timer=null;
    async function tick(){
      if(stopped)return;
      if(document.visibilityState!=='hidden'){
        try{
          const rows=await bridge('list',{archived,offset});
          if(!stopped&&Array.isArray(rows))setItems(rows);
        }catch{}
      }
      if(!stopped)timer=setTimeout(tick,5000);
    }
    timer=setTimeout(tick,5000);
    return()=>{stopped=true;clearTimeout(timer);};
  },[current?.id,current?.status,archived,offset]);

  async function act(label,work){
    if(busyRef.current)return;
    busyRef.current=true;setBusy(label);setError('');setNotice('');
    try{await work();}
    catch(e){if(alive.current)setError(e?.message||'操作未完成');}
    finally{busyRef.current=false;if(alive.current)setBusy('');}
  }
  async function refreshList(flag=archived,next=offset){
    const rows=await bridge('list',{archived:!!flag,offset:Number(next)||0});
    setItems(Array.isArray(rows)?rows:[]);
  }
  async function changeList(flag,next){
    await act('list',async()=>{
      const rows=await bridge('list',{archived:!!flag,offset:Number(next)||0});
      setItems(Array.isArray(rows)?rows:[]);setArchived(!!flag);setOffset(Number(next)||0);
    });
  }
  function openTask(id){
    act('open',async()=>{
      const task=await bridge('get',{id});
      if(!alive.current)return;
      setCurrent(task);setDetailArchived(task.archived===true);setPasteText('');setReviewRequirements('');setPptInstruction('');setDeleteId('');setDrawer('');setSource(task?.result?'result':'');
    });
  }
  async function taskAction(method,message,extra={}){
    if(!current)return;
    await act(method,async()=>{
      let task;try{task=await bridge(method,{id:current.id,...extra});}catch(e){if(method==='handoff'){try{setCurrent(await bridge('get',{id:current.id}));}catch{}}throw e;}
      if(task?.id)setCurrent(task);
      if(method==='restore')setDetailArchived(false);
      if(method==='handoff'&&task?.handoff?.message)setNotice(task.handoff.message);else if(message)setNotice(message);
      await refreshList(archived,offset).catch(()=>{});
    });
  }
  async function archiveCurrent(){
    if(!current)return;
    await act('archive',async()=>{
      await bridge('archive',{id:current.id});
      setDetailArchived(true);setNotice('任务已归档，可在“已归档”中恢复。');
      await refreshList(archived,offset).catch(()=>{});
    });
  }
  async function deleteArchived(){
    if(!current||!detailArchived||deleteId!==current.id)return;
    const id=current.id;
    await act('delete',async()=>{
      await bridge('delete',{id,confirm:true});
      setCurrent(null);setDrawer('');setDeleteId('');setDetailArchived(false);
      setNotice('归档任务记录已删除；本机任务文件已保留。');
      const rows=await bridge('list',{archived,offset});
      if(!rows.length&&offset>0){const next=Math.max(0,offset-PAGE);setOffset(next);await refreshList(archived,next);}
      else setItems(rows);
    });
  }
  async function copyPrompt(){
    if(!current)return;
    await act('copy',async()=>{
      await bridge('copy_prompt',{id:current.id});
      setNotice('指令已复制到剪贴板。');
    });
  }
  async function openFolder(){
    if(!current?.folder)return;
    await act('folder',async()=>{await bridge('open_folder',{id:current.id});});
  }
  async function openFile(name){
    if(!current||!name)return;
    await act('file',async()=>{if(/\.html$/i.test(name)){setAnimationPreview(await bridge('preview_animation',{id:current.id,name}));return;}await bridge('open_file',{id:current.id,name});});
  }
  async function savePastedText(){
    if(!current)return;
    if(!pasteText.trim()){setError('请先粘贴正文。');return;}
    await act('save_text',async()=>{
      const task=await bridge('save_text',{id:current.id,text:pasteText});
      if(task?.id)setCurrent(task);
      setPasteText('');setNotice('正文已保存；确认无误后再标记完成。');
      await refreshList(archived,offset).catch(()=>{});
    });
  }
  async function createTask(){
    if(attachmentBusy){setError('附件识别完成后再保存任务。');return;}
    const instruction=form.instruction.trim();
    if(!instruction){setError('请填写具体要求。');return;}
    if(!form.role){setError('请选择执行角色。');return;}
    await act('create',async()=>{
      const task=await bridge('create',{task_type:form.task_type,role:form.role,instruction,materials:form.materials.trim(),requirements:form.requirements.trim(),attachments:attachments.map(v=>v.id),...(MODE_TASKS.has(form.task_type)?{execution_mode:form.execution_mode}:{})});
      setCurrent(task);setDetailArchived(false);setNotice(task.execution_mode==='external'?'外部任务草稿已保存；检查后点击“打开并填入指令”，由你在客户端发送。':catalog.roles?.[task.role]?.can_run===true?'任务已保存为草稿；检查执行角色后点击“开始执行”。':'任务已保存为手动交接草稿；需要打开对应客户端处理。');
      setForm(previous=>({...previous,instruction:'',materials:'',requirements:''}));setAttachments([]);
      const rows=await bridge('list',{archived:false,offset:0}).catch(()=>null);
      if(rows){setItems(Array.isArray(rows)?rows:[]);setArchived(false);setOffset(0);}
    });
  }
  function selectType(id){
    const meta=catalog.tasks.find(task=>task.id===id);
    setForm(previous=>({...previous,task_type:id,role:initialTaskRole(meta,catalog.roles)}));
    setError('');
  }
  function openSettings(){
    setError('');setNotice('');
    setDraftSettings(normalizeSettings(settings||EMPTY_SETTINGS));
    setSuffixDraft(Object.fromEntries(catalog.tasks.map(task=>[task.id,suffixOf(task.id)])));
    setSettingsTab('qwen');setSettingsOpen(true);
  }
  function updateProvider(key,value){
    const provider=Object.hasOwn(PROVIDERS,settingsTab)?settingsTab:'qwen';
    setDraftSettings(previous=>({...previous,[provider]:{...previous[provider],[key]:value}}));
  }
  async function saveProvider(){
    const provider=Object.hasOwn(PROVIDERS,settingsTab)?settingsTab:'qwen';
    const draft=draftSettings[provider]||EMPTY_PROVIDER;
    if(!draft.base_url.trim()||!draft.model.trim()){setError('请填写接口地址和模型 ID。');return;}
    await act('settings',async()=>{
      const saved=await bridge('save_settings',{provider,base_url:draft.base_url.trim(),model:draft.model.trim(),key:draft.key||'',...(provider==='gemini'?{image_model:(draft.image_model||'').trim()}:{})});
      const normalized=normalizeSettings(saved);
      setSettings(normalized);
      setCatalog(await bridge('catalog'));
      setDraftSettings(previous=>({...previous,[provider]:{...normalized[provider],key:''}}));
      setNotice(`${PROVIDERS[provider]} 连接设置已保存；密钥不会回显。`);
    });
  }
  async function saveTemplates(){
    await act('suffix',async()=>{
      const payload=Object.fromEntries(catalog.tasks.map(task=>[task.id,suffixDraft[task.id]??'']));
      await bridge('save_templates',{suffixes:payload});
      setSuffixes(previous=>({...previous,...payload}));
      setNotice('任务类别的交付后缀已保存。');
      setSettingsOpen(false);
    });
  }
  async function buildReview(){
    if(!current||!reviewSource){setError('请选择原稿来源。');return;}
    if(reviewTooLong){setError('当前正文超过 9000 字符，请按章节拆分后审改；文件也遵守同一上限。');return;}
    if(!reviewReady){setError('审查者或修订者当前不可用，且两者必须不同。');return;}
    await act('review',async()=>{
      const task=await bridge('review_draft',{id:current.id,source:reviewSource,reviewer:availableReviewer,editor:availableEditor,requirements:reviewRequirements});
      setCurrent(task);setDetailArchived(false);setSource(task?.result?'result':'');
      setDrawer('');setNotice('审改草稿已建立并选中；请检查后点击“开始执行”。');
      const rows=await bridge('list',{archived:false,offset:0}).catch(()=>null);
      if(rows){setItems(Array.isArray(rows)?rows:[]);setArchived(false);setOffset(0);}
    });
  }

  async function buildPpt(){
    if(!current)return;
    await act('ppt',async()=>{
      const task=await bridge('ppt_draft',{id:current.id,instruction:pptInstruction});
      setCurrent(task);setDetailArchived(false);setPptInstruction('');setSource('');
      setDrawer('');setNotice('Claude PPT制作草稿已建立，正文已带入。先检查来源与要求，再点击“打开客户端交接”；尚未发送给Claude。');
      const rows=await bridge('list',{archived:false,offset:0});
      setItems(rows);setArchived(false);setOffset(0);
    });
  }

  const provider=Object.hasOwn(PROVIDERS,settingsTab)?settingsTab:'qwen';
  const providerDraft=draftSettings[provider]||EMPTY_PROVIDER;
  const savedProvider=settings?.[provider];

  return <div className="station-shell">
    <aside className="station-sidebar">
      <div className="station-brand"><div><span className="station-kicker">TASK STATION</span><strong>任务工作台</strong></div></div>
      <button className="station-button station-primary" onClick={()=>{setCurrent(null);setDrawer('');setError('');setNotice('已打开新建表单；未保存内容会保留。');}}>新建任务</button>
      <div className="station-side-tools"><button className="station-button" onClick={()=>setDrawer('quota')}>额度监控</button><button className="station-button" onClick={openSettings}>连接与模板</button></div>
      <div className="station-side-head"><span className="station-kicker">任务历史</span><span>{archived?'已归档':'当前'}</span></div>
      <div className="station-tabs">
        <button className={'station-tab'+(archived?'':' station-tab-active')} onClick={()=>changeList(false,0)}>当前</button>
        <button className={'station-tab'+(archived?' station-tab-active':'')} onClick={()=>changeList(true,0)}>已归档</button>
      </div>
      <div className="station-list">
        {items.length?items.map(item=><button key={item.id} className={'station-task'+(current?.id===item.id?' station-selected':'')} disabled={!!busy} onClick={()=>openTask(item.id)}>
          <span className="station-task-top"><strong className="station-task-title">{item.title||'未命名任务'}</strong><span className={'station-badge station-status-'+item.status}>{statusLabel(item.status)}</span></span>
          <span className="station-task-meta">{typeLabel(item.task_type)} · {roleLabel(item.role)} · {fmtTime(item.updated_at)}</span>
          {item.preview&&<span className="station-task-preview">{item.preview}</span>}
        </button>):<p className="station-hint">这里还没有{archived?'已归档':''}任务。</p>}
      </div>
      <div className="station-pager"><button className="station-button station-mini" disabled={offset===0||!!busy} onClick={()=>changeList(archived,Math.max(0,offset-PAGE))}>上一页</button><span>{items.length?`${offset+1}–${offset+items.length}`:'0 条'} · 每页 {PAGE}</span><button className="station-button station-mini" disabled={items.length<PAGE||!!busy} onClick={()=>changeList(archived,offset+PAGE)}>下一页</button></div>
    </aside>

    <main className="station-main">
      <header className="station-top">
        <div><span className="station-kicker">任务安排与交接</span><h1 className="station-title">和助手一起完成任务</h1><p className="station-sub">先告诉我你的目标，检查草稿后，再确认执行。</p></div>
        <div className="station-toolbar"><span className="station-hint">{ready?'本地已连接':'等待连接…'}</span></div>
      </header>
      {error&&<div className="station-warning" role="alert">{error}</div>}
      {notice&&<div className="station-feedback" role="status">{notice}</div>}

      {!current&&<section className="station-card station-compose">
        <div className="station-card-head"><h2>今天想完成什么？</h2><span className="station-hint">先保存草稿，再确认执行或交接</span></div>
        <label className="station-field station-main-request"><span>具体要求</span><textarea rows="6" value={form.instruction} disabled={busy==='create'} placeholder={formMeta?.placeholder||'想完成什么？把高级协作整理好的需求粘贴到这里也可以。'} onChange={e=>setForm(previous=>({...previous,instruction:e.target.value}))}/></label>
        {MODE_TASKS.has(form.task_type)&&<label className="station-field"><span>执行方式</span><select aria-label="任务执行方式" value={form.execution_mode} disabled={!!busy} onChange={e=>setForm(p=>({...p,execution_mode:e.target.value}))}><option value="external">外部客户端 · 打开并填入指令</option><option value="api">API · 在工作站执行</option></select><small className="station-hint">{form.execution_mode==='external'?'使用客户端现有账号；自动填入不会发送或覆盖已有输入。完成后导入成果。':'需要配置对应API；确认执行才发送需求。文件由工作站保存。'}</small></label>}
        <Attachments onBusyChange={setAttachmentBusy} items={attachments} onChange={setAttachments} disabled={!!busy}/>
        <div className="station-compose-agent"><span>{formMeta?.label||'独立任务'} · {MODE_TASKS.has(form.task_type)&&form.execution_mode==='external'?'外部客户端运行':!formRole?'正在读取执行设置':formRole.can_run===true?'可在这里执行':'需要电脑客户端交接'}</span><button className="station-button station-mini" onClick={()=>setDrawer('compose')}>资料与选项</button><span className="station-hint">{form.materials?'已加资料 · ':''}{form.requirements?'已加补充要求':''}</span></div>
        <div className="station-actions"><button className="station-button station-primary" disabled={!ready||!!busy||attachmentBusy} onClick={createTask}>{busy==='create'?'保存中…':'保存任务'}</button><button className="station-button" onClick={()=>setDrawer('preview')}>预览指令</button>{onToAdvanced&&<button className="station-button" disabled={!!busy||attachmentBusy||!form.instruction.trim()} onClick={()=>setAdvancedDraft(advancedBrief({form:{...form,attachments_text:attachments.map(v=>'【附件：'+v.name+'】\n'+v.text).join('\n\n')}}))}>交给高级协作拟定</button>}</div>
      </section>}

      {current?<section className="station-card station-detail">{current.attachments?.length>0&&<details className="attachment-snapshot"><summary>来源附件 · {current.attachments.length} 个（已识别文字）</summary><pre>{current.attachments_text}</pre></details>}
        <div className="station-card-head"><div><span className="station-kicker">{current.workflow?'文字审查与修订':'当前任务'}</span><h2>{current.title||'未命名任务'}</h2></div><div className="station-actions" style={{marginTop:0}}><span className={'station-badge station-status-'+current.status}>{statusLabel(current.status)}</span>{detailArchived&&<span className="station-badge">已归档</span>}</div></div>
        <details className="conversation-details"><summary>任务设置与记录</summary><p className="station-hint">{typeLabel(current.task_type)} · {roleLabel(current.role)} · 更新于 {fmtTime(current.updated_at)}</p></details><div className="station-user-message"><span>你的目标</span><pre>{current.instruction}</pre></div><div className="partner-guidance" role="note" aria-label="搭档操作提示"><span>接下来 · 操作提示</span><p>{partnerGuidance(current.status,{manual:current.execution_mode==='external'||(current.execution_mode!=='api'&&catalog.roles?.[current.role]?.can_run===false),archived:detailArchived})}</p></div>
        {current.handoff_source&&<div className="station-feedback"><strong>这份PPT已带入来源正文快照</strong><p>来源：{current.handoff_source.title} · 当时状态：{statusLabel(current.handoff_source.status)}。尚未发送给模型，请检查要求与执行方式。</p><details><summary>检查带入的正文</summary><pre className="station-pre">{current.materials}</pre></details></div>}
        {current.error&&<div className="station-warning" role="alert">{current.error}</div>}
        {current.handoff?.message&&<p className="station-feedback" role="status">{current.handoff.message}</p>}
        {['api','external'].includes(current.execution_mode)&&<label className="station-field"><span>本任务执行方式</span><select aria-label="已保存任务执行方式" value={current.execution_mode} disabled={!!busy||cancellable||detailArchived||current.status!=='draft'||!!current.result?.trim()||files.length>0} onChange={e=>taskAction('set_execution_mode','执行方式已更改，尚未发送。',{execution_mode:e.target.value})}><option value="external">外部客户端 · 打开并填入指令</option><option value="api">API · 在工作站执行</option></select></label>}
        {current.execution_mode==='api'&&!detailCanRun&&<p className="station-hint">该API尚未就绪。<button className="station-button" onClick={openSettings}>配置连接</button> 或在空白草稿中切换到外部客户端。</p>}
        <div className="station-primary-actions">
          {onToAdvanced&&<button className="station-button" disabled={!!busy||cancellable} onClick={()=>setAdvancedDraft(advancedBrief({task:current}))}>交给高级协作接手</button>}
          {startable&&<button className="station-button station-primary" disabled={!!busy} onClick={()=>taskAction('submit','已提交执行。')}>{busy==='submit'?'提交中…':current.workflow?'开始审查与修订':'开始执行'}</button>}
          {cancellable&&<button className="station-button" disabled={!!busy} onClick={()=>taskAction('cancel','任务已取消。')}>停止执行</button>}
          {completable&&current.status!=='completed'&&<button className="station-button station-primary" disabled={!!busy} onClick={()=>taskAction('complete','任务已标记完成。')}>确认完成</button>}
          {(current.execution_mode==='external'||(current.execution_mode!=='api'&&!detailCanRun))&&!detailArchived&&<button className="station-button station-primary" disabled={!!busy||handoffDisabled} onClick={()=>taskAction('handoff','交接请求已发送。')}>{current.execution_mode==='external'?'打开并填入指令':'打开客户端交接'}</button>}
          {detailArchived?<><button className="station-button" disabled={!!busy} onClick={()=>taskAction('restore','任务已恢复。')}>恢复任务</button><button className="station-button station-danger" disabled={!!busy||cancellable} onClick={()=>setDeleteId(current.id)}>删除归档记录</button></>:<button className="station-button" disabled={!!busy||cancellable} onClick={archiveCurrent}>归档任务</button>}
        </div>
        {deleteId===current.id&&detailArchived&&<div className="station-delete-confirm" role="alertdialog" aria-label="确认删除归档记录">
          <strong>删除“{current.title}”的归档记录？</strong><p>记录将从历史中移除，无法在工作台恢复。本机任务文件和其它审改任务的副本会保留。</p>
          <div className="station-actions"><button className="station-button" disabled={!!busy} onClick={()=>setDeleteId('')}>保留记录</button><button className="station-button station-danger" disabled={!!busy} onClick={deleteArchived}>{busy==='delete'?'删除中…':'确认删除记录'}</button></div>
        </div>}
        {current.workflow&&<>
          <ol className="station-steps" aria-label="审改进度">
            <li className="station-step-done"><b>1</b><span>初稿已保存<small>原稿不会覆盖</small></span></li>
            <li className={current.workflow.review_text?'station-step-done':current.workflow.stage==='审查中'?'station-step-active':''}><b>2</b><span>模型审查<small>{roleLabel(current.workflow.reviewer)}</small></span></li>
            <li className={current.workflow.versions?.length>1?'station-step-done':current.workflow.stage==='修订中'?'station-step-active':''}><b>3</b><span>按意见修订<small>{roleLabel(current.workflow.editor)}</small></span></li>
          </ol>
          <p className="station-hint">当前阶段：{current.workflow.stage}。一次执行依次完成审查和修订。</p>
          <details className="station-fold"><summary>查看本次要求与原稿版本</summary><pre className="station-pre">{current.requirements}</pre><div className="station-files">{(current.workflow.versions||[]).map(version=><div className="station-file" key={version.name}><span><strong>v{String(version.number||0).padStart(3,'0')}</strong> {version.name}</span><button className="station-button station-mini" disabled={!!busy} onClick={()=>openFile(version.name)}>打开版本文件</button></div>)}</div></details>
        </>}
        <div className={current.workflow?'station-review-columns':'station-block'}>
          {current.workflow&&<section className="station-result-panel"><h3>审查意见</h3><p className="station-hint">{roleLabel(current.workflow.reviewer)} 负责指出问题与建议。</p><pre className="station-pre">{current.workflow.review_text||'开始执行后，审查意见会显示在这里。'}</pre></section>}
          <section className={current.workflow?'station-result-panel station-assistant-message':'station-assistant-message'}><h3>{current.workflow?'修订回复':'任务回复'}</h3><p className="station-hint">{current.workflow?'根据左侧意见生成完整修订稿，核对后点击“确认完成”。':'核对正文后，可在下方填写审改要求。'}</p><pre className="station-pre">{current.result||'任务执行后，回复会显示在这里。'}</pre></section>
        </div>
        <div className="station-tool-row" aria-label="任务功能">
          {sourceOptions.length>0&&!detailArchived&&!cancellable&&<button className="station-button" onClick={()=>setDrawer('review')}>审查与修改</button>}
          {current.task_type!=='pptx'&&current.result?.trim()&&!detailArchived&&!cancellable&&<button className="station-button" onClick={()=>setDrawer('ppt')}>制作为PPT</button>}
          {current.task_type==='text'&&current.result?.trim()&&!detailArchived&&!cancellable&&<button className="station-button" disabled={!!busy} onClick={()=>taskAction('export_document','已更新Word成果，请在成果文件中核对。')}>生成Word文件</button>}
          {current.task_type==='xlsx'&&current.result?.trim()&&!detailArchived&&!cancellable&&<button className="station-button" disabled={!!busy} onClick={()=>taskAction('export_spreadsheet','已检查Excel导出，请查看成果文件与任务记录。')}>生成Excel文件</button>}
          <button className="station-button" onClick={()=>setDrawer('files')}>成果文件与导入（{files.length}）</button>
          <button className="station-button" onClick={()=>setDrawer('log')}>执行日志</button>
          <button className="station-button" onClick={()=>setDrawer('info')}>更多操作</button>
        </div>
      </section>:null}

    </main>


    {visible&&drawer==='compose'&&<TaskPanel title="资料与选项" drawer onClose={()=>setDrawer('')} blocked={!!busy}><label className="station-field"><span>任务类别</span><select aria-label="任务类别" value={form.task_type} disabled={!ready||!!busy} onChange={e=>selectType(e.target.value)}>{catalog.tasks.length?catalog.tasks.map(task=><option key={task.id} value={task.id}>{task.label}</option>):<option value="text">正在读取…</option>}</select></label><label className="station-field"><span>执行角色</span><select aria-label="执行角色" value={form.role} disabled={!!busy} onChange={e=>setForm(p=>({...p,role:e.target.value}))}>{(formMeta?.agents||[]).map(a=><option key={a.role_ref} value={a.role_ref}>{form.task_type==='xlsx'&&a.role_ref==='text_1'?a.label:catalog.roles?.[a.role_ref]?.label||a.label}</option>)}</select></label><p className="station-hint">{formRole?.detail}</p><label className="station-field"><span>资料</span><textarea rows="6" value={form.materials} disabled={!!busy} onChange={e=>setForm(p=>({...p,materials:e.target.value}))}/></label><label className="station-field"><span>补充要求</span><textarea rows="4" value={form.requirements} disabled={!!busy} onChange={e=>setForm(p=>({...p,requirements:e.target.value}))}/></label><p className="station-hint">编辑保留在当前草稿，关闭后可继续填写；保存任务才写入历史。</p></TaskPanel>}
    {visible&&drawer==='preview'&&<TaskPanel title="指令预览" onClose={()=>setDrawer('')}><pre className="station-pre">{previewText}</pre></TaskPanel>}
    {visible&&drawer==='quota'&&<TaskPanel title="额度监控" drawer onClose={()=>setDrawer('')}><ClaudeQuota call={bridge}/></TaskPanel>}
    {visible&&current&&drawer==='review'&&<TaskPanel title="审查与修改" drawer onClose={()=>setDrawer('')} blocked={!!busy}>        {sourceOptions.length>0&&!detailArchived&&!cancellable&&<details className="station-review-compose" open={current.workflow?undefined:true} key={current.id}>
          <summary>{current.workflow?'继续完善：再建一轮审改':'2 · 设置审查与修改'}</summary>
          <p className="station-hint">选择原稿和两个模型 → 填写要求 → 建立任务 → 开始审改。TXT/MD 原稿最多 9000 字符。</p>
          <div className="station-grid">
            <label className="station-field station-span"><span>原稿来源</span><select value={reviewSource} disabled={!!busy} onChange={e=>setSource(e.target.value)}>{sourceOptions.map(option=><option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
            <label className="station-field"><span>审查者 · 找问题</span><select value={availableReviewer} disabled={!!busy} onChange={e=>setReviewer(e.target.value)}><option value="">无可用角色</option>{reviewerOptions.map(item=><option key={item.ref} value={item.ref} disabled={!canReviewRole(item.role)}>{item.role.label||item.ref}{canReviewRole(item.role)?'':' · 后续接入'}</option>)}</select></label>
            <label className="station-field"><span>修订者 · 改正文</span><select value={availableEditor} disabled={!!busy} onChange={e=>setEditor(e.target.value)}><option value="">无可用角色</option>{editorOptions.map(item=><option key={item.ref} value={item.ref}>{item.role.label||item.ref}</option>)}</select></label>
            <label className="station-field station-span"><span>本次审改要求（选填）</span><textarea className="station-review-requirements" rows="3" maxLength={4000} value={reviewRequirements} disabled={!!busy} onChange={e=>setReviewRequirements(e.target.value)} placeholder="例如：检查是否编造功能，简化操作步骤，控制在 600 字以内。"/><small>{reviewRequirements.length} / 4000 · 留空使用默认要求；审查者与修订者都会收到。</small></label>
          </div>
          {reviewTooLong&&<p className="station-warning">原稿超过 9000 字符，请按章节拆分；TXT/MD 文件也遵守同一上限。</p>}
          {(!availableReviewer||!availableEditor)&&<p className="station-warning">请先配置两个不同的可用文字角色。</p>}
          <div className="station-actions"><button className="station-button station-primary" disabled={!!busy||!reviewReady} onClick={buildReview}>{busy==='review'?'正在建立…':'建立审改任务'}</button><span className="station-hint">建立后先检查，再点击“开始审查与修订”。</span></div>
        </details>}
</TaskPanel>}
    {visible&&current&&drawer==='ppt'&&<TaskPanel title="制作为PPT" drawer onClose={()=>setDrawer('')} blocked={!!busy}>        {current.task_type!=='pptx'&&current.result?.trim()&&!detailArchived&&!cancellable&&<section className="station-review-compose" aria-label="文字交接PPT">
          <h3>3 · 交给 Claude 制作 PPT</h3>
          <p className="station-hint">带入{current.workflow?'当前修订稿':'当前正文'}，独立保存为新的PPT制作草稿。建立草稿不会调用模型，原任务保留。</p>
          <label className="station-field"><span>PPT制作要求（选填）</span><textarea className="station-ppt-instruction" rows="2" maxLength={2000} value={pptInstruction} disabled={!!busy} onChange={e=>setPptInstruction(e.target.value)} placeholder="例如：6页，面向新用户，青绿色，保留关键数据。留空默认6页简体中文、16:9。"/></label>
          {current.result.length>20000&&<p className="station-warning">正文超过20000字符，请按章节另建任务，不会截断带入。</p>}
          <div className="station-actions"><button className="station-button station-primary" disabled={!!busy||current.result.length>20000} onClick={buildPpt}>{busy==='ppt'?'正在建立…':'建立 Claude PPT 制作草稿'}</button><span className="station-hint">额度仅作提示，是否交接由你决定。</span></div>
        </section>}
</TaskPanel>}
    {visible&&current&&drawer==='files'&&<TaskPanel title="成果文件与导入" drawer onClose={()=>setDrawer('')} blocked={!!busy}>        <details className="station-fold" open><summary>成果文件与导入（{files.length}）</summary>
          <div className="station-actions"><button className="station-button" disabled={!!busy||detailArchived||cancellable} onClick={()=>taskAction('import_result','成果已导入，请核对。')}>导入成果文件</button><button className="station-button" disabled={!!busy||!current.folder} onClick={openFolder}>打开任务文件夹</button></div>
          {files.length?<div className="station-files">{files.map(file=><div className="station-file" key={file.name}><span>{file.name}<small> · {fmtSize(file.size)}</small></span><button className="station-button station-mini" disabled={!!busy} onClick={()=>openFile(file.name)}>打开</button></div>)}</div>:<p className="station-hint">暂无文件。</p>}
          {!current.workflow&&!detailArchived&&<><label className="station-field"><span>粘贴客户端生成的正文</span><textarea rows="3" value={pasteText} disabled={!!busy||cancellable} placeholder="将客户端正文粘贴到这里，再保存。" onChange={e=>setPasteText(e.target.value)}/></label><div className="station-actions"><button className="station-button" disabled={!!busy||cancellable||!pasteText.trim()} onClick={savePastedText}>保存粘贴正文</button></div></>}
        </details>
</TaskPanel>}
    {visible&&current&&drawer==='info'&&<TaskPanel title="更多操作" drawer onClose={()=>setDrawer('')} blocked={!!busy}>        <details className="station-fold" open><summary>更多操作与任务信息</summary><div className="station-actions"><button className="station-button" disabled={!!busy} onClick={copyPrompt}>复制指令</button>{detailCanRun&&current.execution_mode!=='api'&&!current.workflow&&<button className="station-button" disabled={!!busy||handoffDisabled} onClick={()=>taskAction('handoff','交接请求已发送。')}>打开客户端交接</button>}</div><pre className="station-pre">{current.instruction}</pre><p className="station-hint">{current.folder}</p></details>
</TaskPanel>}
    {visible&&current&&drawer==='log'&&<TaskPanel title="执行日志" drawer onClose={()=>setDrawer('')} blocked={!!busy}>        <details className="station-fold" open><summary>执行日志（{events.length}）</summary><div className="station-events">{events.map((event,index)=><div className="station-event" key={index}><span className="station-event-time">{fmtTime(event.time)}</span><span>{event.message}</span></div>)}</div></details>
</TaskPanel>}
    {visible&&advancedDraft!==null&&<BriefDialog title="交给高级协作 · 预览需求" text={advancedDraft} limit={8000} locked={!!busy} onClose={()=>setAdvancedDraft(null)} onUse={text=>{onToAdvanced({text});setAdvancedDraft(null);setDrawer('');}}/>}
    {visible&&pendingTask&&<BriefDialog key={pendingTask.id} title="高级协作 → 独立任务" text={pendingTask.text} limit={24000} hasExisting={attachments.length>0||[form.instruction,form.materials,form.requirements].some(v=>v.trim())} locked={!!busy||attachmentBusy} onClose={onTaskHandled} onUse={(text,replace)=>{setForm(importTask(form,text,replace));setAttachments([]);setCurrent(null);setDetailArchived(false);setDrawer('');onTaskHandled();setNotice('高级协作需求已填入草稿；请选择类别和角色后保存，尚未执行。');}}/>}

    {visible&&animationPreview&&<TaskPanel title="小动画预览" onClose={()=>setAnimationPreview(null)}><p className="station-hint">离线CSS/SVG动画 · 已禁用脚本和网络资源</p><iframe title="生成的小动画" sandbox="" srcDoc={animationPreview.html} style={{width:'100%',height:'55vh',border:0,background:'white'}}/></TaskPanel>}
    {visible&&settingsOpen&&<div className="station-modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget&&!busyRef.current)setSettingsOpen(false);}}>
      <section className="station-modal" role="dialog" aria-modal="true" aria-labelledby="station-settings-title">
        <div className="station-modal-head"><div><span className="station-kicker">本地设置</span><h2 id="station-settings-title">连接与交付后缀</h2></div><button className="station-button station-mini" disabled={!!busy} onClick={()=>setSettingsOpen(false)}>关闭</button></div>
        <div className="station-tabs" role="tablist">
          {Object.entries(PROVIDERS).map(([key,label])=><button key={key} className={'station-tab'+(settingsTab===key?' station-tab-active':'')} onClick={()=>{setSettingsTab(key);setError('');setNotice('');}}>{label}</button>)}
          <button className={'station-tab'+(settingsTab==='suffix'?' station-tab-active':'')} onClick={()=>{setSettingsTab('suffix');setError('');setNotice('');}}>交付后缀</button>
        </div>
        <div className="station-modal-body">
          {error&&<div className="station-warning" role="alert">{error}</div>}
          {notice&&<div className="station-feedback" role="status">{notice}</div>}
          {settingsTab==='suffix'?<div className="station-grid">
            <p className="station-hint station-span">按任务类别修改交付后缀；保存后用于后续任务。</p>
            {catalog.tasks.map(task=><label className="station-field station-span" key={task.id}><span>{task.label}（{task.id}）</span><textarea rows="2" value={suffixDraft[task.id]??''} disabled={!!busy} onChange={e=>setSuffixDraft(previous=>({...previous,[task.id]:e.target.value}))}/></label>)}
          </div>:<div className="station-grid">
            <label className="station-field station-span"><span>接口地址</span><input type="url" value={providerDraft.base_url} disabled={!!busy} spellCheck={false} placeholder="https://..." onChange={e=>updateProvider('base_url',e.target.value)}/></label>
            <label className="station-field station-span"><span>{provider==='gemini'?'文字／文档模型 ID':'模型 ID'}</span><input value={providerDraft.model} disabled={!!busy} spellCheck={false} placeholder="模型名称或 ID" onChange={e=>updateProvider('model',e.target.value)}/></label>
            {provider==='gemini'&&<label className="station-field station-span"><span>图片生成模型 ID</span><input value={providerDraft.image_model||''} disabled={!!busy} spellCheck={false} placeholder="填写已开通图片输出权限的模型ID" onChange={e=>updateProvider('image_model',e.target.value)}/><small className="station-hint">PPTX、XLSX和CSS/SVG动画使用文字模型；图片任务单独使用此模型，不自动回退。</small></label>}
            <label className="station-field station-span"><span>API 密钥</span><small className="station-hint">{savedProvider?.has_key?'已保存；留空保留旧密钥，不回显。':'尚未保存密钥。'}</small><input type="password" autoComplete="new-password" value={providerDraft.key||''} disabled={!!busy} placeholder={savedProvider?.has_key?'留空保留旧密钥':'输入密钥'} onChange={e=>updateProvider('key',e.target.value)}/></label>
            <p className="station-hint station-span">密钥只保存在本机；空密钥不会覆盖已保存的密钥。</p>
          </div>}
        </div>
        <div className="station-modal-foot"><button className="station-button" disabled={!!busy} onClick={()=>setSettingsOpen(false)}>取消</button>{settingsTab==='suffix'?<button className="station-button station-primary" disabled={!!busy||!catalog.tasks.length} onClick={saveTemplates}>{busy==='suffix'?'保存中…':'保存 交付后缀'}</button>:<button className="station-button station-primary" disabled={!!busy} onClick={saveProvider}>{busy==='settings'?'保存中…':'保存连接设置'}</button>}</div>
      </section>
    </div>}
  </div>;
}
