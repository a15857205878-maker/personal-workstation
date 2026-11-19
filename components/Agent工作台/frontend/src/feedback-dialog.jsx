import React,{useCallback,useId,useLayoutEffect,useRef,useState} from 'react';

export function useFeedbackDismiss(dialog){
 const pending=useRef(null);
 useLayoutEffect(()=>()=>{pending.current=null;},[]);
 return useCallback((afterClose)=>{
  const panel=dialog.current;
  if(!panel?.open||pending.current)return;
  const request={};
  pending.current=request;
  function finish(){
   if(pending.current!==request)return;
   pending.current=null;
   panel.close();
   delete panel.dataset.closing;
   afterClose?.();
  }
  panel.dataset.closing='';
  const exit=panel.getAnimations().find(animation=>animation.animationName==='feedback-panel-out');
  if(exit)exit.finished.then(finish,finish);
  else finish();
 },[dialog]);
}

export function PreviewDialog({title,description,opener,frameTitle,onClose,src,srcDoc,sandbox='',controls,actions,status,children,frameKey}){
 const heading=useId(),detail=useId(),panel=useRef(null),closeButton=useRef(null);
 const dismiss=useFeedbackDismiss(panel);
 const [loaded,setLoaded]=useState(null);
 const frame=src??srcDoc;
 useLayoutEffect(()=>{
  const dialog=panel.current;
  dialog.showModal();
  closeButton.current.focus({preventScroll:true});
  return ()=>{
   if(dialog.open)dialog.close();
   if(opener?.isConnected&&opener.getClientRects().length)opener.focus({preventScroll:true});
  };
 },[opener]);
 function close(){dismiss(onClose);}
 return <dialog ref={panel} data-feedback-dialog className="feedback-preview" aria-labelledby={heading}
  aria-describedby={description?detail:undefined} onCancel={event=>{event.preventDefault();close();}}
  onClick={event=>{if(event.target===event.currentTarget)close();}}>
  <div className="feedback-preview-content">
   <header><h2 id={heading}>{title}</h2><button ref={closeButton} className="station-button" type="button" onClick={close}>关闭预览</button></header>
   {description&&<p className="feedback-preview-description" id={detail}>{description}</p>}
   {controls}
   {frame!==undefined?<iframe key={frameKey} title={frameTitle} sandbox={sandbox} src={src} srcDoc={srcDoc} referrerPolicy="no-referrer" onLoad={()=>setLoaded({frame,frameKey})}/>:children}
   <footer>{status??(frame!==undefined&&<span className="feedback-status" data-tone={loaded?.frame===frame&&loaded?.frameKey===frameKey?(srcDoc!==undefined?'ready':'neutral'):'working'} role="status">{loaded?.frame===frame&&loaded?.frameKey===frameKey?(srcDoc!==undefined?'隔离预览已就绪':'文件预览'):'正在打开预览…'}</span>)}{actions?.(dismiss)}</footer>
  </div>
 </dialog>;
}
