import {useEffect,useRef} from 'react';

export default function TownPortal({visible,onExit}){
 const frame=useRef(null);
 const nativeVisible=useRef(window.workstationRoomVisible!==false);
 const sync=()=>{
  const hidden=!visible||!nativeVisible.current||document.hidden;
  frame.current?.contentWindow?.postMessage({t:'workstation-town-visibility',hidden},location.origin);
 };
 useEffect(()=>{
  function nativeVisibility(event){
   if(typeof event.detail?.visible!=='boolean')return;
   nativeVisible.current=event.detail.visible;
   sync();
  }
  if(typeof window.workstationRoomVisible==='boolean')nativeVisible.current=window.workstationRoomVisible;
  sync();
  window.addEventListener('workstation-room-visibility',nativeVisibility);
  document.addEventListener('visibilitychange',sync);
  return ()=>{
   window.removeEventListener('workstation-room-visibility',nativeVisibility);
   document.removeEventListener('visibilitychange',sync);
  };
 },[visible]);
 useEffect(()=>{
  function receive(event){
   if(event.source===frame.current?.contentWindow&&event.origin===location.origin&&
      event.data?.t==='workstation-town-exit'&&visible)onExit?.();
  }
  window.addEventListener('message',receive);
  return ()=>window.removeEventListener('message',receive);
 },[visible,onExit]);
 return <iframe ref={frame} className="ws-town-frame" title="小镇与专注" src="./town/index.html?portal=1" onLoad={sync}/>;
}

