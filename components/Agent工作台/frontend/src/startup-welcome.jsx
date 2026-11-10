import React,{useEffect,useState} from 'react';
import {Command} from 'lucide-react';
import './startup-welcome.css';

export default function StartupWelcome(){
 const [visible,setVisible]=useState(()=>!window.matchMedia('(prefers-reduced-motion: reduce)').matches);
 useEffect(()=>{
  if(!visible)return;
  const media=window.matchMedia('(prefers-reduced-motion: reduce)');
  const reduce=event=>{if(event.matches)setVisible(false);};
  media.addEventListener('change',reduce);
  const timer=setTimeout(()=>setVisible(false),1100);
  return()=>{clearTimeout(timer);media.removeEventListener('change',reduce);};
 },[visible]);
 if(!visible)return null;
 return <div className="startup-welcome" aria-label="欢迎使用个人工作站">
  <div className="startup-welcome-brand"><span aria-hidden="true"><Command size={32}/></span><strong>个人工作站</strong><p>你的工作搭档</p></div>
  <button type="button" onClick={()=>setVisible(false)}>跳过开场</button>
 </div>;
}
