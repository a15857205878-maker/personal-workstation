import React,{useEffect,useRef,useState} from 'react';
import {roomTaskState} from './companion-room-model.mjs';
import './companion-room.css';

// Open the actual pet host instead of drawing a second static resident here.
export default function CompanionRoom({visible,call,butler,companion,onNavigate}){
 const [status,setStatus]=useState(null),[pending,setPending]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState('');
 const wanted=useRef(null),busy=useRef(false),alive=useRef(false);
 useEffect(()=>{
  if(!visible)return;let disposed=false,inFlight=false;alive.current=true;
  const check=async()=>{
   if(disposed||document.hidden||inFlight)return;inFlight=true;
   try{
    const value=await call('workstation_companion_home_status');if(disposed)return;setStatus(value);
    const request=wanted.current;
    if(request&&value.request_id===request.id){
     wanted.current=null;setPending(false);
     if(value.request_state==='opened'){setMessage('小屋已在桌面打开。');setError('')}
     else if(value.request_state==='failed'){setMessage('');setError(value.error||'小屋暂时无法打开，请从桌宠菜单重试。')}
    }else if(request&&Date.now()-request.at>17000){wanted.current=null;setPending(false);setMessage('');setError('尚未收到桌宠确认。请正常重启桌宠，或从桌宠菜单打开小屋；不会自动重发请求。')}
   }catch{if(!disposed)setStatus(null)}finally{
    inFlight=false;
    if(!disposed&&wanted.current&&Date.now()-wanted.current.at>17000){wanted.current=null;setPending(false);setMessage('');setError('等待确认已超时，请检查桌宠后再操作；不会自动重发请求。')}
   }
  };
  check();const timer=setInterval(check,2000);document.addEventListener('visibilitychange',check);
  return()=>{disposed=true;alive.current=false;clearInterval(timer);document.removeEventListener('visibilitychange',check)};
 },[visible,call]);
 const open=async()=>{
  if(busy.current||wanted.current)return;busy.current=true;setPending(true);setError('');setMessage('正在请求打开小屋…');
  try{const result=await call('workstation_companion_home');if(!/^[a-f0-9]{32}$/.test(result?.request_id||''))throw Error('打开请求未被确认，请先查看桌宠状态。');wanted.current={id:result.request_id,at:Date.now()};if(alive.current)setMessage(result.message)}
  catch(e){setPending(false);setMessage('');setError(e.message||'请求结果不明确，请先检查桌宠，避免重复打开。')}
  finally{busy.current=false}
 };
 const task=roomTaskState(butler),connected=status?.connected===true;
 const connection=connected?(status.visible===false?'已连接 · 已隐藏':status.mode==='home'?'已连接 · 小屋模式':'已连接 · 桌面模式')
  :status===null?'正在检查桌宠':companion?.launch_ready?'桌宠尚未连接':'桌宠入口待检查';
 return <article className="companion-home ws-card" aria-label="桌宠生活空间">
  <div className="companion-home-heading">
   <div className="companion-home-title"><h2>龙娘的小屋</h2>
    <p>从工作站打开桌面小屋，或留在工作站逛小镇。</p>
    <span className="companion-connection" data-connected={connected} role="status">{connection}</span>
   </div>
   <button className="ws-primary companion-open" disabled={pending||(!connected&&companion?.launch_ready===false)} onClick={open}>{pending?'等待桌宠确认…':'打开桌面小屋'}</button>
  </div>
  {(message||error)&&<div className="companion-home-result">
   {message&&<p role="status">{message}</p>}{error&&<p className="ws-error" role="alert">{error}</p>}
  </div>}
  <div className="companion-home-body">
   <div className="companion-home-status"><div className={'companion-home-task '+task.kind}><span aria-hidden="true"/><strong>{task.label}</strong></div><p>{task.hint}</p><small>工作概况更新于 {butler?.observed_at?new Date(butler.observed_at*1000).toLocaleTimeString():'尚未同步'}</small></div>
   <div className="ws-actions companion-home-links"><button onClick={()=>onNavigate('town')}>在工作站逛小镇</button><button onClick={()=>onNavigate('reading')}>书房与放松</button></div>
  </div>
 </article>;
}
