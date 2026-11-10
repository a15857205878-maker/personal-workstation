import React,{useEffect,useRef,useState} from 'react';
import ThemePicker from './theme-picker.jsx';

function SettingRow({title,hint,children}){return <div className="ws-settings-option"><div><strong>{title}</strong><p>{hint}</p></div><div className="ws-settings-controls">{children}</div></div>;}
export default function WorkstationPreferences({visible,call,onModels,onQuick,onNavigate}){
 const [connection,setConnection]=useState(null),[busy,setBusy]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const lock=useRef(false);
 async function run(action,payload={}){
  if(lock.current)return;lock.current=true;setBusy(action);setError('');setNotice('');
  try{const result=await call(action,payload);if(['workstation_remote_status','workstation_remote_start'].includes(action))setConnection(result);else if(result?.message)setNotice(result.message);else if(action==='workstation_file_library_open')setNotice('已请求打开手机文件库。');}
  catch(e){setError(e.message||'操作未完成，请重试。');}
  finally{lock.current=false;setBusy('');}
 }
 useEffect(()=>{if(!visible)return;const ready=()=>run('workstation_remote_status');if(window.pywebview?.api?.call)ready();else window.addEventListener('pywebviewready',ready,{once:true});return()=>window.removeEventListener('pywebviewready',ready);},[visible]);
 return <>
  {error&&<p className="ws-error" role="alert">{error}</p>}{notice&&<p className="ws-muted" role="status">{notice}</p>}
  <div className="ws-preferences-grid">
   <article className="ws-card"><h2>外观与窗口</h2><p className="ws-muted">常用偏好，调整后立即生效。</p><div className="ws-settings-options">
    <SettingRow title="深浅主题" hint="与顶部主题按钮同步，偏好自动保存。"><ThemePicker/></SettingRow>
    <SettingRow title="后台运行" hint="收起到右下角托盘，任务继续运行；点击托盘图标恢复。"><button disabled={!!busy} onClick={()=>run('api_window_action',{action:'tray'})}>收起到托盘</button></SettingRow>
    <SettingRow title="窗口与快捷输入" hint="最小化到任务栏；快捷指令使用原来的轻量输入栏。"><button disabled={!!busy} onClick={()=>run('api_window_action',{action:'minimize'})}>最小化</button><button onClick={onQuick}>快捷指令</button></SettingRow>
   </div></article>
   <article className="ws-card"><h2>模型与协作</h2><p className="ws-muted">沿用已有模型、历史和本次任务草稿。</p><div className="ws-settings-options">
    <SettingRow title="模型连接" hint="添加或编辑原模型配置、本机通道与密钥。"><button onClick={()=>onModels('models')}>配置模型</button></SettingRow>
    <SettingRow title="席位与任务预算" hint="在当前协作中调整执行席、审查席、轮数与请求上限。"><button onClick={()=>onModels('options')}>协作选项</button></SettingRow>
    <SettingRow title="聊天与角色" hint="原聊天实验室保留人格、记忆和交流设置。"><button onClick={()=>onNavigate('chat')}>打开聊天实验室</button></SettingRow>
   </div></article>
   <article className="ws-card"><h2>手机与连接</h2><p className="ws-muted" role="status">{busy==='workstation_remote_status'?'正在检查接收器…':connection?connection.online?'接收器已连接':'接收器未连接':'连接状态尚未获取'}</p><div className="ws-settings-options">
    <SettingRow title="远程接收器" hint="仅在点击启动时开启；配对和接收器管理沿用原连接页面。"><button disabled={!!busy} onClick={()=>run('workstation_remote_status')}>检查状态</button>{connection&&!connection.online&&<button disabled={!!busy} onClick={()=>run('workstation_remote_start')}>启动接收器</button>}<button onClick={()=>onNavigate('remote')}>连接与配对</button></SettingRow>
    <SettingRow title="跨网络连接" hint="打开已安装的 Tailscale；不更改网络或防火墙设置。"><button disabled={!!busy} onClick={()=>run('workstation_tailscale_open')}>打开 Tailscale</button></SettingRow>
   </div></article>
   <article className="ws-card"><h2>资源与维护</h2><p className="ws-muted">素材、手机取用文件与桌宠设置入口。</p><div className="ws-settings-options">
    <SettingRow title="图标换装台" hint="添加、预览、应用或还原图标，沿用原素材文件夹。"><button onClick={()=>onNavigate('icons')}>打开换装台</button></SettingRow>
    <SettingRow title="手机文件库" hint="把需要手机取用的文件放入原专用文件夹。"><button disabled={!!busy} onClick={()=>run('workstation_file_library_open')}>打开文件库</button></SettingRow>
    <SettingRow title="桌宠与提醒" hint="通知、勿扰和陪伴设置仍由原桌宠管理。"><button onClick={()=>onNavigate('companion')}>桌宠管理入口</button></SettingRow>
   </div></article>
  </div>
 </>;
}
