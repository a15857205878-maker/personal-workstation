import React,{useEffect,useRef,useState} from 'react';
import {SlidersHorizontal,MessagesSquare,Smartphone,Wrench} from 'lucide-react';
import ThemePicker from './theme-picker.jsx';
import {SectionPicker} from './page-sections.jsx';

const categories=[
 {id:'appearance',label:'外观与窗口',icon:SlidersHorizontal},
 {id:'models',label:'模型与协作',icon:MessagesSquare},
 {id:'connection',label:'手机连接',icon:Smartphone},
 {id:'maintenance',label:'运行维护',icon:Wrench},
];

function SettingRow({title,hint,children}){
 return <div className="ws-settings-option"><div><h3>{title}</h3>{hint&&<p>{hint}</p>}</div><div className="ws-settings-controls">{children}</div></div>;
}

export default function WorkstationPreferences({visible,call,onModels,onQuick,onNavigate,renderMaintenance}){
 const [active,setActive]=useState('appearance');
 const [connection,setConnection]=useState(null),[busy,setBusy]=useState('');
 const [feedback,setFeedback]=useState(null);
 const lock=useRef(false);
 async function run(group,action,payload={}){
  if(lock.current)return;
  lock.current=true;
  setBusy(action);
  setFeedback(null);
  try{
   const result=await call(action,payload);
   if(['workstation_remote_status','workstation_remote_start'].includes(action))setConnection(result);
   else if(result?.message)setFeedback({group,message:result.message});
   else if(action==='workstation_file_library_open')setFeedback({group,message:'已请求打开手机文件库。'});
  }catch(e){
   setFeedback({group,action,message:e.message||'操作未完成，请重试。',error:true});
  }finally{lock.current=false;setBusy('');}
 }
 useEffect(()=>{
  if(!visible||active!=='connection')return;
  const ready=()=>run('connection','workstation_remote_status');
  if(window.pywebview?.api?.call)ready();
  else window.addEventListener('pywebviewready',ready,{once:true});
  return()=>window.removeEventListener('pywebviewready',ready);
 },[visible,active]);
 const lastStatus=connection?(connection.online?'接收器已连接':'接收器未连接'):'接收器状态尚未获取';
 const status=busy==='workstation_remote_status'?'正在检查接收器…':busy==='workstation_remote_start'?'正在启动接收器…':
  feedback?.action==='workstation_remote_status'?'检查失败 · '+lastStatus:lastStatus;
 const panels={
  appearance:<>
   <SettingRow title="深浅主题" hint="与窗口顶部的主题按钮同步。"><ThemePicker/></SettingRow>
   <SettingRow title="聊天背景" hint="预览背景与强度，保存后应用到搭档聊天。"><ThemePicker showBackground/></SettingRow>
   <SettingRow title="窗口与后台" hint="收起到托盘后任务继续运行。"><button disabled={!!busy} onClick={()=>run('appearance','api_window_action',{action:'tray'})}>收起到托盘</button><button disabled={!!busy} onClick={()=>run('appearance','api_window_action',{action:'minimize'})}>最小化</button></SettingRow>
  </>,
  models:<>
   <SettingRow title="模型连接" hint="管理模型配置、本机通道和连接凭据。"><button onClick={()=>onModels('models')}>配置模型</button></SettingRow>
   <SettingRow title="分工与预算" hint="设置协作席位、轮数与调用上限。"><button onClick={()=>onModels('options')}>协作选项</button></SettingRow>
   <SettingRow title="快捷输入" hint="在小窗口准备一份交办草稿。"><button onClick={onQuick}>打开快捷指令</button></SettingRow>
   <SettingRow title="聊天实验室" hint="管理对话角色、风格和记忆。"><button onClick={()=>onNavigate('chat')}>打开聊天实验室</button></SettingRow>
  </>,
  connection:<>
   <p className="ws-connection-state" data-state={connection?.online?'online':connection?'offline':'unknown'} role="status"><span aria-hidden="true"/>{status}</p>
   <SettingRow title="接收器与配对" hint="在电脑启动接收器，再用手机扫码配对。">
    <button onClick={()=>onNavigate('remote')}>连接与配对</button>
    {connection&&!connection.online&&<button disabled={!!busy} onClick={()=>run('connection','workstation_remote_start')}>启动接收器</button>}
    <button disabled={!!busy} onClick={()=>run('connection','workstation_remote_status')}>检查状态</button>
   </SettingRow>
   <SettingRow title="手机文件库" hint="在本机专用文件夹整理手机需要取用的文件。"><button disabled={!!busy} onClick={()=>run('connection','workstation_file_library_open')}>打开文件库</button></SettingRow>
   <SettingRow title="跨网络连接" hint="在不同网络下连接时，可打开已安装的 Tailscale。"><button disabled={!!busy} onClick={()=>run('connection','workstation_tailscale_open')}>打开 Tailscale</button></SettingRow>
  </>,
  maintenance:<>
   {renderMaintenance(visible&&active==='maintenance')}
   <SettingRow title="桌宠与提醒" hint="从管家查看桌宠连接和提醒。"><button onClick={()=>onNavigate('companion')}>桌宠管理入口</button></SettingRow>
   <SettingRow title="桌面图标" hint="在工具里预览、应用或还原图标。"><button onClick={()=>onNavigate('icons')}>打开换装台</button></SettingRow>
  </>,
 };
 return <>
  <SectionPicker label="设置分类" items={categories} value={active} onChange={setActive}/>
  {categories.map(category=><section key={category.id} className="ws-card ws-settings-section ws-section-motion" hidden={active!==category.id} aria-labelledby={`ws-settings-${category.id}`}>
   <h2 id={`ws-settings-${category.id}`}>{category.label}</h2>
   {feedback?.group===category.id&&<p className={feedback.error?'ws-error':'ws-muted'} role={feedback.error?'alert':'status'}>{feedback.message}</p>}
   <div className="ws-settings-options">{panels[category.id]}</div>
  </section>)}
 </>;
}
