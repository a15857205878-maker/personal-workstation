const test=require('node:test'),assert=require('node:assert/strict');
const {bucket,summary,records,viewFromHash,validPreview,keyboardState,frameHeight}=require('./mobile-controller.js');
test('Keyboard layout is based on editing and actual visual viewport reduction',()=>{
 assert.equal(keyboardState(844,480,true),true);assert.equal(keyboardState(844,480,false),false);assert.equal(keyboardState(844,790,true),false);assert.equal(keyboardState(0,0,true),false);assert.equal(keyboardState(844,NaN,true),false);
});
test('Keyboard stays stable through a brief blur until viewport recovers',()=>{
 assert.equal(keyboardState(844,510,false,true),true);assert.equal(keyboardState(844,750,false,true),true);assert.equal(keyboardState(844,800,false,true),false);assert.equal(keyboardState(844,750,true,false),false);
});
test('Embedded input area ends near keyboard instead of using a fixed header deduction',()=>{
 assert.equal(frameHeight(450,0,100,80,true),342);assert.equal(frameHeight(450,30,90,80,true),382);assert.equal(frameHeight(844,0,100,80,false),652);
});
test('Chinese task and collaboration states have one consistent category',()=>{
 for(const s of ['running','stopping','执行中','排队中','等待交接'])assert.equal(bucket(s),'active');
 for(const s of ['草稿','结果待确认','需要检查','interrupted'])assert.equal(bucket(s),'attention');
 for(const s of ['completed','已完成'])assert.equal(bucket(s),'completed');
 assert.equal(bucket('future-state'),'other');assert.equal(bucket('failed'),'failed');
});
const list={tasks:[{id:'a',status:'草稿',title:'草稿'},{id:'b',status:'已完成',title:'结果'},{id:'c',status:'执行中',title:'文档'}],collaborations:[{id:'d',status:'running',task:'协作'},{id:'e',status:'failed',task:'失败'}]};
test('Summary reports actual returned scope and never invents running tasks',()=>{assert.deepEqual(summary(list),{active:2,attention:1,completed:1,total:5});assert.deepEqual(summary({}),{active:0,attention:0,completed:0,total:0});});
test('Filters retain kind and input data, search is literal and handles unknown states',()=>{const copy=JSON.stringify(list);assert.deepEqual(records(list,'active').map(x=>x.id),['c','d']);assert.equal(records(list,'all','文档')[0].kind,'task');assert.equal(records(list,'all','协作')[0].kind,'collaboration');assert.equal(JSON.stringify(list),copy);assert.equal(records(list,'all','<script>').length,0);});
test('Navigation accepts only own views, never external locations',()=>{assert.equal(viewFromHash('#tasks'),'tasks');assert.equal(viewFromHash('#new'),'new');assert.equal(viewFromHash('#https://bad'),'sessions');assert.equal(viewFromHash(''),'sessions');});
test('Merged session preview accepts only paired local viewer pages',()=>{
 assert.equal(viewFromHash('#sessions'),'sessions');assert.equal(viewFromHash('#files'),'files');
 const origin='http://127.0.0.1:8765';assert.equal(validPreview(origin+'/preview-viewer?token=paired&id=x',origin,'paired'),origin+'/preview-viewer?token=paired&id=x');
 for(const value of ['https://outside.example/preview-viewer?token=paired',origin+'/preview-viewer?token=wrong',origin+'/api/workbench?token=paired','javascript:alert(1)'])assert.equal(validPreview(value,origin,'paired'),null);
});
test('Legacy phone root enters unified controller while embedded and explicit sessions stay put',()=>{
 const fs=require('node:fs'),vm=require('node:vm');const html=fs.readFileSync(__dirname+'/mobile_bot.html','utf8');const source=html.match(/<script id="mobile-entry">([\s\S]*?)<\/script>/)[1];
 for(const [pathname,search,embedded,redirect] of [['/','?token=paired',false,true],['/sessions','?token=paired',false,false],['/','?token=paired&desktop_embed=1',false,false],['/','?token=paired',true,false]]){
  const calls=[],window={};const location={pathname,search,hash:'',href:'http://127.0.0.1:8765'+pathname+search,replace:value=>calls.push(value)};vm.runInNewContext(source,{window,parent:embedded?{}:window,location,URL,URLSearchParams});assert.equal(calls.length,redirect?1:0);if(redirect)assert.equal(calls[0],'http://127.0.0.1:8765/collaboration?token=paired');
 }
});
test('A write transport failure marks connection offline without retrying',async()=>{
 const fs=require('node:fs'),vm=require('node:vm');const html=fs.readFileSync(__dirname+'/collaboration.html','utf8');
 const source=html.slice(html.indexOf('async function api('),html.indexOf('function selectOptions('));const changes=[];let attempts=0;const entry={id:'same-request'};
 const context={encodeURIComponent,token:'fixture',AbortController,setTimeout,clearTimeout,requestEntry:()=>entry,newRequestId:()=>entry.id,entries:[],persist(){},pendingNotice(){},mobile:{online:value=>changes.push(value)},fetch:async()=>{attempts++;throw Error('offline');}};
 const api=vm.runInNewContext('('+source.trim()+')',context);await assert.rejects(api('task_create',{instruction:'test'}),/不会自动重试/);
 assert.deepEqual(changes,[false]);assert.equal(attempts,1);assert.equal(entry.state,'pending');
});

 test('Reachable receiver with unavailable task gateway is not a network outage',async()=>{
 const fs=require('node:fs'),vm=require('node:vm');const html=fs.readFileSync(__dirname+'/collaboration.html','utf8');
 const source=html.slice(html.indexOf('async function api('),html.indexOf('function selectOptions('));
 const reachable=[],online=[];const context={encodeURIComponent,token:'fixture',AbortController,setTimeout,clearTimeout,mobile:{receiver:value=>reachable.push(value),online:value=>online.push(value)},fetch:async()=>({ok:false,status:503,json:async()=>({ok:false,error_code:'gateway_unavailable_or_uncertain',error:'电脑任务接口未连接'})})};
 const api=vm.runInNewContext('('+source.trim()+')',context);await assert.rejects(api('list'),/电脑任务接口/);assert.deepEqual(reachable,[true]);assert.deepEqual(online,[false]);
 });
 test('Unreachable receiver is reported separately without replay',async()=>{
 const fs=require('node:fs'),vm=require('node:vm');const html=fs.readFileSync(__dirname+'/collaboration.html','utf8');
 const source=html.slice(html.indexOf('async function api('),html.indexOf('function selectOptions('));const reachable=[];let attempts=0;
 const context={encodeURIComponent,token:'fixture',AbortController,setTimeout,clearTimeout,mobile:{receiver:value=>reachable.push(value),online(){}},fetch:async()=>{attempts++;throw Error('offline');}};
 const api=vm.runInNewContext('('+source.trim()+')',context);await assert.rejects(api('list'));assert.deepEqual(reachable,[false]);assert.equal(attempts,1);
 });

