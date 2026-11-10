export const STARTER_TASKS={
 "docx": "请制作一份可下载的 DOCX 周计划。\n包括：本周目标、周一到周日安排、待办清单。每天留出学习、工作和休息时间，用简洁中文。安排作为可修改的示例，不编造我的个人经历。",
 "xlsx": "请制作一份采购预算 Excel：牛奶2盒，每盒12元；面包3袋，每袋8元；鸡蛋1盒18元。\n列出品名、数量、单价、小计和总额，使用公式计算，检查汇总结果，实际生成可编辑的 XLSX 文件。",
 "pptx": "请制作一份3页的可编辑 PPTX，主题是“我的一周工作计划”。\n第1页：本周目标；第2页：每日安排；第3页：检查清单。用简洁中文和蓝白配色，不超过5个要点/页。实际生成文件，材料不足时明确说明。"
};
export function starterTask(format,current=""){return current.trim()?current:(STARTER_TASKS[format]||current);}

export function taskVoice(task={},connected=true){
 if(!connected)return '连接暂时断开，已保留上次读取的记录。恢复连接后再核对进度，请不要重复提交。';
 if(['failed','失败','needs_attention','interrupted'].includes(task.status))return '这一步需要处理。先看看错误和执行记录，再决定是否重试。';
 if(task.status==='stopping')return '正在请求停止，请稍等电脑确认；已经发出的请求可能仍会计费。';
 if(['cancelled','已取消'].includes(task.status))return '本次处理已取消，已有记录和成果为你保留，可以随时回看。';
 if(['completed','已完成'].includes(task.status))return task.files?.length?'成果文件已就绪。可以先预览，想调整的地方直接写在下方。':(!task.output_format||task.output_format==='text')?'本轮文字已完成。先看看回复，需要调整时再准备下一轮。':'这轮处理已结束，但还未收到可下载文件。先看看执行记录，再决定下一步。';
 if(['running','执行中'].includes(task.status))return task.stage?'正在进行：'+String(task.stage).slice(0,80)+'。进度会在这里更新，你也可以补充要求。':'电脑正在处理，进度会在这里更新。你可以补充要求，无需重复提交。';
 return '把目标和参考材料准备好，检查清楚后再确认开始。';
}

export function collaborationSignals(task={}){
 const steps=task.steps||[],round=Math.max(Number(task.round)||0,...steps.map(s=>Number(s.round)||0));
 const current=steps.filter(s=>(Number(s.round)||0)===round);
 return [['制作','提案'],['审查','审查'],['修订','修订']].map(([label,key])=>{
  const step=[...current].reverse().find(s=>String(s.stage||'').includes(key));
  const state=step?.state==='completed'?'done':step?.state==='failed'?'error':step?.state==='running'&&task.status==='running'?'running':!step&&task.status==='running'&&String(task.stage||'').includes(key)?'running':'waiting';
  return {label,state,text:({done:'已完成',error:'需处理',running:'进行中',waiting:'待进行'})[state]};
 });
}

export const PARTNER_NAV=[
 {id:'partner',label:'搭档',icon:'chat',secondary:['work','chat','companion','overview']},
 {id:'tasks',label:'任务',icon:'tasks',secondary:[]},
 {id:'artifacts',label:'成果',icon:'artifacts',secondary:['site-materials']},
 {id:'pack',label:'工具',icon:'tools',secondary:['icons']},
 {id:'games',label:'休闲',icon:'leisure',secondary:['wheel','reading','town']},
];
export function partnerState(session,history=false){return history?'history':!session?'welcome':['running','stopping'].includes(session.status)?'running':'result';}
export function checkedDraft(plan,attachments=[]){return {plan:JSON.parse(JSON.stringify({...plan,task:plan.task.trim()})),attachments:JSON.parse(JSON.stringify(attachments))};}
export function revisionDraft(source,text,plan,include={}){
 if(!text.trim())throw Error('请先填写修改要求。');
 const context=[];
 if(include.goal&&source.task)context.push('原目标：'+source.task);
 if(include.result){const final=[...(source.steps||[])].reverse().find(s=>s.state==='completed'&&s.content);if(final)context.push('原公开成果摘录：'+final.content.slice(0,3500));if(source.files?.length)context.push('原成果仅供参考，未附加二进制文件：'+source.files.map(a=>a.name).join('、'));}
 const task=[...context,'本轮修改要求：'+text.trim(),'这是新一轮协作；保留原成果，不覆盖原件。'].join('\n\n');
 if(task.length>8000)throw Error('带入内容超过8000字，请减少原成果摘录。');
 return {...plan,task};
}
const ORIGIN='http://127.0.0.1:8765';
export function sessionEmbedUrl(value){try{const url=new URL(value);if(url.origin!==ORIGIN||url.username||url.password)return '';url.searchParams.set('desktop_embed','1');return url.href;}catch{return '';}}
export function previewUrl(value,session){try{const url=new URL(value),base=new URL(session);return url.origin===ORIGIN&&url.origin===base.origin&&!url.username&&!url.password&&['/preview-viewer','/file-viewer'].includes(url.pathname)&&!!base.searchParams.get('token')&&url.searchParams.get('token')===base.searchParams.get('token')?url.href:'';}catch{return '';}}

export function stepProgress(session){const steps=session?.steps||[];const planned=Number(session?.planned_calls)||Number(session?.rounds)*3||steps.length;return {completed:steps.filter(step=>step.state==='completed').length,total:Math.max(0,planned||0)};}
