export function preferenceWriter(send,onError=()=>{}){
 let tail=Promise.resolve(),key=null;
 return {
  markSaved(value){key=JSON.stringify(value);},
  save(value){
   const snapshot={...value},next=JSON.stringify(snapshot);if(next===key)return tail;key=next;
   const request=tail.then(()=>send(snapshot));
   tail=request.catch(error=>{if(key===next)key=null;onError(error);});return tail;
  }
 };
}
export function whenBridgeReady(root,load){
 if(root.pywebview?.api?.call){load();return()=>{};}
 root.addEventListener('pywebviewready',load,{once:true});
 return()=>root.removeEventListener('pywebviewready',load);
}
