/* Paired companion UI. All model execution and records remain on the desktop. */
(()=>{
 'use strict';
 const $=id=>document.getElementById(id),token=new URLSearchParams(location.search).get('token')||'';
 const embedded=new URLSearchParams(location.search).get('mobile_embed')==='1'&&window.parent!==window;
 const states={prepared:'待确认',queued:'排队中',starting:'正在启动',running:'进行中',stopping:'正在停止',completed:'已完成',failed:'失败',cancelled:'已取消',interrupted:'已中断',skipped:'未发送'};
 const formats={text:'文字',docx:'文档 DOCX',xlsx:'表格 XLSX',pptx:'演示 PPTX',svg:'示意图 SVG'};
 const running=s=>['starting','running','stopping'].includes(s);
 const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
 const drafts=new Map(),attempts=new Map(),readers=new Set();let boot=null,session=null,selected='',mutating=false,loading=false,polling=false,revision=0,lastRender='',historyLimit=12,syncing=null,connection=null,lastRecovery=0;
 const planDrafts=new Map();
 let planSource='',editingPlan=null;
 const canHandoff=()=>boot?.task_handoff===true&&boot?.receiver_task_handoff===true;
 const canDraft=()=>canHandoff()&&boot?.dragon_planning===true;
 const storageKey='partner-request-v1-'+[...token].reduce((a,c)=>(a*31+c.charCodeAt(0))>>>0,0);
 try{for(const [k,v] of JSON.parse(sessionStorage.getItem(storageKey)||'[]'))attempts.set(k,v);}catch{}
 function showError(text){$('error').textContent=text||'';$('error').hidden=!text;}
 function connectionState(value){
  connection=value;
  const label=value===false?'同步中断，已保留输入和上次记录。':value===true?(session?(running(session.status)?'成员正在处理':'已同步电脑记录')+' · '+session.call_count+'/'+session.call_limit+' 次调用':'电脑已连接，请新建群聊。'):'正在连接电脑…';
  if($('status').textContent!==label)$('status').textContent=label;
  controls();
 }
 function rememberAttempts(){while(attempts.size>10)attempts.delete(attempts.keys().next().value);try{sessionStorage.setItem(storageKey,JSON.stringify([...attempts].slice(-10)));}catch{}}
 async function rpc(action,payload={},write=false){
  const signature=JSON.stringify([action,payload]);let request_id;
  if(write){request_id=attempts.get(signature)||[...crypto.getRandomValues(new Uint8Array(16))].map(b=>b.toString(16).padStart(2,'0')).join('');attempts.set(signature,request_id);rememberAttempts();}
  const snapshot=action==='center_bootstrap'||action==='center_get';
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),snapshot?10000:30000);
  if(snapshot)readers.add(controller);
  try{
   const response=await fetch('/api/workbench?token='+encodeURIComponent(token),{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,payload,...(request_id?{request_id}:{})}),signal:controller.signal});
   const result=await response.json();
   if(!response.ok||!result.ok){
    const code=result.error_code||result.error;
    if(write&&!['desktop_operation_failed','operation_uncertain_inspect_desktop','gateway_operation_failed','gateway_unavailable_or_uncertain','request_pending_inspect_desktop'].includes(code)){attempts.delete(signature);rememberAttempts();}
    throw Error(result.error||'电脑未接受请求，请刷新核对。');
   }
   if(write){attempts.delete(signature);rememberAttempts();}
   return result.data;
  }catch(e){if(e.name==='AbortError')throw Error('连接超时，请刷新会话核对。不会自动重发；再次发送相同内容会沿用原请求编号。');throw e;}
  finally{clearTimeout(timer);readers.delete(controller);}
 }
 function identity(p){const v=boot?.identities?.[p?.id]||{};return {...p,name:v.nickname||p?.name||'成员',avatar:v.avatar||''};}
 function avatar(p,seat){const n=el('span',undefined,'portrait'),v=seat==='U'?{name:boot?.identities?.user?.nickname||'你',avatar:boot?.identities?.user?.avatar}:identity(p);
  if(v.avatar?.startsWith('data:image/webp;base64,')&&v.avatar.length<=24000){const img=el('img');img.src=v.avatar;img.alt=v.name+'的头像';n.append(img);}else{n.textContent=[...v.name][0]||seat;}return n;
 }
 function options(){
  const prior=$('target').value,seats=Object.keys(session?.roles||{}),all=seats.join(''),sets=[all,[...seats].reverse().join(''),...seats];
  if(seats.length===3)for(let i=0;i<3;i++)for(let j=i+1;j<3;j++)sets.push(seats[i]+seats[j]);
  $('target').replaceChildren();for(const set of [...new Set(sets)]){const o=el('option',set.length===1?'只请 '+identity(session.roles[set]).name:[...set].map(s=>identity(session.roles[s]).name).join(' → '));o.value=set;$('target').append(o);}
  $('target').value=sets.includes(prior)?prior:all;budget();
 }
 function budget(){const count=$('target').value.length;if(count===1)$('rounds').value='1';$('rounds').disabled=mutating||loading||count===1||running(session?.status)||!!session?.archived;$('budget').textContent='本轮接话最多 '+count*Number($('rounds').value)+' 次，剩余 '+Math.max(0,(session?.call_limit||30)-(session?.call_count||0))+' 次；文件交付另计。';}
 function controls(){
  const busy=running(session?.status),blocked=mutating||loading,prepared=session?.turns?.some(t=>t.state==='prepared');
  const insufficient=session&&$('target').value.length*Number($('rounds').value)>session.call_limit-session.call_count;
  $('send').disabled=connection!==true||!session||blocked||busy||prepared||session.archived||insufficient||!$('input').value.trim();
  $('stop').hidden=!busy;
  $('plan-new').hidden=!canHandoff()||!session||busy||prepared;
  $('plan-new').disabled=connection!==true||blocked||!!session?.archived||!(session?.call_count<session?.call_limit);
  $('dragon-draft').hidden=!canDraft()||!session||busy||prepared;
  $('dragon-draft').disabled=connection!==true||blocked||!!session?.archived||!$('input').value.trim()||!(session?.call_limit-session?.call_count>=2);
  $('plan-jump').hidden=!prepared&&!busy;
  $('plan-add').disabled=blocked||$('plan-jobs').childElementCount>=4;
  const stale=editingPlan&&session?.turns?.find(turn=>turn.id===editingPlan.turn_id&&turn.state==='prepared')?.plan_revision!==editingPlan.plan_revision;
  $('plan-prepare').disabled=connection!==true||blocked||busy||(!editingPlan&&prepared)||!!stale||!!session?.archived;
  if(stale&&$('plan-dialog').open)planError('另一端已修改或确认草案，请关闭并重新打开。');
  for(const b of $('feed').querySelectorAll('[data-plan-action]')){
   b.disabled=connection!==true||blocked||busy||!!session?.archived;
  }
  $('stop').disabled=blocked||connection!==true;
  $('new').disabled=connection!==true||blocked||busy||prepared;$('sessions').disabled=connection!==true||blocked||busy||prepared;$('target').disabled=blocked||busy||prepared;
  $('input').disabled=blocked||busy||prepared||!!session?.archived;$('create').disabled=blocked;$('cancel-create').disabled=blocked;
  $('manage').disabled=!session||blocked||busy||prepared;$('save-manage').disabled=blocked;$('cancel-manage').disabled=blocked;
  $('hint').textContent=session?.archived?'此会话已归档，请在会话管理中恢复。':insufficient?'剩余次数不足，请减少成员或轮数，或新建会话。':prepared?(canHandoff()?'有分工等待确认。':'有分工等待在电脑确认。'):'模型连接与头像设置在电脑端。';
  for(const b of document.querySelectorAll('.retry-item'))b.disabled=blocked||busy||prepared||!!session?.archived||session.call_count>=session.call_limit;
  budget();
 }
 function appendMessage(parent,message,roles){
  const user=message.seat==='U',p=roles?.[message.seat],who=user?(boot?.identities?.user?.nickname||'你'):identity(p).name;
  const row=el('article',undefined,'chat-row'+(user?' user':'')),body=el('div'),meta=el('span',who,'speaker');
  if(message.at){const time=new Date(message.at);if(!Number.isNaN(time.getTime()))meta.textContent+=' · '+time.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});}
  body.append(meta,el('div',message.content||(['failed','cancelled'].includes(message.state)?'没有完整回复。':message.state==='completed'?'本条没有正文。':'正在接话…'),'bubble'));
  if(!user){const details=el('details'),summary=el('summary','来源');details.dataset.panel='source-'+message.id;details.append(summary,el('small',(p?.name||'')+' · '+(message.model||p?.model||'')+' · '+(message.state||'')));body.append(details);}
  row.dataset.messageKey=message.id||'';row.append(avatar(p,user?'U':message.seat),body);parent.append(row);
 }
 async function download(run,file){
  try{showError('');const data=await rpc('center_artifact',{id:selected,run_id:run.id,name:file.name});if(data.size>10*1024*1024)throw Error('成果超过手机下载上限，请在电脑查看。');
   const raw=atob(data.content_base64),bytes=Uint8Array.from(raw,c=>c.charCodeAt(0)),url=URL.createObjectURL(new Blob([bytes],{type:'application/octet-stream'})),a=el('a');a.href=url;a.download=data.name;a.rel='noopener';a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);
  }catch(e){showError(e.message);}
 }
 function files(parent,run){for(const f of run?.files||[]){const b=el('button','下载 '+f.name,'file');b.type='button';b.onclick=()=>download(run,f);parent.append(b);}}
 function pane(label,key){
  const detail=el('details');
  detail.dataset.panel=key;
  detail.append(el('summary',label));
  return detail;
 }
 function button(label,action,primary=false){
  const b=el('button',label,primary?'primary':undefined);
  b.type='button';
  b.onclick=action;
  return b;
 }
 function renderDelivery(box,job,index){
  const run=job.run;
  if(!run)return;
  const item=el('div',undefined,'round-output');
  const profile=identity(run.roles?.A||job.roles?.A);
  item.append(el('strong',job.title),el('small',profile.name+' · '+(states[run.status]||'待更新')));
  const final=(run.steps||[]).filter(s=>s.state==='completed').at(-1);
  if(run.files?.length)files(item,run);
  else if(final&&run.status==='completed')item.append(el('div',final.content,'round-text'));
  else if(run.error)item.append(el('p',run.error,'turn-state'));
  if(run.steps?.length){
   const details=pane('查看执行记录','steps-'+index);
   for(const step of run.steps){details.append(el('small',states[step.state]||'待更新'),el('div',step.content||step.error||'','round-text'));}
   item.append(details);
  }
  box.append(item);
 }
 function collaboration(turn,section,roles){
  const jobs=turn.jobs||[],prepared=turn.state==='prepared',active=running(turn.state);
  const entries=jobs.length?jobs:[{title:'本轮任务',state:turn.state,run:turn.run,roles,output_format:turn.output_format}];
  const statesForJobs=entries.map(job=>prepared?'prepared':job.run?.status||job.state);
  const done=statesForJobs.filter(state=>state==='completed').length;
  const box=el('div',undefined,'round-work');
  box.dataset.state=turn.state;
  const header=el('header',undefined,'round-heading');
  header.append(el('strong',prepared?'确认本次分工':turn.phase==='planning'&&active?'龙娘正在拟分工':active?'分工进度':'协作结果'));
  if(!prepared)header.append(el('small','已完成 '+done+'/'+entries.length+' 项'));
  box.append(header);
  const details=pane('分工与要求','requirements');
  const checklist=el('ul',undefined,'round-checklist');
  for(const [index,job] of entries.entries()){
   const row=el('li'),label=el('div'),meta=el('small',identity(job.roles?.A||job.run?.roles?.A).name+(formats[job.output_format]?' · '+formats[job.output_format]:''));
   label.append(el('strong',job.title),meta);
   row.append(label,el('span',states[statesForJobs[index]]||'待更新'));
   checklist.append(row);
   if(job.instruction)details.append(el('p',job.title+' · '+job.instruction));
  }
  if(prepared||active||done!==entries.length)box.append(checklist);
  else details.insertBefore(checklist,details.children[1]||null);
  box.append(details);
  if(prepared&&canHandoff()){
   const actions=el('div',undefined,'round-approval'),payload={id:selected,turn_id:turn.id};
   const confirm=button('确认执行',()=>mutate('center_confirm',{...payload,...(turn.drafted?{plan_revision:turn.plan_revision}:{})}),true);
   const cancel=button('取消本次计划',()=>mutate('center_cancel_plan',payload));
   confirm.dataset.planAction='confirm';cancel.dataset.planAction='cancel';
   actions.append(el('p','确认后将调用模型 '+entries.length+' 次。'),cancel);
   if(turn.drafted&&turn.job_plan?.length&&canDraft()){
    const edit=button('修改分工',()=>editDraft(turn));edit.dataset.planAction='edit';actions.append(edit);
   }
   actions.append(confirm);
   box.append(actions);
  }
  section.append(box);
  if(entries.some(job=>job.run)){
   const output=el('div',undefined,'round-deliveries');
   const hasFiles=entries.some(job=>job.run?.files?.length);
   output.append(el('h3',hasFiles?'本轮交付':'执行结果'));
   if(turn.accepted_at)output.append(el('small','已确认完成'));
   else if(turn.state==='completed'&&canDraft()&&entries.some(job=>job.run?.status==='completed'&&(job.run.files?.length||job.run.steps?.some(step=>step.state==='completed'&&step.content)))){
    const accept=button('确认完成',()=>mutate('center_accept',{id:selected,turn_id:turn.id}));accept.dataset.planAction='accept';output.append(accept);
   }
   entries.forEach((job,index)=>renderDelivery(output,job,index));
   section.append(output);
  }
 }
 function renderTurn(turn,roles){
  const section=el('section',undefined,'cooperation-turn');
  section.dataset.cooperationTurn=turn.id;
  if(turn.retry_of?.turn_id)section.append(el('p','单独重试 · '+turn.retry_label+' · 仅补这一项','turn-state'));
  appendMessage(section,{id:turn.id+'/U',seat:'U',content:turn.text,at:turn.at},roles);
  if(turn.draft_reply)appendMessage(section,{id:turn.id+'/draft',seat:'D',state:'completed',model:turn.draft_model,content:turn.draft_reply},{D:{name:'龙娘 · 分工建议',model:turn.draft_model}});
  const isTask=turn.kind==='execute'||!!turn.jobs?.length;
  const messages=(turn.run?.messages||[]).filter(m=>m.seat!=='U');
  if(isTask&&!(turn.drafted&&turn.state==='completed'&&!turn.jobs?.length))collaboration(turn,section,roles);
  if(messages.length){
   const parent=isTask?pane('制作前讨论 · '+messages.length+' 条发言','discussion'):section;
   for(const message of messages)appendMessage(parent,message,turn.run.roles||roles);
   if(isTask)section.append(parent);
  }
  if(!isTask)files(section,turn.run);
  for(const f of turn.failures||[]){
   const box=el('div',undefined,'failure'),text=el('div');
   text.append(el('strong',f.label+' · '+f.title),el('small',f.hint));box.append(text);
   if(f.retryable){const retry=button('重试这一项',()=>mutate('center_retry',{id:selected,turn_id:turn.id,item:f.item}));retry.className='retry-item';box.append(retry);}
   const detail=pane('详情','failure-'+f.item);
   detail.append(el('p',f.detail),el('small',f.blocked_reason||'仅重试这项，将另计一次调用。'));box.append(detail);section.append(box);
  }
  if(turn.report||turn.error&&!turn.failures?.length)section.append(el('p',turn.report||turn.error,'turn-state'));
  return section;
 }
 function render(value){
  if(value.id!==selected)return;session=value;
  const fingerprint=JSON.stringify([value,boot?.identities,canHandoff(),canDraft()]);if(fingerprint===lastRender){controls();return;}lastRender=fingerprint;
  const feed=$('feed'),nearBottom=embedded?feed.scrollTop+feed.clientHeight>=feed.scrollHeight-130:innerHeight+scrollY>=document.documentElement.scrollHeight-130,top=embedded?feed.scrollTop:scrollY;const previousKeys=new Set([...feed.querySelectorAll('[data-message-key]')].map(n=>n.dataset.messageKey)),animate=feed.dataset.motionTarget===value.id&&!loading;feed.dataset.motionTarget=value.id;
  const previous=new Map([...feed.querySelectorAll('[data-cooperation-turn]')].map(row=>[row.dataset.cooperationTurn,row]));
  const children=[];$('members').replaceChildren();
  for(const [seat,p] of Object.entries(value.roles||{})){const item=el('div',undefined,'member'),text=el('span',identity(p).name);text.append(el('small',p.model));item.append(avatar(p,seat),text);$('members').append(item);}
  if(value.history_omitted){const older=el('button','加载更早记录（还有 '+value.history_omitted+' 轮）');older.type='button';older.id='load-older';older.onclick=()=>{historyLimit=Math.min(60,historyLimit+12);open(selected).catch(e=>showError(e.message));};children.push(older);}
  if(!value.turns?.length)children.push(el('p','和搭档们聊聊吧。也可以直接交办一件事。','turn-state'));
  for(const turn of value.turns||[]){
   const prior=previous.get(turn.id),key=JSON.stringify([turn,value.roles,boot?.identities,canHandoff(),canDraft()]);
   if(prior?.renderKey===key){children.push(prior);continue;}
   const row=renderTurn(turn,value.roles);
   row.renderKey=key;
   const expanded=new Set([...prior?.querySelectorAll('details[data-panel][open]')||[]].map(d=>d.dataset.panel));
   for(const details of row.querySelectorAll('details[data-panel]'))details.open=expanded.has(details.dataset.panel);
   children.push(row);
  }
  const retain=new Set(children);
  for(const old of [...feed.children])if(!retain.has(old))old.remove();
  let cursor=feed.firstChild;
  for(const child of children){
   if(cursor!==child)feed.insertBefore(child,cursor);
   cursor=child.nextSibling;
  }
  while(cursor){const next=cursor.nextSibling;cursor.remove();cursor=next;}
  if(animate)for(const row of feed.querySelectorAll('[data-message-key]'))if(row.dataset.messageKey&&!previousKeys.has(row.dataset.messageKey))row.classList.add('mobile-message-enter');
  options();controls();if(embedded){requestAnimationFrame(()=>{feed.scrollTop=nearBottom?feed.scrollHeight:top;});$('group-current-title').textContent=value.title||'搭档群聊';}else if(nearBottom)requestAnimationFrame(()=>scrollTo(0,document.documentElement.scrollHeight));else scrollTo(0,top);
 }
 async function open(id){
  const changed=selected!==id;
  if(changed){
   drafts.set(selected,$('input').value);
   historyLimit=12;
   selected=id;
   try{sessionStorage.setItem(storageKey+'-selected',id);}catch{}
   $('input').value=drafts.get(id)||'';
   session=null;
   lastRender='';
   $('feed').replaceChildren(el('p','正在读取群聊…'));
  }
  revision++;
  if(changed){$('target').replaceChildren();$('rounds').value='1';}
  if(!id){session=null;$('feed').replaceChildren(el('p','从上方选择或新建群聊。'));controls();return;}
  const version=revision;loading=true;controls();
  try{const value=await rpc('center_get',{id,history_limit:historyLimit});if(id===selected&&version===revision){render(value);connectionState(true);}}
  catch(error){if(id===selected&&version===revision)connectionState(false);throw error;}
  finally{if(id===selected&&version===revision){loading=false;controls();}}
 }
 function listSessions(){const choice=selected,query=$('history-search').value.trim().toLocaleLowerCase();$('sessions').replaceChildren(el('option','选择群聊'));$('sessions').firstChild.value='';for(const row of boot?.sessions||[]){if(row.id!==choice&&((row.archived&&!$('show-archived').checked)||!row.title.toLocaleLowerCase().includes(query)))continue;const o=el('option',(row.archived?'[已归档] ':'')+row.title+' · '+row.call_count+'/'+row.call_limit);o.value=row.id;$('sessions').append(o);}$('sessions').value=choice;}
 function refresh(){
  if(syncing)return syncing;
  if(mutating||loading||polling||navigator.onLine===false)return;
  const version=revision;
  syncing=(async()=>{
   try{
    const latest=await rpc('center_bootstrap');
    if(version!==revision||mutating||loading)return;
    boot=latest;
    let id=selected;
    if(!id){
     let saved='';try{saved=sessionStorage.getItem(storageKey+'-selected')||'';}catch{}
     id=boot.sessions?.find(s=>s.id===saved&&!s.archived)?.id||boot.sessions?.find(s=>!s.archived)?.id||'';
    }
    await open(id);
    listSessions();
    connectionState(true);
   }catch{
    if(version===revision||!session)connectionState(false);
   }finally{syncing=null;}
  })();
  return syncing;
 }
 function planError(message){
  $('plan-error').textContent=message;
  $('plan-error').hidden=!message;
 }
 function formValues(){
  return {text:$('plan-goal').value,jobs:[...$('plan-jobs').children].map(row=>Object.fromEntries([...row.querySelectorAll('[name]')].map(field=>[field.name,field.value])))};
 }
 function planField(row,label,field){
  const wrapper=el('label',label);
  wrapper.append(field);
  row.append(wrapper);
 }
 function planJob(value={}){
  const row=el('fieldset',undefined,'phone-plan-job');
  row.append(el('legend','子任务'));
  const title=el('input');
  title.name='title';title.maxLength=60;title.required=true;title.value=value.title||'';
  const owner=el('select'),format=el('select'),instruction=el('textarea');
  owner.name='primary_id';format.name='output_format';instruction.name='instruction';
  const profiles=editingPlan?[...new Map([...Object.values(session.roles),...(boot?.profiles||[]).filter(p=>p.available)].map(p=>[p.id,p])).values()]:Object.values(session.roles);
  for(const profile of profiles){
   const option=el('option',identity(profile).name);
   option.value=profile.id;owner.append(option);
  }
  for(const [id,label] of Object.entries(formats)){const option=el('option',label);option.value=id;format.append(option);}
  if(value.primary_id){
   if(![...owner.options].some(option=>option.value===value.primary_id)){
    const option=el('option','原负责人不可用，请重新选择');option.value=value.primary_id;option.disabled=true;owner.append(option);
   }
   owner.value=value.primary_id;
  }
  format.value=value.output_format||'text';
  instruction.rows=2;instruction.maxLength=1000;instruction.value=value.instruction||'';
  planField(row,'名称',title);planField(row,'负责人',owner);planField(row,'交付格式',format);planField(row,'补充要求（可选）',instruction);
  row.append(button('移除此项',()=>{if($('plan-jobs').childElementCount>1){row.remove();updatePlanJobs();}}));
  $('plan-jobs').append(row);
  updatePlanJobs();
 }
 function updatePlanJobs(){
  const rows=[...$('plan-jobs').children];
  rows.forEach((row,index)=>{row.querySelector('legend').textContent='子任务 '+(index+1);row.querySelector('button').hidden=rows.length===1;});
  controls();
 }
 $('plan-new').onclick=()=>{
  if(!session||$('plan-new').disabled)return;
  planSource=$('input').value;
  editingPlan=null;$('plan-title').textContent='交办任务';$('plan-goal').readOnly=false;$('plan-prepare').textContent='检查分工';
  const draft=planDrafts.get(selected);
  $('plan-goal').value=draft?.text??planSource;
  $('plan-jobs').replaceChildren();
  for(const job of draft?.jobs||[{}])planJob(job);
  planError('');$('plan-dialog').showModal();
 };
 function editDraft(turn){
  editingPlan={turn_id:turn.id,plan_revision:turn.plan_revision};
  $('plan-title').textContent='修改分工';$('plan-prepare').textContent='保存分工';
  $('plan-goal').value=turn.text;$('plan-goal').readOnly=true;
  $('plan-jobs').replaceChildren();for(const job of turn.job_plan)planJob(job);
  planError('');$('plan-dialog').showModal();controls();
 }
 $('dragon-draft').onclick=()=>{if(!$('dragon-draft').disabled)mutate('center_draft',{id:selected,text:$('input').value.trim()});};
 $('plan-add').onclick=()=>{if($('plan-jobs').childElementCount<4)planJob();};
 function closePlan(){
  if(mutating)return;
  if(!editingPlan)planDrafts.set(selected,formValues());
  editingPlan=null;
  $('plan-dialog').close();
 }
 $('plan-close').onclick=closePlan;
 $('plan-dialog').addEventListener('cancel',event=>{event.preventDefault();closePlan();});
 $('plan-form').onsubmit=event=>{
  event.preventDefault();
  if($('plan-prepare').disabled)return;
  const values=formValues();
  if(!values.text.trim()||values.jobs.some(job=>!job.title.trim())){planError('请填写总目标和每项名称。');return;}
  planError('');
  if(editingPlan)mutate('center_edit_plan',{id:selected,...editingPlan,jobs:values.jobs});
  else mutate('center_prepare',{id:selected,text:values.text.trim(),jobs:values.jobs});
 };
 function turnInProgress(){return [...session?.turns||[]].reverse().find(turn=>turn.state==='prepared'||running(turn.state));}
 $('plan-jump').onclick=()=>{
  const turn=turnInProgress();
  if(turn)$('feed').querySelector('[data-cooperation-turn="'+turn.id+'"]')?.scrollIntoView({block:'start'});
 };
 async function mutate(action,payload){
  if(mutating||loading||connection!==true)return;mutating=true;revision++;controls();showError('');
  try{let value=await rpc(action,payload,true);if(action==='center_accept')value=await rpc('center_get',{id:selected,history_limit:historyLimit});
   if(action==='center_create'){drafts.set(selected,$('input').value);selected=value.id;$('input').value='';$('target').replaceChildren();$('rounds').value='1';}
   if(action==='center_create'||action==='center_send')historyLimit=12;
   render(value);if(navigator.onLine!==false)connectionState(true);
   if(action==='center_prepare'){
    planDrafts.delete(selected);
    $('plan-dialog').close();
    if(planSource.trim()===payload.text&&$('input').value===planSource){$('input').value='';drafts.set(selected,'');}
    requestAnimationFrame(()=>$('plan-jump').click());
   }if(action==='center_edit_plan'){editingPlan=null;$('plan-dialog').close();}
   if(action==='center_create')$('create-dialog').close();if(action==='center_manage')$('manage-dialog').close();if(action==='center_send'||action==='center_draft'){$('input').value='';drafts.set(selected,'');}
   if(action==='center_draft')requestAnimationFrame(()=>$('plan-jump').click());
   boot=await rpc('center_bootstrap');listSessions();if(action==='center_create')$('create-dialog').close();
  }catch(e){if((action==='center_prepare'||action==='center_edit_plan')&&$('plan-dialog').open)planError(e.message);else showError(e.message);}finally{mutating=false;controls();}
 }

 if(embedded){
  document.documentElement.dataset.groupEmbedded='true';
  const drawer=el('dialog');drawer.id='group-conversations';drawer.setAttribute('aria-label','群聊会话列表');const back=el('button','返回聊天');back.type='button';back.id='group-list-back';back.onclick=()=>drawer.close();drawer.append(back,$('sessions'),$('new'),$('history-tools'));document.body.append(drawer);
  const bar=document.querySelector('.partner-tools'),list=el('button','会话');list.id='group-list';list.type='button';list.onclick=()=>drawer.showModal();const title=el('strong','搭档群聊');title.id='group-current-title';bar.prepend(list,title);$('theme').hidden=true;
  const tools=el('details');tools.id='group-tools';tools.append(el('summary','更多'),$('refresh'));bar.append(tools);
  $('sessions').addEventListener('change',()=>drawer.close());
  window.WorkstationGroupNavigation={async open(id,turnId,fromToday=false){
   if(typeof id!=='string'||!/^[a-f0-9]{32}$/.test(id)||typeof turnId!=='string'||!/^[a-f0-9]{32}$/.test(turnId))return false;
   if(syncing)await syncing;
   const blocked=()=>mutating||loading||$('plan-dialog').open||(id!==selected&&!fromToday&&(running(session?.status)||session?.turns?.some(t=>t.state==='prepared')));
   if(blocked())return false;
   const latest=await rpc('center_bootstrap');if(!latest.sessions?.some(s=>s.id===id)||blocked())return false;boot=latest;listSessions();
   await open(id);listSessions();if(!session?.turns?.some(t=>t.id===turnId)&&session?.history_omitted){historyLimit=60;await open(id);}
   const row=[...$('feed').querySelectorAll('[data-message-key]')].find(n=>n.dataset.messageKey===turnId+'/U');
   await new Promise(resolve=>requestAnimationFrame(resolve));if(row){row.scrollIntoView({block:'start',behavior:'instant'});row.classList.add('turn-focus');setTimeout(()=>row.classList.remove('turn-focus'),1600);}else showError('本轮超出手机最近60轮范围，请在电脑查看更早记录。');return !!row;
  }};
 }

 $('back').href='/mobile?token='+encodeURIComponent(token);
 $('theme').onclick=()=>{if(window.WorkstationMobileVisual){window.WorkstationMobileVisual.toggle();return;}document.documentElement.dataset.scheme=document.documentElement.dataset.scheme==='dark'?'light':'dark';};
 document.documentElement.dataset.scheme=matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';
 $('refresh').onclick=()=>{showError('');resume(true);};
 $('sessions').onchange=()=>open($('sessions').value).catch(e=>showError(e.message));
 $('input').oninput=()=>{drafts.set(selected,$('input').value);controls();};
 $('target').onchange=controls;$('rounds').onchange=controls;
 $('history-search').oninput=listSessions;$('show-archived').onchange=listSessions;
 $('manage').onclick=()=>{if(!session)return;$('title-input').value=session.title;$('archive-input').checked=!!session.archived;$('manage-dialog').showModal();};
 $('cancel-manage').onclick=()=>$('manage-dialog').close();
 $('manage-form').onsubmit=e=>{e.preventDefault();const p={id:selected};if($('title-input').value.trim()!==session.title)p.title=$('title-input').value.trim();if($('archive-input').checked!==!!session.archived)p.archived=$('archive-input').checked;if(Object.keys(p).length>1)mutate('center_manage',p);else $('manage-dialog').close();};
 $('composer').onsubmit=e=>{e.preventDefault();if($('send').disabled)return;mutate('center_send',{id:selected,text:$('input').value.trim(),target:$('target').value,rounds:Number($('rounds').value)});};
 $('stop').onclick=()=>{
  const turn=turnInProgress();
  if(turn&&running(turn.state))mutate('center_stop',{id:selected,...(canHandoff()?{turn_id:turn.id}:{})});
 };
 $('new').onclick=()=>{if(!boot)return;const profiles=boot.profiles.filter(p=>p.available);for(const [i,id] of ['member-a','member-b','member-c'].entries()){const s=$(id);s.replaceChildren();if(i===2){const o=el('option','不加入第三位');o.value='';s.append(o);}for(const p of profiles){const o=el('option',identity(p).name+' · '+p.model);o.value=p.id;s.append(o);}s.value=profiles[i]?.id||(i<2?profiles[0]?.id||'':'');}$('create-dialog').showModal();};
 $('cancel-create').onclick=()=>$('create-dialog').close();
 $('create-form').onsubmit=e=>{e.preventDefault();const p={primary_id:$('member-a').value,reviewer_id:$('member-b').value};if($('member-c').value)p.third_id=$('member-c').value;mutate('center_create',p);};
 function visible(){return !document.hidden&&(!embedded||parent.document.body.dataset.mobileView==='chat');}
 async function poll(){
  if(polling||syncing||mutating||loading||!visible()||navigator.onLine===false)return;
  if(!boot||!session){if(connection!==true||selected)resume();return;}
  polling=true;const id=selected,version=revision;
  try{const value=await rpc('center_get',{id,history_limit:historyLimit});if(id===selected&&version===revision){render(value);connectionState(true);}}
  catch{if(id===selected&&version===revision)connectionState(false);}
  finally{polling=false;}
 }
 function resume(force=false){
  if(!visible()||syncing||mutating||loading||polling||navigator.onLine===false)return;
  const now=Date.now();
  if(!force&&now-lastRecovery<1500)return;
  lastRecovery=now;
  if(force||!boot||!session||connection===false)refresh();
  else poll();
 }
 window.WorkstationGroupResume=()=>resume();
 document.addEventListener('visibilitychange',()=>resume());
 window.addEventListener('pageshow',event=>{if(event.persisted)resume();});
 window.addEventListener('online',()=>resume(true));
 window.addEventListener('offline',()=>{
  for(const controller of readers)controller.abort();
  connectionState(false);
 });
 connectionState(navigator.onLine===false?false:null);resume();setInterval(poll,1800);
})();
