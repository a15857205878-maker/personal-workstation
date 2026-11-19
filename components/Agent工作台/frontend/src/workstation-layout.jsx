import React,{useCallback,useEffect,useRef,useState} from 'react';
import {Search,ArrowLeft,MessageCircle,Files,Briefcase,Coffee,Settings,Smartphone,X,ChevronRight,Package,Palette,Workflow,LayoutDashboard,Zap,Bell,House,BookOpen,Gamepad2,Dices,MessageSquare,Play,LayoutTemplate} from 'lucide-react';
import DesktopTitlebar from './desktop-titlebar.jsx';
import {SectionPicker} from './page-sections.jsx';
import {FUNCTION_GROUPS,findFunctions,pageInfo} from './workstation-navigation.mjs';
import {PARTNER_NAV} from './partner-model.mjs';
import {useFeedbackDismiss} from './feedback-dialog.jsx';
const icons={partner:MessageCircle,artifacts:Files,pack:Briefcase,leisure:Coffee};
const directoryIcons={
 ...icons,work:Workflow,overview:LayoutDashboard,quick:Zap,pack:Package,icons:Palette,
 'site-materials':LayoutTemplate,companion:Bell,town:House,reading:BookOpen,games:Gamepad2,
 wheel:Dices,remote:Smartphone,settings:Settings,chat:MessageSquare,replay:Play,
};
const toolTabs=[{id:'pack',label:'资料与打包',icon:Package},{id:'icons',label:'图标换装台',icon:Palette}];
export default function WorkstationLayout({mode,onNavigate,onQuick,onBack,canGoBack=false,conversationSlot,children}){
 const [query,setQuery]=useState(''),[category,setCategory]=useState('work');
 const page=pageInfo(mode),searching=!!query.trim(),menu=useRef(null),trigger=useRef(null),content=useRef(null),searchInput=useRef(null),previousFocus=useRef(null);
 const groups=searching?findFunctions(query):FUNCTION_GROUPS;
 const matches=groups.flatMap(group=>group.items);
 const showingTools=toolTabs.some(item=>item.id===mode);
 const dismiss=useFeedbackDismiss(menu);
 function restoreFocus(){
  const target=previousFocus.current;
  if(target instanceof HTMLElement&&target!==document.body&&target.isConnected)target.focus({preventScroll:true});
  else trigger.current?.focus();
 }
 function close(){dismiss(restoreFocus);}
 function activate(item){
  dismiss(()=>{
   restoreFocus();
   if(item.action==='quick'){onQuick();return;}
   if(item.action==='replay'){window.dispatchEvent(new Event('workstation-replay-startup'));return;}
   onNavigate(item.id);
   requestAnimationFrame(()=>content.current?.focus({preventScroll:true}));
  });
 }
 const open=useCallback((anchor=document.activeElement)=>{
  if(!menu.current||menu.current.open)return;
  previousFocus.current=anchor;
  setQuery('');
  setCategory(FUNCTION_GROUPS.find(group=>group.items.some(item=>item.id===mode))?.id||'work');
  menu.current.showModal();
  searchInput.current?.focus();
 },[mode]);
 useEffect(()=>{
  function shortcut(event){
   if(event.isComposing||event.repeat||event.altKey||event.shiftKey||(!event.ctrlKey&&!event.metaKey)||event.key.toLowerCase()!=='k')return;
   if(document.querySelector('dialog[open]')&&!menu.current?.open)return;
   event.preventDefault();
   if(menu.current?.open)searchInput.current?.focus();
   else open();
  }
  window.addEventListener('keydown',shortcut);
  return()=>window.removeEventListener('keydown',shortcut);
 },[open]);
 return <div className={'app-shell partner-shell messenger-shell workstation-studio'+(['partner','work'].includes(mode)?' partner-focused':'')+(mode==='site-materials'?' materials-focused':'')}><a className="app-skip" href="#app-content">跳到当前页面</a><DesktopTitlebar/>
 <aside id="app-sidebar" className="app-sidebar">
  <button ref={trigger} className="app-nav-item studio-search-launcher" aria-label="全部功能" aria-keyshortcuts="Control+K Meta+K" title="全部功能 · Ctrl+K" onClick={()=>open(trigger.current)}><Search size={18} aria-hidden="true"/><span>全部功能</span><kbd aria-hidden="true" data-key="Ctrl K"/></button>
  <nav className="app-navigation" aria-label="工作站主导航">{PARTNER_NAV.map(item=>{const Icon=icons[item.id],selected=mode===item.id||item.secondary.includes(mode);return <button key={item.id} className={'app-nav-item'+(selected?' is-current':'')} aria-label={item.label} aria-current={selected?'page':undefined} title={item.label} onClick={()=>onNavigate(item.id)}><Icon size={19} aria-hidden="true"/><span>{item.label}</span></button>;})}</nav>
  <div className="app-conversation-slot" ref={conversationSlot}/>
  <div className="app-sidebar-foot">
   <button className={'app-nav-item'+(mode==='remote'?' is-current':'')} aria-label="手机连接" aria-current={mode==='remote'?'page':undefined} title="手机连接" onClick={()=>onNavigate('remote')}><Smartphone size={18} aria-hidden="true"/><span>手机连接</span></button>
   <button className={'app-nav-item'+(mode==='settings'?' is-current':'')} aria-label="连接与设置" aria-current={mode==='settings'?'page':undefined} title="设置与维护" onClick={()=>onNavigate('settings')}><Settings size={18} aria-hidden="true"/><span>设置</span></button>
  </div>
 </aside>
 <div className="app-main"><header className={'app-topbar'+(showingTools?' has-tools-switch':'')}>
  <div className="app-location"><button className="app-nav-toggle app-back" aria-label="返回上一页" title="返回上一页" disabled={!canGoBack} onClick={onBack}><ArrowLeft size={18}/></button>{!showingTools&&<div className="app-breadcrumb-drag pywebview-drag-region"><strong>{page.label}</strong></div>}</div>
  {showingTools&&<><SectionPicker navigation className="tools-page-switch" label="工具分类" items={toolTabs} value={mode} onChange={onNavigate}/><div className="app-breadcrumb-drag pywebview-drag-region" aria-hidden="true"/></>}
 </header><div role="region" id="app-content" ref={content} className="app-content" tabIndex={-1} aria-label={page.label}>{children}</div></div>
 <dialog ref={menu} data-feedback-dialog className="function-dialog" aria-labelledby="function-menu-title" onCancel={e=>{e.preventDefault();close();}} onClick={e=>{if(e.target===e.currentTarget)close();}}><header><h2 id="function-menu-title">全部功能</h2><button aria-label="关闭全部功能" onClick={close}><X size={20}/></button></header><label className="function-search"><Search size={18} aria-hidden="true"/><input ref={searchInput} type="search" aria-label="查找功能" placeholder="搜索功能，例如手机、书房" value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.nativeEvent.isComposing&&searching&&matches.length===1){e.preventDefault();activate(matches[0]);}}}/></label>
 <div className="studio-function-body"><div className="function-categories" role="group" aria-label="功能分类">{FUNCTION_GROUPS.map(group=><button key={group.id} type="button" aria-pressed={!searching&&category===group.id} onClick={()=>{setQuery('');setCategory(group.id);}}>{group.label}</button>)}</div>
 <div className="function-groups" key={searching?'search':category}>
  {searching&&<p className="function-count" role="status">找到 {matches.length} 项功能</p>}
  {groups.map(group=><section key={group.id} aria-label={group.label} hidden={!searching&&group.id!==category}>{searching&&<h3>{group.label}</h3>}{group.items.filter(item=>searching||item.action!=='replay').map(item=>{
   const Icon=directoryIcons[item.id];
   return <button key={item.id} className="function-destination" data-route={item.action?undefined:item.id} aria-current={mode===item.id?'page':undefined} onClick={()=>activate(item)}>
    {Icon&&<span className="studio-function-icon" aria-hidden="true"><Icon size={16}/></span>}
    <span className="studio-function-text"><strong>{item.label}</strong><small>{item.hint}</small></span><ChevronRight className="studio-function-arrow" size={16} aria-hidden="true"/>
   </button>;
  })}</section>)}
  {!matches.length&&<p className="function-empty">试试「手机」「书房」或「交办」。</p>}
  {!searching&&<div className="function-footer"><button onClick={()=>activate({action:'replay'})}>重播开场</button></div>}
 </div></div></dialog></div>;
}
