const test=require('node:test'),assert=require('node:assert/strict');
const {classify,chooseTask,chooseModels}=require('./keyword-router.js');
const catalog={task_catalog:{tasks:[{id:'text',label:'生成文本',default_role_ref:'a',agents:[{role_ref:'a'},{role_ref:'b'}]},{id:'pptx',label:'生成PPT',default_role_ref:'manual',agents:[{role_ref:'manual'}]}],roles:{a:{can_run:true,label:'默认模型'},b:{can_run:true},manual:{can_run:false}}},profiles:[{id:'p',requires_key:false},{id:'q',requires_key:true,has_key:true},{id:'missing',requires_key:true,has_key:false}]};
test('Explicit keyword commands select bounded existing workflows',()=>{
 for(const text of ['帮我写一份项目文档','我要一份周报','给我写个方案'])assert.equal(classify(text).kind,'task');
 assert.equal(classify('请用双模型给我设计一个网页').kind,'collab');assert.equal(classify('双模型帮我分析这份报告').kind,'collab');assert.equal(classify('把电脑上次选好的文件打包成ZIP').kind,'pack');assert.equal(classify('请生成PPT').task_type,'pptx');
});
test('Questions, negations and ambiguous goals do not start work',()=>{
 for(const text of ['你好','什么是双模型？','请问怎么压缩文件？','不要执行任务','我不想用双模型，聊聊天','例如：帮我写文档'])assert.equal(classify(text).kind,'chat',text);
 assert.equal(classify('用双模型').kind,'clarify');assert.equal(classify('帮我压缩图片').kind,'clarify');assert.equal(classify('').kind,'clarify');
 assert.equal(classify('不要用双模型，帮我写一份文档').kind,'task');
});
test('Selection uses available configured roles; manual file tasks stay manual',()=>{
 assert.equal(chooseTask('text',catalog).role,'a');assert.equal(chooseTask('pptx',catalog).manual,true);
 const copy=structuredClone(catalog);copy.task_catalog.roles.a.can_run=false;assert.equal(chooseTask('text',copy).role,'b');assert.throws(()=>chooseTask('xlsx',catalog),/未接入/);
});
test('Dual model selection cannot use missing keys or silently turn into one model',()=>{
 assert.deepEqual(chooseModels(catalog,'q','p'),{primary:'q',reviewer:'p'});assert.deepEqual(chooseModels(catalog,'missing','missing'),{primary:'p',reviewer:'q'});assert.throws(()=>chooseModels({...catalog,profiles:[catalog.profiles[0]]}),/两/);
});

test('Explaining ZIP and writing about it never selects packing; negated work stays conversation',()=>{
 for(const text of ['帮我解释ZIP格式','请告诉我怎么压缩文件','我想知道打包的原理','请不要生成PPT'])assert.equal(classify(text).kind,'chat',text);
 assert.equal(classify('帮我写一份关于zip的说明文档').kind,'task');assert.equal(classify('帮我写一份关于zip的说明文档').task_type,'text');
 assert.equal(classify('不要用双模型，帮我写一份文档').kind,'task');assert.equal(classify('帮我把资料打包成ZIP，不要删除原件').kind,'pack');
});

test('Everyday spreadsheet and PPTX instructions use existing catalog types without claiming automatic execution',()=>{
 for(const goal of ['帮我整理成表格','做一份预算表','我要一份收支表'])assert.equal(classify(goal).task_type,'xlsx',goal);
 for(const goal of ['做一份PPTX','帮我制作演示文稿'])assert.equal(classify(goal).task_type,'pptx',goal);
 assert.equal(classify('帮我修改网站里的表格').task_type,'web_edit');
 assert.equal(classify('请不要生成表格').kind,'chat');assert.equal(classify('表格是什么').kind,'chat');
 assert.equal(chooseTask('pptx',catalog).manual,true);assert.throws(()=>chooseTask('xlsx',catalog),/未接入/);
});

