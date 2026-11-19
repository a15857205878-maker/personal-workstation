import React,{useEffect,useId,useRef,useState} from 'react';
import {Moon,Sun} from 'lucide-react';

// Legacy values remain readable for existing preference files and older clients.
export const PALETTES=[{id:'mint',label:'薄荷绿'},{id:'blue',label:'雾蓝'},{id:'lavender',label:'浅紫'},{id:'apricot',label:'暖杏'},{id:'coastal',label:'海岸手札'}];
export const DEFAULT_APPEARANCE={theme:'mint',color_scheme:'light',chat_background:'auto',background_strength:35};
const CACHE_KEY='workstation.appearance';
let appearanceSaving=false,appearanceRevision=0;
const notifyAppearance=(value)=>window.dispatchEvent(new CustomEvent('workstation-appearance-changed',{detail:value}));
const validTheme=value=>PALETTES.some(item=>item.id===value);
const validScheme=value=>value==='light'||value==='dark';
const backgrounds=[['garden','雾屿花园'],['observatory','月夜观测站'],['auto','跟随深浅主题'],['coast','海岸'],['aurora','极光'],['none','纯色']];
const validBackground=value=>backgrounds.some(([id])=>id===value);
const validStrength=value=>Number.isInteger(value)&&value>=0&&value<=60;
const backgroundScene=(choice,scheme)=>choice==='auto'?(scheme==='dark'?'aurora':'coast'):choice;
const backgroundImage=scene=>scene==='none'?'none':`var(--partner-${scene})`;

function BackgroundDial({value,onChange,disabled}){
 const id=useId(),input=useRef(null),sweep=value/60*260;
 function adjust(event){
  const bounds=event.currentTarget.getBoundingClientRect();
  const x=event.clientX-bounds.left-bounds.width/2,y=event.clientY-bounds.top-bounds.height/2;
  if(Math.hypot(x,y)<8)return;
  const angle=Math.max(-130,Math.min(130,Math.atan2(x,-y)*180/Math.PI));
  onChange(Math.round((angle+130)/260*60));
 }
 return <div className="chat-background-dial-row">
  <div><label htmlFor={id}>背景强度</label><small>拖动旋钮，或用方向键微调。</small></div>
  <div className="chat-background-dial" data-disabled={disabled||undefined} style={{'--dial-sweep':sweep+'deg','--dial-angle':sweep-130+'deg'}}
   onPointerDown={event=>{if(disabled||event.button!==0)return;event.currentTarget.setPointerCapture(event.pointerId);input.current.focus({preventScroll:true});adjust(event);event.preventDefault();}}
   onPointerMove={event=>{if(!disabled&&event.currentTarget.hasPointerCapture(event.pointerId))adjust(event);}}>
   <span aria-hidden="true"/>
   <input ref={input} type="range" id={id} min="0" max="60" value={value} disabled={disabled} onChange={event=>onChange(Number(event.target.value))}/>
  </div>
  <output htmlFor={id}>{value}%</output>
 </div>;
}

export function normalizeAppearance(value,fallback=DEFAULT_APPEARANCE){
 const base=fallback&&validTheme(fallback.theme)&&validScheme(fallback.color_scheme)?fallback:DEFAULT_APPEARANCE;
 return {
  theme:validTheme(value?.theme)?value.theme:base.theme,
  color_scheme:validScheme(value?.color_scheme)?value.color_scheme:base.color_scheme,
  chat_background:validBackground(value?.chat_background)?value.chat_background:validBackground(base.chat_background)?base.chat_background:'auto',
  background_strength:validStrength(value?.background_strength)?value.background_strength:validStrength(base.background_strength)?base.background_strength:35
 };
}

export function mergeAppearance(current,patch,returned){
 const merged=normalizeAppearance(current);
 if(patch&&validTheme(patch.theme))merged.theme=patch.theme;
 if(patch&&validScheme(patch.color_scheme))merged.color_scheme=patch.color_scheme;
 if(returned&&validTheme(returned.theme))merged.theme=returned.theme;
 if(returned&&validScheme(returned.color_scheme))merged.color_scheme=returned.color_scheme;
 for(const value of [patch,returned]){if(validBackground(value?.chat_background))merged.chat_background=value.chat_background;if(validStrength(value?.background_strength))merged.background_strength=value.background_strength;}
 return merged;
}

export function nextColorScheme(scheme){return scheme==='dark'?'light':'dark';}

// The API is authoritative; the local cache is only a paint hint before it answers.
export async function appearanceRequest(action,payload={}){
 const api=window.pywebview?.api;
 if(!api||typeof api.call!=='function')throw Error('正在等待本地桌面服务。');
 const result=await api.call(action,payload);
 if(result?.ok===false)throw Error(result.error||'操作未完成');
 if(result&&result.ok===true)return result.data??{};
 return result??{};
}

export function applyAppearance(appearance,root=document.documentElement){
 const value=normalizeAppearance(appearance);
 root.dataset.palette=value.theme;
 root.dataset.colorScheme=value.color_scheme;
 root.setAttribute('color-scheme',value.color_scheme);
 root.style.colorScheme=value.color_scheme;
 root.dataset.chatBackground=value.chat_background;root.dataset.backgroundStrength=String(value.background_strength);
 root.style.setProperty('--chat-bg-image',backgroundImage(backgroundScene(value.chat_background,value.color_scheme)));
 root.style.setProperty('--chat-bg-opacity',String(value.background_strength/100));
}

