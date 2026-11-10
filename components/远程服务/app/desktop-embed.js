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
  if(event.source!==parent||!/^http:\/\/127\.0\.0\.1:\d{1,5}$/.test(event.origin)||event.data?.type!=='workstation-visual-theme'||!['light','dark'].includes(event.data.scheme))return;
  const dark=event.data.scheme==='dark',root=document.documentElement;
  const values={'--bg':dark?'#151c27':'#edf3f9','--panel':dark?'#1e2938':'#f4f8fd','--card':dark?'#1e2938':'#fbfdff','--line':dark?'#35445a':'#d4dfec','--line-soft':dark?'#35445a':'#d4dfec','--ink':dark?'#e6edf6':'#24354c','--muted':dark?'#a8bbcf':'#647a92','--faint':dark?'#92a6bd':'#7f93a8','--accent':'#5e9df6','--accent-strong':'#3f7fdf','--accent-soft':dark?'#243d61':'#e6f0fe','--accent-softer':dark?'#1e2938':'#f4f8fd','--danger':dark?'#f0a39d':'#ad332c'};
  for(const [key,value] of Object.entries(values))root.style.setProperty(key,value);
  root.dataset.workstationScheme=event.data.scheme;root.style.colorScheme=event.data.scheme;
  const scenery=event.data.scenery;
  if(scenery&&Number.isFinite(scenery.offset)&&scenery.offset>=0&&scenery.offset<=2000&&Number.isFinite(scenery.bottom)&&Math.abs(scenery.bottom)<=1000){
   root.style.setProperty('--joined-offset',scenery.offset+'px');root.style.setProperty('--joined-bottom',scenery.bottom+'px');root.dataset.workstationScenery='joined';
  }
 });
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