test('File quick commands never become document/model generation or accept arbitrary paths',()=>{
 for(const goal of ['查看成果','帮我查看任务成果','文件列表'])assert.equal(classify(goal).kind,'files',goal);
 assert.equal(classify('预览文件').action,'preview');assert.equal(classify('下载文件').action,'download');
 const exact=classify('帮我下载统计表.xlsx');assert.equal(exact.kind,'files');assert.equal(exact.action,'download');assert.equal(exact.query,'统计表.xlsx');
 assert.equal(classify('请预览报告.pptx').kind,'files');assert.equal(classify('不要下载文件').kind,'chat');assert.equal(classify('请问怎么下载文件').kind,'chat');
 for(const goal of ['预览 C:\\私人\\报告.docx','下载https://outside/file.pdf','下载../secret.txt'])assert.equal(classify(goal).kind,'clarify',goal);
});


test('Independent task commands cover the existing catalog with everyday goals',()=>{
 const examples={text:['帮我总结这段会议记录','请翻译这篇文章','润色这封邮件','写一份通知','起草本周计划'],research:['查找PYNQ相关论文','帮我搜索参考资料','检索这个课题的文献'],web_check:['检查这个网页的布局','帮我测试网站'],web_edit:['修改页面布局','帮我美化这个网站'],image:['帮我生成一张图片','画一张海报'],software_operation:['帮我操作这个软件导出数据','操作软件完成文件转换','请启动这个程序'],software_error:['帮我排查软件报错','解决Excel启动错误','修复程序崩溃问题'],pptx:['制作一份演示文稿'],xlsx:['整理一份预算表']};
 for(const [type,goals] of Object.entries(examples))for(const goal of goals)assert.equal(classify(goal).task_type,type,goal);
 for(const goal of ['不要启动这个程序','例如操作软件导出数据','请问如何处理软件报错','帮我解释程序崩溃的原理'])assert.equal(classify(goal).kind,'chat',goal);
 assert.equal(classify('下载参考资料.pdf').kind,'files');assert.equal(classify('帮我用双模型排查软件报错').kind,'collab');
});
test('Task examples only expose configured known types and all route back to their real task',()=>{
 const {taskCommands}=require('./keyword-router.js');
 const tasks=['text','pptx','xlsx','image','research','web_check','web_edit','software_operation','software_error'].map(id=>({id,label:id}));
 const commands=taskCommands([...tasks,{id:'future',label:'未接入'}]);assert.equal(commands.length,9);
 for(const item of commands){assert.equal(classify(item.example).task_type,item.id);assert.ok(item.label);}
 assert.deepEqual(taskCommands(undefined),[]);assert.equal(taskCommands([{id:'document',label:'制作文档'}])[0].id,'document');
 assert.equal(taskCommands([{id:'pptx',label:'自定义演示名称'}])[0].label,'自定义演示名称');
});


test('Writing about a capability stays writing, and positive goals survive negative suffixes',()=>{
 for(const goal of ['帮我写一封介绍Excel的邮件','帮我写一份关于修复软件报错的说明文档','请翻译这篇PPT设计说明','帮我总结网页检查报告'])assert.equal(classify(goal).task_type,'text',goal);
 assert.equal(classify('请帮我分别整理这两份文档').task_type,'text');
 assert.equal(classify('帮我生成图片不要PPT').task_type,'image');
 assert.equal(classify('帮我写文档，不用双模型').task_type,'text');
 for(const goal of ['请别运行任务','不要下载文件','帮我不要生成PPT'])assert.equal(classify(goal).kind,'chat',goal);
});
test('Multiple separate output requests ask for a choice before preparing one task',()=>{
 for(const goal of ['帮我生成一份PPT和一张预算表','做一份预算表以及PPT','帮我制作PPT，同时生成Excel表格'])assert.equal(classify(goal).kind,'clarify',goal);
 assert.equal(classify('帮我制作PPT，介绍预算表的用法').task_type,'pptx');
 assert.equal(classify('帮我用双模型制作PPT和预算表').kind,'collab');
});
