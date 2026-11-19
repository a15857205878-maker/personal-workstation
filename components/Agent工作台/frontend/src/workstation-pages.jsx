import React,{useEffect,useRef,useState} from 'react';
import {ChevronRight,ClipboardCheck,RefreshCw} from 'lucide-react';
import './workstation-pages.css';
import './page-polish.css';
import WorkstationPreferences from './workstation-preferences.jsx';
import ArtifactBrowserPanel from './artifact-browser.jsx';
import {CenterMetrics,RecentCenter} from './center-status.jsx';
import {PageEmpty} from './page-sections.jsx';

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
export function usePage(load,visible,pollMs=0){
 const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),inFlight=useRef(false),completion=useRef(Promise.resolve());
 async function run(fn=load,quiet=false){if(inFlight.current)return;inFlight.current=true;let finish;completion.current=new Promise(resolve=>{finish=resolve;});if(!quiet)setBusy(true);setError('');try{const value=await fn();if(value!==undefined)setData(value);return value;}catch(e){setError(e.message);}finally{inFlight.current=false;finish();if(!quiet)setBusy(false);}}
 async function runQueued(fn){while(inFlight.current)await completion.current;return run(fn);}
 useEffect(()=>{if(!visible)return;const ready=()=>run();if(window.pywebview?.api?.call)ready();else window.addEventListener('pywebviewready',ready,{once:true});const timer=pollMs?setInterval(()=>{if(!document.hidden&&window.pywebview?.api?.call)run(load,true);},pollMs):null;return()=>{window.removeEventListener('pywebviewready',ready);if(timer)clearInterval(timer);};},[visible,pollMs]);
 return {data,setData,error,busy,run,runQueued};
}
export function Frame({title,description,page,children,className='',showBusy=true}){return <div className={`ws-page ${className}`}><header className="ws-page-heading"><div><h1>{title}</h1>{description&&<p>{description}</p>}</div>{page&&<button disabled={page.busy} onClick={()=>page.run()}>刷新</button>}</header>{page?.error&&<p className="ws-error" role="alert">{page.error}</p>}{page?.busy&&showBusy&&<p className="ws-muted" role="status">正在处理…</p>}{children}</div>;}
function Empty({children}){return <p className="ws-empty">{children}</p>;}
export function Overview({visible,onNavigate,onConversation}){
 const p=usePage(()=>desktopCall('workstation_overview'),visible,5000),d=p.data;
 return <Frame title="工作概览" description="查看当前搭档的进度、待处理回复和成果。" page={p}>
  <CenterMetrics counts={d?.counts} unknown={d?.center_available===false}/>
  <p className="ws-muted">{d?.scope}</p>{d?.warnings?.map((w,i)=><p className="ws-error" key={i}>{w}</p>)}
  <div className="ws-dashboard-grid"><article className="ws-card"><div className="ws-section-title"><h2>最近搭档会话</h2><button onClick={()=>onNavigate('partner')}>打开搭档</button></div><RecentCenter rows={d?.conversations} onConversation={onConversation}/></article>
  <article className="ws-card"><div className="ws-section-title"><h2>继续工作</h2></div><div className="ws-entry-list">{[['partner','搭档','继续讨论、交办与分工'],['artifacts','成果中心','按会话查找已生成文件'],['pack','资料与打包','整理素材并打包文件'],['remote','手机连接','群聊、成果与文件传输']].map(([id,title,hint])=><button key={id} onClick={()=>onNavigate(id)}><span><strong>{title}</strong><small>{hint}</small></span><ChevronRight size={16}/></button>)}</div></article></div>
  <details className="ws-card"><summary>历史记录参考 · {d?.counts?.tasks??'—'} 个旧任务 / {d?.counts?.collaborations??'—'} 个原运行记录</summary><p className="ws-muted">{d?.history_scope}</p>{d?.history_warnings?.map((w,i)=><p key={i} className="ws-error">{w}</p>)}<button onClick={()=>onNavigate('artifacts')}>查看历史成果</button></details>
 </Frame>;
}
export function Artifacts({visible,onConversation,onNavigate,turn,onClearTurn}){
 const p=usePage(()=>desktopCall('workstation_artifacts'),visible);
 return <Frame title={turn?'本轮成果':'成果'} description={turn?'查看本轮登记的文件，或回到任务原记录。':'查找搭档交付、已添加的文件和历史成果。'} page={p} className="ws-polished-page" showBusy={!!p.data}>
  {p.data?.warnings?.map((w,i)=><p className="ws-error" key={i}>{w}</p>)}
  <ArtifactBrowserPanel page={p} call={desktopCall} visible={visible} onConversation={onConversation} onNavigate={onNavigate} turn={turn} onClearTurn={onClearTurn}/>
 </Frame>;
}
function SettingsDiagnostics({visible}){
 const p=usePage(()=>desktopCall('workstation_diagnostics'),visible),d=p.data;
 const checks=Array.isArray(d?.checks)?d.checks:[];
 const attention=checks.filter(c=>['warning','error'].includes(c.state||c.status));
 const label={ok:'正常',warning:'待检查',error:'异常'};
 const checkRows=rows=>rows.map((c,i)=><div className="ws-check" key={c.id||i}><span className={'ws-check-state '+(c.state||c.status)}>{label[c.state||c.status]||'检查'}</span><span>{c.message||c.name||c.id}</span></div>);
 return <div className="ws-settings-diagnostics">
  <div className="ws-section-title"><h3>接口与运行自检</h3><button disabled={p.busy} onClick={()=>p.run()}>重新检查</button></div>
  {p.error&&<p role="alert" className="ws-error">{d?'刷新失败，显示上一次的检查结果。':''}{p.error}</p>}
  {!d?<PageEmpty compact icon={p.error?RefreshCw:ClipboardCheck} title={p.error?'自检未完成':'正在读取检查结果…'} busy={!p.error}/>:
   <>
    <p className="ws-muted" role="status">{p.busy?'正在更新检查结果…':attention.length?`有 ${attention.length} 项需要核对`:checks.length?'当前检查范围内未发现异常':'暂时没有检查结果'}</p>
    {attention.length>0&&<div className="ws-diagnostic-list">{checkRows(attention)}</div>}
    {checks.length>0&&<details className="ws-diagnostic-list"><summary>查看全部 {checks.length} 项检查</summary>{d.scope&&<p className="ws-muted">{d.scope}</p>}{checkRows(checks)}</details>}
   </>}
 </div>;
}
export function SettingsPage({visible,onModels,onQuick,onNavigate}){
 return <Frame title="设置与维护" description="管理外观、协作模型、手机连接和运行入口。" className="ws-polished-page">
  <WorkstationPreferences visible={visible} call={desktopCall} onModels={onModels} onQuick={onQuick} onNavigate={onNavigate} renderMaintenance={active=><SettingsDiagnostics visible={active}/>}/>
 </Frame>;
}
