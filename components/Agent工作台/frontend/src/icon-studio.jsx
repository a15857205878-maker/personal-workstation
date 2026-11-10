import React,{useEffect,useState} from 'react';
import {Palette,RefreshCw,Plus,FolderOpen,RotateCcw} from 'lucide-react';
import {toolCall,usePage,Frame} from './workstation-pages.jsx';
import './icon-studio.css';
const invoke=payload=>toolCall('icon_studio',payload);

export default function IconStudio({visible}){
 const p=usePage(()=>invoke({action:'load'}),visible),d=p.data;
 const [targetId,setTarget]=useState(''),[assetId,setAsset]=useState(''),[preview,setPreview]=useState(null),[previewBusy,setPreviewBusy]=useState(false),[confirm,setConfirm]=useState(null);
 const target=d?.targets?.find(x=>x.id===targetId)||d?.targets?.[0],asset=d?.assets?.find(x=>x.id===assetId)||d?.assets?.[0];
 useEffect(()=>{if(d?.preferred_asset)setAsset(d.preferred_asset);},[d?.revision]);
 useEffect(()=>{
  if(!visible||!d?.revision||!target||!asset){setPreview(null);return;}
  let live=true;setPreviewBusy(true);setPreview(null);
  invoke({action:'preview',revision:d.revision,target:target.id,asset:asset.id}).then(value=>{if(live)setPreview(value);}).catch(error=>{if(live)setPreview({warnings:[error.message]});}).finally(()=>{if(live)setPreviewBusy(false);});
  return()=>{live=false;};
 },[visible,d?.revision,target?.id,asset?.id]);
 const operate=action=>p.run(()=>invoke({action}));
 const request=action=>setConfirm({action,revision:d.revision,target:target?.id,asset:asset?.id,targetName:target?.name,assetName:asset?.name});
 const execute=async()=>{
  const value=confirm;setConfirm(null);
  await p.run(()=>invoke(value.action==='restore_all'?{action:value.action,revision:value.revision}:value.action==='restore'?{action:value.action,revision:value.revision,target:value.target}:{action:value.action,revision:value.revision,target:value.target,asset:value.asset}));
 };
 return <div className="icon-studio-page"><Frame title="图标换装台" description="在当前工作站预览、换装和还原。原素材只读，新增图标单独保存。" page={p}>
  <div className="ws-actions icon-studio-toolbar"><button disabled={p.busy} onClick={()=>operate('import')}><Plus size={15}/> 添加图标</button><button disabled={p.busy} onClick={()=>operate('choose_collection')}><FolderOpen size={15}/> 选择素材文件夹</button><button disabled={p.busy||!d?.revision} onClick={()=>request('restore_all')}><RotateCcw size={15}/> 还原本工具全部</button></div>
  {d?.warnings?.map((message,i)=><p className="ws-error" role="alert" key={i}>{message}</p>)}
  {d?.message&&<p className="companion-notice" role="status">{d.message}</p>}
  {d?.import_errors?.map((x,i)=><p key={i} className="ws-error" role="alert">{x.name}：{x.message}</p>)}
  {d?.operation_errors?.map((x,i)=><p key={i} className="ws-error" role="alert">{x}</p>)}
  <div className="icon-studio-grid">
   <section className="ws-card"><div className="ws-section-title"><h2>桌面与 FloatingDock 快捷方式</h2><small>{d?.targets?.length??'—'} 项</small></div>
    {d&&!d.targets?.length&&<p className="ws-empty">当前扫描目录没有可显示的快捷方式。</p>}
    <div className="icon-target-list" role="list">{d?.targets?.map(item=><button key={item.id} type="button" data-icon-target={item.id} className={'icon-target'+(target?.id===item.id?' selected':'')} aria-pressed={target?.id===item.id} disabled={p.busy} onClick={()=>setTarget(item.id)}><Palette size={21}/><span><strong>{item.name}</strong><small>{item.kind==='system'?'Windows 系统图标':item.editable?'普通快捷方式':'特殊应用入口 · 只读'}</small></span></button>)}</div>
   </section>
   <section className="ws-card"><h2>伙伴素材</h2><label className="icon-select-label">选择图标<select aria-label="选择换装图标" value={asset?.id||''} disabled={p.busy||!d?.assets?.length} onChange={e=>setAsset(e.target.value)}>{d?.assets?.map(item=><option key={item.id} value={item.id}>{item.name}{item.source==='新增'?'（新增）':''}</option>)}</select></label>
    <div className="icon-compare" aria-busy={previewBusy}>{[['current','当前图标'],['proposed','换装预览']].map(([key,label])=><div key={key}><span>{label}</span><div className="icon-preview">{preview?.[key]?<img alt={label} src={preview[key]}/>:<Palette size={35}/>}</div></div>)}</div>
    {previewBusy&&<p className="ws-muted">正在读取预览…</p>}
    {preview?.warnings?.map((message,i)=><p key={i} className="ws-muted">{message}</p>)}
    {target&&<p className="ws-path">{target.name}<br/>{target.path}</p>}
    {target&&!target.editable&&<p className="ws-muted">此特殊入口已识别，暂不支持换装或还原。</p>}
    <div className="ws-actions"><button className="ws-primary" disabled={p.busy||previewBusy||!target?.editable||!asset} onClick={()=>request('apply')}>应用图标</button><button disabled={p.busy||!target?.editable} onClick={()=>request('restore')}>还原选中项</button></div>
    <details className="icon-resource-info"><summary>素材位置与说明</summary><p className="ws-muted">原素材：{d?.collection||'未找到，请选择文件夹'}</p><p className="ws-muted">新增素材：{d?.added_collection||'读取中'}</p><p className="ws-muted">添加支持 ICO、PNG，不修改所选原文件。重复素材不覆盖；添加后不会自动给软件应用图标。换装后仍由你手动加入 FloatingDock。</p></details>
   </section>
  </div>
  {confirm&&<div className="icon-confirm-mask"><section className="ws-card icon-confirm" role="dialog" aria-modal="true" aria-label="确认图标操作"><h2>{confirm.action==='apply'?'应用图标':confirm.action==='restore'?'还原选中项':'还原本工具全部'}</h2><p>{confirm.action==='apply'?`将“${confirm.targetName}”换成“${confirm.assetName}”，并保留原还原记录。`:confirm.action==='restore'?`还原“${confirm.targetName}”。`:'还原本换装台修改过的全部图标，包含有记录的系统图标。其他工具的备份不处理。'}</p><div className="ws-actions"><button autoFocus onClick={()=>setConfirm(null)}>取消</button><button className="ws-primary" onClick={execute}>确认操作</button></div></section></div>}
 </Frame></div>;
}
