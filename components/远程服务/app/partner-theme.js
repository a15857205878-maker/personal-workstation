(function(root){
'use strict';
const key='workstation-partner-theme-v1';
function themeMessage(event,origin,source,desktopEmbed=false){return source&&event.source===source&&(event.origin===origin||desktopEmbed&&/^http:\/\/127\.0\.0\.1:\d{1,5}$/.test(event.origin))&&event.data?.type==='workstation-visual-theme'&&['light','dark'].includes(event.data.scheme)?event.data.scheme:null;}
function taskVoice(task={},connected=true){
 if(!connected)return '连接暂时断开，已保留上次读取的记录。恢复连接后再核对进度，请不要重复提交。';
 if(['failed','失败','needs_attention','interrupted'].includes(task.status))return '这一步需要处理。先看看错误和执行记录，再决定是否重试。';
 if(task.status==='stopping')return '正在请求停止，请稍等电脑确认；已经发出的请求可能仍会计费。';
 if(['cancelled','已取消'].includes(task.status))return '本次处理已取消，已有记录和成果为你保留，可以随时回看。';
 if(['completed','已完成'].includes(task.status))return task.files?.length?'成果文件已就绪。可以先预览，想调整的地方直接写在下方。':(!task.output_format||task.output_format==='text')?'本轮文字已完成。先看看回复，需要调整时再准备下一轮。':'这轮处理已结束，但还未收到可下载文件。先看看执行记录，再决定下一步。';
 if(['running','执行中'].includes(task.status))return task.stage?'正在进行：'+String(task.stage).slice(0,80)+'。进度会在这里更新，你也可以补充要求。':'电脑正在处理，进度会在这里更新。你可以补充要求，无需重复提交。';
 return '把目标和参考材料准备好，检查清楚后再确认开始。';
}
function collaborationSignals(task={}){
 const steps=task.steps||[],round=Math.max(Number(task.round)||0,...steps.map(s=>Number(s.round)||0));
 const current=steps.filter(s=>(Number(s.round)||0)===round);
 return [['制作','提案'],['审查','审查'],['修订','修订']].map(([label,key])=>{
  const step=[...current].reverse().find(s=>String(s.stage||'').includes(key));
  const state=step?.state==='completed'?'done':step?.state==='failed'?'error':step?.state==='running'&&task.status==='running'?'running':!step&&task.status==='running'&&String(task.stage||'').includes(key)?'running':'waiting';
  return {label,state,text:({done:'已完成',error:'需处理',running:'进行中',waiting:'待进行'})[state]};
 });
}
function setHistoryCollapsed(d,value){
 d.documentElement.dataset.historyCollapsed=String(value);
 const toggle=d.getElementById('partnerHistoryToggle'),restore=d.getElementById('partnerHistoryRestore');
 toggle?.setAttribute('aria-expanded',String(!value));restore?.setAttribute('aria-expanded',String(!value));
 if(value)restore?.focus();else toggle?.focus();
}
function mount(){const d=root.document;if(!d)return;let current='light';try{current=localStorage.getItem(key)||'light';}catch{}if(!['light','dark'].includes(current))current='light';
 function apply(theme){current=theme;d.documentElement.dataset.partnerTheme=theme;d.documentElement.style.colorScheme=theme;try{localStorage.setItem(key,theme);}catch{}for(const b of d.querySelectorAll('.partner-theme-toggle')){b.textContent=theme==='dark'?'浅色':'深色';b.setAttribute('aria-label','切换到'+(theme==='dark'?'浅色':'深色')+'模式');}for(const f of d.querySelectorAll('iframe[data-workstation-session]')){try{f.contentWindow.postMessage({type:'workstation-visual-theme',scheme:theme},location.origin);}catch{}}}
 root.addEventListener('message',event=>{const theme=themeMessage(event,location.origin,root.parent!==root?root.parent:null,new URLSearchParams(location.search).get('desktop_embed')==='1');if(theme)apply(theme);});
 function ready(){apply(current);
 const sidebar=d.getElementById('sidebar'),app=d.querySelector('.app');
 if(sidebar&&app&&!d.getElementById('partnerHistoryToggle')&&new URLSearchParams(location.search).get('single_simple')!=='1'){
  const toggle=d.createElement('button'),restore=d.createElement('button');
  toggle.id='partnerHistoryToggle';toggle.className='partner-history-toggle';toggle.type='button';toggle.textContent='收起历史';toggle.setAttribute('aria-controls','sidebar');toggle.setAttribute('aria-expanded','true');
  restore.id='partnerHistoryRestore';restore.className='partner-history-restore';restore.type='button';restore.textContent='历史';restore.setAttribute('aria-label','展开历史会话');restore.setAttribute('aria-controls','sidebar');restore.setAttribute('aria-expanded','false');
  toggle.onclick=()=>{if(root.matchMedia('(max-width:760px)').matches)d.getElementById('sidebarClose')?.click();else setHistoryCollapsed(d,true);};restore.onclick=()=>setHistoryCollapsed(d,false);
  sidebar.querySelector('.side-head')?.append(toggle);app.append(restore);
 }
let mobileEmbedded=false;try{mobileEmbedded=root.parent!==root&&root.parent.location.origin===location.origin&&root.frameElement?.dataset.workstationSession==='1';}catch{}const top=d.querySelector('.mc-top')||d.querySelector('.topbar');if(top&&!mobileEmbedded&&!top.querySelector('.partner-theme-toggle')){const b=d.createElement('button');b.type='button';b.className='partner-theme-toggle';b.onclick=()=>root.WorkstationMobileVisual?root.WorkstationMobileVisual.toggle():apply(current==='dark'?'light':'dark');top.append(b);apply(current);}for(const f of d.querySelectorAll('iframe[data-workstation-session]'))f.addEventListener('load',()=>apply(current));}
 apply(current);if(d.readyState==='loading')d.addEventListener('DOMContentLoaded',ready);else ready();root.WorkstationPartnerTheme={taskVoice,collaborationSignals,apply,get theme(){return current;}};
}
if(typeof module!=='undefined'&&module.exports)module.exports={taskVoice,themeMessage,collaborationSignals,setHistoryCollapsed};else mount();
})(typeof window!=='undefined'?window:globalThis);