test('Task suggestions only refer to an existing catalog and require a different selection',()=>{
 const {taskSuggestion}=require('./mobile-controller.js');const tasks=[{id:'text',label:'生成文本',agents:[{}]},{id:'pptx',label:'生成PPT',agents:[{}]},{id:'xlsx',label:'生成Excel',agents:[{}]}];
 assert.deepEqual(taskSuggestion('做一份产品介绍PPT',tasks,'text'),{id:'pptx',label:'生成PPT'});
 assert.deepEqual(taskSuggestion('制作 Excel 销售表',tasks,'text'),{id:'xlsx',label:'生成Excel'});
 assert.equal(taskSuggestion('做PPT',tasks,'pptx'),null);assert.equal(taskSuggestion('做PPT',[], 'text'),null);
 assert.equal(taskSuggestion('帮我处理一下',tasks,'text'),null);assert.equal(taskSuggestion('生成图片',tasks,'text'),null);
 assert.equal(taskSuggestion('做PPT',[{id:'pptx',label:'PPT',agents:[]}],'text'),null);
});
test('Switching modes carries a goal only into an empty draft and never truncates it',()=>{
 const {carriedGoal}=require('./mobile-controller.js');assert.equal(carriedGoal('目标',''),'目标');assert.equal(carriedGoal('目标','  '),'目标');assert.equal(carriedGoal('目标','已有草稿'),'已有草稿');const long='长'.repeat(9000);assert.equal(carriedGoal(long,''),long);
});

