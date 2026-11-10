import React,{useEffect,useState} from 'react';
import {TaskPanel} from './task-panel.jsx';

export default function ArtifactBrowserPanel({page:p,call,visible}){
 const [query,setQuery]=useState(''),[source,setSource]=useState('all'),[preview,setPreview]=useState(null);
 useEffect(()=>{if(!visible)return;const refresh=()=>p.run();window.addEventListener('focus',refresh);return()=>window.removeEventListener('focus',refresh);},[visible]);
 const items=(p.data?.items||[]).filter(f=>(source==='all'||f.source_kind===source)&&[f.name,f.title,f.source_label].join(' ').toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
 const size=value=>value>=1048576?(value/1048576).toFixed(1)+' MB':Math.max(1,Math.ceil(value/1024))+' KB';
 async function act(action,payload={},refresh=false){await p.run(async()=>{const result=await call(action,payload);if(action==='workstation_artifact_preview'){setPreview(result);return;}if(refresh)return result;});}
 return <>
  <div className="ws-artifact-controls"><div className="ws-actions"><button disabled={p.busy} onClick={()=>act('workstation_artifact_add_files',{},true)}>添加文件</button><button disabled={p.busy} onClick={()=>act('workstation_artifact_add_folder',{},true)}>添加成果文件夹</button></div><p className="ws-muted">选择下载目录或其他成果位置后，刷新即可看到新文件。文件保留在原位置。</p>
   <div className="ws-artifact-filters"><input type="search" aria-label="搜索成果" placeholder="搜索文件名或任务…" value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label="成果来源" value={source} onChange={e=>setSource(e.target.value)}>{[['all','全部来源'],['station','独立任务'],['collaboration','双模型协作'],['external','外部文件']].map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></div>
  </div>
  {(p.data?.sources||[]).length>0&&<details className="ws-card ws-artifact-sources"><summary>管理已添加的位置 · {p.data.sources.length}</summary><p className="ws-muted">移除只取消成果列表的来源，不删除原文件，也不改变手机文件权限。</p>{p.data.sources.map(s=><div className="ws-row" key={s.id}><div><strong>{s.label}</strong><small>{s.kind==='folder'?'文件夹（仅当前层）':'单独文件'} · {s.path}</small></div><button disabled={p.busy} onClick={()=>act('workstation_artifact_source_remove',{id:s.id},true)}>移除来源</button></div>)}</details>}
  <article className="ws-card"><div className="ws-section-title"><h2>成果文件</h2><span className="ws-muted">显示 {items.length} 项</span></div>{!items.length&&<p className="ws-empty">{query||source!=='all'?'没有匹配的成果。':'当前还没有成果。外部客户端生成的文件可通过上方按钮添加。'}</p>}
   {items.map(f=><div className="ws-row ws-artifact-row" key={f.id}><div><strong>{f.name}</strong><small><span className="ws-badge">{f.source_label}</span> {f.title} · {size(f.size)}{f.modified?' · '+new Date(f.modified*1000).toLocaleString():''}</small></div><div className="ws-actions">{f.can_preview&&<button disabled={p.busy} onClick={()=>act('workstation_artifact_preview',{id:f.id})}>隔离预览</button>}{f.can_open&&<button disabled={p.busy} onClick={()=>act('workstation_artifact_open',{id:f.id})}>打开文件</button>}<button disabled={p.busy} onClick={()=>act('workstation_artifact_locate',{id:f.id})}>定位文件夹</button></div></div>)}
  </article>
  {preview&&<TaskPanel title={'预览 · '+preview.name} onClose={()=>setPreview(null)}><p className="ws-muted">隔离预览不运行脚本或外部资源；完整程序请从原成果入口审查。</p><iframe title="成果隔离预览" sandbox="" srcDoc={preview.html} style={{width:'100%',height:'55vh',border:0,background:'#fff'}}/></TaskPanel>}
 </>;
}
