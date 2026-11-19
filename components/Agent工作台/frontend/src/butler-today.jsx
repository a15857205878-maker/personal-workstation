import React from 'react';
import {ArrowUpRight,CheckCircle2,Clock3,ListTodo} from 'lucide-react';
import DragonMark from './dragon-mark.jsx';

const groups=[
 {id:'prepared',label:'待确认',tone:'attention',icon:ListTodo,empty:'没有待确认的分工',action:'确认分工'},
 {id:'active',label:'进行中',tone:'working',icon:Clock3,empty:'当前没有执行中的任务',action:'查看进度'},
 {id:'review',label:'可验收',tone:'ready',icon:CheckCircle2,empty:'没有待验收的成果',action:'查看成果'},
];
const phases={starting:'准备启动',running:'正在执行',stopping:'正在停止'};

export default function ButlerToday({today,busy,partial,onConversation,onAccept,pendingId,notice}){
 function item(entry,group){
  const delivery=['review','accepted'].includes(group.id);
  const detail=delivery?(entry.file_count?`${entry.file_count} 份文件`:group.id==='accepted'?'已确认完成':'文字成果'):phases[entry.state]||'待确认分工';
  return <li className="butler-today-item" key={entry.conversation_id+':'+entry.turn_id}><button type="button" onClick={()=>onConversation?.({
   conversation_id:entry.conversation_id,turn_id:entry.turn_id,section:delivery?'delivery':'progress',fromToday:true,
  })}><span><strong>{entry.title}{entry.job_count>1?'等 '+entry.job_count+' 项':''}</strong><small>{entry.conversation_title} · {detail}</small></span>
   <span className="butler-today-action">{group.action}<ArrowUpRight size={14} aria-hidden="true"/></span>
  </button>{group.id==='review'&&<button type="button" className="butler-accept-button" disabled={!!pendingId} onClick={()=>onAccept(entry)}>{pendingId===entry.turn_id?'正在确认…':'确认完成'}</button>}</li>;
 }
 return <section className="ws-card butler-today" aria-labelledby="butler-today-title">
  <header><DragonMark/><div><small className="ws-muted">龙娘管家</small><h2 id="butler-today-title">今日事务</h2></div></header>
  {notice&&<p className="ws-muted" role="status">{notice}</p>}
  {!today&&<p role="status" className="ws-muted">{busy?'正在读取今日事务…':'暂时无法读取今日事务，请刷新。'}</p>}
  {today&&<div className="butler-today-grid">{groups.map(group=>{
   const {count=0,items=[]}=today[group.id]||{};
   const Icon=group.icon;
   return <section className="butler-today-group" key={group.id} aria-label={group.label}>
    <h3><Icon size={16} aria-hidden="true"/><span>{group.label}</span><span className="feedback-status" data-tone={group.tone}>{partial&&!count?'—':count}</span></h3>
    {items.length?<ul>{items.slice(0,4).map(entry=>item(entry,group))}</ul>:<p className="ws-muted">{partial?'部分任务状态暂不可读':group.empty}</p>}
    {items.length>4&&<details><summary>展开更多 · {items.length-4}</summary><ul>{items.slice(4).map(entry=>item(entry,group))}</ul></details>}
    {count>items.length&&<small>先显示最近 {items.length} 项</small>}
    {group.id==='review'&&today.accepted?.count>0&&<details className="butler-accepted">
     <summary>今天已确认 · {today.accepted.count}</summary>
     <ul>{today.accepted.items.map(entry=>item(entry,{id:'accepted',action:'查看成果'}))}</ul>
    </details>}
   </section>;
  })}</div>}
 </section>;
}