function readCache(){
 try{
  const raw=window.localStorage?.getItem(CACHE_KEY);
  if(!raw)return null;
  const value=JSON.parse(raw);
  return validTheme(value?.theme)&&validScheme(value?.color_scheme)?value:null;
 }catch{return null;}
}
function writeCache(value){
 try{window.localStorage?.setItem(CACHE_KEY,JSON.stringify(value));}catch{/* private mode */ }
}

export default function ThemePicker({showBackground=false}){
 const [appearance,setAppearance]=useState(()=>readCache()||DEFAULT_APPEARANCE),[ready,setReady]=useState(false),[saving,setSaving]=useState(''),[error,setError]=useState('');
 const scheme=appearance.color_scheme;
 const [draft,setDraft]=useState({chat_background:'auto',background_strength:35}),[dirty,setDirty]=useState(false);
 useEffect(()=>{if(!dirty)setDraft({chat_background:appearance.chat_background??'auto',background_strength:appearance.background_strength??35});},[appearance,dirty]);
 useEffect(()=>{const sync=event=>setAppearance(previous=>normalizeAppearance(event.detail,previous));window.addEventListener('workstation-appearance-changed',sync);return()=>window.removeEventListener('workstation-appearance-changed',sync);},[]);
 useEffect(()=>{
  const cached=readCache();
  if(cached)setAppearance(cached);
 },[]);
 useEffect(()=>{applyAppearance(appearance);},[appearance]);
 useEffect(()=>{
  let live=true;
  async function load(){
   if(!window.pywebview?.api?.call){window.addEventListener('pywebviewready',load,{once:true});return;}
   const revision=appearanceRevision;
   try{const data=await appearanceRequest('api_appearance_get');if(!live||revision!==appearanceRevision)return;const value=normalizeAppearance(data);setAppearance(value);writeCache(value);notifyAppearance(value);setError('');}
   catch{if(live)setError('外观读取失败，可重新选择。');}
   finally{if(live)setReady(true);}
  }
  load();
  return()=>{live=false;window.removeEventListener('pywebviewready',load);};
 },[]);
 async function update(patch){
  if(!ready||saving)return;
  if(appearanceSaving){setError('另一项外观正在保存，请稍后再试；当前选择已保留。');return;}
  appearanceSaving=true;
  const previous=appearance;
  setSaving(patch.color_scheme?'scheme':'palette');setError('');
  try{
   const data=await appearanceRequest('api_appearance_save',patch);
   const value=mergeAppearance(previous,patch,data);
   appearanceRevision++;
   setAppearance(value);writeCache(value);notifyAppearance(value);setDirty(false);
  }catch{
   // Keep the last successfully saved state instead of pretending the write landed.
   setAppearance(previous);
   setError('外观未保存，已保留原设置。');
  }finally{appearanceSaving=false;setSaving('');}
 }
 if(showBackground){
  const scene=backgroundScene(draft.chat_background,scheme),disabled=!ready||!!saving;
  function change(patch){setDirty(true);setDraft(previous=>({...previous,...patch}));}
  return <div className="chat-background-controls">
   <div className="chat-background-options" role="group" aria-label="聊天背景">
    {backgrounds.map(([id,name])=><button key={id} type="button" disabled={disabled} aria-pressed={draft.chat_background===id} onClick={()=>change({chat_background:id})}>
     <span aria-hidden="true" style={{backgroundImage:backgroundImage(backgroundScene(id,scheme))}}/>{name}
    </button>)}
   </div>
   <div className="chat-background-preview" data-scene={scene} style={{'--chat-bg-image':backgroundImage(scene),'--chat-bg-opacity':draft.background_strength/100}}><span>背景预览</span></div>
   <BackgroundDial value={draft.background_strength} disabled={disabled||scene==='none'} onChange={value=>change({background_strength:value})}/>
   <div className="chat-background-save"><button type="button" className="auto-button auto-primary" disabled={disabled||!dirty} onClick={()=>update(draft)}>{saving?'保存中…':'保存背景'}</button>
    {dirty&&!saving&&<small>保存后应用到搭档聊天。</small>}
    {!dirty&&ready&&!error&&<small role="status">已使用当前背景。</small>}
   </div>
   {error&&<small role="alert">{error}</small>}
  </div>;
 }
 const next=nextColorScheme(scheme);
 return <div className={'theme-picker'+(saving?' is-saving':'')}>
  <button type="button" className="theme-scheme-toggle" aria-label={'切换到'+(next==='dark'?'深色':'浅色')+'主题'} title={'切换到'+(next==='dark'?'深色':'浅色')+'主题'} disabled={!ready||!!saving} onClick={()=>update({color_scheme:next})}>
   {scheme==='dark'?<Moon size={12} aria-hidden="true"/>:<Sun size={12} aria-hidden="true"/>}<span>{next==='dark'?'深色':'浅色'}</span>
  </button>
  {error&&<small className="theme-picker-error" role="alert">{error}</small>}
 </div>;
}