test('Known offline state blocks task writes before creating a receipt or sending traffic',async()=>{
 const fs=require('node:fs'),vm=require('node:vm');const html=fs.readFileSync(__dirname+'/collaboration.html','utf8');const source=html.slice(html.indexOf('async function api('),html.indexOf('function selectOptions('));let attempts=0,receipts=0;
 const context={encodeURIComponent,token:'fixture',AbortController,setTimeout,clearTimeout,mobile:{connected:false,online(){},receiver(){}},fetch:async()=>{attempts++;throw Error('should not send');},requestEntry(){receipts++;return {id:'new'};},newRequestId(){},entries:[],persist(){},pendingNotice(){}};
 const api=vm.runInNewContext('('+source.trim()+')',context);await assert.rejects(api('task_submit',{id:'draft'}));assert.equal(attempts,0);assert.equal(receipts,0);
});
test('Known offline state still permits read-only checks to recover connection',async()=>{
 const fs=require('node:fs'),vm=require('node:vm');const html=fs.readFileSync(__dirname+'/collaboration.html','utf8');const source=html.slice(html.indexOf('async function api('),html.indexOf('function selectOptions('));let attempts=0;
 const context={encodeURIComponent,token:'fixture',AbortController,setTimeout,clearTimeout,mobile:{connected:false,receiver(){}},fetch:async()=>{attempts++;return {ok:true,json:async()=>({ok:true,data:{tasks:[]}})};}};
 const api=vm.runInNewContext('('+source.trim()+')',context);await api('list');assert.equal(attempts,1);
});

test('Reachable receiver can explicitly launch workstation while task gateway is offline',async()=>{
 const fs=require('node:fs'),vm=require('node:vm');const html=fs.readFileSync(__dirname+'/collaboration.html','utf8');const source=html.slice(html.indexOf('async function api('),html.indexOf('function selectOptions('));let attempts=0;
 const entry={id:'launch'};const context={encodeURIComponent,token:'fixture',AbortController,setTimeout,clearTimeout,mobile:{connected:false,receiverConnected:true,receiver(){},online(){}},fetch:async()=>{attempts++;return {ok:true,json:async()=>({ok:true,data:{message:'launched'}})};},requestEntry:()=>entry,newRequestId(){},entries:[],persist(){},pendingNotice(){}};
 const api=vm.runInNewContext('('+source.trim()+')',context);await api('app_launch',{id:'workbench'});assert.equal(attempts,1);assert.equal(entry.state,'done');
});

test('Mobile contextual navigation has stable parents and readable page titles',()=>{
 const {viewContext}=require('./mobile-controller.js');assert.deepEqual(viewContext('detail'),{title:'任务详情',parent:'tasks'});assert.deepEqual(viewContext('new'),{title:'布置任务',parent:'tasks'});assert.deepEqual(viewContext('files'),{title:'文件与文字',parent:'connection'});assert.deepEqual(viewContext('home'),{title:'个人工作站',parent:null});
});

test('Partner hints follow real wire states and preserve manual/unknown boundaries',()=>{
 const {partnerHint}=require('./mobile-controller.js');assert.match(partnerHint('草稿'),/检查/);assert.match(partnerHint('草稿',true),/电脑客户端/);assert.match(partnerHint('执行中'),/不要重复提交/);assert.match(partnerHint('running'),/不要重复提交/);assert.match(partnerHint('结果待确认'),/确认/);assert.match(partnerHint('failed'),/错误/);assert.match(partnerHint('future'),/核对/);assert.doesNotMatch(partnerHint('future'),/已完成|正在处理/);
});

