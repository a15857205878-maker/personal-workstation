import React,{useEffect,useState} from 'react';
import {PawPrint,ArrowUpRight} from 'lucide-react';
import {desktopCall,usePage,Frame} from './workstation-pages.jsx';
import CompanionRoom from './companion-room.jsx';

export default function CompanionPage({visible,onNavigate}){
 const load=async()=>{
  const [butler,compat]=await Promise.all([desktopCall('workstation_butler_status'),desktopCall('workstation_companion_status').catch(()=>null)]);
  return {butler,compat};
 };
 const p=usePage(load,visible),d=p.data?.butler,c=p.data?.compat;
 const [notice,setNotice]=useState('');
 useEffect(()=>{
  if(!visible)return;let disposed=false,inFlight=false;
  const timer=setInterval(async()=>{if(document.hidden||inFlight)return;inFlight=true;try{const value=await load();if(!disposed)p.setData(value)}catch{if(!disposed)p.setData(old=>old?{...old,butler:null}:old)}finally{inFlight=false}},5000);
  return()=>{disposed=true;clearInterval(timer)};
 },[visible]);
 const launch=()=>p.run(async()=>{const result=await desktopCall('workstation_companion_launch');setNotice(result.message);return load();});
 return <div className="companion-page"><Frame title="个人管家" description="工作概况、近期提醒与常用功能，在个人中心内继续处理。" page={p}>
  {notice&&<p className="companion-notice" role="status">{notice}</p>}
  <CompanionRoom visible={visible} call={desktopCall} butler={d} onNavigate={onNavigate}/>
  {d?.warnings?.map((warning,i)=><p role="alert" className="ws-error" key={i}>{warning}</p>)}
  <div className="ws-stats">{[['tasks','独立任务'],['collaborations','双模型协作'],['active','正在进行'],['attention','需要关注']].map(([key,label])=><div className="ws-card" key={key}><strong>{d?.counts?.[key]??'—'}</strong><span>{label}</span></div>)}</div>
  <p className="ws-muted">{d?.scope}</p>
  <div className="ws-setup-grid companion-grid">
   <article className="ws-card"><h2>近期工作站提醒</h2><p className="ws-muted">复用任务与协作的状态记录；这里查看近期事件，不改变桌宠收件箱的已读状态。</p>
    {d&&!d.notices?.length&&<p className="ws-empty">暂时没有近期状态提醒。</p>}
    {d?.notices?.slice(0,12).map(item=><div className="butler-center-notice" key={item.id}><div><strong>{item.label}</strong><small>{item.source}{item.at>0?' · '+new Date(item.at*1000).toLocaleString():''}</small></div><button onClick={()=>onNavigate(item.page)}>去处理</button></div>)}
   </article>
   <article className="ws-card"><h2>继续处理</h2><div className="ws-entry-list">{[['tasks','任务与交接','检查结果、补充需求或继续任务'],['work','双模型协作','回到执行与审查'],['chat','聊天实验室','继续交流与角色实验'],['remote','远程连接','手机任务与远程会话'],['artifacts','查看成果','检查文件与交付结果'],['settings','设置与维护','模型配置及运行检查']].map(([id,title,hint])=><button key={id} data-butler-page={id} onClick={()=>onNavigate(id)}><span><strong>{title}</strong><small>{hint}</small></span><ArrowUpRight size={15}/></button>)}</div></article>
  </div>
  <details className="ws-card butler-compatibility"><summary>桌面角色与原版兼容</summary><div className="companion-intro"><div className="companion-mark"><PawPrint size={25}/></div><div><h2>桌宠伴随组件</h2><p>需要桌面角色、原 Agent 进度卡、勿扰与陪伴时，继续使用现有桌宠。蓝发原版和龙娘设置保留。</p></div><button className="ws-primary" disabled={p.busy||!c?.launch_ready} onClick={launch}>启动桌宠 <ArrowUpRight size={14}/></button></div>
   <div className="companion-check"><span>桌宠启动入口</span><strong>{c?c.launch_ready?'已配置':'需要检查':'未连接兼容组件'}</strong></div><div className="companion-check"><span>工作站连接配置</span><strong>{c?c.workbench_linked?'位置一致':'需要检查':'未检查'}</strong></div>
   {c?.warnings?.map((warning,i)=><p className="ws-muted" key={i}>{warning}</p>)}<p className="ws-muted">已隐藏的桌宠可从系统托盘恢复。通知偏好、勿扰和陪伴记录仍由桌宠管理，个人中心不另外写一份配置。</p>
  </details>
  <details className="ws-card butler-compatibility"><summary>新增模块与组件边界</summary><p className="ws-muted">此页的工作概况、工作站提醒与功能导航属于个人中心管家模块，可以在未安装桌宠或角色模型时使用。桌面角色、原版适配与渲染运行库属于可选兼容组件；源码修改、角色资源和第三方依赖的来源分别记录，现有许可声明继续保留。</p></details>
 </Frame></div>;
}
