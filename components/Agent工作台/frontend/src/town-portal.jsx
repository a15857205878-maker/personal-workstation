import {useEffect,useRef} from 'react';
export default function TownPortal({visible,onExit}){
 const frame=useRef(null);
 const sync=()=>frame.current?.contentWindow?.postMessage({t:'workstation-town-visibility',hidden:!visible},location.origin);
 useEffect(sync,[visible]);
 useEffect(()=>{function receive(e){if(e.source===frame.current?.contentWindow&&e.origin===location.origin&&e.data?.t==='workstation-town-exit'&&visible)onExit?.();}window.addEventListener('message',receive);return()=>window.removeEventListener('message',receive)},[visible,onExit]);
 return <iframe ref={frame} className="ws-town-frame" title="小镇与专注" src="./town/index.html?portal=1" onLoad={sync}/>;
}
