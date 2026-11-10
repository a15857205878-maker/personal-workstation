import React,{useEffect,useState} from 'react';
const LABELS={limited:'已达限额',available:'官网确认可用',unknown:'待核实',login_required:'需要登录',read_failed:'读取失败',stale:'记录已过期',due:'到恢复时间 · 待核实'};
const time=value=>{if(!value)return '尚未核对';const d=new Date(value);return Number.isNaN(d.getTime())?'待核实':d.toLocaleString('zh-CN',{timeZone:'Asia/Tokyo',hour12:false});};
export default function ClaudeQuota({call}){
  const [record,setRecord]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{
    let ended=false,pending=false;
    async function read(){if(pending||!window.pywebview?.api?.call)return;pending=true;try{const r=await call('quota');if(!ended){setRecord(r);setError('');}}catch{if(!ended)setError('检查记录暂时不可读，不代表额度可用。');}finally{pending=false;}}
    read();const timer=setInterval(read,60000);window.addEventListener('pywebviewready',read);
    return()=>{ended=true;clearInterval(timer);window.removeEventListener('pywebviewready',read);};
  },[call]);
  async function action(open){if(busy)return;setBusy(true);setError('');try{if(open)await call('quota_open');else setRecord(await call('quota'));}catch(e){setError(e.message);}finally{setBusy(false);}}
  const state=record?.effective_state||'unknown';
  return <section className="station-quota" aria-label="Claude PPT额度监控">
    <div className="station-card-head"><div><h2>Claude · PPTX 额度监控</h2><p className="station-hint">每日 09:00（日本时间）官网核对 · 此处展示最近检查记录</p></div><span className={'station-badge'+(state==='limited'?' station-quota-limited':'')}>{LABELS[state]||'待核实'}</span></div>
    <div className="station-meta"><span>最近核对：{time(record?.checked_at)}</span><span>恢复时间：{record?.reset_at?time(record.reset_at):(record?.reset_text||'官网未提供')}</span></div>
    {['due','stale','unknown','login_required','read_failed'].includes(state)&&<p className="station-hint">需要重新核对官网；时间到达或检查失败不会自动判定可用。</p>}
    {error&&<p className="station-warning" role="alert">{error}</p>}
    <div className="station-actions"><button className="station-button station-mini" disabled={busy} onClick={()=>action(false)}>读取最新检查记录</button><button className="station-button station-mini" disabled={busy} onClick={()=>action(true)}>打开 Claude 核对</button></div>
    {record?.source_text&&<details className="station-quota-evidence"><summary>官网提示与监控说明</summary><p>{record.source_text}</p><p>来源：{record.source_url}</p><p>当前免费账号未提供可见百分比。定时检查依赖电脑、Codex和已登录的Chrome可用，不会发送生成任务或自动付费；不会阻止你自行在客户端操作。</p></details>}
  </section>;
}
