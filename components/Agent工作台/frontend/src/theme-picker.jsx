import React,{useEffect,useState} from 'react';
import {Moon,Sun} from 'lucide-react';

// Legacy values remain readable for existing preference files and older clients.
export const PALETTES=[{id:'mint',label:'薄荷绿'},{id:'blue',label:'雾蓝'},{id:'lavender',label:'浅紫'},{id:'apricot',label:'暖杏'},{id:'coastal',label:'海岸手札'}];
export const DEFAULT_APPEARANCE={theme:'mint',color_scheme:'light'};
const CACHE_KEY='workstation.appearance';
let appearanceSaving=false,appearanceRevision=0;
const notifyAppearance=(value)=>window.dispatchEvent(new CustomEvent('workstation-appearance-changed',{detail:value}));
const validTheme=value=>PALETTES.some(item=>item.id===value);
const validScheme=value=>value==='light'||value==='dark';

export function normalizeAppearance(value,fallback=DEFAULT_APPEARANCE){
 const base=fallback&&validTheme(fallback.theme)&&validScheme(fallback.color_scheme)?fallback:DEFAULT_APPEARANCE;
 return {
  theme:validTheme(value?.theme)?value.theme:base.theme,
  color_scheme:validScheme(value?.color_scheme)?value.color_scheme:base.color_scheme
 };
}

export function mergeAppearance(current,patch,returned){
 const merged=normalizeAppearance(current);
 if(patch&&validTheme(patch.theme))merged.theme=patch.theme;
 if(patch&&validScheme(patch.color_scheme))merged.color_scheme=patch.color_scheme;
 if(returned&&validTheme(returned.theme))merged.theme=returned.theme;
 if(returned&&validScheme(returned.color_scheme))merged.color_scheme=returned.color_scheme;
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

export default function ThemePicker(){
 const [appearance,setAppearance]=useState(()=>readCache()||DEFAULT_APPEARANCE),[ready,setReady]=useState(false),[saving,setSaving]=useState(''),[error,setError]=useState('');
 const scheme=appearance.color_scheme;
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
  if(!ready||saving||appearanceSaving)return;
  appearanceSaving=true;
  const previous=appearance;
  setSaving(patch.color_scheme?'scheme':'palette');setError('');
  try{
   const data=await appearanceRequest('api_appearance_save',patch);
   const value=mergeAppearance(previous,patch,data);
   appearanceRevision++;
   setAppearance(value);writeCache(value);notifyAppearance(value);
  }catch{
   // Keep the last successfully saved state instead of pretending the write landed.
   setAppearance(previous);
   setError('外观未保存，已保留原设置。');
  }finally{appearanceSaving=false;setSaving('');}
 }
 const next=nextColorScheme(scheme);
 return <div className={'theme-picker'+(saving?' is-saving':'')}>
  <button type="button" className="theme-scheme-toggle" aria-label={'切换到'+(next==='dark'?'深色':'浅色')+'主题'} title={'切换到'+(next==='dark'?'深色':'浅色')+'主题'} disabled={!ready||!!saving} onClick={()=>update({color_scheme:next})}>
   {scheme==='dark'?<Moon size={12} aria-hidden="true"/>:<Sun size={12} aria-hidden="true"/>}<span>{next==='dark'?'深色':'浅色'}</span>
  </button>
  {error&&<small className="theme-picker-error" role="alert">{error}</small>}
 </div>;
}
