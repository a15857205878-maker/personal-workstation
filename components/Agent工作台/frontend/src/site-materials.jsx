import React,{useEffect,useRef,useState} from 'react';
import {moveEntry,exportable,mergeSnapshot} from './site-materials-model.mjs';
import './site-materials.css';

async function api(action,payload={}){
 const result=await window.pywebview.api.call('workstation_materials_'+action,payload);
 if(!result.ok)throw Error(result.error||'操作未完成');return result.data;
}
const kindNames={update:'更新记录',source:'资料出处',step:'展示步骤'};
function Preview({data,onClose}){
 const dialog=useRef(null);
 useEffect(()=>{dialog.current.showModal();},[]);
 return <dialog className="materials-preview" ref={dialog} onCancel={onClose} aria-label="素材预览"><button autoFocus onClick={onClose}>关闭预览</button>{data.kind==='image'?<img src={data.url} alt="所选素材原件预览"/>:<pre>{data.text}</pre>}</dialog>;
}
export default function SiteMaterials({visible}){
 const [state,setState]=useState({projects:[],revision:''}),[draft,setDraft]=useState(null),[dirty,setDirty]=useState(false);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[title,setTitle]=useState('');
 const [tab,setTab]=useState('journal'),[sources,setSources]=useState(null),[sourceTab,setSourceTab]=useState('library');
 const [query,setQuery]=useState(''),[searchMode,setSearchMode]=useState('content'),[selected,setSelected]=useState([]),[preview,setPreview]=useState(null),[exported,setExported]=useState(null);
 const loaded=useRef(false),gate=useRef(false);
 function receive(next,id=draft?.id){setState(next);setDraft(next.projects.find(p=>p.id===id)||next.projects[0]||null);setDirty(false);}
 async function run(fn){if(gate.current)return;gate.current=true;setBusy(true);setError('');setNotice('');try{return await fn();}catch(e){setError(e.message||'操作未完成');return null;}finally{gate.current=false;setBusy(false);}}
 useEffect(()=>{if(visible&&!loaded.current){loaded.current=true;run(async()=>receive(await api('list')));}},[visible]);
 useEffect(()=>{const prevent=e=>{if(dirty){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',prevent);return()=>window.removeEventListener('beforeunload',prevent);},[dirty]);
 const publicRows=exportable(draft?.entries||[],selected),disabled=busy||dirty;
 function edit(fields){if(gate.current)return;setDraft(old=>({...old,...fields}));setDirty(true);setExported(null);}
 function entryEdit(id,fields){edit({entries:draft.entries.map(e=>e.id===id?{...e,...fields}:e)});}
 function choose(project){if(dirty&&!window.confirm('当前项目有未保存修改，放弃这些修改并切换项目？'))return;setDraft(structuredClone(project));setDirty(false);setSelected([]);setExported(null);setSources(null);setError('');setTab('journal');}
 const mutate=async(action,extra={})=>{const next=await api(action,{id:draft.id,revision:state.revision,...extra});receive(next);};
 const showPreview=entry=>run(async()=>setPreview(await api('preview',{id:draft.id,entry_id:entry.id})));
 return <div className="site-materials" aria-busy={busy}>
  <header className="materials-heading"><div><p className="materials-kicker">个人网站 · 内容准备</p><h1>网站素材台</h1><p>把项目更新、资料出处与展示步骤放在一起，准备可用于网站的真实内容。</p></div><button disabled={busy} onClick={()=>{if(dirty&&!window.confirm('刷新会放弃当前未保存修改，继续？'))return;run(async()=>{const next=await api('list');setDraft(mergeSnapshot(draft,next,false));setState(next);setDirty(false);});}}>刷新档案</button></header>
  {error&&<p className="materials-error" role="alert">{error}</p>}{notice&&<p className="materials-notice" role="status">{notice}</p>}
  <fieldset disabled={busy} className="materials-controls"><div className="materials-workspace"><aside className="materials-projects" aria-label="项目档案">
   <h2>项目</h2><form onSubmit={e=>{e.preventDefault();run(async()=>{const next=await api('create',{title,revision:state.revision});receive(next,next.projects.at(-1).id);setTitle('');setSelected([]);setExported(null);});}}><label>新项目名称<input value={title} maxLength={120} onChange={e=>setTitle(e.target.value)} placeholder="例如：个人工作站"/></label><button disabled={disabled||!title.trim()}>建立项目</button></form>
   <div className="materials-project-list">{state.projects.map(p=><button key={p.id} className={draft?.id===p.id?'is-current':''} aria-current={draft?.id===p.id?'true':undefined} disabled={busy} onClick={()=>choose(p)}><strong>{p.title}</strong><small>{p.version||'版本未填写'} · {p.entries.length} 条</small></button>)}</div>
   {!state.projects.length&&<p className="materials-empty">先建立一个项目，再逐步添加更新和素材。</p>}
  </aside><main className="materials-main">
   {!draft?<div className="materials-empty"><h2>从一个项目开始</h2><p>写下已经完成的功能，选入现有成果，再整理成网站介绍和操作分镜。</p></div>:<>
    <div className="materials-project-head"><div><h2>{draft.title}</h2><small>{dirty?'有未保存修改':'已保存到本机'} · {draft.entries.length} 个条目</small></div><button className="materials-primary" disabled={busy||!dirty} onClick={()=>run(async()=>{receive(await api('save',{project:draft,revision:state.revision}));setNotice('项目、条目与展示顺序已保存。');})}>保存修改</button></div>
    <nav className="materials-tabs" aria-label="素材准备流程">{[['journal','1 项目记录'],['sources','2 查找与选材'],['story','3 整理与导出']].map(([id,label])=><button key={id} aria-pressed={tab===id} onClick={()=>setTab(id)}>{label}</button>)}</nav>
    {dirty&&<p className="materials-hint">可继续编辑和切换上方步骤；添加素材、预览原件或导出前，请先保存修改。</p>}
    {tab==='journal'&&<>
     <div className="materials-fields"><label>项目名称<input maxLength={120} value={draft.title} onChange={e=>edit({title:e.target.value})}/></label><label>当前版本<input maxLength={100} value={draft.version} placeholder="例如 v1.0" onChange={e=>edit({version:e.target.value})}/></label><label className="materials-span">项目待办（仅内部，不导出）<textarea maxLength={6000} value={draft.todo} onChange={e=>edit({todo:e.target.value})}/></label></div>
     <div className="materials-actions"><h3>更新与素材条目</h3><button disabled={disabled} onClick={()=>run(()=>mutate('add'))}>添加文字记录</button></div>
     {!draft.entries.length&&<p className="materials-empty">记录一个已完成的功能，或到“查找与选材”加入图片、录屏和资料。</p>}
     {draft.entries.map((entry,index)=><article className="materials-entry" key={entry.id}>
      <div className="materials-entry-heading"><strong>{String(index+1).padStart(2,'0')} · {kindNames[entry.kind]}</strong><span>{entry.public?'可选入网站包':'仅内部'}</span></div>
      <label>条目标题<input maxLength={200} value={entry.title} onChange={e=>entryEdit(entry.id,{title:e.target.value})}/></label>
      <div className="materials-fields"><label>用途<select value={entry.kind} onChange={e=>entryEdit(entry.id,{kind:e.target.value})}>{Object.entries(kindNames).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label><label>日期<input maxLength={40} value={entry.date} onChange={e=>entryEdit(entry.id,{date:e.target.value})}/></label><label>版本标签<input maxLength={100} value={entry.version} onChange={e=>entryEdit(entry.id,{version:e.target.value})}/></label></div>
      <label>网站说明<textarea maxLength={6000} value={entry.description} placeholder="介绍这个功能、这张图或这个操作步骤" onChange={e=>entryEdit(entry.id,{description:e.target.value})}/></label>
      {(entry.source||entry.file_name)&&<div className="materials-source"><small>出处：{entry.source||entry.file_name}</small>{entry.excerpt&&<blockquote>{entry.excerpt}</blockquote>}{entry.file_name&&<p>原件：{entry.file_name} · {{ready:'可用',changed:'已变化，请移除旧条目并重新选入',missing:'缺失，请重新选择',none:''}[entry.file_status]}</p>}</div>}
      <label className="materials-check"><input type="checkbox" checked={entry.public} onChange={e=>entryEdit(entry.id,{public:e.target.checked})}/>允许将此条目选入网站素材包</label>
      <details><summary>内部备注与整理</summary><label>内部备注（不导出）<textarea maxLength={6000} value={entry.notes} onChange={e=>entryEdit(entry.id,{notes:e.target.value})}/></label><div className="materials-actions"><button disabled={busy} onClick={()=>{if(window.confirm('移除此条目？原文件仍会保留。'))edit({entries:draft.entries.filter(e=>e.id!==entry.id)});}}>移除条目</button></div></details>
     </article>)}
     <details className="materials-delete"><summary>项目管理</summary><p>删除档案仅移除项目记录，原文件和已导出素材包保留。</p><button disabled={disabled} onClick={()=>{if(window.confirm('删除“'+draft.title+'”的项目档案？原件和导出包保留。'))run(async()=>{const next=await api('delete',{id:draft.id,revision:state.revision});receive(next);setSelected([]);});}}>删除项目档案</button></details>
    </>}
    {tab==='sources'&&<>
     <p className="materials-hint">选入的是原文件引用。新增条目默认为“仅内部”，可在项目记录里编写说明并选择是否用于网站。</p>
     <div className="materials-actions"><button disabled={disabled} onClick={()=>run(()=>mutate('pick'))}>选择本地图片、录屏或文档</button><button disabled={busy} onClick={()=>{setSourceTab('library');setSources(null);}}>共享文件库</button><button disabled={busy} onClick={()=>run(async()=>{setSourceTab('artifacts');setSources(await api('artifacts'));})}>已有工作站成果</button></div>
     {sourceTab==='library'&&<form className="materials-search" onSubmit={e=>{e.preventDefault();run(async()=>setSources(await api('search',{query,mode:searchMode})));}}><label>搜索资料<input maxLength={120} value={query} onChange={e=>setQuery(e.target.value)} placeholder={searchMode==='content'?'输入正文关键词':'输入文件名，留空浏览'}/></label><label>检索范围<select value={searchMode} onChange={e=>setSearchMode(e.target.value)}><option value="content">正文与出处</option><option value="filename">文件名</option></select></label><button disabled={busy||(searchMode==='content'&&!query.trim())}>查找</button></form>}
     {sources?.warnings?.map((w,i)=><p className="materials-hint" key={i}>{w}</p>)}{sources?.limited&&<p className="materials-hint">本次达到检索范围或结果上限，请缩小目录或使用更具体的关键词。</p>}{sources?.unavailable>0&&<p className="materials-hint">部分共享目录暂不可用。</p>}
     {sourceTab==='library'&&sources&&!sources.roots?.length&&<p>尚未选择共享文件夹，请在“连接与设置 → 手机与远程连接”中选择。</p>}
     {sources&&(sourceTab==='library'?sources.files:sources.items)?.length===0&&<p className="materials-empty">没有找到素材，可以更换关键词或选择本地文件。</p>}
     {(sourceTab==='library'?sources?.files:sources?.items)?.map(row=><article className="materials-search-result" key={row.id}><strong>{row.name}</strong><small>{row.relative||row.source_label||row.task_title} {row.location&&' · '+row.location}</small>{row.excerpt&&<blockquote>{row.excerpt}</blockquote>}<button disabled={disabled} onClick={()=>run(async()=>{await mutate(sourceTab==='library'?'add_library':'add_artifact',sourceTab==='library'?{file_id:row.id}:{artifact_id:row.id});setNotice('已加入项目，默认仅内部。可到项目记录填写网站说明。');})}>加入当前项目</button></article>)}
    </>}
    {tab==='story'&&<>
     <p className="materials-hint">上下调整顺序后先保存；仅勾选已允许用于网站且原件可用的条目。内部备注与项目待办不会导出。请先核对截图和录屏中的个人内容。</p>
     <div className="materials-actions"><button disabled={busy} onClick={()=>setSelected(draft.entries.filter(e=>e.public&&!['missing','changed'].includes(e.file_status)).map(e=>e.id))}>选择所有可导出条目</button><button disabled={busy} onClick={()=>setSelected([])}>清除选择</button></div>
     <ol className="materials-story">{draft.entries.map((entry,i)=><li key={entry.id}><div className="materials-story-heading"><label className="materials-check"><input type="checkbox" checked={selected.includes(entry.id)} disabled={!entry.public||['missing','changed'].includes(entry.file_status)||busy} onChange={e=>setSelected(old=>e.target.checked?[...old,entry.id]:old.filter(id=>id!==entry.id))}/><strong>{entry.title}</strong></label><span>{entry.public?kindNames[entry.kind]:'仅内部'}</span></div><p>{entry.description||'尚未填写网站说明'}</p><small>{entry.source} {entry.file_name&&' · '+entry.file_name}</small>{['missing','changed'].includes(entry.file_status)&&<p className="materials-error">素材原件{entry.file_status==='missing'?'缺失':'已变化'}，重新选入后可导出。</p>}<div className="materials-actions"><button disabled={busy||i===0} aria-label={'上移 '+entry.title} onClick={()=>edit({entries:moveEntry(draft.entries,entry.id,-1)})}>上移</button><button disabled={busy||i===draft.entries.length-1} aria-label={'下移 '+entry.title} onClick={()=>edit({entries:moveEntry(draft.entries,entry.id,1)})}>下移</button><button disabled={disabled} onClick={()=>showPreview(entry)}>预览素材</button>{entry.file_name&&<button disabled={disabled} onClick={()=>run(()=>api('open',{id:draft.id,entry_id:entry.id}))}>打开原件</button>}</div></li>)}</ol>
     <section className="materials-export"><h3>本次导出预览 · {publicRows.length} 条</h3>{publicRows.map((e,i)=><article key={e.id}><strong>{i+1}. {e.title}</strong><p>{e.description}</p>{e.excerpt&&<blockquote>{e.excerpt}</blockquote>}<small>{e.source}</small></article>)}<p>生成 updates.md、manifest.json、storyboard.html 和选中的媒体原件，另附 ZIP 素材包。录屏保留原片，不剪辑或转码。</p><button className="materials-primary" disabled={disabled||!publicRows.length} onClick={()=>run(async()=>{const out=await api('export',{id:draft.id,selected:publicRows.map(e=>e.id),revision:state.revision});receive(out.snapshot);setExported(out);setNotice(out.message);})}>导出网站素材包</button>{exported&&<div role="status"><p>已导出 {exported.count} 条 · 尚未发布</p><button onClick={()=>run(()=>api('open_export',{id:draft.id,export_id:exported.id}))}>打开本次导出文件夹</button></div>}</section>
     {draft.exports.length>0&&<details><summary>历史导出（{draft.exports.length}）</summary>{[...draft.exports].reverse().map(row=><p key={row.id}>{row.created} · {row.count} 条 <button disabled={busy} onClick={()=>run(()=>api('open_export',{id:draft.id,export_id:row.id}))}>打开文件夹</button></p>)}</details>}
    </>}
   </>}
  </main></div></fieldset>{preview&&<Preview data={preview} onClose={()=>setPreview(null)}/>}
 </div>;
}
