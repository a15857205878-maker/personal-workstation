import {useEffect,useRef,useState} from 'react';
import {createBridge} from './lib/bridge.js';
import {isYardCareRequest} from './lib/yard-care-contract.mjs';
import {RoomTown} from './RoomTown.jsx';

// Workstation composition only. All town state still belongs to TownAdapter.
export function TownPortal(){
 const bridge=useRef(null);if(!bridge.current)bridge.current=createBridge(window);
 const [view,setView]=useState('yard'),[hidden,setHidden]=useState(document.hidden);const frame=useRef(null),hostHidden=useRef(false);
 useEffect(()=>{function sync(){setHidden(document.hidden||hostHidden.current)}async function receive(e){
  if(e.origin!==location.origin)return;
  if(e.source===parent&&e.data?.t==='workstation-town-visibility'){hostHidden.current=!!e.data.hidden;sync();return;}
  if(e.source!==frame.current?.contentWindow)return;
  if(e.data?.t==='room-town-call'){if(!isYardCareRequest(e.data))return;const source=e.source,result=await bridge.current.call(e.data.action,e.data.payload);if(source===frame.current?.contentWindow)source.postMessage({t:'room-town-reply',id:e.data.id,result},location.origin);return;}
  if(e.data?.t==='room-town-exit'){if(parent===window)window.pywebview?.api?.close_town?.();else parent.postMessage({t:'workstation-town-exit'},location.origin);return;}
  if(e.data?.t==='room-town-close')setView('alarm');
 }window.addEventListener('message',receive);document.addEventListener('visibilitychange',sync);return()=>{window.removeEventListener('message',receive);document.removeEventListener('visibilitychange',sync)};},[]);
 useEffect(()=>{frame.current?.contentWindow?.postMessage({t:'room-town-visibility',hidden:hidden||view!=='yard'},location.origin)},[hidden,view]);
 return <div style={{height:'100dvh'}}>{view==='yard'?<iframe ref={frame} title="小镇院落首页" src="./yard/index.html?host=workstation" onLoad={()=>frame.current?.contentWindow?.postMessage({t:'room-town-visibility',hidden},location.origin)} style={{width:'100%',height:'100%',border:0,display:'block'}}/>:<RoomTown view={view} hiddenByHost={hidden} onBack={()=>setView('yard')} onExit={()=>{setView('yard');parent.postMessage({t:'workstation-town-exit'},location.origin)}}/>}</div>;
}
