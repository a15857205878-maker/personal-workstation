/* Paired visual projection only. No model/settings mutations. */
(function(root){'use strict';
const defaults={color_scheme:'light',chat_background:'auto',background_strength:35};
function normalize(v={}){return {color_scheme:['light','dark'].includes(v?.color_scheme)?v.color_scheme:'light',chat_background:['auto','coast','aurora','garden','observatory','none'].includes(v?.chat_background)?v.chat_background:'auto',background_strength:Number.isInteger(v?.background_strength)&&v.background_strength>=0&&v.background_strength<=60?v.background_strength:35};}
function view(value,override){const v=normalize(value),scheme=['light','dark'].includes(override)?override:v.color_scheme;return {scheme,scene:v.chat_background==='auto'?(scheme==='dark'?'aurora':'coast'):v.chat_background,strength:v.background_strength};}
if(typeof module!=='undefined'&&module.exports){module.exports={normalize,view};return;}
const query=new URLSearchParams(root.location.search);if(query.get('desktop_embed')==='1')return;
function mount(){const d=root.document;if(!d.getElementById('partner-app')&&!d.querySelector('.mobile-controller'))return;
 const embedded=query.get('mobile_embed')==='1'&&root.parent!==root;
 let preference=defaults,override=null,polling=false,active=true,activeController=null;const token=query.get('token');
 function refreshFrames(){const v=view(preference,override);for(const f of d.querySelectorAll('iframe[data-workstation-session],iframe[data-workstation-group]')){try{f.contentWindow.postMessage({type:'workstation-visual-theme',skin:'messenger',scheme:v.scheme,chat_background:preference.chat_background,background_strength:v.strength},root.location.origin);}catch{}}}
 function apply(){const v=view(preference,override),html=d.documentElement;html.dataset.mobileMessenger='true';html.dataset.scheme=v.scheme;html.dataset.mobileScene=v.scene;html.style.colorScheme=v.scheme;
  root.WorkstationPartnerTheme?.apply(v.scheme);
  html.style.setProperty('--mm-image',v.scene==='none'?'none':`var(--partner-${v.scene})`);html.style.setProperty('--mm-opacity',String(v.strength/100));
  const status=d.getElementById('mobile-visual-status');if(status)status.textContent=(override?'本机临时主题':'跟随电脑主题')+' · 背景强度 '+v.strength+'%';refreshFrames();
 }
 function receive(v){if(v&&typeof v==='object'){preference=normalize(v);apply();}}
 function toggle(){override=view(preference,override).scheme==='dark'?'light':'dark';apply();}
 function follow(){override=null;apply();sync();}
 root.WorkstationMobileVisual={receive,toggle,follow,refreshFrames};
 const section=d.getElementById('partner-app')||d.querySelector('.mobile-controller main');
 const menu=d.createElement('details');menu.className='mobile-visual-menu';const summary=d.createElement('summary');summary.textContent='外观';menu.append(summary);
 const status=d.createElement('small');status.id='mobile-visual-status';menu.append(status);
 const hint=d.createElement('p');hint.textContent='背景在电脑“设置 → 聊天背景”中选择，约15秒内同步。';menu.append(hint);
 const theme=d.createElement('button');theme.type='button';theme.textContent='临时切换深浅';theme.onclick=toggle;menu.append(theme);
 const followButton=d.createElement('button');followButton.type='button';followButton.id='follow-desktop-appearance';followButton.textContent='跟随电脑外观';followButton.onclick=follow;menu.append(followButton);
 if(!embedded&&d.getElementById('mcSettings'))d.getElementById('mcSettings').prepend(menu);else if(section&&!embedded){const anchor=d.querySelector('.partner-tools')||d.querySelector('.mc-top');if(anchor)anchor.after(menu);else section.prepend(menu);}
 const members=d.getElementById('members');if(members&&!members.closest('details')){const box=d.createElement('details');box.className='mobile-member-details';const title=d.createElement('summary');title.textContent='成员资料';box.append(title);members.before(box);box.append(members);}
 const input=d.getElementById('input');if(input){let height=72,drag=null;const handle=d.createElement('div');handle.id='mobile-input-resize';handle.className='mobile-input-resize';handle.tabIndex=0;handle.setAttribute('role','separator');handle.setAttribute('aria-label','调整消息与输入区大小');handle.setAttribute('aria-orientation','horizontal');handle.setAttribute('aria-valuemin','48');handle.title='上下拖动调整；双击恢复';
  const limit=()=>Math.floor(Math.min(220,Math.max(48,root.innerHeight*.28)));
  function fit(){const visible=Math.min(height,limit());input.style.setProperty('height',visible+'px','important');handle.setAttribute('aria-valuenow',visible);handle.setAttribute('aria-valuemax',limit());}
  function size(value){height=Math.round(Math.max(48,Math.min(limit(),value)));fit();}
  input.before(handle);fit();handle.onpointerdown=e=>{if(e.button!==0)return;drag={y:e.clientY,height:input.offsetHeight};handle.setPointerCapture(e.pointerId);e.preventDefault();};handle.onpointermove=e=>{if(drag)size(drag.height-(e.clientY-drag.y));};const stop=e=>{drag=null;if(handle.hasPointerCapture(e.pointerId))handle.releasePointerCapture(e.pointerId);};handle.onpointerup=stop;handle.onpointercancel=stop;handle.onlostpointercapture=()=>{drag=null;};handle.ondblclick=()=>size(72);handle.onkeydown=e=>{if(['ArrowUp','ArrowDown','Home'].includes(e.key)){e.preventDefault();size(e.key==='Home'?72:input.offsetHeight+(e.key==='ArrowUp'?16:-16));}};root.addEventListener('resize',fit);
 }
 async function sync(){if(polling||!active||!token||d.hidden)return;polling=true;const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),8000);activeController=controller;
  try{const r=await root.fetch('/api/workbench?token='+encodeURIComponent(token),{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'center_bootstrap',payload:{}}),signal:controller.signal});const value=await r.json();if(active&&r.ok&&value.ok&&value.data?.appearance)receive(value.data.appearance);}
  catch{/* Chat retains its independent errors and draft; keep last good appearance. */}finally{clearTimeout(timer);if(activeController===controller)activeController=null;polling=false;}
 }
 apply();if(embedded){root.addEventListener('message',event=>{try{if(event.source!==root.parent||event.origin!==root.location.origin||root.frameElement?.dataset.workstationGroup!=='1'||event.data?.type!=='workstation-visual-theme'||!['light','dark'].includes(event.data.scheme))return;receive({color_scheme:event.data.scheme,chat_background:event.data.chat_background,background_strength:event.data.background_strength});}catch{}});return;}let timer=null;const visible=()=>{if(!d.hidden)sync();},start=()=>{active=true;if(timer===null)timer=setInterval(sync,15000);d.addEventListener('visibilitychange',visible);sync();},stop=()=>{active=false;if(timer!==null)clearInterval(timer);timer=null;activeController?.abort();d.removeEventListener('visibilitychange',visible);};start();root.addEventListener('pagehide',stop);root.addEventListener('pageshow',start);
}
if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})(typeof window!=='undefined'?window:globalThis);
