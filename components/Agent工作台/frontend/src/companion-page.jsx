import React,{useRef,useState} from 'react';
import {ArrowUpRight} from 'lucide-react';
import {desktopCall,usePage,Frame} from './workstation-pages.jsx';
import CompanionRoom from './companion-room.jsx';
import {CenterMetrics,RecentCenter} from './center-status.jsx';
import ButlerToday from './butler-today.jsx';

export default function CompanionPage({visible,onNavigate,onConversation}){
 const load=async()=>{
  const [butler,compat]=await Promise.all([desktopCall('workstation_butler_status'),desktopCall('workstation_companion_status').catch(()=>null)]);
  return {butler,compat};
 };
 const p=usePage(load,visible,5000),d=p.data?.butler,c=p.data?.compat;
 const [notice,setNotice]=useState('');
 const [pendingId,setPendingId]=useState(''),[reviewNotice,setReviewNotice]=useState('');
 const pending=useRef(false);
 async function accept(entry){
  if(pending.current)return;
  pending.current=true;setPendingId(entry.turn_id);setReviewNotice('');
  try{
   await p.runQueued(async()=>{
    await desktopCall('api_center_accept',{id:entry.conversation_id,turn_id:entry.turn_id});
    setReviewNotice('已确认完成');
    return load();
   });
  }finally{pending.current=false;setPendingId('');}
 }
 const launch=()=>p.run(async()=>{
  const result=await desktopCall('workstation_companion_launch');
  setNotice(result.message);
  return load();
 });
 return <div className="companion-page"><Frame title="个人管家" description="查看今日事务、桌宠提醒和常用功能。" page={p}>
  <ButlerToday today={d?.today} busy={p.busy||!p.data&&!p.error} partial={d?.overview_state==='unavailable'} onConversation={onConversation}
   onAccept={accept} pendingId={pendingId} notice={reviewNotice}/>
  <CompanionRoom visible={visible} call={desktopCall} butler={d} companion={c} onNavigate={onNavigate}/>
  {d?.warnings?.map((warning,i)=><p role="alert" className="ws-error" key={i}>{warning}</p>)}
  <CenterMetrics counts={d?.counts} unknown={d?.overview_state!=='ready'}/>
  <p className="ws-muted">{d?.scope}</p>
  <div className="ws-setup-grid companion-grid">
   <article className="ws-card"><h2>近期工作站提醒</h2><p className="ws-muted">直接读取当前搭档状态；历史提醒单列，不改变桌宠收件箱的已读状态。</p>
    {d&&!d.notices?.length&&<p className="ws-empty">暂时没有近期状态提醒。</p>}
    {d?.notices?.slice(0,12).map(item=><div className="butler-center-notice" key={item.id}><div><strong>{item.label}</strong><small>{item.source}{item.at>0?' · '+new Date(item.at*1000).toLocaleString():''}</small></div><button onClick={()=>item.conversation_id?onConversation?.({conversation_id:item.conversation_id,turn_id:item.turn_id}):onNavigate(item.page==='tasks'?'artifacts':item.page)}>去处理</button></div>)}
    <details><summary>最近会话</summary><RecentCenter rows={d?.recent} onConversation={onConversation}/></details>
    {!!d?.history_notices?.length&&<details><summary>历史提醒 · {d.history_notices.length}</summary>{d.history_notices.slice(0,8).map(item=><p key={item.id}>{item.source} · {item.label}</p>)}</details>}
   </article>
   <article className="ws-card"><h2>继续处理</h2><div className="ws-entry-list">{[['partner','搭档群聊','讨论、交办和继续对话'],['work','双模型协作','回到执行与审查'],['chat','聊天实验室','继续交流与角色实验'],['remote','远程连接','手机任务与远程会话'],['artifacts','查看成果','检查文件与交付结果'],['settings','设置与维护','模型配置及运行检查']].map(([id,title,hint])=><button key={id} data-butler-page={id} onClick={()=>onNavigate(id)}><span><strong>{title}</strong><small>{hint}</small></span><ArrowUpRight size={15}/></button>)}</div></article>
  </div>
  <details className="ws-card butler-compatibility"><summary>检查桌宠连接</summary>
   <div className="companion-check"><span>龙娘桌宠启动入口</span><strong>{c?c.launch_ready?'已配置':'需要检查':'正在检查'}</strong></div>
   <div className="companion-check"><span>工作站连接配置</span><strong>{c?c.workbench_linked?'位置一致':'需要检查':'正在检查'}</strong></div>
   <div className="ws-actions"><button disabled={p.busy||!c?.launch_ready} onClick={launch}>启动龙娘桌宠</button></div>
   {notice&&<p role="status">{notice}</p>}
   {c?.warnings?.map((warning,i)=><p className="ws-muted" key={i}>{warning}</p>)}
  </details>
 </Frame></div>;
}
