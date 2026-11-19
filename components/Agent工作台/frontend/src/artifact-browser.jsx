import React,{useEffect,useRef,useState} from 'react';
import {Archive,FileText,Files,FolderOpen,History,RefreshCw,Search} from 'lucide-react';
import {PreviewDialog} from './feedback-dialog.jsx';
import ArtifactReview,{artifactFileKey} from './artifact-review.jsx';
import {saveCollaborationFile} from './collaboration-files.jsx';
import {artifactGroups,validCenterLink} from './center-artifacts.mjs';
import {PageEmpty,SectionPicker} from './page-sections.jsx';

const categories=[{id:'all',label:'全部',icon:Files},{id:'center',label:'搭档交付',icon:FileText},{id:'external',label:'添加的文件',icon:FolderOpen},{id:'history',label:'历史成果',icon:History}];
const historicalSources=['station','collaboration'];
const isCenterFile=file=>file.source_kind==='center'&&validCenterLink(file)&&!!file.turn_id&&/^[a-f0-9]{32}$/.test(file.run_id);
const fromTurn=(file,turn)=>isCenterFile(file)&&file.conversation_id===turn.conversation_id&&file.turn_id===turn.turn_id;

export default function ArtifactBrowserPanel({page:p,call,visible,onConversation,onNavigate,turn,onClearTurn}){
 const [query,setQuery]=useState(''),[source,setSource]=useState('all'),[preview,setPreview]=useState(null);
 const active=useRef(visible),scopeButton=useRef(null),openedScope=useRef(null);
 active.current=visible;
 useEffect(()=>{if(!visible)setPreview(null);},[visible]);
 useEffect(()=>{if(!visible)return;const refresh=()=>p.run();window.addEventListener('focus',refresh);return()=>window.removeEventListener('focus',refresh);},[visible]);
 const rows=p.data?.items||[];
 const groupSource=historicalSources.includes(source)?'history':source;
 const roundFiles=turn?rows.filter(f=>f.source_kind==='center'&&f.conversation_id===turn.conversation_id&&f.turn_id===turn.turn_id):[];
 if(turn?.files?.length){
  const order=new Map(turn.files.map((file,index)=>[artifactFileKey(file),index]));
  const rank=file=>order.get(artifactFileKey(file))??order.size;
  roundFiles.sort((a,b)=>rank(a)-rank(b));
 }
 const groups=turn?artifactGroups(roundFiles):artifactGroups(rows,query,source);
 const count=groups.reduce((total,group)=>total+group.items.length,0);
 const requested=turn?.file&&rows.find(file=>fromTurn(file,turn)&&artifactFileKey(file)===artifactFileKey(turn.file));
 useEffect(()=>{
  if(visible&&requested&&openedScope.current!==turn){
   openedScope.current=turn;
   reviewTurn(requested,scopeButton.current);
  }
 },[visible,turn,requested]);
 const size=value=>value>=1048576?(value/1048576).toFixed(1)+' MB':Math.max(1,Math.ceil(value/1024))+' KB';
 async function act(action,payload={},refresh=false,opener=null){
  await p.run(async()=>{
   const result=await call(action,payload);
   if(action==='workstation_artifact_preview'&&active.current)setPreview({result,id:payload.id,opener});
   if(refresh)return result;
  });
 }
 function reviewTurn(file,opener){
  const files=(turn?roundFiles:rows).filter(entry=>fromTurn(entry,file)).map(entry=>({
   ...entry,catalogId:entry.id,label:(entry.job_title||entry.title||'交付文件')+' · '+entry.name.split('.').pop().toUpperCase(),
  }));
  if(files.length)setPreview({files,initialFile:artifactFileKey(file),id:file.id,opener});
 }
 function toTask(file){
  onConversation?.({conversation_id:file.conversation_id,turn_id:file.turn_id,section:'delivery',file:file.run_id?{run_id:file.run_id,name:file.name}:undefined});
 }
 async function save(file){
  await p.run(async()=>{
   const data=await call('api_collaboration_file',{id:file.run_id,name:file.name});
   if(data.name!==file.name)throw Error('文件名与当前成果不一致，请刷新后再试。');
   saveCollaborationFile(data);
  });
 }
 const addFiles=()=>act('workstation_artifact_add_files',{},true);
 const addFolder=()=>act('workstation_artifact_add_folder',{},true);
 const resetFilters=()=>{setQuery('');setSource('all');};
 const firstUse=!!p.data&&!rows.length&&!turn&&source==='all'&&!query.trim();
 function empty(){
  if(!p.data)return <PageEmpty icon={p.error?RefreshCw:Files} title={p.error?'成果列表暂未读到':'正在读取成果…'} description={p.error?'刷新后再查看文件和历史记录。':undefined} busy={!p.error}/>;
  if(turn)return <PageEmpty icon={FileText} title="近期成果列表里没有这轮的文件" description="可从原任务核对交付或查看更早的文件。"/>;
  if(query.trim())return <PageEmpty icon={Search} title="没有找到匹配的成果" description="可以换个关键词，或查看其他来源。"><button onClick={resetFilters}>清除筛选</button></PageEmpty>;
  if(source==='external')return <PageEmpty icon={FolderOpen} title="还没有添加文件" description="可以登记本机的文件或成果文件夹。原文件保留在原位置。"><button className="ws-primary" disabled={p.busy} onClick={addFiles}>添加文件</button><button disabled={p.busy} onClick={addFolder}>添加成果文件夹</button></PageEmpty>;
  if(groupSource==='history')return <PageEmpty icon={Archive} title="当前范围内没有历史成果" description="以往任务和高级协作的已登记文件会显示在这里。"><button onClick={resetFilters}>查看全部成果</button></PageEmpty>;
  return <PageEmpty icon={Files} title={source==='center'?'还没有搭档交付':'还没有成果'} description="搭档交付的文件会出现在这里，也可以直接添加已有文件。"><button className="ws-primary" onClick={()=>onNavigate?.('partner')}>打开搭档</button>{firstUse&&<><button disabled={p.busy} onClick={addFiles}>添加文件</button><button disabled={p.busy} onClick={addFolder}>添加成果文件夹</button></>}</PageEmpty>;
 }
 return <>
  {turn?<div className="ws-artifact-scope ws-actions" aria-label="本轮成果筛选">
   <strong>仅显示本轮文件</strong>
   <button className="ws-primary" onClick={()=>toTask(turn)}>回到对话中的任务</button>
   {groups[0]?.items.some(isCenterFile)&&<button ref={scopeButton} aria-haspopup="dialog" onClick={event=>reviewTurn(groups[0].items.find(isCenterFile),event.currentTarget)}>浏览本轮文件</button>}
   <button onClick={()=>{resetFilters();onClearTurn();}}>查看全部成果</button>
  </div>:<>
   <SectionPicker items={categories} label="成果分类" value={groupSource} onChange={setSource}/>
   <div className="ws-artifact-toolbar">
    <label className="ws-artifact-search"><Search aria-hidden="true" size={17}/><input type="search" aria-label="搜索成果" placeholder="搜索文件、群聊或负责人" value={query} onChange={e=>setQuery(e.target.value)}/></label>
    <label className="ws-artifact-history" hidden={groupSource!=='history'}><span>历史来源</span><select aria-label="成果来源" value={groupSource==='history'?source:'history'} onChange={e=>setSource(e.target.value)}><option value="history">全部历史</option><option value="station">历史任务成果</option><option value="collaboration">历史高级协作</option></select></label>
    {p.data&&!firstUse&&(source!=='external'||count>0||!!query.trim())&&<div className="ws-actions"><button disabled={p.busy} onClick={addFiles}>添加文件</button><button disabled={p.busy} onClick={addFolder}>添加成果文件夹</button></div>}
   </div>
  </>}
  {!!p.data&&count>0&&<p className="ws-artifact-count ws-muted" role="status">{turn?`共 ${count} 个文件`:`显示 ${count} 项`}</p>}
  <div className="ws-artifact-results ws-section-motion" key={turn?`turn-${turn.turn_id}`:source}>
   {!count&&empty()}
   {groups.map(group=><article className="ws-card ws-artifact-group" key={group.id}><div className="ws-section-title"><h2>{group.title}{group.archived?' · 已归档':''}</h2>{!turn&&group.link&&<button onClick={()=>onConversation?.(group.link)}>回到群聊</button>}</div>
    {group.items.map(f=><div className="ws-row ws-artifact-row" key={f.id} data-previewing={preview?.id===f.id||undefined}><div><strong>{f.name}</strong><small><span className="ws-badge">{f.source_label}</span> {f.job_title||f.title}{f.owner_name?' · '+f.owner_name:''}{f.owner_model?' / '+f.owner_model:''}{f.is_retry?' · 单项重试成果':''} · {size(f.size)}{f.modified?' · '+new Date(f.modified*1000).toLocaleString():''}</small></div><div className="ws-actions">
     {isCenterFile(f)?<>
      <button aria-haspopup="dialog" onClick={event=>reviewTurn(f,event.currentTarget)}>预览文件</button>
      <button disabled={p.busy} onClick={()=>save(f)}>保存副本</button>
      {!turn&&<button onClick={()=>toTask(f)}>查看原记录</button>}
     </>:<>
      {validCenterLink(f)&&<button onClick={()=>onConversation?.(f)}>查看原记录</button>}
      {f.can_preview&&<button aria-haspopup="dialog" disabled={p.busy} onClick={event=>act('workstation_artifact_preview',{id:f.id},false,event.currentTarget)}>隔离预览</button>}
     </>}
     {f.can_open&&<button disabled={p.busy} onClick={()=>act('workstation_artifact_open',{id:f.id})}>打开文件</button>}
     <button disabled={p.busy} onClick={()=>act('workstation_artifact_locate',{id:f.id})}>定位文件夹</button>
    </div></div>)}
   </article>)}
  </div>
  {!turn&&(p.data?.sources||[]).length>0&&<details className="ws-card ws-artifact-sources"><summary>管理已添加的位置 · {p.data.sources.length}</summary><p className="ws-muted">移除来源后，原文件仍保留在电脑原位置。</p>{p.data.sources.map(s=><div className="ws-row" key={s.id}><div><strong>{s.label}</strong><small>{s.kind==='folder'?'文件夹（仅当前层）':'单独文件'} · {s.path}</small></div><button disabled={p.busy} onClick={()=>act('workstation_artifact_source_remove',{id:s.id},true)}>移除来源</button></div>)}</details>}
  {!turn&&p.data?.scope&&<details className="ws-artifact-about"><summary>收录范围</summary><p className="ws-muted">{p.data.scope}</p></details>}
  {visible&&preview&&(preview.files?<ArtifactReview {...preview} call={call} onClose={()=>setPreview(null)}
   onSelect={file=>setPreview(current=>current?{...current,id:file.catalogId}:current)} onConversation={file=>{setPreview(null);toTask(file);}}/>:
   <PreviewDialog title={'预览 · '+preview.result.name} description="打开原件可查看完整版式。"
    frameTitle="成果隔离预览" opener={preview.opener} srcDoc={preview.result.html} onClose={()=>setPreview(null)}/>)}
 </>;
}
