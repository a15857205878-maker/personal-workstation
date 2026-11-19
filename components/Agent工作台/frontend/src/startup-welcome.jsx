import React,{useEffect,useState} from 'react';
import {Command} from 'lucide-react';
import './startup-welcome.css';
export default function StartupWelcome(){
 const [visible,setVisible]=useState(()=>!window.matchMedia('(prefers-reduced-motion: reduce)').matches),[manual,setManual]=useState(false),[generation,setGeneration]=useState(0);
 useEffect(()=>{const replay=()=>{setManual(true);setGeneration(v=>v+1);setVisible(true);};window.addEventListener('workstation-replay-startup',replay);return()=>window.removeEventListener('workstation-replay-startup',replay);},[]);
 useEffect(()=>{if(!visible)return;const media=window.matchMedia('(prefers-reduced-motion: reduce)'),reduce=e=>{if(e.matches)setVisible(false);};media.addEventListener('change',reduce);const timer=setTimeout(()=>setVisible(false),3000);return()=>{clearTimeout(timer);media.removeEventListener('change',reduce);};},[visible,generation]);
 if(!visible)return null;
 return <div key={generation} className={'startup-welcome'+(manual?' startup-manual':'')} aria-label="欢迎使用个人工作站">
  <div className="startup-welcome-brand"><div className="startup-symbol" aria-hidden="true"><span className="startup-thread thread-one"/><span className="startup-thread thread-two"/><span className="startup-thread thread-three"/><i><Command size={34}/></i></div><strong>个人工作站</strong><p>让想法，在这里相遇。</p></div>
  <button type="button" onClick={()=>setVisible(false)}>跳过开场</button>
 </div>;
}
