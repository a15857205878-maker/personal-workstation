const test=require('node:test'),assert=require('node:assert/strict');
const {fileQuery}=require('./pc_file_search.js');
test('Default folder view hides raw text and data files without deleting them',()=>{
 const {visibleFiles}=require('./pc_file_search.js');const rows=['wave.png','summary.json','events.csv','说明.txt','photo.JPG'].map(name=>({name}));
 assert.deepEqual(visibleFiles(rows).map(r=>r.name),['wave.png','photo.JPG']);assert.equal(visibleFiles(rows,true),rows);assert.equal(rows.length,5);
});
test('Preview supports bounded inert images and text, leaving active files download only',()=>{
 const {previewKind}=require('./pc_file_search.js');
 assert.equal(previewKind('wave.PNG',20000),'image/png');
 assert.equal(previewKind('results.csv',4000),'text');
 for(const name of ['script.html','drawing.svg','app.js','report.pdf'])assert.equal(previewKind(name,100),null);
 assert.equal(previewKind('large.csv',600000),null);assert.equal(previewKind('huge.png',11000000),null);
});
test('Explicit PC file commands are separated from conversation and generation requests',()=>{
 for(const [text,query] of [['找电脑文件：预算','预算'],['帮我找电脑文件 report.pdf','report.pdf'],['查找电脑文件 会议记录','会议记录'],['帮我找一下电脑里的预算表','预算表'],['帮我找电脑上的报告.pdf这个文件','报告.pdf']])assert.equal(fileQuery(text),query);
 for(const text of ['帮我写文档','请问怎么找电脑文件','不要找电脑文件','帮我查找资料','你好'])assert.equal(fileQuery(text),null);
});

test('Calling for files opens the dedicated library, optionally with a filename',()=>{
 for(const text of ['我要调用文件','调用文件','打开文件库','查看文件库'])assert.equal(fileQuery(text),'',text);
 assert.equal(fileQuery('我要调用文件：预算'),'预算');assert.equal(fileQuery('调用文件 report.pdf'),'report.pdf');assert.equal(fileQuery('不要调用文件'),null);
});
