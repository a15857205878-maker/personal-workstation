(function(root){
'use strict';
function collaborationGoal(text){if(typeof text!=='string')return null;const match=text.trim().match(/^(?:(?:请)?(?:用|使用)|我(?:想)?要(?:用)?)双模型(?:协作)?[：:\s,，]*([\s\S]*)$/)||text.trim().match(/^双模型(?:协作)?(?:[：:\s,，]+|$)([\s\S]*)$/);return match?match[1].trim():null;}
function mount(){let parent;try{if(root.parent===root||root.parent.location.origin!==root.location.origin||root.frameElement?.dataset.workstationSession!=='1')return;parent=root.parent;}catch(e){return;}
 const doc=root.document,input=doc.getElementById('composerInput'),form=doc.getElementById('composer'),models=doc.getElementById('sessionModels'),status=doc.getElementById('composerStatus');if(!input||!form||!models)return;
 const button=doc.createElement('button');button.id='sessionCollaboration';button.type='button';button.textContent='双模型';button.title='设置双模型协作，确认后执行';models.append(button);
 function prepare(text){const sourceText=input.value,tray=doc.getElementById('attachmentTray'),hasAttachments=!!tray&&!tray.hidden&&tray.childElementCount>0;if(hasAttachments||text.length>8000||sourceText.length>20000){if(status)status.textContent=hasAttachments?'请先处理会话附件；双模型不会自动带入这些附件。':'双模型目标最多8000字，请先缩短内容。';return;}parent.postMessage({type:'workstation-session-collaboration',text,sourceText,hasAttachments},location.origin);}
 button.onclick=()=>prepare(collaborationGoal(input.value)??input.value.trim());
 form.addEventListener('submit',event=>{const text=collaborationGoal(input.value);if(text===null)return;event.preventDefault();event.stopImmediatePropagation();prepare(text);},true);
 root.addEventListener('message',event=>{const data=event.data;if(event.origin!==location.origin||event.source!==parent||data?.type!=='workstation-session-collaboration-result')return;if(status&&typeof data.message==='string')status.textContent=data.message;if(data.status==='accepted'&&typeof data.sourceText==='string'&&input.value===data.sourceText){input.value='';input.dispatchEvent(new Event('input',{bubbles:true}));}});
}
if(typeof module!=='undefined'&&module.exports)module.exports={collaborationGoal};else mount();
})(typeof window!=='undefined'?window:globalThis);
