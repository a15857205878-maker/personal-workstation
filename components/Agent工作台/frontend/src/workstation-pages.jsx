import React,{useEffect,useRef,useState} from 'react';
import {ChevronRight} from 'lucide-react';
import './workstation-pages.css';
import WorkstationPreferences from './workstation-preferences.jsx';
import ArtifactBrowserPanel from './artifact-browser.jsx';

export async function desktopCall(action,payload={}){
 if(!window.pywebview?.api?.call)throw Error('正在等待本地桌面服务，请稍后刷新。');
 const result=await window.pywebview.api.call(action,payload);
 if(!result.ok)throw Error(result.error||'操作未完成');
 return result.data;
}
export const toolCall=(action,payload={})=>desktopCall('workstation_tool_call',{action,payload});
export const activeJob=job=>['queued','running'].includes(job?.status);
export const packPayload=(files,output_dir)=>({files:files.map(file=>file.path),output_dir});
export const selectedOutput=result=>result.cancelled?null:result.output_dir||result.path||'';
const jobLabel={queued:'排队中',running:'打包中',completed:'已完成',failed:'失败',uncertain:'需要核对'};
export function usePage(load,visible){
 const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),inFlight=useRef(false);
 async function run(fn=load){if(inFlight.current)return;inFlight.current=true;setBusy(true);setError('');try{const value=await fn();if(value!==undefined)setData(value);return value;}catch(e){setError(e.message);}finally{inFlight.current=false;setBusy(false);}}
 useEffect(()=>{if(!visible)return;if(window.pywebview?.api?.call){run();return;}const ready=()=>run();window.addEventListener('pywebviewready',ready,{once:true});return()=>window.removeEventListener('pywebviewready',ready);},[visible]);
 return {data,setData,error,busy,run};
}
export function Frame({title,description,page,children}){return <div className="ws-page"><header className="ws-page-heading"><div><h1>{title}</h1><p>{description}</p></div>{page&&<button disabled={page.busy} onClick={()=>page.run()}>刷新</button>}</header>{page?.error&&<p className="ws-error" role="alert">{page.error}</p>}{page?.busy&&<p className="ws-muted" role="status">正在处理…</p>}{children}</div>;}
function Empty({children}){return <p className="ws-empty">{children}</p>;}
export function Overview({visible,onNavigate,onTask}){
 const p=usePage(()=>desktopCall('workstation_overview'),visible),d=p.data;
 return <Frame title="工作概览" description="继续手上的任务，或开始一项新的工作。" page={p}>
  <div className="ws-stats">{[['tasks','独立任务'],['collaborations','双模型协作'],['active','正在进行'],['attention','需要关注']].map(([key,label])=><div className="ws-card" key={key}><strong>{d?.counts?.[key]??'—'}</strong><span>{label}</span></div>)}</div>
  <p className="ws-muted">{d?.scope}</p>{d?.warnings?.map((w,i)=><p className="ws-error" key={i}>{w}</p>)}
  <div className="ws-dashboard-grid"><article className="ws-card"><div className="ws-section-title"><h2>最近任务</h2><button onClick={()=>onNavigate('tasks')}>查看全部</button></div>
   {!d?.tasks?.length&&<Empty>还没有任务记录。从右侧开始你的第一项工作。</Empty>}
   {d?.tasks?.slice(0,5).map(t=><div className="ws-task-row" key={t.id}><button onClick={()=>onTask(t.id)}><strong>{t.title||'未命名任务'}</strong></button><small>{t.status}</small></div>)}
   <div className="ws-section-title" style={{marginTop:24}}><h2>最近协作</h2><small>执行与审查，接着进行</small></div>
   {!d?.collaborations?.length&&<Empty>还没有双模型协作记录。</Empty>}
   {d?.collaborations?.slice(0,3).map(t=><div className="ws-task-row" key={t.id}><strong>{t.title||t.task||'协作记录'}</strong><small>{t.status}</small></div>)}
  </article><article className="ws-card"><div className="ws-section-title"><h2>开始工作</h2><small>按目标选择入口</small></div><div className="ws-entry-list">
   {[['tasks','新建独立任务','文档、内容、审查与交接'],['work','双模型协作','执行提案、审查与修订'],['pack','资料与打包','整理素材、打包交付文件'],['remote','远程连接','手机任务、历史会话与配对']].map(([id,title,hint])=><button key={id} onClick={()=>onNavigate(id)}><span><strong>{title}</strong><small>{hint}</small></span><ChevronRight size={16} aria-hidden="true"/></button>)}
  </div></article></div>
  <article className="ws-card ws-rest-row"><div><h2>留一点休息时间</h2><p>游戏、轮盘和小镇，放在独立的休闲空间。</p></div><div className="ws-actions"><button onClick={()=>onNavigate('games')}>游戏资料库</button><button onClick={()=>onNavigate('wheel')}>休闲轮盘</button><button onClick={()=>onNavigate('town')}>小镇与专注</button></div></article>
 </Frame>;
}
export function Artifacts({visible}){
 const p=usePage(()=>desktopCall('workstation_artifacts'),visible);
 return <Frame title="成果" description={p.data?.scope||'汇总任务成果，以及你添加的其他位置文件。'} page={p}>{p.data?.warnings?.map((w,i)=><p className="ws-error" key={i}>{w}</p>)}<ArtifactBrowserPanel page={p} call={desktopCall} visible={visible}/></Frame>;
}
export function SettingsPage({visible,onModels,onQuick,onNavigate}){
 const p=usePage(()=>desktopCall('workstation_diagnostics'),visible),d=p.data;
 const checks=Array.isArray(d?.checks)?d.checks:[];
 const attention=checks.filter(c=>['warning','error'].includes(c.state||c.status));
 const label={ok:'正常',warning:'待检查',error:'异常'};
 const checkRows=rows=>rows.map((c,i)=><div className="ws-check" key={c.id||i}><span className={'ws-check-state '+(c.state||c.status)}>{label[c.state||c.status]||'检查'}</span><span>{c.message||c.name||c.id}</span></div>);
 return <Frame title="设置与维护" description="管理工作站偏好，检查模块连接与运行入口。" page={p}>
  {!!attention.length&&<p className="ws-muted" role="status">有 {attention.length} 项运行检查需要关注，可展开下方高级维护查看。</p>}
  <WorkstationPreferences visible={visible} call={desktopCall} onModels={onModels} onQuick={onQuick} onNavigate={onNavigate}/>
  <details className="ws-card ws-settings-diagnostics" style={{marginTop:18}}><summary>高级维护 · 接口与运行自检{attention.length?` · ${attention.length} 项待检查`:""}</summary><div className="ws-section-title"><h2>接口与运行自检</h2><span className="ws-muted">{d?.scope}</span></div><div className="ws-actions">{Object.entries(d?.counts||{}).map(([k,v])=><span className="ws-badge" key={k}>{label[k]||k} {v}</span>)}</div>
   {!!d&&<div className="ws-diagnostic-list">{attention.length?checkRows(attention):<p className="ws-muted">当前检查范围内未发现异常入口。</p>}</div>}
   {!!checks.length&&<details className="ws-diagnostic-list"><summary>查看全部 {checks.length} 项检查</summary>{checkRows(checks)}</details>}
  </details>
 </Frame>;
}
