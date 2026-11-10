(function(root){
'use strict';
function classify(value){
 const text=String(value||'').trim();if(!text)return {kind:'clarify',message:'想做什么？先写一句目标。'};
 if(/^(例如|比如|什么|怎么|如何|为什么|请问|是否|能不能|能否)/.test(text)||/(不要|(?<![分识区辨])别|不用).{0,6}(执行|派发|分发|运行).{0,4}(任务|指令)?/.test(text))return {kind:'chat'};
 const intent=text.split(/[，,。；;！!？?\n]/).map(part=>part.replace(/(?:不要|不用|不想|(?<![分识区辨])别).*/, '')).filter(part=>part.trim()).join('，');
 if(!intent||/(解释|告诉我|想知道|什么是|怎么|如何|原理)/.test(intent))return {kind:'chat'};
 const prefix='(?:(?:请|帮我|麻烦|我要|我想要|我想|给我)\\s*)?';
 if(new RegExp('^'+prefix+'(?:查看(?:任务)?成果|查看文件(?:列表)?|文件列表)\\s*$').test(intent))return {kind:'files',action:'list',query:''};
 const file=new RegExp('^'+prefix+'(预览|下载)\\s*(.*)$').exec(intent);
 if(file){
  const query=file[2].trim();
  if(['','文件','成果','原文件','成果文件','任务成果','这个文件','该文件'].includes(query))return {kind:'files',action:file[1]==='预览'?'preview':'download',query:''};
  if(/^[^\\/:\x00-\x1f]{1,220}\.[a-z0-9]{1,12}$/i.test(query))return {kind:'files',action:file[1]==='预览'?'preview':'download',query};
  return {kind:'clarify',message:'请用“查看成果、预览文件、下载文件”，或填写已有成果文件名；不接收电脑路径或网址。'};
 }
 const directive=/^(请|帮我|麻烦|我要|我想|我需要|给我|用|使用|让|安排|生成|制作|做|写|起草|整理|打包|压缩|单任务|单模型|双模型|两个模型|把|将|不要|查找|搜索|检索|查阅|查询|修改|调整|优化|美化|检查|测试|修复|排查|解决|操作|打开|启动|运行|撰写|润色|翻译|总结|归纳|画)/.test(intent);
 if(!directive)return {kind:'chat'};
 const dual=/(双模型|两个模型|两位模型)/.test(intent)&&!/(不要|不用|不想|别).{0,4}(双模型|两个模型|两位模型)/.test(text);
 if(dual)return /(设计|分析|生成|制作|写|整理|研究|规划|检查|做|排查|修复|解决|翻译|总结|润色|查找|操作)/.test(text)?{kind:'collab'}:{kind:'clarify',message:'想让双模型完成什么？再补一句具体目标。'};
 // A requested piece of writing can mention tools without requesting those tools.
 if(/^(?:(?:请|帮我|麻烦|我要|我想要|我想|给我)\s*)*(?:翻译|润色|总结|归纳)/.test(intent)||/(?:写|撰写|起草).{0,80}(?:邮件|通知|说明文档)/.test(intent)||/(?:写|撰写|起草).*(?:关于|介绍|有关).*(?:文档|报告|文章|说明)/.test(intent))return {kind:'task',task_type:'text'};
 const slides='(?:pptx?|幻灯片|演示文稿)',sheets='(?:excel|xlsx|表格|预算表|收支表|统计表|清单表)',join='.{0,50}(?:和|以及|同时|另外|再生成).{0,30}';
 if(new RegExp(slides+join+sheets+'|'+sheets+join+slides,'i').test(intent))return {kind:'clarify',message:'这次同时包含PPT和表格。请先选一个独立任务，或明确使用双模型处理整体目标。'};
 if(/(打包|压缩)/i.test(intent)&&!/(写|起草|撰写).*(文档|说明|报告|文章)/.test(intent)&&!/(不要|不用|不想|别).{0,4}(打包|压缩)/.test(text)){
  if(/压缩(图片|视频|音频)/.test(text)&&!/(文件|zip|打包)/i.test(text))return {kind:'clarify',message:'目前先支持文件生成ZIP，图片或视频压缩还没有接入。'};
  return {kind:'pack'};
 }
 const rules=[
  ['software_error',/(处理|修复|排查|解决).*(报错|错误|崩溃|异常|故障)/],
  ['web_edit',/(修改|调整|优化|美化).*(网页|网站|页面)/],
  ['web_check',/(检查|测试|审查).*(网页|网站|页面)/],
  ['software_operation',/软件操作|操作.*(软件|程序|应用)|(启动|打开|运行).*(软件|程序|应用)|使用.*(软件|程序|应用).*(操作|导出|转换)/],
  ['research',/(查找|查询|查阅|检索|搜索).*(资料|文献|论文|来源|信息|教程)/],
  ['pptx',/ppt|幻灯片|演示文稿/i],
  ['xlsx',/excel|xlsx|电子表格|表格|收支表|预算表|统计表|清单表/i],
  ['image',/生成.*(图片|图像)|画一|绘制|插画|设计.*(海报|插图)/],
  ['text',/文档|报告|方案|文章|说明|周报|通知|邮件|计划|摘要|总结|归纳|润色|翻译|单任务|单模型/]
 ];
 const match=rules.find(([,pattern])=>pattern.test(intent));return match?{kind:'task',task_type:match[0]}:{kind:'chat'};
}
const taskExamples={text:'帮我写一份项目进展文档',pptx:'帮我制作一份项目介绍PPT',xlsx:'帮我整理一份预算表',image:'帮我生成一张项目封面图片',research:'帮我查找这个课题的参考资料',web_check:'帮我检查这个网页的布局',web_edit:'帮我修改这个网页的布局',software_operation:'帮我操作这个软件导出数据',software_error:'帮我排查这个软件的报错'};
function taskCommands(tasks){return (tasks||[]).filter(t=>t&&typeof t.id==='string'&&(taskExamples[t.id]||t.id==='document')).map(t=>({id:t.id,label:t.label||'制作文档',example:taskExamples[t.id]||taskExamples.text}));}
function chooseTask(type,catalog){
 const tasks=catalog?.task_catalog?.tasks||[],roles=catalog?.task_catalog?.roles||{};
 const task=tasks.find(t=>t.id===type)||(type==='text'?tasks.find(t=>/文本|文档/.test(t.label)):null);
 if(!task)throw Error('这个任务类型尚未接入电脑，请改用已配置的任务。');
 const agents=(task.agents||[]).filter(a=>roles[a.role_ref]);const preferred=agents.find(a=>a.role_ref===task.default_role_ref),available=agents.filter(a=>roles[a.role_ref].can_run===true);
 const agent=(preferred&&roles[preferred.role_ref].can_run===true?preferred:null)||available[0]||preferred||agents[0];
 if(!agent)throw Error('这个任务还没有可用的执行角色，请先在电脑配置。');
 return {task_type:task.id,role:agent.role_ref,manual:roles[agent.role_ref].can_run!==true};
}
function chooseModels(catalog,primary,reviewer){
 const enabled=(catalog?.profiles||[]).filter(p=>p.id&&(!p.requires_key||p.has_key));
 if(enabled.length<2)throw Error('双模型需要两个可用配置，请先在电脑设置中完成配置。');
 const a=enabled.find(p=>p.id===primary)||enabled[0];const b=enabled.find(p=>p.id===reviewer&&p.id!==a.id)||enabled.find(p=>p.id!==a.id);return {primary:a.id,reviewer:b.id};
}
const api={classify,taskCommands,chooseTask,chooseModels};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.WorkstationCommands=api;
})(typeof window!=='undefined'?window:globalThis);
