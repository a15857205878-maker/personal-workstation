(function(root){
'use strict';
function bucket(value){
 if(['running','stopping','执行中','排队中','等待交接','queued','pending'].includes(value))return 'active';
 if(['草稿','结果待确认','需要检查','interrupted','needs_attention'].includes(value))return 'attention';
 if(['completed','已完成'].includes(value))return 'completed';
 if(['failed','失败'].includes(value))return 'failed';
 return 'other';
}
function nativeTasks(rows){return rows.filter(t=>t&&typeof t.id==='string'&&/^[a-f0-9]{32}$/.test(t.id)&&['codex','deepseek-flash','codex-deepseek-code'].includes(t.agent));}
function records(list={},filter='all',query=''){
 const all=[...(list.tasks||[]).map(x=>({...x,kind:'task'})),...(list.collaborations||[]).map(x=>({...x,kind:'collaboration'})),...(list.native||[]).map(x=>({...x,kind:'native'}))];
 const needle=query.trim().toLocaleLowerCase();
 return all.filter(x=>(filter==='all'||bucket(x.status)===filter)&&(!needle||String(x.title||x.goal||x.instruction||x.task||'').toLocaleLowerCase().includes(needle)));
}
function summary(list){const all=records(list);return {active:all.filter(x=>bucket(x.status)==='active').length,attention:all.filter(x=>bucket(x.status)==='attention').length,completed:all.filter(x=>bucket(x.status)==='completed').length,total:all.length};}
function viewFromHash(hash){const key=hash.replace(/^#/,'');return ['home','tasks','new','sessions','files','connection'].includes(key)?key:'sessions';}
function sessionCollaborationIntent(event,origin,source){const data=event?.data;if(!source||event.origin!==origin||event.source!==source||data?.type!=='workstation-session-collaboration'||typeof data.text!=='string'||data.text.length>8000||typeof data.sourceText!=='string'||data.sourceText.length>20000||typeof data.hasAttachments!=='boolean')return null;return {text:data.text,sourceText:data.sourceText,hasAttachments:data.hasAttachments};}
function validPreview(value,origin,token){try{const url=new URL(value);return url.origin===origin&&['/preview-viewer','/file-viewer'].includes(url.pathname)&&url.searchParams.get('token')===token?url.href:null;}catch{return null;}}
function keyboardState(layoutHeight,visualHeight,editing,wasOpen=false){if(!Number.isFinite(layoutHeight)||!Number.isFinite(visualHeight)||visualHeight<=0)return false;const reduction=layoutHeight-visualHeight;return wasOpen?reduction>80:!!editing&&reduction>140;}
function typingTarget(node){if(!node||node.disabled||node.readOnly)return false;if(node.isContentEditable)return true;if(['TEXTAREA','SELECT'].includes(node.tagName))return true;return node.tagName==='INPUT'&&!['file','checkbox','radio','button','submit','reset','range','color','hidden'].includes(node.type);}
function frameHeight(visualHeight,offsetTop,frameTop,navigationHeight,keyboard){return Math.max(160,Math.round(visualHeight+offsetTop-frameTop-(keyboard?8:navigationHeight+12)));}
function carriedGoal(source,destination){return destination.trim()?destination:source;}
function taskSuggestion(goal,tasks,currentId){
 if(/不要|不用|不想|请问|如何|怎么/.test(goal))return null;
 const rules=[['web_edit',/修改网页|修改网站/],['web_check',/检查网页|检查网站/],['pptx',/ppt|幻灯片|演示文稿/i],['xlsx',/excel|xlsx|电子表格|表格|收支表|预算表|统计表|清单表/i],['image',/生成图片|画一|绘制|插画/],['software_error',/报错|异常信息|错误日志/],['research',/查找资料|查询资料|检索资料|搜索资料/],['text',/写.*文档|起草|撰写|写.*文章/]];
 const match=rules.find(([,pattern])=>pattern.test(goal));if(!match||match[0]===currentId)return null;
 const task=(tasks||[]).find(t=>t.id===match[0]&&t.agents?.length);return task?{id:task.id,label:task.label}:null;
}
function viewContext(view){return {title:({home:'个人工作站',tasks:'成果与进度',new:'布置任务',detail:'任务详情',sessions:'搭档',files:'文件与文字',connection:'连接与设置'})[view]||'个人工作站',parent:({new:'tasks',detail:'tasks',files:'connection'})[view]||null};}
function partnerHint(status,manual=false){const options={manual};
 const aliases={'草稿':'draft','排队中':'queued','执行中':'running','等待交接':'waiting_handoff','需要用户处理':'needs_user','结果待确认':'awaiting_confirmation','已完成':'completed','失败':'failed','已取消':'cancelled','需要检查':'needs_check'};
 const state=aliases[status]||status;
 if(options.archived)return '这份任务已归档。先回看内容，需要继续时再恢复记录。';
 if(options.readOnly)return '这是只读的历史记录。可以回看回复，再返回当前协作。';
 if(options.manual&&['draft','waiting_handoff','needs_user'].includes(state))return '目标已保存，接下来需要在电脑客户端完成交接。';
 return ({draft:'先检查目标与参考材料，确认清楚后再开始处理。',queued:'任务已排队，轮到它时会更新进度，请不要重复提交。',running:'电脑正在处理，进度会在这里更新。可以补充要求，请不要重复提交。',stopping:'正在请求停止，先等状态更新。已发出的请求可能仍计费。',waiting_handoff:'目标已保存，接下来需要在电脑客户端完成交接。',needs_user:'这一步需要你处理。先看任务说明与记录，再继续交接。',awaiting_confirmation:'回复已经回来，先看看结果，符合预期后再确认完成。',completed:'本次记录已完成。先看看回复和成果，需要调整时再继续。',failed:'这次处理遇到了问题。先看看错误说明，再决定重试还是调整要求。',cancelled:'这次处理已取消。记录会保留，可以先核对已产生的内容。',interrupted:'上次处理已中断。先核对实际进度，再决定后续处理。',needs_check:'这项任务需要核对。先看错误或处理记录，确认实际进度。'})[state]||'先核对当前状态与记录，再决定下一步。';
}
function fileTaskChoice(tasks,selected){return selected?.kind==='task'&&typeof selected.id==='string'&&(tasks||[]).some(task=>task.id===selected.id)?selected.id:'';}
function workbenchPreviewable(name){return /\.(pdf|png|jpe?g|webp|bmp|gif|tiff?|docx|pptx|xlsx|odt|odp|ods|txt|md|csv|json|py|js|log)$/i.test(String(name||''));}
function taskKindLabel(task,kind){if(kind==='native')return task.agent==='codex-deepseek-code'?'网页与代码项目':task.agent==='deepseek-flash'?'DeepSeek任务':'Codex任务';return kind==='collaboration'?'双模型协作':task?.task_type==='program_pack'?'电脑文件打包':'独立任务';}
function compactTaskResult(task={},kind='task',connected=false){const files=(task.files||[]).filter(f=>typeof f.name==='string'&&f.name);const expected=({docx:'docx',xlsx:'xlsx',pptx:'pptx'})[kind==='collaboration'?task.output_format:task.task_type];return connected===true&&['completed','已完成'].includes(task.status)&&!task.error&&files.length>0&&files.every(f=>!(Number(f.size)>10*1024*1024))&&(!expected||files.some(f=>f.name.toLowerCase().endsWith('.'+expected)));}
function taskSnapshot(task={},kind='task',manual=false,connected=true){
 const status=task.status,files=(task.files||[]).filter(f=>typeof f.name==='string'&&f.name);
 const states={
  '草稿':['等待确认','先核对目标与材料，确认后电脑才会执行。'],
  '排队中':['等待电脑执行','电脑已接收，正在排队，请勿重复提交。'],queued:['等待电脑执行','电脑已接收，正在排队，请勿重复提交。'],pending:['等待电脑执行','记录显示等待中，请先核对进度。'],
  '执行中':['电脑处理中','执行尚未结束，返回的文字可能还不完整。'],running:['电脑处理中','执行尚未结束，返回的文字可能还不完整。'],stopping:['正在停止','已请求停止，先等待电脑回报；已发出的调用可能仍计费。'],
  '结果待确认':['核对结果','内容已返回，请检查正文和成果文件，再确认完成。'],
  '已完成':['已完成','请查看下方成果。完成状态不代表一定生成了文件。'],completed:['已完成','请查看下方成果。完成状态不代表一定生成了文件。'],
  '失败':['需要处理','请核对错误与处理记录，修正后再决定下一步。'],failed:['需要处理','请核对错误与处理记录，修正后再决定下一步。'],
  '需要检查':['需要核对','回执或进度尚未确定，请在电脑核对，不要重复提交。'],interrupted:['需要核对','运行曾中断，请在电脑核对，不要重复提交。'],
  '等待交接':['电脑端交接','目标已保存，请在电脑客户端继续，并导入成果。'],'需要用户处理':['需要处理','请在电脑查看任务记录，完成需要你处理的步骤。'],
  '已取消':['已取消','保留已有内容；取消不保证远端已发出的请求立即停止。'],cancelled:['已取消','保留已有内容；取消不保证远端已发出的请求立即停止。']
 };
 let [phase,hint]=states[status]||['需要核对','尚不认识这个状态，请在电脑查看原记录。'];
 if(kind==='collaboration'&&status==='running'&&typeof task.stage==='string'&&task.stage.trim())phase=({'提案':'制作','审查':'审查','修订':'修订','生成文件':'生成文件'})[task.stage]||task.stage.slice(0,60);
 if(manual&&['草稿','等待交接','需要用户处理'].includes(status)){phase='电脑端交接';hint='目标已保存，需要在电脑客户端完成交接；尚未自动执行。';}
 if(files.length&&['completed','已完成'].includes(status))hint='文件已生成，可先预览核对，再下载原件。';
 if(task.error)hint=String(task.error);
 if(!connected)hint='当前显示上次读取的状态。请恢复连接后核对最新进度，不要重复提交。';
 const hasText=!!String(task.result||'').trim()||(task.steps||[]).some(step=>!!String(step.content||'').trim());
 let output=files.length?'已有 '+files.length+' 个成果文件，可从下方下载。':hasText?'已有文字回复，当前没有可下载文件。':'当前没有可下载文件。';
 const expected=({docx:'DOCX',pptx:'PPTX',xlsx:'XLSX'})[kind==='collaboration'?task.output_format:task.task_type];
 if(expected&&!files.some(f=>f.name.toLowerCase().endsWith('.'+expected.toLowerCase())))output+=' 尚未收到'+expected+'成果文件。';
 if(files.some(f=>Number(f.size)>10*1024*1024))output+=' 超过10MiB的文件请在电脑取用。';
 return {phase,hint,output,type:taskKindLabel(task,kind)};
}
function mount({token,onOpen,onCommand,onSessionCollaboration,commandStorageKey}){
 if(!root.document||new URLSearchParams(location.search).get('desktop_embed')==='1')return null;
 const doc=root.document,$=id=>doc.getElementById(id),main=doc.querySelector('main');
 let detailParent='tasks';let list={},view=viewFromHash(location.hash),filter='all',query='',connected=null,receiverReachable=null,working=false;const frames=new Map();
 function el(tag,text,cls){const x=doc.createElement(tag);if(text!==undefined)x.textContent=text;if(cls)x.className=cls;return x;}
 function button(text,fn,cls){const x=el('button',text,cls);x.type='button';x.onclick=fn;return x;}
 function link(text,path,cls){const x=el('a',text,cls);x.href=path+'?token='+encodeURIComponent(token);return x;}
 function symbol(name){const svg=doc.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('width','21');svg.setAttribute('height','21');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.7');svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');svg.setAttribute('aria-hidden','true');const p=doc.createElementNS(svg.namespaceURI,'path');p.setAttribute('d',({home:'M3 10 12 3 21 10V21H15V14H9V21H3Z',tasks:'M8 4H20V21H4V4H8M8 3H16V7H8ZM8 12H16M8 16H13',sessions:'M21 11A9 9 0 0 1 5 17L2 20 3 14A9 9 0 1 1 21 11ZM8 11H8.01M12 11H12.01M16 11H16.01',connection:'M3 4H21V17H3ZM8 21H16M12 17V21',plus:'M12 5V19M5 12H19'})[name]);svg.append(p);return svg;}
 function switchView(next,force=false){if(['home','new'].includes(next))next='sessions';if(!force&&(working||$('confirmation')?.open))return;view=next;if(view!=='sessions')doc.body.dataset.webPreview='closed';if(['sessions','files'].includes(view))ensureFrame(view);if(view==='tasks')readNativeResults();doc.body.dataset.mobileView=view;const context={...viewContext(view),...(view==='detail'?{parent:detailParent}:{} )};headerBack.hidden=!context.parent;pageTitle.textContent=context.title;for(const [key,b]of navButtons)b.setAttribute('aria-current',key===view||key==='sessions'&&['home','new'].includes(view)||key==='tasks'&&view==='detail'||key==='connection'&&view==='files'?'page':'false');if(['home','tasks','new','sessions','files','connection'].includes(view))history.replaceState(null,'','#'+view);root.requestAnimationFrame(()=>{root.scrollTo({top:0,left:0,behavior:"instant"});scheduleViewport();});}
 doc.body.classList.add('mobile-controller');doc.body.dataset.mobileView=view;
 const top=el('div',undefined,'mc-top');const brand=el('div',undefined,'mc-brand');brand.append(symbol('connection'));const names=el('div');names.append(el('small','PERSONAL WORKSTATION'),el('strong','个人工作站'));brand.append(names);const pageTitle=names.querySelector('strong');const headerBack=button('‹',()=>{const parent=view==='detail'?detailParent:viewContext(view).parent;if(parent)switchView(parent);},'mc-header-back');headerBack.id='mcHeaderBack';headerBack.setAttribute('aria-label','返回上一层');top.prepend(headerBack);const state=el('span','正在连接','mc-connection');state.id='mcConnection';state.setAttribute('role','status');top.append(brand,state);main.prepend(top);
 const home=el('section',undefined,'mc-home');home.id='mcHome';const hero=el('div',undefined,'mc-hero');hero.append(el('span','你的电脑，随时待命','mc-eyebrow'),el('h1','把想法，往前推进一步'),el('p','你来定目标，工作站帮你接着做。'));const create=button('独立任务',()=>begin('task'),'mc-create');create.prepend(symbol('plus'));const dual=button('双模型协作',()=>begin('collab'),'mc-create mc-dual');dual.prepend(symbol('tasks'));const starts=el('div',undefined,'mc-start-actions');starts.append(create,dual);const manualModes=el('details',undefined,'mc-entry-options');manualModes.append(el('summary','更多处理方式'),starts);hero.append(manualModes);home.append(hero);
 const commandForm=el('form',undefined,'mc-command-form');commandForm.id='mcCommandForm';const commandLabel=el('label','告诉搭档，你想做什么？');commandLabel.htmlFor='mcCommandInput';const commandInput=el('textarea');commandInput.id='mcCommandInput';commandInput.maxLength=8000;commandInput.placeholder='例如：帮我写一份文档 / 用双模型设计网页 / 把电脑已选文件打包';const commandSend=button('发送指令',null,'primary');commandSend.id='mcCommandSend';commandSend.type='submit';const commandNotice=el('p','支持独立任务、双模型、打包与成果指令；发送后先检查，再确认执行。','mc-command-feedback');commandNotice.id='mcCommandFeedback';commandNotice.setAttribute('role','status');commandForm.append(commandLabel,commandInput,commandSend,commandNotice);hero.after(commandForm);try{if(commandStorageKey)commandInput.value=localStorage.getItem(commandStorageKey)||'';}catch{}commandInput.addEventListener('input',()=>{try{if(commandStorageKey)localStorage.setItem(commandStorageKey,commandInput.value);}catch{}});commandForm.onsubmit=async event=>{event.preventDefault();if(working||$('confirmation')?.open||!commandInput.value.trim())return;commandSend.disabled=true;try{await onCommand?.(commandInput.value.trim());}catch(error){commandFeedback(error.message,true);}finally{commandSend.disabled=false;}};commandInput.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();commandForm.requestSubmit();}});
 const fileShortcuts=el('div',undefined,'mc-file-shortcuts');fileShortcuts.setAttribute('aria-label','成果快捷指令');for(const text of ['查看成果'])fileShortcuts.append(button(text,()=>{if(!working)onCommand?.(text);}));commandForm.append(fileShortcuts);
 const taskCommandsPanel=el('details',undefined,'mc-task-commands');taskCommandsPanel.id='mcTaskCommands';const taskCommandsList=el('div',undefined,'mc-task-command-list');taskCommandsPanel.append(el('summary','任务指令'),el('p','点选只填入示例，补充具体目标与资料后发送。模型与执行方式会在检查时显示。','mc-scope'),taskCommandsList);commandForm.append(taskCommandsPanel);
 function renderTaskCommands(tasks){taskCommandsList.replaceChildren();const commands=root.WorkstationCommands.taskCommands(tasks);taskCommandsPanel.hidden=!commands.length;for(const item of commands){const b=button(item.label,()=>{if(working)return;if(commandInput.value.trim()){commandFeedback('输入框已有内容，已为你保留；清空后可填入任务示例。');return;}commandInput.value=item.example;commandInput.dispatchEvent(new Event('input',{bubbles:true}));commandInput.focus();commandInput.setSelectionRange(0,commandInput.value.length);commandFeedback('已填入示例，请按你的目标修改；发送后检查任务和执行角色。');});b.dataset.taskCommand=item.id;taskCommandsList.append(b);}}
 taskCommandsPanel.hidden=true;
 function commandFeedback(text,error=false){commandNotice.textContent=text;commandNotice.classList.toggle('error',error);scheduleViewport();}
 const stats=el('div',undefined,'mc-stats'),statValues={};for(const [key,label]of [['active','进行中'],['attention','待确认'],['completed','已完成']]){const b=button('',()=>{filter=key;applyFilter();switchView('tasks');});const count=el('strong','—');statValues[key]=count;b.append(count,el('span',label));stats.append(b);}home.append(stats);
 const shortcuts=el('div',undefined,'mc-shortcuts');shortcuts.append(button('查看电脑任务  →',()=>switchView('tasks')),button('继续电脑会话  →',()=>switchView('sessions')));home.append(shortcuts);
 const recentTitle=el('div',undefined,'mc-section-title');recentTitle.append(el('h2','优先处理'),button('查看全部',()=>switchView('tasks')));home.append(recentTitle);const recent=el('div',undefined,'mc-recent');home.append(recent);const scope=el('p','仅显示手机创建的工作站任务；电脑已有对话请进入“会话”。','mc-scope');home.append(scope);home.prepend(stats);home.prepend(hero);hero.after(commandForm);recent.after(shortcuts);top.after(home);
 const heading=el('div',undefined,'mc-view-heading');const headingTitle=el('h1','成果与进度');heading.append(headingTitle,button('返回对话',()=>switchView('sessions'),'mc-new-small'));heading.id='mcTaskHeading';home.after(heading);
 const filters=el('div',undefined,'mc-filters');const filterButtons=[];for(const [key,label]of [['all','全部'],['active','进行中'],['attention','待确认'],['completed','已完成'],['failed','失败']]){const b=button(label,()=>{filter=key;applyFilter();});b.dataset.filter=key;filterButtons.push(b);filters.append(b);}heading.after(filters);
 const search=el('input');search.type='search';search.placeholder='查找任务';search.setAttribute('aria-label','查找手机任务');search.className='mc-search';search.oninput=()=>{query=search.value;applyFilter();};filters.after(search);
 const listEmpty=el('p','这个分类下还没有任务。','mc-empty');listEmpty.hidden=true;$('records').after(listEmpty);
 const back=button('‹ 返回任务列表',()=>switchView(detailParent),'mc-detail-back');$('detail').prepend(back);$('detailMeta').after($('detailActions'));
 const userMessage=el('details',undefined,'mc-user-message');userMessage.append(el('summary','查看完整需求'),$('detailInstruction'));
 const stepHistory=el('details',undefined,'mc-step-history');stepHistory.id='mcStepHistory';stepHistory.append(el('summary','协作过程与回复'),$('steps'));const assistantMessage=el('div',undefined,'mc-assistant-message');assistantMessage.append(el('h3','进度与回复'),$('detailError'),stepHistory,$('result'),$('fileList'));assistantMessage.querySelector('#detailError').setAttribute('role','alert');
 const diagnostics=el('details',undefined,'mc-task-diagnostics');diagnostics.id='mcTaskDiagnostics';diagnostics.append(el('summary','处理记录'),$('detailMeta'),$('events'));const guidanceCard=el('div',undefined,'mc-partner-guidance');guidanceCard.id='mcPartnerGuidance';guidanceCard.setAttribute('role','note');guidanceCard.setAttribute('aria-label','搭档操作提示');const guidanceText=el('p');guidanceCard.append(el('small','接下来 · 操作提示'),guidanceText);let hintStatus=null,hintManual=false;function renderGuidance(){guidanceCard.hidden=hintStatus===null||!!lastDetail;const text=connected===true?partnerHint(hintStatus,hintManual):'暂时无法确认电脑的最新进度。先恢复连接，再核对记录。';if(guidanceText.textContent!==text)guidanceText.textContent=text;}function guidance(status,manual){hintStatus=status;hintManual=manual;renderGuidance();}guidanceCard.hidden=true;$('detailActions').after(guidanceCard,userMessage,assistantMessage,diagnostics);
 $('notePanel').querySelector('label').textContent='补充你的想法';
 const composeBack=button('‹ 返回任务列表',()=>switchView('tasks'),'mc-compose-back');doc.querySelector('nav.tabs').before(composeBack);

 // Move existing controls, not their values or handlers; desktop layout is unchanged.
 const taskAvatar=el('span',undefined,'partner-avatar');taskAvatar.dataset.person='user';taskAvatar.setAttribute('aria-hidden','true');$('detailTitle').classList.add('partner-user-title');$('detailTitle').before(taskAvatar);$('detailTitle').parentElement.classList.add('partner-user-title-row');
 const overview=el('section',undefined,'mc-task-overview');overview.id='mcTaskOverview';const assistantAvatar=el('span',undefined,'partner-avatar');assistantAvatar.dataset.person='assistant';assistantAvatar.setAttribute('aria-hidden','true');overview.append(assistantAvatar);overview.append(el('h3','任务状态与成果'));const destination=el('p',undefined,'mc-task-destination');destination.id='mcTaskDestination';const phase=el('strong');phase.id='mcTaskPhase';phase.setAttribute('role','status');const progressHint=el('p');progressHint.id='mcTaskNext';const outcome=el('p',undefined,'mc-output-summary');outcome.id='mcTaskOutput';overview.append(destination,phase,progressHint,el('h4','成果文件'),outcome,$('fileList'));userMessage.before(overview);overview.after($('fileList'),userMessage);let lastDetail=null;
 const signalList=el('ol',undefined,'partner-step-signals');signalList.setAttribute('aria-label','本轮协作步骤');overview.after(signalList);
 function renderTaskDetail(){if(!lastDetail)return;const value=taskSnapshot(lastDetail.task,lastDetail.kind,lastDetail.manual,connected===true);if(lastDetail.kind==='collaboration'&&!lastDetail.manual&&!lastDetail.task.error&&['running','stopping','completed','failed','cancelled','interrupted'].includes(lastDetail.task.status))value.hint=root.WorkstationPartnerTheme.taskVoice(lastDetail.task,connected===true);for(const [element,text]of [[destination,value.type+(lastDetail.destination?' · '+lastDetail.destination:'')+' · '+lastDetail.readAt+' 读取'],[phase,value.phase],[progressHint,value.hint],[outcome,value.output]])if(element.textContent!==text)element.textContent=text;signalList.replaceChildren();signalList.hidden=lastDetail.kind!=='collaboration';
 if(!signalList.hidden)for(const s of root.WorkstationPartnerTheme.collaborationSignals(lastDetail.task)){const li=el('li');li.dataset.state=s.state;if(s.state==='running')li.setAttribute('aria-current','step');const dot=el('span',undefined,'partner-signal-dot');dot.setAttribute('aria-hidden','true');li.append(dot,el('strong',s.label),el('small',s.text));signalList.append(li);}
 overview.setAttribute('aria-label','搭档 · 任务状态');overview.dataset.state=bucket(lastDetail.task.status);overview.dataset.compact=String(compactTaskResult(lastDetail.task,lastDetail.kind,connected===true));doc.body.dataset.partnerState=bucket(lastDetail.task.status);}
 function taskDetail(task,kind,manual,destination){const key=kind+':'+task.id+':'+task.status;if(stepHistory.dataset.state!==key){stepHistory.open=false;stepHistory.dataset.state=key;}lastDetail={task,kind,manual,destination,readAt:new Date().toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',second:'2-digit'})};renderTaskDetail();renderGuidance();}
 const taskSettings=el('details',undefined,'mc-advanced');taskSettings.id='mcTaskSettings';taskSettings.append(el('summary','任务类型与执行设置'));taskSettings.append($('taskType').closest('.cols'));const executionHint=[...$('taskPanel').querySelectorAll('p.muted')].find(p=>p.textContent.startsWith('模型与执行方式'));if(executionHint)taskSettings.append(executionHint);
 const taskConfig=el('p','连接电脑后读取执行配置。','mc-config-summary');$('saveTask').before(taskConfig,taskSettings);
 $('taskPanel').querySelector('h2').textContent='告诉电脑，要做什么？';$('taskPanel').querySelector('p.muted').textContent='填写目标 → 检查任务 → 确认执行；下一步只保存草稿。';$('saveTask').textContent='下一步：检查任务';$('previewCollab').textContent='下一步：检查任务';$('taskTab').textContent='独立任务';$('collabTab').textContent='双模型协作';
 const attachmentDetails=$('materials').closest('details');attachmentDetails.querySelector('summary').textContent='材料与附件（选填）';
 const collabSettings=el('details',undefined,'mc-advanced');collabSettings.id='mcCollabSettings';collabSettings.append(el('summary','模型、轮数与预算设置'));
 collabSettings.append($('primary').closest('.cols'),$('rounds').closest('.cols'),$('tokens').previousElementSibling,$('tokens'),$('budget'));
 const collabConfig=el('p','连接电脑后读取模型配置。','mc-config-summary');$('previewCollab').before(collabConfig,collabSettings);
 $('collabPanel').querySelector('h2').textContent='两个模型，一起完成';$('collabPanel').querySelector('p.muted').textContent='填写目标 → 检查任务 → 确认执行；执行和审查设置沿用上次选择。';
 function selectedText(id){const input=$(id);return input.selectedOptions?.[0]?.textContent||'';}
 let taskCatalog=[];
 function advice(id,isTask){const box=el('div',undefined,'mc-compose-advice'),hint=el('p'),apply=button('采用建议',()=>{const candidate=taskSuggestion($(id).value,taskCatalog,$('taskType').value);if(!candidate)return;$('taskType').value=candidate.id;$('taskType').dispatchEvent(new Event('change',{bubbles:true}));});box.id=isTask?'mcTaskAdvice':'mcCollabAdvice';apply.hidden=true;box.append(hint,apply);$(id).after(box);return ()=>{const text=$(id).value.trim(),candidate=isTask?taskSuggestion(text,taskCatalog,$('taskType').value):null;apply.hidden=!candidate;apply.textContent=candidate?'采用“'+candidate.label+'”':'采用建议';hint.textContent=!isTask&&text.length>8000?'当前目标超过双模型的 8000 字限制，请缩短后再检查。':candidate?'按目标建议使用“'+candidate.label+'”，点采用后才切换。':!text?'直接写目标即可；用途、输出形式或参考材料能让要求更清楚。':'检查时会列出当前设置与要求；确认前不会执行。';};}
 const updateTaskAdvice=advice('instruction',true),updateCollabAdvice=advice('collabTask',false);
 for(const id of ['instruction','collabTask'])$(id).addEventListener('input',()=>{updateTaskAdvice();updateCollabAdvice();});
 const collabContext=el('div',undefined,'mc-collab-context'),collabComposer=el('div',undefined,'mc-collab-composer');for(const child of [...$('collabPanel').children])if(!['collabTask','mcCollabAdvice','previewCollab'].includes(child.id))collabContext.append(child);collabComposer.append($('collabTask'),$('mcCollabAdvice'),$('previewCollab'));$('collabPanel').append(collabContext,collabComposer);
 function configured(tasks){
  if(Array.isArray(tasks)){taskCatalog=tasks;renderTaskCommands(tasks);}updateTaskAdvice();updateCollabAdvice();
  const role=selectedText('taskRole');taskConfig.textContent=role?selectedText('taskType')+' · 使用当前执行设置，可展开修改。':'连接电脑后读取执行配置。';
  const primary=selectedText('primary'),reviewer=selectedText('reviewer');collabConfig.textContent=primary&&reviewer?'执行与审查已就绪 · '+$('rounds').value+' 轮协作。模型与调用上限可展开查看。':'连接电脑后读取模型配置。';
 }
 doc.addEventListener('change',event=>{if(['taskType','taskRole','primary','reviewer','rounds','calls'].includes(event.target.id))configured();});
 const connect=el('section',undefined,'mc-settings');connect.id='mcSettings';connect.append(el('h1','连接与设置'),el('p','任务在电脑上执行。手机锁屏或离开页面不会停止电脑任务。','mc-scope'));const connectionCard=el('div',undefined,'mc-device');connectionCard.append(symbol('connection'));const device=el('div');device.append(el('strong','我的电脑'));const detailState=el('p','正在检查工作站连接');const receiverState=el('p','远程服务：正在检查','mc-scope');receiverState.id='mcReceiverState';device.append(receiverState,detailState);connectionCard.append(device);connect.append(connectionCard,button('重新检查连接',()=>$('refresh').click(),'mc-reconnect'),el('h2','更多功能'),button('文件与文字传输  →',()=>switchView('files'),'mc-setting-link'),el('h2','使用说明'),el('p','搭档：单模型对话、双模型协作与对话模板。成果：已有任务的进度、文件与网页。旧分类任务保留记录，不再提供重复的新建入口。','mc-scope'),el('p','回执不确定时先刷新核对，不会自动重复执行。当前版本需要在前台查看进度，尚未接入系统推送。','mc-scope'));const requirements=el('details',undefined,'mc-advanced');requirements.id='mcRequirements';requirements.append(el('summary','电脑需要保持什么状态？'));for(const text of ['电脑开机、联网并保持唤醒；锁屏可以，睡眠或休眠会中断连接。','跨网络使用时，手机和电脑的 Tailscale 都要保持已连接。','电脑的个人工作站 → 远程：启动远程接收服务。服务在后台运行即可。','独立任务和双模型协作还需要个人工作站保持运行；可以最小化，也可以切换其他页面。关闭退出工作站会停止任务接口。','首次连接在电脑远程页扫码配对；之后使用已保存的手机入口。若重新配对或地址改变，请重新扫码。'])requirements.append(el('p',text,'mc-scope'));connect.insertBefore(requirements,connect.querySelector('h2'));const appTools=el('details',undefined,'mc-advanced');appTools.id='mcAppTools';appTools.append(el('summary','电脑应用入口'),$('appsSection'));connect.append(appTools);main.append(connect);
 // Legacy task forms remain available to old records, without a duplicate mobile entry.
 const navigation=el('nav',undefined,'mc-bottom-nav');navigation.setAttribute('aria-label','手机主导航');const navButtons=[];for(const [key,label]of [['sessions','搭档'],['tasks','成果'],['connection','更多']]){const b=button('',()=>switchView(key));b.dataset.view=key;b.append(symbol(key),el('span',label));navigation.append(b);navButtons.push([key,b]);}doc.body.append(navigation);
 function applyFilter(){const visible=new Set(records(list,filter,query).map(x=>x.kind+':'+x.id));let count=0;for(const b of $('records').children){if(!b.dataset.recordId)continue;b.hidden=!visible.has(b.dataset.recordKind+':'+b.dataset.recordId);if(!b.hidden)count++;}listEmpty.hidden=!Object.keys(list).length||count>0;for(const b of filterButtons)b.setAttribute('aria-pressed',String(b.dataset.filter===filter));}
 function update(value){list={...value,native:list.native||[]};renderNativeResults();readNativeResults();renderSessionCollaborations();online(true);const counts=summary(list);for(const key of Object.keys(statValues))statValues[key].textContent=counts[key];recent.replaceChildren();const items=records(list);const priority=x=>({attention:0,active:1,failed:2,other:3,completed:4})[bucket(x.status)];items.sort((a,b)=>priority(a)-priority(b));const urgent=items.filter(x=>['attention','active'].includes(bucket(x.status)));for(const item of (urgent.length?urgent:items).slice(0,3)){const b=button('',()=>{setDetailParent('tasks');openRecord(item);},'mc-recent-item');const mark=el('span',undefined,'mc-record-mark '+bucket(item.status));mark.append(symbol('tasks'));const text=el('span',undefined,'mc-record-text');text.append(el('strong',String(item.title||item.instruction||item.task||'未命名任务').slice(0,90)),el('small',taskKindLabel(item,item.kind)));b.append(mark,text,el('span',taskSnapshot(item,item.kind).phase,'mc-status '+bucket(item.status)));recent.append(b);}if(!items.length)recent.append(el('p','还没有任务，从上方新建第一项吧。','mc-empty'));applyFilter();}
 function connectionStatus(){renderGuidance();renderTaskDetail();state.textContent=connected?'电脑已连接':receiverReachable===true?'任务接口未连接':receiverReachable===false?'远程服务未连接':'正在连接';state.classList.toggle('is-offline',connected!==true);receiverState.textContent=receiverReachable===true?'远程服务：可达':receiverReachable===false?'远程服务：未收到响应':'远程服务：正在检查';detailState.textContent=connected?'工作站任务接口：已连接':receiverReachable===true?'工作站任务接口：暂不可用。请检查电脑工作站是否运行；若提示配对失效，请重新扫码。':'请检查电脑是否唤醒、远程接收服务是否运行，以及手机和电脑的 Tailscale 连接。';}
 function receiver(value){receiverReachable=value;if(!value)connected=false;connectionStatus();}
 function online(value){connected=value;if(value)receiverReachable=true;connectionStatus();if(!value){for(const x of Object.values(statValues))x.textContent='—';}}

 function setDetailParent(parent){detailParent=parent==='sessions'?'sessions':'tasks';back.textContent=detailParent==='sessions'?'‹ 返回会话':'‹ 返回任务列表';}
 function renderSessionCollaborations(){
  const frame=frames.get('sessions');if(!frame)return;
  try{const d=frame.contentDocument,sidebar=d?.getElementById('sidebar');if(!sidebar)return;let group=d.getElementById('sessionCollaborationHistory');
   if(!group){group=d.createElement('details');group.id='sessionCollaborationHistory';group.style.cssText='margin:8px 12px;max-height:28dvh;overflow:auto';sidebar.insertBefore(group,sidebar.querySelector('.side-foot'));}
   const opened=group.open;group.replaceChildren();const rows=(list.collaborations||[]).slice(0,20),summary=d.createElement('summary');summary.textContent='双模型记录（'+(list.collaborations||[]).length+'）';group.append(summary);group.open=opened;
   if(!rows.length){const p=d.createElement('p');p.textContent='还没有双模型协作。';p.className='hint';group.append(p);}
   for(const row of rows){const b=d.createElement('button');b.type='button';b.className='conv-item';b.dataset.collaborationId=row.id;b.textContent=(row.title||row.task||'双模型协作')+' · '+taskSnapshot(row,'collaboration').phase;b.onclick=()=>{setDetailParent('sessions');onOpen('collaboration',row.id);};group.append(b);}
  }catch{}
 }
 function begin(kind){switchView('sessions');if(kind==='collab')sessionAction('remoteWorkstationOpenCollaboration').then(open=>open()).catch(error=>{resultsStatus.textContent=error.message;});}
 async function conversationDraft(text){
  switchView('sessions');ensureFrame('sessions');const frame=frames.get('sessions');
  for(let attempt=0;attempt<60;attempt++){if(view!=='sessions')return {accepted:false,reason:'内容仍保留在助手输入框，可稍后继续。'};try{const prepare=frame.contentWindow.remoteWorkstationPrepareDraft;if(typeof prepare==='function')return prepare(text);}catch{}await new Promise(resolve=>setTimeout(resolve,100));}
  return {accepted:false,reason:'请在对话页选择或新建会话；原文仍保留在助手输入框。'};
 }
 function ensureFrame(key){
  if(frames.has(key))return;
  const section=el('section',undefined,'mc-embedded-view');section.id=key==='sessions'?'mcSessions':'mcFiles';
  const frame=el('iframe');if(key==='sessions')frame.dataset.workstationSession='1';frame.title=key==='sessions'?'电脑会话':'文件与文字传输';frame.referrerPolicy='no-referrer';frame.setAttribute('sandbox','allow-scripts allow-same-origin allow-forms allow-downloads');
  frame.src=(key==='sessions'?'/sessions':'/transfer')+'?token='+encodeURIComponent(token)+'&desktop_embed=1';
  frame.onload=()=>{try{const d=frame.contentDocument;if(!d)return;d.documentElement.classList.add('mobile-session-surface');const style=d.createElement('style');style.textContent=`
   :root{font-family:"Segoe UI","Microsoft YaHei UI",sans-serif!important}
   .main{background-image:none!important}.composer:before{display:none!important}.character-credit{display:none!important}button,input,textarea{font-family:inherit!important}html.mobile-session-surface :is(input,textarea,select){font-size:16px!important}html.mobile-session-surface #composerInput{height:64px!important;min-height:64px!important;max-height:64px!important;overflow-y:auto!important}html.mobile-session-surface .composer{padding-bottom:8px!important}html.mobile-session-surface #sessionModels{display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr));gap:4px;padding:6px 8px}html.mobile-session-surface #sessionModels>span{display:none!important}html.mobile-session-surface #sessionModels>button{min-width:0;padding:6px 2px;font-size:12px;white-space:nowrap}html.mobile-session-surface .app,html.mobile-session-surface .main{min-height:0!important}
  `;d.documentElement.classList.add('partner-mobile-embedded');d.head.append(style);root.WorkstationPartnerTheme?.apply(root.WorkstationPartnerTheme.theme);renderSessionCollaborations();d.addEventListener('focusin',editingFocus,true);d.addEventListener('focusout',editingBlur,true);}catch{}};
  section.append(frame);main.append(section);frames.set(key,frame);
 }
 let deliveryDialog=null;
 function previewDelivery(task){
  const data=task.artifact_preview;if(!data)return;
  if(!deliveryDialog){deliveryDialog=el('dialog',undefined,'mc-delivery-preview');deliveryDialog.setAttribute('aria-label','成果内容预览');doc.body.append(deliveryDialog);}
  deliveryDialog.replaceChildren();const close=button('关闭',()=>deliveryDialog.close(),'mc-preview-close');deliveryDialog.append(el('h2','成果预览'),close,el('p','用于核对文字与内容，原文件排版请下载查看。','mc-scope'));
  if(data.type==='docx'){const text=el('div',String(data.text||'').slice(0,12000),'mc-delivery-text');deliveryDialog.append(text);}
  if(data.type==='pptx')for(const [i,slide]of (data.slides||[]).slice(0,12).entries()){const card=el('article',undefined,'mc-delivery-slide');card.append(el('small',String(i+1)+' / '+data.slides.length),el('h3',slide.title||''),el('p',slide.subtitle||''));const bullets=el('ul');for(const item of (slide.bullets||[]).slice(0,6))bullets.append(el('li',String(item)));card.append(bullets);deliveryDialog.append(card);}
  if(!deliveryDialog.open)deliveryDialog.showModal();
 }
 let previewDialog=null;
 function openPreview(value){
  const url=validPreview(value,location.origin,token);if(!url)return;
  if(!previewDialog){previewDialog=el('dialog',undefined,'mc-preview');previewDialog.setAttribute('aria-label','远程文件预览');const close=button('关闭预览',()=>previewDialog.close());const frame=el('iframe');frame.title='远程文件预览';frame.setAttribute('sandbox','allow-scripts allow-same-origin allow-forms allow-downloads');frame.referrerPolicy='no-referrer';previewDialog.append(close,frame);previewDialog.addEventListener('close',()=>{frame.src='about:blank';});doc.body.append(previewDialog);}
  previewDialog.querySelector('iframe').src=url;if(!previewDialog.open)previewDialog.showModal();
 }
 root.addEventListener('message',event=>{
  if(event.origin===location.origin&&event.source===frames.get('sessions')?.contentWindow&&event.data?.type==='workstation-web-preview-state'&&typeof event.data.open==='boolean'){doc.body.dataset.webPreview=event.data.open?'open':'closed';scheduleViewport();return;}
  const session=frames.get('sessions'),intent=sessionCollaborationIntent(event,location.origin,session?.contentWindow);if(intent){setDetailParent('sessions');onSessionCollaboration?.(intent,event.source);return;}
  if(event.origin!==location.origin||![...frames.values()].some(frame=>frame.contentWindow===event.source)||event.data?.type!=='remote-workstation-navigation')return;
  if(event.data.page==='sessions'){switchView('sessions');return;}
  if(event.data.page==='collaboration'){begin('collab');return;}
  if(event.data.page==='transfer'){switchView('files');return;}
  openPreview(event.data.preview);
 });
 let viewportTimer=null,editingBlurTimer=null,keyboardOpen=false,lastViewportHeight=0;
 function activeEditor(){let active=doc.activeElement;try{if(active?.tagName==='IFRAME')active=active.contentDocument?.activeElement;}catch{}return typingTarget(active);}
 function editingFocus(event){clearTimeout(editingBlurTimer);if(typingTarget(event.target)){doc.body.dataset.editing='true';scheduleViewport();}else editingBlur();}
 function editingBlur(){clearTimeout(editingBlurTimer);editingBlurTimer=setTimeout(()=>{if(!activeEditor())doc.body.dataset.editing='false';scheduleViewport();},140);}

 function syncViewport(){
  const viewport=root.visualViewport;
  let active=doc.activeElement;try{if(active?.tagName==='IFRAME')active=active.contentDocument?.activeElement;}catch{}
  const editing=typingTarget(active);
  // Freeze geometry during user zoom, but release editing state after blur.
  if(viewport&&Math.abs((viewport.scale||1)-1)>.05){if(!editing){keyboardOpen=false;doc.body.dataset.keyboard='closed';doc.body.dataset.editing='false';for(const frame of frames.values()){try{frame.contentDocument.documentElement.dataset.mobileKeyboard='closed';}catch{}}}return;}
  const height=viewport?.height||root.innerHeight,next=keyboardState(root.innerHeight,height,editing,keyboardOpen),changed=next!==keyboardOpen;
  if((keyboardOpen&&!next)||(!next&&lastViewportHeight>0&&height-lastViewportHeight>140))doc.body.dataset.editing='false';keyboardOpen=next;doc.body.dataset.keyboard=next?'open':'closed';const typing=next||doc.body.dataset.editing==='true';
  if(changed||Math.abs(height-lastViewportHeight)>=6){doc.documentElement.style.setProperty('--mc-viewport-height',Math.round(height)+'px');lastViewportHeight=height;}
  for(const [key,frame]of frames){
   try{frame.contentDocument.documentElement.dataset.mobileKeyboard=typing?'open':'closed';}catch{}
   if(key!==view)continue;
   const section=frame.parentElement,top=section.getBoundingClientRect().top;
   const available=doc.body.dataset.webPreview==='open'?Math.max(160,Math.round(height+(viewport?.offsetTop||0)-top)):frameHeight(height,viewport?.offsetTop||0,top,navigation.getBoundingClientRect().height,typing);
   const previous=parseFloat(section.style.getPropertyValue('--mc-frame-height'));
   if(changed||!Number.isFinite(previous)||Math.abs(previous-available)>=8)section.style.setProperty('--mc-frame-height',available+'px');
  }
 }
 function scheduleViewport(){clearTimeout(viewportTimer);viewportTimer=setTimeout(syncViewport,100);}
 root.visualViewport?.addEventListener('resize',scheduleViewport);root.addEventListener('resize',scheduleViewport);doc.addEventListener('focusin',editingFocus,true);doc.addEventListener('focusout',editingBlur,true);syncViewport();

 async function sessionAction(action){switchView('sessions');ensureFrame('sessions');for(let i=0;i<60;i++){const w=frames.get('sessions')?.contentWindow;if(typeof w?.[action]==='function')return w[action];await new Promise(resolve=>setTimeout(resolve,80));}throw Error('会话页尚未就绪，请稍后再试。');}
 async function openRecord(item){if(item.kind!=='native')return onOpen(item.kind,item.id);try{const open=await sessionAction('openWorkstationTask');if(!await open(item.id))throw Error('当前会话正在处理，或该记录暂不可用，请稍后重试。');}catch(error){switchView('tasks');resultsStatus.textContent=error.message;}}
 const resultsStatus=el('p','任务记录包含进度、待处理事项和已有成果。','mc-scope');resultsStatus.id='mcResultsStatus';heading.append(resultsStatus);
 let nativeReading=false;
 function renderNativeResults(){
  const rows=list.native||[];for(const node of [...$('records').children])if(node.dataset.recordKind==='native')node.remove();
  for(const item of rows){const b=button('',()=>openRecord({...item,kind:'native'}));b.dataset.recordId=item.id;b.dataset.recordKind='native';b.dataset.state=item.status;b.append(el('strong',item.title||item.goal||'任务成果'),el('small',taskKindLabel(item,'native')+' · '+(({completed:'已完成',running:'进行中',queued:'排队中',needs_attention:'需要处理',cancelled:'已停止',failed:'失败'})[item.status]||'需要核对')));$('records').append(b);}
  if(rows.length)for(const node of [...$('records').children])if(!node.dataset.recordId&&node.tagName==='P')node.remove();
  const counts=summary(list);for(const key of Object.keys(statValues))statValues[key].textContent=counts[key];applyFilter();
 }
 async function readNativeResults(){if(nativeReading)return;nativeReading=true;const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),12000);try{
  const response=await fetch('/api/bot/tasks?'+new URLSearchParams({token}),{cache:'no-store',credentials:'same-origin',signal:abort.signal});if(!response.ok)throw Error();const data=await response.json();const rows=Array.isArray(data)?data:data.tasks;if(!Array.isArray(rows))throw Error();
  list.native=nativeTasks(rows);renderNativeResults();resultsStatus.textContent='已合并网页项目、原生任务和工作站任务；点开查看进度与成果。';
 }catch{resultsStatus.textContent='部分任务记录暂未刷新，保留上次读取的内容；可稍后重试。';}finally{clearTimeout(timer);nativeReading=false;}}

 readNativeResults();root.setInterval(()=>{if(view==='tasks')readNativeResults();},12000);
 root.addEventListener('hashchange',()=>switchView(viewFromHash(location.hash)));
 switchView(view);
 root.PCFileSearch?.mount();
 return {setDetailParent,update,online,receiver,configured,guidance,taskDetail,commandFeedback,preview:openPreview,previewDelivery,compose:begin,conversationDraft,detail(){switchView('detail',true);},busy(value){working=value;},shouldPoll(){return ['home','tasks','detail'].includes(view)||(view==='sessions'&&(list.collaborations||[]).some(row=>bucket(row.status)==='active'));},get connected(){return connected;},get receiverConnected(){return receiverReachable;}};
}
const api={compactTaskResult,nativeTasks,sessionCollaborationIntent,fileTaskChoice,workbenchPreviewable,taskSnapshot,taskKindLabel,bucket,summary,records,viewFromHash,validPreview,keyboardState,typingTarget,frameHeight,carriedGoal,taskSuggestion,viewContext,partnerHint,mount};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.WorkstationMobile=api;
})(typeof window!=='undefined'?window:globalThis);
