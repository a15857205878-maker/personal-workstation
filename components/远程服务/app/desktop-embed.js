/* Loaded only for the paired workstation frame. No desktop bridge access. */
(()=>{
 'use strict';
 if(parent===window||new URLSearchParams(location.search).get('desktop_embed')!=='1')return;
 // Cosmetic-only messages from the owning loopback app; no commands/credentials.
 const themeStyle=document.createElement('style');
 themeStyle.textContent=`
 :root[data-workstation-scheme]{color:var(--ink)!important;background:var(--bg)!important}
 :root[data-workstation-scheme] body{color:var(--ink)!important;background:var(--bg)!important}
 :root[data-workstation-scheme] :is(section,.card,.panel,.message,.messages-card,dialog){background:var(--card)!important;color:var(--ink)!important;border-color:var(--line)!important}
 :root[data-workstation-scheme] :is(input,select,textarea,button,.message-list){background:var(--panel)!important;color:var(--ink)!important;border-color:var(--line)!important}
 :root[data-workstation-scheme] :is(button.primary,.tabs button[aria-selected=true]){background:var(--accent)!important;color:#fff!important}
 :root[data-workstation-scheme] :is(.muted,small,.message-head,.message-status,.message-hint){color:var(--muted)!important}
 :root[data-workstation-scheme] :is(.message-text,pre,h1,h2,h3){color:var(--ink)!important}
 :root[data-workstation-scheme] :is(a,.copy-message){color:var(--accent)!important}
 :root[data-workstation-scheme] button.danger{color:var(--danger)!important}
 `;
 // A single artwork coordinate system across the shell and this clipped viewport.
 themeStyle.textContent+=`
 :root[data-workstation-scenery=joined]{--joined-base:#e3ebf5;--joined-height:320px;--joined-size:560px;--joined-opacity:.82}
 :root[data-workstation-scenery=joined][data-workstation-scheme=dark]{--joined-base:#101721;--joined-height:250px;--joined-size:460px;--joined-opacity:.62}
 :root[data-workstation-scenery=joined] .app{position:relative;isolation:isolate;background:var(--joined-base)!important}
 :root[data-workstation-scenery=joined] .app::before{content:'';position:fixed;z-index:-1;pointer-events:none;left:calc(-1 * var(--joined-offset));right:0;bottom:calc(-1 * var(--joined-bottom));height:var(--joined-height);background:var(--partner-scenery) left bottom/auto var(--joined-size) no-repeat;mask-image:linear-gradient(transparent,#000 45%);opacity:var(--joined-opacity)}
 :root[data-workstation-scenery=joined] .app>.sidebar{background:transparent!important}
 :root[data-workstation-scenery=joined] .main::after{display:none!important}
 `;
 document.head.appendChild(themeStyle);
 window.addEventListener('message',event=>{
  const pairedMobile=event.origin===location.origin&&window.frameElement?.dataset.workstationSession==='1';
  if(event.source!==parent||!(/^http:\/\/127\.0\.0\.1:\d{1,5}$/.test(event.origin)||pairedMobile)||event.data?.type!=='workstation-visual-theme'||!['light','dark'].includes(event.data.scheme))return;
  const dark=event.data.scheme==='dark',root=document.documentElement;
  const values={'--bg':dark?'#151c27':'#edf3f9','--panel':dark?'#1e2938':'#f4f8fd','--card':dark?'#1e2938':'#fbfdff','--line':dark?'#35445a':'#d4dfec','--line-soft':dark?'#35445a':'#d4dfec','--ink':dark?'#e6edf6':'#24354c','--muted':dark?'#a8bbcf':'#647a92','--faint':dark?'#92a6bd':'#7f93a8','--accent':'#5e9df6','--accent-strong':'#3f7fdf','--accent-soft':dark?'#243d61':'#e6f0fe','--accent-softer':dark?'#1e2938':'#f4f8fd','--danger':dark?'#f0a39d':'#ad332c'};
  for(const [key,value] of Object.entries(values))root.style.setProperty(key,value);
  if(new URLSearchParams(location.search).get('single_simple')==='1'){
   const neutral={'--bg':dark?'#1b1e24':'#f4f5f7','--panel':dark?'#292e37':'#f5f6f8','--card':dark?'#23272f':'#ffffff','--line':dark?'#353b46':'#e0e3e8','--line-soft':dark?'#353b46':'#e0e3e8','--ink':dark?'#e5e8ee':'#252b35','--muted':dark?'#a0aab8':'#64707e','--faint':dark?'#8e99a9':'#77818f','--accent':dark?'#87a9e6':'#426ab3','--accent-strong':dark?'#a3bff1':'#365c9f','--accent-soft':dark?'#2d3d58':'#e8eef9','--accent-softer':dark?'#292e37':'#f5f6f8'};
   for(const [key,value] of Object.entries(neutral))root.style.setProperty(key,value);
  }
  root.dataset.workstationScheme=event.data.scheme;root.style.colorScheme=event.data.scheme;
  if(new URLSearchParams(location.search).get('single_simple')==='1'){
   const choice=['auto','coast','aurora','garden','observatory','none'].includes(event.data.chat_background)?event.data.chat_background:'auto';
   const strength=Number.isInteger(event.data.background_strength)&&event.data.background_strength>=0&&event.data.background_strength<=60?event.data.background_strength:35;
   const scene=choice==='auto'?(dark?'aurora':'coast'):choice;
   root.dataset.chatBackground=choice;root.dataset.backgroundStrength=String(strength);
   root.style.setProperty('--single-bg-image',scene==='none'?'none':`var(--partner-${scene})`);
   root.style.setProperty('--single-bg-opacity',String(strength/100));
   root.style.setProperty('--single-bg-rgb',dark?'27 30 36':'244 245 247');
  }
  const scenery=event.data.skin==='messenger'?null:event.data.scenery;
  if(event.data.skin==='messenger')delete root.dataset.workstationScenery;
  if(scenery&&Number.isFinite(scenery.offset)&&scenery.offset>=0&&scenery.offset<=2000&&Number.isFinite(scenery.bottom)&&Math.abs(scenery.bottom)<=1000){
   root.style.setProperty('--joined-offset',scenery.offset+'px');root.style.setProperty('--joined-bottom',scenery.bottom+'px');root.dataset.workstationScenery='joined';
  }
 });
 if(new URLSearchParams(location.search).get('single_simple')==='1'){
  const style=document.createElement('style');style.textContent=`
  :root[data-workstation-messenger]{--single-history-width:248px;--partner-bg:#f4f5f7!important;--partner-panel:#f5f6f8!important;--partner-card:#ffffff!important;--partner-line:#e0e3e8!important;--partner-ink:#252b35!important;--partner-muted:#64707e!important;--partner-accent:#426ab3!important;--partner-soft:#e8eef9!important}
  html[data-workstation-messenger] body,html[data-workstation-messenger] :is(button,input,select,textarea,p,h1,h2,h3){font-family:'Microsoft YaHei','Microsoft YaHei UI','Segoe UI',sans-serif!important}
  html[data-workstation-messenger] .app{grid-template-columns:var(--single-history-width) 6px minmax(0,1fr)!important;background:var(--bg)!important}
  html[data-workstation-messenger] .app::before,html[data-workstation-messenger] .sidebar::before,html[data-workstation-messenger] .main::after,html[data-workstation-messenger] .composer::before{display:none!important}
  html[data-workstation-messenger] .sidebar{grid-column:1;padding:14px 12px;background:var(--panel)!important;border:0;gap:10px}
  html[data-workstation-messenger] .sidebar .brand,html[data-workstation-messenger] .side-section-label,html[data-workstation-messenger] .side-foot{display:none!important}
  html[data-workstation-messenger] .side-head{gap:10px;align-items:stretch}
  html[data-workstation-messenger] .side-head-actions{width:100%;justify-content:space-between}
  html[data-workstation-messenger] .new-btn{width:100%;min-height:36px;font-size:13px;border-radius:7px;background:var(--card)!important;color:var(--ink)!important;border:1px solid var(--line)!important;box-shadow:none}
  html[data-workstation-messenger] .single-model-choice{padding:0;font-size:12px;gap:6px}
  html[data-workstation-messenger] .single-history-label{font-size:12px;color:var(--muted);font-weight:500;margin:8px 0 0}
  html[data-workstation-messenger] .main{position:relative;isolation:isolate;grid-column:3;background:var(--bg)!important}
  html[data-workstation-messenger] .main::before{display:none!important}
  html[data-workstation-messenger] .topbar{min-height:68px;padding:12px 20px;background:transparent!important;backdrop-filter:none;box-shadow:none}
  html[data-workstation-messenger] .topbar h1{font-size:15px;letter-spacing:normal;font-weight:600}
  html[data-workstation-messenger] .meta{font-size:12px}
  html[data-workstation-messenger] .partner-theme-toggle{display:none!important}
  html[data-workstation-messenger] .conversation{padding:18px 24px;scrollbar-width:thin;background:transparent!important}
  html[data-workstation-messenger] .empty-state{background:transparent!important}
  html:root[data-workstation-messenger] :is(.conversation,.empty-state){background-image:linear-gradient(rgb(var(--single-bg-rgb,244 245 247) / calc(1 - var(--single-bg-opacity,.35))),rgb(var(--single-bg-rgb,244 245 247) / calc(1 - var(--single-bg-opacity,.35)))),var(--single-bg-image,var(--partner-scenery))!important;background-size:cover!important;background-position:center center!important}
  html:root[data-workstation-messenger][data-chat-background=coast] :is(.conversation,.empty-state),html:root[data-workstation-messenger][data-chat-background=auto][data-workstation-scheme=light] :is(.conversation,.empty-state){background-position:center bottom!important}
  html:root[data-workstation-messenger]:is([data-chat-background=garden],[data-chat-background=observatory]) :is(.conversation,.empty-state){background-position:85% bottom!important}
  @media(max-width:600px){html:root[data-workstation-messenger][data-chat-background=coast] :is(.conversation,.empty-state),html:root[data-workstation-messenger][data-chat-background=auto][data-workstation-scheme=light] :is(.conversation,.empty-state){background-position:85% bottom!important}}
  html[data-workstation-messenger] .new-hint{padding:16px;border-radius:10px;margin-bottom:16px}
  html[data-workstation-messenger] .new-hint h2{font-size:16px}
  html[data-workstation-messenger] .new-hint p{font-size:12px;line-height:1.7}
  html[data-workstation-messenger] .partner-template-grid{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 0}
  html[data-workstation-messenger] .partner-template-grid button{display:flex;align-items:center;gap:6px;min-height:36px;font-size:12px;padding:7px 12px!important;border-radius:7px}
  html[data-workstation-messenger] .partner-template-grid button:before{width:18px;height:18px;margin:0}
  html[data-workstation-messenger] .new-mark{width:30px;height:30px;border-radius:8px}
  html[data-workstation-messenger] .new-hint-tip{margin-top:6px}
  html[data-workstation-messenger] .conversation-inner,html[data-workstation-messenger] .composer-inner{max-width:none}
  html[data-workstation-messenger] .conv-item{border:0;border-radius:8px;box-shadow:none;padding:12px 10px}
  html[data-workstation-messenger] .conv-item[aria-current=true]{background:var(--accent-soft)!important;box-shadow:none;border:0}
  html[data-workstation-messenger] .msg-bubble{border:1px solid var(--line)!important;border-radius:3px 12px 12px 12px!important;background:var(--card)!important;box-shadow:none!important;padding:10px 14px}
  html[data-workstation-messenger] .msg.user .msg-bubble{background:var(--accent-soft)!important;border:0!important;border-radius:12px 3px 12px 12px!important}
  html[data-workstation-messenger] .msg-text{font-size:14px;line-height:1.75}
  html[data-workstation-messenger] .msg-head{font-size:12px;color:var(--muted)}
  html[data-workstation-messenger] .composer{padding:10px 22px 14px;background:var(--card)!important;border-top:0;backdrop-filter:none;max-height:52%;overflow:auto}
  html[data-workstation-messenger] .composer-box{border:0!important;box-shadow:none!important;padding:0;border-radius:0;background:var(--card)!important}
  html[data-workstation-messenger] #composerInput{background:var(--card)!important;color:var(--ink)!important;border:0;border-radius:0;padding:6px 0;min-height:60px;resize:none;font-size:14px;line-height:1.7}
  html[data-workstation-messenger][data-single-manual-input=true] #composerInput{height:var(--single-input-height)!important;min-height:48px!important;max-height:none!important}
  html[data-workstation-messenger] #sendButton{border-radius:7px;box-shadow:none;background:var(--accent)!important;color:var(--single-on-accent,#fff)!important;min-width:74px}
  html[data-workstation-messenger][data-workstation-scheme=dark]{--single-on-accent:#182238;--partner-bg:#1b1e24!important;--partner-panel:#292e37!important;--partner-card:#23272f!important;--partner-line:#353b46!important;--partner-ink:#e5e8ee!important;--partner-muted:#a0aab8!important;--partner-accent:#87a9e6!important;--partner-soft:#2d3d58!important}
  html[data-workstation-messenger] .single-resize{position:relative;z-index:2;flex:none;touch-action:none;user-select:none}
  html[data-workstation-messenger] .single-resize:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
  html[data-workstation-messenger] #singleHistoryResize{grid-column:2;cursor:col-resize;background:var(--panel);border-right:1px solid var(--line)}
  html[data-workstation-messenger] #singleHistoryResize::after{content:'';position:absolute;width:3px;height:36px;left:1px;top:calc(50% - 18px);border-radius:4px;background:var(--line)}
  html[data-workstation-messenger] #singleInputResize{height:10px;cursor:row-resize;background:var(--card);border-top:1px solid var(--line)}
  html[data-workstation-messenger] #singleInputResize::after{content:'';position:absolute;width:34px;height:3px;left:calc(50% - 17px);top:3px;border-radius:4px;background:var(--line)}
  html[data-workstation-messenger] #singleInputResize:has(+ #composer[hidden]){display:none}
  html[data-workstation-messenger] .single-resize:hover::after{background:var(--accent)!important}
  html[data-workstation-messenger] .single-message-enter{animation:single-bubble-in .2s ease-out both}
  @keyframes single-bubble-in{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}
  @media(max-width:760px){html[data-workstation-messenger] .app{grid-template-columns:minmax(0,1fr)!important}html[data-workstation-messenger] #singleHistoryResize{display:none}html[data-workstation-messenger] .main{grid-column:1}html[data-workstation-messenger] .sidebar{width:min(86vw,340px)}html[data-workstation-messenger] .sidebar .sidebar-close{display:inline-grid}html[data-workstation-messenger] .conversation{padding:12px}html[data-workstation-messenger] .composer{padding:8px 12px}html[data-workstation-messenger] #composerInput{font-size:16px}html[data-workstation-messenger] .topbar{padding:8px 12px;min-height:58px}}
  html[data-workstation-history-host] .app{grid-template-columns:minmax(0,1fr)!important}
  html[data-workstation-history-host] :is(.sidebar,#singleHistoryResize,#drawerButton,#emptyPick){display:none!important}
  html[data-workstation-history-host] .main{grid-column:1}
  html[data-workstation-history-host] .topbar{min-height:62px;padding:8px 16px;border-bottom:1px solid var(--line);background:var(--card)!important}
  html[data-workstation-history-host] #statusPanel:has(.status-line):not(:has(.wait-summary,.notice,.error-box,.status-line .status-hint)){display:none}
  @media(pointer:coarse){html[data-workstation-messenger] #singleInputResize{height:18px}}
  @media(prefers-reduced-motion:reduce){html[data-workstation-messenger] .single-message-enter{animation:none!important}}
  `;document.head.append(style);
  function mountSingle(){
   const d=document,app=d.getElementById('app'),main=d.querySelector('.main'),sidebar=d.getElementById('sidebar'),composer=d.getElementById('composer'),input=d.getElementById('composerInput');
   if(!app||!main||!sidebar||!composer||!input||d.getElementById('singleHistoryResize'))return;
   d.documentElement.dataset.workstationMessenger='true';
   let width=248,height=72;
   const widthFor=v=>Math.round(Math.max(180,Math.min(360,Math.max(180,(app.clientWidth||1000)-340),v)));
   const heightFor=v=>Math.round(Math.max(48,Math.min(300,Math.max(48,Math.floor((main.clientHeight||800)*.36)),v)));
   function applyWidth(v){width=widthFor(v);d.documentElement.style.setProperty('--single-history-width',width+'px');vertical.setAttribute('aria-valuenow',width);vertical.setAttribute('aria-valuemax',widthFor(360));}
   function fitHeight(){const visible=heightFor(height);d.documentElement.style.setProperty('--single-input-height',visible+'px');horizontal.setAttribute('aria-valuenow',visible);horizontal.setAttribute('aria-valuemax',heightFor(300));}
   function applyHeight(v){height=heightFor(v);d.documentElement.dataset.singleManualInput='true';fitHeight();}
   function separator(id,axis,label){const node=d.createElement('div');node.id=id;node.className='single-resize';node.tabIndex=0;node.setAttribute('role','separator');node.setAttribute('aria-label',label);node.setAttribute('aria-orientation',axis==='width'?'vertical':'horizontal');node.setAttribute('aria-valuemin',axis==='width'?'180':'48');node.title='拖动调整；方向键微调；双击或 Home 恢复';let drag=null;
    const coordinate=e=>axis==='width'?e.clientX:e.clientY,change=axis==='width'?applyWidth:applyHeight,reset=()=>change(axis==='width'?248:72);
    node.addEventListener('pointerdown',e=>{if(e.button!==0)return;drag={position:coordinate(e),value:axis==='width'?width:height};node.setPointerCapture(e.pointerId);e.preventDefault();});
    node.addEventListener('pointermove',e=>{if(drag)change(drag.value+(coordinate(e)-drag.position)*(axis==='width'?1:-1));});
    const stop=e=>{drag=null;if(node.hasPointerCapture(e.pointerId))node.releasePointerCapture(e.pointerId);};node.addEventListener('pointerup',stop);node.addEventListener('pointercancel',stop);node.addEventListener('lostpointercapture',()=>{drag=null;});node.addEventListener('dblclick',reset);
    node.addEventListener('keydown',e=>{const keys=axis==='width'?{ArrowLeft:-16,ArrowRight:16}:{ArrowUp:16,ArrowDown:-16};if(e.key in keys){e.preventDefault();change((axis==='width'?width:height)+keys[e.key]);}else if(e.key==='Home'){e.preventDefault();reset();}});return node;
   }
   const vertical=separator('singleHistoryResize','width','调整单模型会话列表宽度'),horizontal=separator('singleInputResize','height','调整单模型聊天与输入区大小');sidebar.after(vertical);composer.before(horizontal);applyWidth(width);horizontal.setAttribute('aria-valuenow',height);horizontal.setAttribute('aria-valuemax',heightFor(300));
   const observer=new ResizeObserver(()=>{if(app.clientWidth>0&&main.clientHeight>0){applyWidth(width);if(d.documentElement.dataset.singleManualInput==='true')fitHeight();else horizontal.setAttribute('aria-valuemax',heightFor(300));}});const observe=()=>{observer.observe(app);observer.observe(main);};observe();window.addEventListener('pageshow',observe);window.addEventListener('pagehide',()=>observer.disconnect());
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mountSingle,{once:true});else mountSingle();
 }

 const send=value=>parent.postMessage({type:'remote-workstation-navigation',...value},'*');
 function route(value){
  let url;try{url=new URL(value,location.href);}catch{return false;}
  if(url.origin!==location.origin)return false;
  const pages={'/':'sessions','/bot':'sessions','/sessions':'sessions','/workbench':'sessions','/collaboration':'collaboration','/transfer':'transfer'};
  if(pages[url.pathname]){send({page:pages[url.pathname]});return true;}
  if(['/preview-viewer','/file-viewer'].includes(url.pathname)){send({preview:url.href});return true;}
  return false;
 }
 document.addEventListener('click',event=>{
  const anchor=event.target.closest?.('a[href]');
  if(anchor&&route(anchor.href)){event.preventDefault();event.stopImmediatePropagation();}
  else if(anchor){
   try{const url=new URL(anchor.href,location.href);
    if(url.origin===location.origin&&(/^\/(?:artifact|input|file)\//.test(url.pathname)||url.pathname.startsWith('/api/bot/reply-input/')||url.pathname==='/api/workbench-artifact')){
     anchor.target='_self';anchor.download='';
    }
   }catch{}
  }
 },true);
 // The existing PDF flow reserves a blank popup before asynchronous generation.
 // Give it a location setter that opens the host's preview pane instead.
 window.open=value=>{
  if(value&&value!=='about:blank'){route(value);return null;}
  let closed=false;
  return {get closed(){return closed;},close(){closed=true;},location:{set href(href){
   if(!route(href))throw Error('不支持的窗口内预览地址');
  }}};
 };
})();
