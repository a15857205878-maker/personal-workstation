import React,{useRef,useState} from 'react';
import {desktopCall,usePage,Frame} from './workstation-pages.jsx';
export default function Leisure({visible,onNavigate,onRead}){
 const [minutes,setMinutes]=useState(15),[focusBusy,setFocusBusy]=useState(false),focusLock=useRef(false);
 const p=usePage(()=>desktopCall('workstation_leisure_status'),visible,5000),reading=p.data?.reading,focus=p.data?.focus;
 const focusText=focus?.kind==='running'?`专注进行中 · 剩余 ${Math.ceil(focus.remaining/60)} 分钟`:focus?.kind==='paused'?'专注已暂停':focus?.kind==='idle'?'当前没有专注计时':'专注状态暂不可确认';
 async function focusAction(action){if(focusLock.current)return;focusLock.current=true;setFocusBusy(true);try{await p.runQueued(async()=>{await desktopCall('workstation_town_call',{action,payload:action==='focus_start'?{task:'阅读与休息',minutes}:{}});return desktopCall('workstation_leisure_status');});}finally{focusLock.current=false;setFocusBusy(false);}}
 return <Frame title="休闲" description="玩一会儿、读几页，或去小镇休息。" page={p}>
  {reading?.warnings?.map((w,i)=><p className="ws-error" key={i}>{w}</p>)}
  {reading?.resume&&<article className="ws-card"><div className="ws-section-title"><div><h2>上次阅读 · {reading.resume.title}</h2><p className="ws-muted">{reading.resume.format==='.pdf'?`记在第 ${reading.resume.page} 页`:`已读 ${Math.round(reading.resume.position*100)}%`}</p></div><button onClick={()=>onRead(reading.resume.id)}>继续阅读</button></div></article>}
  <article className="ws-card" aria-label="专注快捷操作"><h2>给自己一段专注时间</h2><p className="ws-muted">{focusText} · 与小镇共用同一计时。</p><div className="ws-actions">{focus?.kind==='idle'&&<><label>时长 <select aria-label="专注时长" value={minutes} disabled={p.busy||focusBusy} onChange={e=>setMinutes(Number(e.target.value))}>{[5,15,25,45].map(n=><option key={n} value={n}>{n} 分钟</option>)}</select></label><button disabled={p.busy||focusBusy} onClick={()=>focusAction('focus_start')}>开始专注</button></>}{focus?.kind==='running'&&<button disabled={p.busy||focusBusy} onClick={()=>focusAction('focus_pause')}>暂停专注</button>}{focus?.kind==='paused'&&<button disabled={p.busy||focusBusy} onClick={()=>focusAction('focus_resume')}>继续专注</button>}<button onClick={()=>onNavigate('town')}>到小镇查看</button></div></article>
  <div className="ws-grid">{[['games','游戏资料库','查找游戏、收藏和已有工具。'],['wheel','轮盘','不知道选什么时，从自己的候选里抽一个。'],['reading','书房与放松',reading?.counts?`${reading.counts.books} 本读物 · ${reading.counts.reading} 本在读 · ${reading.counts.audio} 首本地音频`:'本地读物、笔记与环境音。'],['town','小镇与专注',focusText]].map(([id,title,hint])=><article className="ws-card" key={id}><h2>{title}</h2><p className="ws-muted">{hint}</p><button onClick={()=>onNavigate(id)}>进入{title}</button></article>)}</div>
 </Frame>;
}
