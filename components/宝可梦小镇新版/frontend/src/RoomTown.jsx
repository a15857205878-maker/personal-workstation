import {useEffect,useRef,useState} from 'react';
import {createBridge} from './lib/bridge.js';
import {isSnapshot} from './lib/town.js';
import {FocusView} from './components/FocusView.jsx';
export function RoomTown({onBack,onExit,hiddenByHost=false}){
 const bridge=useRef(null),locked=useRef(false),alive=useRef(true),hidden=useRef(hiddenByHost);if(!bridge.current)bridge.current=createBridge(window);
 const [snapshot,setSnapshot]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 async function call(action,payload={}){if(locked.current)return {ok:false};locked.current=true;if(action!=='focus_state')setBusy(true);try{const r=await bridge.current.call(action,payload);if(alive.current){if(r.ok&&isSnapshot(r.data)){setSnapshot(r.data);setError('')}else setError(r.error||'暂时无法读取专注状态')}return r}finally{locked.current=false;if(alive.current)setBusy(false)}}
 useEffect(()=>{alive.current=true;call('bootstrap');const timer=setInterval(()=>{if(!document.hidden&&!hidden.current)call('focus_state')},1000);function receive(e){if(e.source===parent&&e.origin===location.origin&&e.data?.t==='room-town-visibility')hidden.current=!!e.data.hidden}window.addEventListener('message',receive);return()=>{alive.current=false;clearInterval(timer);window.removeEventListener('message',receive)}},[]);
 useEffect(()=>{hidden.current=hiddenByHost},[hiddenByHost]);
 useEffect(()=>{if(snapshot||error)parent.postMessage({t:'room-alarm-ready'},location.origin)},[!!snapshot,!!error]);
 function back(){if(busy)return;if(onBack)onBack();else parent.postMessage({t:'room-town-close'},location.origin)}
 useEffect(()=>{function key(e){if(e.key==='Escape'&&!e.defaultPrevented&&!busy&&!document.querySelector('input:focus,textarea:focus')){e.preventDefault();back()}}window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key)},[busy,onBack]);
 return <div className="room-town-app room-alarm"><header className="room-town-head"><h1>专注闹钟</h1><div className="room-exit-actions"><button className="button button--soft" disabled={busy} onClick={back}>{onBack?'返回院落':'收起闹钟'}</button>{onExit&&<button className="button button--soft" disabled={busy} onClick={onExit}>关闭小镇</button>}</div></header>{error&&<p role="alert">{error}<button className="button" disabled={busy} onClick={()=>call('bootstrap')}>重试</button></p>}{snapshot?<FocusView compact snapshot={snapshot} busy={busy} motion={false} hidden={hiddenByHost||document.hidden} onAction={call}/>:<p role="status">正在读取专注…</p>}</div>
}
