'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const theme=require('./partner-theme.js');
const parent={};const origin='https://paired.local';
assert.equal(theme.themeMessage({origin,source:parent,data:{type:'workstation-visual-theme',scheme:'dark'}},origin,parent),'dark');
assert.equal(theme.themeMessage({origin:'https://other.local',source:parent,data:{type:'workstation-visual-theme',scheme:'dark'}},origin,parent),null);
assert.equal(theme.themeMessage({origin,source:{},data:{type:'workstation-visual-theme',scheme:'dark'}},origin,parent),null);
assert.equal(theme.themeMessage({origin,source:parent,data:{type:'workstation-visual-theme',scheme:'invalid'}},origin,parent),null);
assert.equal(theme.themeMessage({origin,source:null,data:{type:'workstation-visual-theme',scheme:'dark'}},origin,null),null);
const html=fs.readFileSync(__dirname+'/collaboration.html','utf8');
const script=[...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].find(m=>!m[0].startsWith('<script id="mobile-controller-script"'))[1];
const ctx={module:{exports:{}}};vm.createContext(ctx);new vm.Script(script).runInContext(ctx);
const {revisionDraft}=ctx.module.exports;
assert.equal(revisionDraft({status:'running',task:'old'},'change',''),null);
assert.equal(revisionDraft({status:'completed',task:'old'},'change','retained'),null);
assert.equal(revisionDraft({status:'completed',task:'old'},'',''),null);
const draft=revisionDraft({id:'old-id',status:'completed',task:'原目标',files:[{name:'result.pptx'}]},'改成三页','');
assert.match(draft,/原目标/);assert.match(draft,/改成三页/);assert.match(draft,/result.pptx/);assert.match(draft,/原文件保留/);
assert.doesNotMatch(draft,/attachment_ids|request_id/);
console.log('PASS partner theme origin/source and completed revision draft guards');
const test=require('node:test');
test('Desktop theme accepts only owning loopback parent when embedded',()=>{
 assert.equal(theme.themeMessage({origin:'http://127.0.0.1:47631',source:parent,data:{type:'workstation-visual-theme',scheme:'dark'}},origin,parent,true),'dark');
 assert.equal(theme.themeMessage({origin:'http://127.0.0.1:47631',source:{},data:{type:'workstation-visual-theme',scheme:'dark'}},origin,parent,true),null);
 assert.equal(theme.themeMessage({origin:'https://arbitrary.local',source:parent,data:{type:'workstation-visual-theme',scheme:'dark'}},origin,parent,true),null);
 assert.equal(theme.themeMessage({origin:'http://127.0.0.1:47631',source:parent,data:{type:'workstation-visual-theme',scheme:'dark'}},origin,parent,false),null);
});
function revisionFixture(status='completed',current='',attachments=[]){
 const calls=[],nodes={};const originalParent={insertBefore(p){p.parentNode=this;}};
 Object.assign(nodes,{note:{value:'调整颜色'},collabTask:{value:current,addEventListener(){},dispatchEvent(){}},addNote:{},sessionCollaborationDialog:{open:false,addEventListener(){},showModal(){this.open=true;},close(){this.open=false;}},sessionCollaborationClose:{},sessionCollaborationHost:{append(p){p.parentNode=this;}},sessionCollaborationNotice:{},collabPanel:{hidden:true,parentNode:originalParent,nextSibling:null}});
 const c={revisionDraft,$:id=>nodes[id],selected:{kind:'collaboration',id:'original',value:{id:'original',task:'旧目标',status,files:[{name:'old.pptx'}]}},attachments,run:fn=>fn(),api:async(...args)=>{calls.push(args);},show:async()=>{},message(){},Event:class{},mobile:{setDetailParent(){}}};
 vm.createContext(c);vm.runInContext(script.slice(script.indexOf('let conversationCollab=null;'),script.indexOf('try{entries=JSON.parse')),c);
 const handler=script.slice(script.indexOf("$('addNote').onclick="),script.indexOf("$('addNote').onclick=")+script.slice(script.indexOf("$('addNote').onclick=")).indexOf('\n'));
 vm.runInContext(handler,c);return {c,nodes,calls,originalParent};
}
test('Checking completed revision prepares reviewable draft without a request, and preserves its source',async()=>{
 const f=revisionFixture();await f.nodes.addNote.onclick();assert.equal(f.calls.length,0);assert.equal(f.nodes.sessionCollaborationDialog.open,true);assert.match(f.nodes.collabTask.value,/调整颜色/);assert.equal(f.c.selected.value.task,'旧目标');assert.equal(f.nodes.note.value,'调整颜色');
 f.c.acceptedSessionCollaboration();assert.equal(f.nodes.collabTask.value,'');assert.equal(f.nodes.collabPanel.parentNode,f.originalParent);
});
test('Revision protects existing goal and attachments',async()=>{
 let f=revisionFixture('completed','already typed');await assert.rejects(f.nodes.addNote.onclick(),/已有草稿/);assert.equal(f.nodes.collabTask.value,'already typed');assert.equal(f.calls.length,0);
 f=revisionFixture('completed','',[{id:'kept'}]);await assert.rejects(f.nodes.addNote.onclick(),/已有附件/);assert.equal(f.nodes.collabTask.value,'');assert.equal(f.calls.length,0);
});
test('A late accepted revision never consumes a newer edited draft',async()=>{
 const f=revisionFixture();await f.nodes.addNote.onclick();f.nodes.collabTask.value='changed during receipt';f.c.acceptedSessionCollaboration();assert.equal(f.nodes.collabTask.value,'changed during receipt');
});
test('Running collaboration uses the original text note endpoint only',async()=>{
 const f=revisionFixture('running');await f.nodes.addNote.onclick();assert.deepEqual(f.calls.map(c=>c[0]),['collaboration_note']);assert.equal(f.calls[0][1].id,'original');assert.equal(f.calls[0][1].text,'调整颜色');assert.equal(f.nodes.collabTask.value,'');
});
test('Real server stage changes the status label without inventing percentages',()=>{
 const mobile=require('./mobile-controller.js');assert.equal(mobile.taskSnapshot({status:'running',stage:'审查'},'collaboration').phase,'审查');assert.equal(mobile.taskSnapshot({status:'running',stage:'提案'},'collaboration').phase,'制作');assert.doesNotMatch(mobile.taskSnapshot({status:'running'},'collaboration').hint,/%|预计/);
});
const noticeMobile=require('./mobile-controller.js');
test('Completed result condenses only verified files with no warnings and a current connection',()=>{
 const compact=noticeMobile.compactTaskResult;
 assert.equal(compact({status:'completed',output_format:'pptx',files:[{name:'real.pptx'}]},'collaboration',true),true);
 for(const [task,connected]of [[{status:'completed',output_format:'pptx',files:[]},true],[{status:'completed',output_format:'pptx',files:[{name:'only.txt'}]},true],[{status:'completed',output_format:'pptx',files:[{name:'real.pptx'}]},false],[{status:'completed',files:[{name:'real.pptx'}],error:'生成有错误'},true],[{status:'completed',files:[{name:'large.pptx',size:11*1024*1024}]},true]])assert.equal(compact(task,'collaboration',connected),false);
 const css=fs.readFileSync(__dirname+'/partner-theme.css','utf8');assert.match(css,/#mcTaskOverview\[data-state=completed\]\[data-compact=true\] :is\(h3,h4,#mcTaskDestination,#mcTaskNext,#mcTaskOutput\)/);
});
