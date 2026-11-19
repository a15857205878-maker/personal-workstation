import React,{Suspense,lazy,useState,useEffect,useRef} from 'react';
import {createRoot} from 'react-dom/client';
import './base.css';
import Quick from './quick.jsx';
import StartupWelcome from './startup-welcome.jsx';
import TownPortal from './town-portal.jsx';
import {acceptBrief} from './workspace-transfer.mjs';
const AutoWorkspace=lazy(()=>import('./agent-center.jsx'));
const GroupChat=lazy(()=>import('./group-chat.jsx'));
const RemoteWorkspace=lazy(()=>import('./remote-workspace.jsx'));
const CompanionPage=lazy(()=>import('./companion-page.jsx'));
const ReadingRoom=lazy(()=>import('./reading-room.jsx'));
const Leisure=lazy(()=>import('./leisure.jsx'));
const IconStudio=lazy(()=>import('./icon-studio.jsx'));
const SiteMaterials=lazy(()=>import('./site-materials.jsx'));
import PartnerPage from './partner-page.jsx';
import WorkstationLayout from './workstation-layout.jsx';
import {navigateTrail,correctTrail} from './app-interaction.mjs';
import {pageInfo,resolvePage} from './workstation-navigation.mjs';
import './theme.css';
import './finish.css';
import './workstation-shell.css';
import './coastal-ui.css';
import './app-layout.css';
import './unified-theme.css';
import './conversation-ui.css';
import './partner-art.css';
import './partner-ui.css';
import './messenger-ui.css';
import './workstation-studio.css';
import {Overview,Artifacts,SettingsPage} from './workstation-pages.jsx';
if(!location.pathname.endsWith('/quick.html')){
 try{
  const cached=JSON.parse(localStorage.getItem('workstation.appearance')||'null');
  const palettes=['mint','blue','lavender','apricot','coastal'];
  if(cached&&palettes.includes(cached.theme)&&(cached.color_scheme==='light'||cached.color_scheme==='dark')){
   document.documentElement.dataset.palette=cached.theme;
   document.documentElement.dataset.colorScheme=cached.color_scheme;
   document.documentElement.setAttribute('color-scheme',cached.color_scheme);
   document.documentElement.style.colorScheme=cached.color_scheme;
  }
 }catch{/* first paint falls back to the light defaults */}
}
function App(){
 const [mode,setMode]=useState('partner'),[visited,setVisited]=useState({partner:true}),[error,setError]=useState('');
 const [trail,setTrail]=useState(['partner']);
 const toolMode=useRef('games'),isToolMode=['pack','games','wheel'].includes(mode);
 if(isToolMode)toolMode.current=mode;
 const incomingEvents=useRef(new Set()),workPreview=useRef(false);
 const [pendingSetup,setPendingSetup]=useState(null);
 const [conversationSlot,setConversationSlot]=useState(null);
 const [pendingConversation,setPendingConversation]=useState(null);
 const [artifactTurn,setArtifactTurn]=useState(null);
 function openTurnArtifacts(turn){if(!/^[a-f0-9]{32}$/.test(turn.conversation_id)||!/^[a-f0-9]{32}$/.test(turn.turn_id))return;choose('artifacts',turn);}
 const [pendingReading,setPendingReading]=useState(null);
 function resumeReading(id){if(!/^[a-f0-9]{32}$/.test(id))return;setPendingReading({id,nonce:Date.now()});choose('reading');}
 function openConversation(value){const id=value.conversation_id||value.id,turn_id=value.turn_id;if(!/^[a-f0-9]{32}$/.test(id)||turn_id&&!/^[a-f0-9]{32}$/.test(turn_id))return;setPendingConversation({id,turn_id,section:value.section,file:value.file,fromToday:value.fromToday===true,nonce:Date.now()});choose('work');}
 function clearPendingConversation(nonce){setPendingConversation(value=>nonce!==undefined&&value?.nonce!==nonce?value:null);}
 function openSetup(section='models'){setPendingSetup({id:Date.now(),section});choose('work');}
 useEffect(()=>{window.workbenchReceive=event=>{if(event?.request_id&&incomingEvents.current.has(event.request_id))return true;let accepted=false;if(event?.kind==='navigate'&&typeof event.page==='string'&&pageInfo(resolvePage(event.page)).id===resolvePage(event.page)){const tool=document.querySelector('iframe[title="个人工具中心原生页面"]');if(['pack','games','wheel'].includes(event.page)&&tool?.contentDocument?.querySelector('[role="dialog"][aria-modal="true"]')&&tool.contentWindow.location.hash!=='#'+event.page)return false;if([...document.querySelectorAll('dialog[open]:not([data-modeless]),[role="dialog"][aria-modal="true"]')].some(dialog=>dialog.getClientRects().length))return false;choose(event.page);accepted=true;}if(event?.kind==='center_turn'){
 if(!/^[a-f0-9]{32}$/.test(event.conversation_id)||!/^[a-f0-9]{32}$/.test(event.turn_id)||!['progress','delivery'].includes(event.section))return false;
 if([...document.querySelectorAll('dialog[open]:not([data-modeless]),[role="dialog"][aria-modal="true"]')].some(dialog=>dialog.getClientRects().length))return false;
 const tool=document.querySelector('iframe[title="个人工具中心原生页面"]');
 if(tool?.getClientRects().length&&tool.contentDocument?.querySelector('[role="dialog"][aria-modal="true"]'))return false;
 openConversation({...event,fromToday:true});accepted=true;
}if(event?.kind==='task'){choose('artifacts');accepted=true;}if(event?.kind==='advanced'){if(workPreview.current)return false;toWork({text:event.text});accepted=true;}if(accepted&&event.request_id){incomingEvents.current.add(event.request_id);if(incomingEvents.current.size>64)incomingEvents.current.delete(incomingEvents.current.values().next().value);}return accepted;};return()=>{delete window.workbenchReceive;};},[]);
 const [pendingWork,setPendingWork]=useState(null);
 function toWork(brief){if(workPreview.current)throw Error('高级协作还有待确认的需求，请先处理该预览。');const text=acceptBrief(brief.text,8000);workPreview.current=true;setPendingWork({...brief,text,id:Date.now()+'w'});choose('work');}
 function correctToolPage(next){setTrail(old=>correctTrail(old,next));setMode(next);setVisited(old=>({...old,[next]:true}));}
 function choose(next,turn=null){next=resolvePage(next);if(next==='artifacts')setArtifactTurn(turn);setTrail(old=>navigateTrail(old,next));setMode(next);setVisited(old=>({...old,[next]:true}));}
 useEffect(()=>{const blocked=event=>{const frame=document.querySelector('iframe[title="个人工具中心原生页面"]');if(event.origin===location.origin&&event.source===frame?.contentWindow&&event.data?.type==='workstation-tools-navigation-blocked'&&['pack','games','wheel'].includes(event.data.page))correctToolPage(event.data.page);};window.addEventListener('message',blocked);return()=>window.removeEventListener('message',blocked);},[]);
 const quick=async()=>{try{const r=await window.pywebview.api.call('api_quick_open',{});if(!r.ok)throw Error(r.error);setError('');}catch(e){setError(e.message);}};
 return <><StartupWelcome/><WorkstationLayout mode={mode} onNavigate={choose} onQuick={quick} canGoBack={trail.length>1} conversationSlot={setConversationSlot} onBack={()=>{if(trail.length>1)choose(trail.at(-2));}}>
  {error&&<p role="alert" className="workstation-error">{error}</p>}
  <section className="mode-pane" data-page="overview" hidden={mode!=='overview'}><Overview visible={mode==='overview'} onNavigate={choose} onConversation={openConversation}/></section>
  <section className="mode-pane" hidden={mode!=='chat'}>{visited.chat&&<Suspense fallback={<p className="workstation-loading">正在打开实验群聊…</p>}><GroupChat/></Suspense>}</section>
  <section className="mode-pane partner-pane" hidden={!['partner','work'].includes(mode)}>{(visited.partner||visited.work)&&<PartnerPage visible={['partner','work'].includes(mode)} forceDual={mode==='work'} onNavigate={choose} conversationSlot={conversationSlot}>{(dualVisible,historyProps)=><Suspense fallback={<p className="workstation-loading">正在打开双模型协作…</p>}><AutoWorkspace {...historyProps} onTurnArtifacts={openTurnArtifacts} pendingConversation={pendingConversation} onConversationHandled={clearPendingConversation} pendingSetup={pendingSetup} onSetupHandled={()=>setPendingSetup(null)} visible={dualVisible} pendingBrief={pendingWork} onBriefHandled={()=>{setPendingWork(null);workPreview.current=false;}}/></Suspense>}</PartnerPage>}</section>
  <section className={'mode-pane ws-town-pane'+(mode==='pack'?' ws-polish-pane':'')} hidden={!isToolMode}>{(visited.pack||visited.games||visited.wheel)&&<iframe className="ws-town-frame" title="个人工具中心原生页面" src={'./tools/index.html#'+toolMode.current}/>}</section>
  <section className="mode-pane ws-town-pane" hidden={mode!=='town'}>{visited.town&&<TownPortal visible={mode==='town'} onExit={()=>choose('partner')}/>}</section>
  <section className="mode-pane" hidden={mode!=='remote'}>{visited.remote&&<Suspense fallback={<p className="workstation-loading">正在打开远程工作台…</p>}><RemoteWorkspace visible={mode==='remote'}/></Suspense>}</section>
  <section className="mode-pane" hidden={mode!=='companion'}>{visited.companion&&<Suspense fallback={<p className="workstation-loading">正在读取桌宠连接…</p>}><CompanionPage visible={mode==='companion'} onNavigate={choose} onConversation={openConversation}/></Suspense>}</section>
  <section className="mode-pane ws-polish-pane" hidden={mode!=='artifacts'}>{visited.artifacts&&<Artifacts visible={mode==='artifacts'} onConversation={openConversation} onNavigate={choose} turn={artifactTurn} onClearTurn={()=>setArtifactTurn(null)}/>}</section>
  <section className="mode-pane" hidden={mode!=='site-materials'}>{visited['site-materials']&&<Suspense fallback={<p>正在打开网站素材台…</p>}><SiteMaterials visible={mode==='site-materials'}/></Suspense>}</section>
  <section className="mode-pane" hidden={mode!=='leisure'}>{visited.leisure&&<Suspense fallback={<p>正在打开休闲区…</p>}><Leisure visible={mode==='leisure'} onNavigate={choose} onRead={resumeReading}/></Suspense>}</section>
  <section className="mode-pane" hidden={mode!=='reading'}>{visited.reading&&<Suspense fallback={<p>正在打开书房…</p>}><ReadingRoom visible={mode==='reading'} onNavigate={choose} pendingReading={pendingReading} onReadingHandled={()=>setPendingReading(null)}/></Suspense>}</section>
  <section className="mode-pane ws-icon-page" hidden={mode!=='icons'}>{visited.icons&&<Suspense fallback={<p className="workstation-loading">正在读取图标换装台…</p>}><IconStudio visible={mode==='icons'}/></Suspense>}</section>
  <section className="mode-pane ws-polish-pane" hidden={mode!=='settings'}>{visited.settings&&<SettingsPage visible={mode==='settings'} onNavigate={choose} onModels={openSetup} onQuick={quick}/>}</section>
 </WorkstationLayout></>;
}
createRoot(document.getElementById('root')).render(location.pathname.endsWith('/quick.html')?<Quick/>:<App/>);
