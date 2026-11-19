import React,{useEffect,useState} from 'react';
import {Palette,RefreshCw,Plus,FolderOpen,RotateCcw,Search} from 'lucide-react';
import {toolCall,usePage,Frame} from './workstation-pages.jsx';
import {PageEmpty} from './page-sections.jsx';
import useDialog from './use-dialog.js';
import './icon-studio.css';
const invoke=payload=>toolCall('icon_studio',payload);

function IconConfirmation({value,onClose,onConfirm}){
 const ref=useDialog(onClose);
 return <div className="icon-confirm-mask"><section className="ws-card icon-confirm" role="dialog" aria-modal="true" aria-label="确认图标操作" ref={ref}>
  <h2>{value.action==='apply'?'应用图标':value.action==='restore'?'还原选中项':'还原本工具全部'}</h2>
  <p>{value.action==='apply'?`将“${value.targetName}”换成“${value.assetName}”，并保留原还原记录。`:value.action==='restore'?`还原“${value.targetName}”。`:'还原本换装台修改过的全部图标，包含有记录的系统图标。其他工具的备份不处理。'}</p>
  <div className="ws-actions"><button onClick={onClose}>取消</button><button className="ws-primary" onClick={onConfirm}>确认操作</button></div>
 </section></div>;
}

export default function IconStudio({visible}){
 const p=usePage(()=>invoke({action:'load'}),visible),d=p.data;
 const [query,setQuery]=useState(''),[targetId,setTarget]=useState(''),[assetId,setAsset]=useState(''),[preview,setPreview]=useState(null),[previewBusy,setPreviewBusy]=useState(false),[confirm,setConfirm]=useState(null);
 const target=d?.targets?.find(x=>x.id===targetId)||d?.targets?.[0],asset=d?.assets?.find(x=>x.id===assetId)||d?.assets?.[0];
 const visibleTargets=(d?.targets||[]).filter(item=>[item.name,item.path,item.location_label].join(' ').toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())),selectionVisible=!!target&&visibleTargets.some(item=>item.id===target.id);
 useEffect(()=>{if(d?.preferred_asset)setAsset(d.preferred_asset);},[d?.revision]);
 useEffect(()=>{
  if(!visible||!d?.revision||!selectionVisible||!asset){setPreview(null);setPreviewBusy(false);return;}
  let live=true;setPreviewBusy(true);setPreview(null);
  invoke({action:'preview',revision:d.revision,target:target.id,asset:asset.id}).then(value=>{if(live)setPreview(value);}).catch(error=>{if(live)setPreview({warnings:[error.message]});}).finally(()=>{if(live)setPreviewBusy(false);});
  return()=>{live=false;};
 },[visible,d?.revision,target?.id,asset?.id,selectionVisible]);
 const operate=action=>p.run(()=>invoke({action}));
 const request=action=>setConfirm({action,revision:d.revision,target:target?.id,asset:asset?.id,targetName:target?.name+' · '+(target?.location_label||'所选路径'),assetName:asset?.name});
 const execute=async()=>{
  const value=confirm;setConfirm(null);
  await p.run(()=>invoke(value.action==='restore_all'?{action:value.action,revision:value.revision}:value.action==='restore'?{action:value.action,revision:value.revision,target:value.target}:{action:value.action,revision:value.revision,target:value.target,asset:value.asset}));
 };
 return <div className="icon-studio-page"><Frame title="图标换装台" description="先选一个快捷方式，再预览、应用或还原图标。" page={p} className="ws-polished-page" showBusy={!!d}>
  {d?.warnings?.map((message,i)=><p className="ws-error" role="alert" key={i}>{message}</p>)}
  {d?.target_notice&&<p className="ws-muted">{d.target_notice}</p>}
  {d?.message&&<p className="companion-notice" role="status">{d.message}</p>}
  {d?.import_errors?.map((x,i)=><p key={i} className="ws-error" role="alert">{x.name}：{x.message}</p>)}
  {d?.operation_errors?.map((x,i)=><p key={i} className="ws-error" role="alert">{x}</p>)}
  {!d?<PageEmpty icon={p.error?RefreshCw:Palette} title={p.error?'换装台暂未读到数据':'正在读取快捷方式和图标…'} busy={!p.error}/>:<>
  <div className="ws-actions icon-studio-toolbar"><button disabled={p.busy} onClick={()=>operate('import')}><Plus size={15}/> 添加图标</button><button disabled={p.busy} onClick={()=>operate('choose_collection')}><FolderOpen size={15}/> 选择素材文件夹</button></div>
  <div className="icon-studio-grid icon-entry-grid">
   <section className="ws-card"><div className="ws-section-title"><h2>快捷方式</h2><small>{query.trim()?`显示 ${visibleTargets.length} 项`:`${d.targets?.length||0} 项`}</small></div>
    <input type="search" aria-label="查找快捷方式" placeholder="搜索名称、桌面或 FloatingDock" value={query} onChange={e=>setQuery(e.target.value)}/>
    {!visibleTargets.length&&<div className="icon-empty-space">{d.targets?.length?<PageEmpty compact icon={Search} title="没有匹配的快捷方式" description="试试软件名称或入口位置。"><button onClick={()=>setQuery('')}>清空搜索</button></PageEmpty>:<PageEmpty compact icon={FolderOpen} title="还没有可换装的快捷方式" description="在桌面或 Dock 添加快捷方式后，点击上方刷新。"/>}</div>}
    <div className="icon-target-list" role="list">{visibleTargets.map(item=><button key={item.id} type="button" data-icon-target={item.id} className={'icon-target'+(target?.id===item.id?' selected':'')} aria-pressed={target?.id===item.id} disabled={p.busy} onClick={()=>setTarget(item.id)}><Palette size={21}/><span><strong>{item.name}</strong><small>{item.location_label||'入口位置待刷新'}{item.duplicate_count>1?' · 同名 '+item.duplicate_count+' 处':''}{!item.editable?' · 只读':''}</small></span></button>)}</div>
   </section>
   <section className="ws-card"><h2>图标与预览</h2>
    {asset?<label className="icon-select-label">选择图标<select aria-label="选择换装图标" value={asset.id} disabled={p.busy} onChange={e=>setAsset(e.target.value)}>{d.assets.map(item=><option key={item.id} value={item.id}>{item.name}{item.source==='新增'?'（新增）':''}</option>)}</select></label>:<PageEmpty compact icon={Palette} title="还没有可用的图标素材" description="可以添加 ICO、PNG，或选择现有素材文件夹。"/>}
    {selectionVisible&&asset&&<div className="icon-compare" aria-busy={previewBusy}>{[['current','当前图标'],['proposed','换装预览']].map(([key,label])=><div key={key}><span>{label}</span><div className="icon-preview">{preview?.[key]?<img alt={label} src={preview[key]}/>:<Palette aria-hidden="true" size={35}/>}</div></div>)}</div>}
    {previewBusy&&<p className="ws-muted">正在读取预览…</p>}
    {preview?.warnings?.map((message,i)=><p key={i} className="ws-muted">{message}</p>)}
    {selectionVisible&&<p className="ws-path">{target.name}<br/>{target.path}</p>}
    {target&&!selectionVisible&&<p className="ws-muted icon-selection-notice" role="status">当前选中项不在搜索结果中，请从左侧选择要修改的入口，或清空搜索。</p>}
    {selectionVisible&&target.duplicate_count>1&&<p className="ws-muted" role="status">同名有 {target.duplicate_count} 个入口，当前会修改“{target.location_label}”这一份。</p>}
    {selectionVisible&&!target.editable&&<p className="ws-muted">此特殊入口暂不支持换装或还原。</p>}
    <div className="ws-actions"><button className="ws-primary" disabled={p.busy||previewBusy||!selectionVisible||!target?.editable||!asset} onClick={()=>request('apply')}>应用图标</button><button disabled={p.busy||!selectionVisible||!target?.editable} onClick={()=>request('restore')}>还原选中项</button></div>
    <details className="icon-resource-info"><summary>素材位置与批量还原</summary><p className="ws-muted">原素材位置 {d.collection||'未配置'}</p><p className="ws-muted">新增素材位置 {d.added_collection||'未找到'}</p><button disabled={p.busy||!d.revision} onClick={()=>request('restore_all')}><RotateCcw size={15} aria-hidden="true"/> 还原本工具全部</button></details>
   </section>
  </div>
  </>}
  {visible&&confirm&&<IconConfirmation value={confirm} onClose={()=>setConfirm(null)} onConfirm={execute}/>}
 </Frame></div>;
}
