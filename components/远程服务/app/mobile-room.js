(function(root){
 'use strict';
 const countKeys=['tasks','collaborations','active','attention'];
 function roomState(value,now=Date.now(),failed=false){
  const at=Number(value?.observed_at)*1000,c=value?.counts;
  const fresh=value?.observed_at!=null&&Number.isFinite(at)&&now-at>=-5000&&now-at<=15000;
  if(failed||value?.version!==1||value?.overview_state!=='ready'||!fresh||!countKeys.every(k=>Number.isInteger(c?.[k])&&c[k]>=0&&c[k]<=200))return {kind:'unknown',label:failed?'连接中断':'状态未知',hint:failed?'保留上次摘要，当前状态未确认。':'摘要不可用或已过期，请重新读取。'};
  if(c.attention>0)return {kind:'attention',label:'需要处理',hint:`${c.attention} 项工作需要关注。`};
  if(c.active>0)return {kind:'working',label:'正在工作',hint:`${c.active} 项任务或协作进行中。`};
  const done=Number(value.recent_completed_at)*1000;
  if(value.recent_completed_at!=null&&Number.isFinite(done)&&now-done>=-5000&&now-done<60000)return {kind:'done',label:'最近有工作完成',hint:'可前往成果查看实际结果。'};
  return {kind:'idle',label:'当前无进行中任务',hint:'角色活动与电脑任务状态分别显示。'};
 }
 const scenes={room:'小屋',home:'庭院',plaza:'广场',orchard:'果园',desktop:'桌面'};
 const poses={back:'背身停留',turn:'回头',relax:'放松',rest:'休息',front:'正面停留',sit:'坐在长椅上'};
 function activityState(value,now=Date.now(),failed=false){
  const at=Number(value?.observed_at)*1000;
  if(failed||value?.available!==true||typeof value.observed_at!=='number'||!Number.isFinite(at)||now-at < -5000||now-at>15000||!Object.hasOwn(scenes,value.scene)||!Object.hasOwn(poses,value.pose)||!['night','automatic','held'].every(k=>typeof value[k]==='boolean')||!['stable','switching','paused'].includes(value.phase)||typeof value.changed_at!=='number'||!Number.isFinite(value.changed_at))return {kind:'unknown',label:'活动状态未知'};
  const mode=value.held?'固定场景':value.phase==='paused'?'暂停':value.automatic?'自动活动':'当前活动';
  return {...value,kind:'known',mode,label:`${scenes[value.scene]} · ${poses[value.pose]} · ${mode}${value.phase==='switching'?' · 正在切换':''} · ${value.night?'夜间':'白天'}`};
 }
 function acceptObservation(last,next){
  if(!last)return true;
  if(typeof last.observed_at==='number'&&typeof next?.observed_at==='number'&&next.observed_at<last.observed_at)return false;
  const before=last.pet_activity?.observed_at,after=next?.pet_activity?.observed_at;
  return !(next?.pet_activity?.available===true&&typeof before==='number'&&typeof after==='number'&&after<before);
 }
 function activityVisual(state,assets){return state.kind==='known'?assets[state.scene+'.'+state.pose]||null:null;}
 function activityNarrative(state){
  if(state.kind!=='known')return '当前活动未知';
  if(state.scene==='desktop')return '她回到桌面陪你了。';
  if(state.phase==='switching')return `正在${scenes[state.scene]}附近换个地方。`;
  if(state.scene==='room')return ({back:'她正在小屋的书桌前待着。',turn:'她在小屋里回头看了看。',relax:'她靠在小屋的扶手椅上放松。',rest:'她正在小屋里闭目休息。'})[state.pose]||'她正在小屋里待着。';
  const place=scenes[state.scene];return state.pose==='sit'?`她在${place}的长椅上歇一会儿。`:state.pose==='back'?`她背对着这边，在${place}停留。`:`她站在${place}，面朝这边。`;
 }
 const bundledAssets=(typeof module!=='undefined'&&module.exports)?{}:JSON.parse('__PET_ACTIVITY_ASSETS__');
 function shouldRead(open,visible,view){return !!open&&visible==='visible'&&view==='connection';}
 function mount(host,{token,fetcher=root.fetch.bind(root),preview='__ROOM_PREVIEW_DATA__',activityAssets=bundledAssets}={}){
  const d=host.ownerDocument,el=(tag,text,cls)=>{const n=d.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;};
  const card=el('details',null,'mobile-room-card');card.id='mcRoomOverview';
  const summary=el('summary','伙伴观察窗'),title=el('p','等待电脑连接','mobile-room-caption');
  const img=el('img');img.src=preview;img.alt='桌宠小屋的固定视角静态预览';img.width=820;img.height=590;img.loading='lazy';
  const picture=el('div',null,'mobile-room-picture'),previousImage=el('img');previousImage.alt='';previousImage.setAttribute('aria-hidden','true');previousImage.className='mobile-room-previous';previousImage.style.opacity='0';picture.append(img,previousImage);
  const activity=el('p','活动状态未知','mobile-room-activity');activity.setAttribute('role','status');
  const activityTime=el('p','活动更新时间：尚未读取','mobile-room-time');
  const explanation=el('p','跟随电脑上的真实场景与姿态，约每5秒同步；这里是状态示意，不是屏幕直播。','mobile-room-scope');
  const status=el('p','尚未读取','mobile-room-state');status.setAttribute('role','status');
  const hint=el('p','展开后读取电脑工作概况。','mobile-room-hint'),counts=el('p',null,'mobile-room-counts'),time=el('p','更新时间：尚未读取','mobile-room-time');
  const scope=el('p','仅汇总最近100个未归档任务与最近100个协作记录，不包含任务正文。','mobile-room-scope');
  const actions=el('div',null,'mobile-room-actions'),refresh=el('button','刷新概况'),results=el('button','查看任务与成果');refresh.type=results.type='button';actions.append(refresh,results);
  const about=el('details',null,'mobile-room-about');about.append(el('summary','同步说明'),explanation,scope);
  const work=el('details',null,'mobile-room-about');work.append(el('summary','电脑工作概况'),status,hint,counts,time);
  card.append(summary,picture,title,activity,activityTime,actions,work,about);host.insertBefore(card,host.children[1]||null);
  let last=null,lastKnownActivity=null,error='',inflight=null,generation=0,active=false,timer=null,disposed=false,imageEpoch=0,desiredImage=preview,hasActivityImage=false,fadeTimer=null;
  function showImage(source){
   if(source===desiredImage)return;desiredImage=source;const epoch=++imageEpoch;
   const promote=()=>{
    if(disposed||epoch!==imageEpoch)return;
    root.clearTimeout(fadeTimer);const moving=active&&!root.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    previousImage.src=img.src;previousImage.style.transition='none';previousImage.style.opacity=moving?'1':'0';
    img.style.transition='none';img.style.opacity=moving?'0':'1';img.src=source;
    void picture.offsetWidth;
    img.style.transition='';previousImage.style.transition='';img.style.opacity='1';previousImage.style.opacity='0';
    fadeTimer=root.setTimeout(()=>{previousImage.removeAttribute('src')},moving?360:0);
   };
   const next=new root.Image();next.onload=promote;next.onerror=()=>{if(epoch===imageEpoch){desiredImage=img.getAttribute('src');title.textContent='画面暂未载入，保留上一幅。'}};next.src=source;
  }
  function render(){
   const a=activityState(last?.pet_activity,Date.now(),!!error),visual=activityVisual(a,activityAssets);
   const previous=activityState(lastKnownActivity,(lastKnownActivity?.observed_at||0)*1000);
   const narrative=activityNarrative(a)+(a.kind==='unknown'&&previous.kind==='known'?' · 上次：'+activityNarrative(previous):'');if(activity.textContent!==narrative)activity.textContent=narrative;activity.dataset.state=a.kind;
   const old=a.kind==='unknown'?(lastKnownActivity||last?.pet_activity):last?.pet_activity,atActivity=old?.observed_at;
   activityTime.textContent=a.kind==='unknown'?'同步已暂停 · '+(old?'保留上次画面和时间':'等待电脑连接'):a.held?'固定在这里 · 刚刚同步':a.phase==='paused'?'电脑暂时暂停活动 · 刚刚同步':a.automatic?'自动生活中 · 刚刚同步':'正在陪你 · 刚刚同步';
   activityTime.title=typeof atActivity==='number'&&Number.isFinite(atActivity)?'活动更新时间：'+new Date(atActivity*1000).toLocaleString('zh-CN',{hour12:false}):'尚未读取';
   picture.dataset.stale=String(a.kind==='unknown');
   if(a.kind==='known')picture.dataset.night=String(a.night);
   if(visual){hasActivityImage=true;showImage(visual);img.alt=activityNarrative(a)+' 同步示意';title.textContent=scenes[a.scene]+(a.night?' · 夜晚':' · 此刻');}
   else if(a.kind==='unknown'&&hasActivityImage){img.alt='上次同步的场景，当前状态未确认';title.textContent='上次同步画面 · 当前活动未确认';}
   else {showImage(preview);img.alt='固定小屋预览，未代表当前活动';title.textContent=a.kind==='known'?'暂无匹配画面 · 以下仅为小屋预览':'等待连接 · 当前活动未确认';}
   const s=roomState(last,Date.now(),!!error);status.textContent=s.label;status.dataset.state=s.kind;hint.textContent=error||s.hint;
   counts.textContent=last&&countKeys.every(k=>Number.isInteger(last.counts?.[k]))?`${s.kind==='unknown'?'上次摘要：':''}任务 ${last.counts.tasks} · 协作 ${last.counts.collaborations} · 进行中 ${last.counts.active} · 待处理 ${last.counts.attention}`:'任务 — · 协作 — · 进行中 — · 待处理 —';
   const at=last?.observed_at;time.textContent='更新时间：'+(typeof at==='number'&&Number.isFinite(at)?new Date(at*1000).toLocaleString('zh-CN',{hour12:false}):'尚未读取')+(s.kind==='unknown'&&last?'（当前未确认）':'');
   refresh.disabled=!!inflight;
  }
  async function read(){
   if(!active||inflight||disposed)return;const id=++generation,controller=new AbortController();inflight=controller;render();
   const timeout=root.setTimeout(()=>controller.abort(),8000);
   try{
    const response=await fetcher('/api/workbench?action=room_status&token='+encodeURIComponent(token||''),{cache:'no-store',credentials:'same-origin',signal:controller.signal});
    const body=await response.json();
    if(id!==generation||!active||disposed)return;
    if(!response.ok||!body.ok){error=body.error_code==='unknown_action'||response.status===400?'小屋摘要接口尚未载入，请在任务结束后正常重开电脑工作站与远程接收服务。':response.status===403?'配对验证未通过，请从原手机入口重新进入。':'电脑工作站暂不可读；保留上次摘要。';}
    else if(body.data?.version!==1){error='小屋摘要格式暂不可用；保留上次摘要。';}
    else if(acceptObservation(last,body.data)){last=body.data;if(activityState(last.pet_activity).kind==='known')lastKnownActivity=last.pet_activity;error='';}
   }catch(e){if(id===generation&&active&&!disposed)error='未收到电脑响应；保留上次摘要，请确认电脑唤醒并联网。';}
   finally{root.clearTimeout(timeout);if(inflight===controller)inflight=null;if(!disposed)render();}
  }
  function sync(){const next=shouldRead(card.open,d.visibilityState,d.body.dataset.mobileView);if(next===active)return;active=next;if(active){read();}else{generation++;inflight?.abort();inflight=null;render();}}
  function poll(){if(active){render();read();}}
  function offline(){generation++;inflight?.abort();inflight=null;error='手机网络已断开；保留上次摘要，当前状态未确认。';render();}
  function pagehide(event){if(event.persisted){active=false;generation++;inflight?.abort();inflight=null;}else stop();}
  function stop(){if(disposed)return;disposed=true;generation++;imageEpoch++;root.clearTimeout(fadeTimer);inflight?.abort();inflight=null;root.clearInterval(timer);observer.disconnect();card.removeEventListener('toggle',sync);d.removeEventListener('visibilitychange',sync);root.removeEventListener('offline',offline);root.removeEventListener('online',poll);root.removeEventListener('pagehide',pagehide);root.removeEventListener('pageshow',sync);}
  const observer=new MutationObserver(sync);observer.observe(d.body,{attributes:true,attributeFilter:['data-mobile-view']});
  card.addEventListener('toggle',sync);d.addEventListener('visibilitychange',sync);root.addEventListener('offline',offline);root.addEventListener('online',poll);root.addEventListener('pagehide',pagehide);root.addEventListener('pageshow',sync);
  refresh.onclick=read;results.onclick=()=>d.querySelector('.mc-bottom-nav button[data-view="tasks"]')?.click();
  timer=root.setInterval(poll,5000);sync();return {dispose:stop,refresh:read,element:card};
 }
 const api={roomState,activityState,activityVisual,activityNarrative,acceptObservation,shouldRead,mount};if(typeof module!=='undefined'&&module.exports)module.exports=api;root.WorkstationMobileRoom=api;
 if(typeof document!=='undefined')document.addEventListener('DOMContentLoaded',()=>{const host=document.getElementById('mcSettings');if(host&&!document.getElementById('mcRoomOverview'))mount(host,{token:new URLSearchParams(location.search).get('token')||''});});
})(typeof window==='undefined'?globalThis:window);