const {taskSnapshot,taskKindLabel}=require('./mobile-controller.js');
test('Unified task snapshot never treats text or model completion as a downloadable file',()=>{
 const single=taskSnapshot({status:'结果待确认',result:'正文',files:[]},'task');
 assert.equal(single.phase,'核对结果');assert.match(single.output,/文字/);assert.match(single.output,/没有/);
 const dual=taskSnapshot({status:'completed',steps:[{content:'方案'}]},'collaboration');
 assert.equal(dual.phase,'已完成');assert.match(dual.output,/文字/);assert.match(dual.output,/没有/);
 const pack=taskSnapshot({status:'已完成',task_type:'program_pack',files:[{name:'资料.zip',size:12}]},'task');
 assert.equal(pack.phase,'已完成');assert.match(pack.output,/1/);assert.equal(taskKindLabel(pack.record||{task_type:'program_pack'},'task'),'电脑文件打包');
});
test('Unified task snapshot preserves manual, uncertain, failed and offline boundaries',()=>{
 assert.equal(taskSnapshot({status:'草稿'},'task',true).phase,'电脑端交接');
 assert.equal(taskSnapshot({status:'排队中'},'task').phase,'等待电脑执行');
 assert.equal(taskSnapshot({status:'running'},'collaboration').phase,'电脑处理中');
 assert.match(taskSnapshot({status:'需要检查'},'task').hint,/不要重复/);
 assert.equal(taskSnapshot({status:'future-state'},'task').phase,'需要核对');
 assert.equal(taskSnapshot({status:'失败',error:'缺少材料'},'task').hint,'缺少材料');
 const offline=taskSnapshot({status:'执行中'},'task',false,false);assert.match(offline.hint,/上次/);assert.match(offline.hint,/恢复连接/);
 assert.match(taskSnapshot({status:'已完成',files:[{name:'大包.zip',size:11*1024*1024}]},'task').output,/电脑/);
});

test('Office task status distinguishes an actual requested extension from text or other files',()=>{
 const ppt=taskSnapshot({task_type:'pptx',status:'结果待确认',result:'逐页大纲',files:[{name:'大纲.txt',size:100}]},'task',true);assert.match(ppt.output,/尚未收到PPTX/);
 const excel=taskSnapshot({task_type:'xlsx',status:'草稿',files:[]},'task',true);assert.equal(excel.phase,'电脑端交接');assert.match(excel.output,/尚未收到XLSX/);
 const ready=taskSnapshot({task_type:'xlsx',status:'结果待确认',files:[{name:'统计表.xlsx',size:1234}]},'task',true);assert.doesNotMatch(ready.output,/尚未收到/);assert.match(ready.output,/1/);
});

test('File command context only uses a task returned by the paired task list',()=>{
 const {fileTaskChoice}=require('./mobile-controller.js');const tasks=[{id:'a'},{id:'b'}];
 assert.equal(fileTaskChoice(tasks,{kind:'task',id:'a'}),'a');assert.equal(fileTaskChoice(tasks,{kind:'task',id:'missing'}),'');assert.equal(fileTaskChoice(tasks,{kind:'collaboration',id:'a'}),'');assert.equal(fileTaskChoice([],null),'');
});


test('Only the registered paired session frame may prepare collaboration UI',()=>{
 const {sessionCollaborationIntent}=require('./mobile-controller.js');const source={};const data={type:'workstation-session-collaboration',text:'写一份方案',sourceText:'用双模型写一份方案',hasAttachments:false};
 assert.equal(sessionCollaborationIntent({origin:'http://paired',source,data},'http://paired',source).text,'写一份方案');
 for(const event of [{origin:'https://outside',source,data},{origin:'http://paired',source:{},data},{origin:'http://paired',source,data:{...data,text:'x'.repeat(8001)}},{origin:'http://paired',source,data:{...data,type:'run-command'}}])assert.equal(sessionCollaborationIntent(event,'http://paired',source),null);
});

test('Results combine native projects and workbench tasks without losing ownership',()=>{
 const rows=records({tasks:[{id:'same',status:'已完成',title:'文档'}],native:[{id:'same',status:'needs_attention',goal:'网页'}]});
 assert.equal(rows.length,2);assert.equal(rows[1].kind,'native');assert.equal(records({native:[{id:'n',status:'needs_attention',goal:'网页'}]},'attention','网页').length,1);
 assert.equal(summary({native:[{id:'n',status:'running'}]}).active,1);
});

test('Results admit only native records that the conversation view can open',()=>{
 const {nativeTasks}=require('./mobile-controller.js');
 const id='a'.repeat(32);assert.deepEqual(nativeTasks([{id,agent:'demo'},{id,agent:'codex'},{id,agent:'deepseek-flash'},{id,agent:'codex-deepseek-code'},{id:'invalid',agent:'codex'},null]).map(t=>t.agent),['codex','deepseek-flash','codex-deepseek-code']);
});
