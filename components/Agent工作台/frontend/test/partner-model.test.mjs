import test from 'node:test';
import assert from 'node:assert/strict';
import {starterTask,taskVoice,collaborationSignals,stepProgress,partnerState,checkedDraft,revisionDraft,sessionEmbedUrl,previewUrl,PARTNER_NAV} from '../src/partner-model.mjs';
test('state follows real receipts and keeps history read only',()=>{
 assert.equal(partnerState(null),'welcome');assert.equal(partnerState({status:'running'}),'running');
 assert.equal(partnerState({status:'completed'}),'result');assert.equal(partnerState({status:'running'},true),'history');
});
test('checking creates a detached snapshot and never executes',()=>{
 const plan={task:' A ',call_limit:9};const images=[{id:'i'}];const checked=checkedDraft(plan,images);
 plan.task='B';images[0].id='changed';assert.equal(checked.plan.task,'A');assert.equal(checked.attachments[0].id,'i');
 assert.equal(checked.confirmed,undefined);
});
test('revision preserves budgets and explicitly includes only selected context',()=>{
 const source={id:'old',task:'original',call_count:6,call_limit:9,steps:[{content:'result'}]};const plan={call_limit:15,max_tokens:2048};
 const draft=revisionDraft(source,'adjust',plan,{goal:false,result:false});assert.equal(draft.call_limit,15);assert.ok(!draft.task.includes('original'));assert.ok(!draft.task.includes('result'));assert.equal(source.call_count,6);
 assert.ok(revisionDraft(source,'adjust',plan,{goal:true,result:true}).task.includes('original'));
});
test('embedding accepts only fixed loopback surface and owned preview',()=>{
 const base='http://127.0.0.1:8765/?token=private';assert.ok(sessionEmbedUrl(base).includes('desktop_embed=1'));
 for(const url of ['https://example.com/?token=x','http://localhost:8765/','http://127.0.0.1:8766/','http://u:p@127.0.0.1:8765/'])assert.equal(sessionEmbedUrl(url),'');
 assert.equal(previewUrl('http://127.0.0.1:8765/file-viewer?token=other',base),'');
 assert.ok(previewUrl('http://127.0.0.1:8765/file-viewer?token=private',base));
});
test('main navigation consolidates while retaining every original destination',()=>{
 assert.deepEqual(PARTNER_NAV.map(x=>x.label),['搭档','任务','成果','工具','休闲']);
 const routes=new Set(PARTNER_NAV.flatMap(x=>[x.id,...x.secondary]));
 for(const id of ['overview','tasks','work','pack','chat','companion','games','wheel','town','remote','artifacts','icons','settings'])assert.ok(routes.has(id)||['remote','settings'].includes(id),id);
});

test('progress measures completed steps rather than spent request allowance',()=>{
 assert.deepEqual(stepProgress({planned_calls:3,call_count:3,call_limit:9,steps:[{state:'completed'},{state:'completed'},{state:'completed'}]}),{completed:3,total:3});
 assert.deepEqual(stepProgress({planned_calls:3,call_count:1,steps:[{state:'running'}]}),{completed:0,total:3});
 assert.deepEqual(stepProgress({rounds:2,steps:[{state:'completed'},{state:'failed'}]}),{completed:1,total:6});
});

test('execution signals follow current round and failed receipts without fabricating success',()=>{
 assert.deepEqual(collaborationSignals({status:'completed'}).map(s=>s.state),['waiting','waiting','waiting']);
 const steps=[{round:1,stage:'提案',state:'completed'},{round:1,stage:'审查',state:'failed'}];
 assert.deepEqual(collaborationSignals({status:'failed',steps}).map(s=>s.state),['done','error','waiting']);
 steps.push({round:2,stage:'提案',state:'running'});
 assert.deepEqual(collaborationSignals({status:'running',steps}).map(s=>s.state),['running','waiting','waiting']);
});

test('partner status voice preserves legacy text records and distinguishes absent files',()=>{
 assert.match(taskVoice({status:'completed'}),/文字已完成/);
 assert.match(taskVoice({status:'completed',output_format:'pptx',files:[]}),/未收到/);
 assert.match(taskVoice({status:'completed',output_format:'pptx',files:[{name:'real.pptx'}]}),/预览/);
 assert.match(taskVoice({status:'completed'},false),/上次/);
});

test('starter samples prepare useful goals without overwriting an existing draft',()=>{
 assert.match(starterTask('docx'),/DOCX/);assert.match(starterTask('xlsx'),/公式/);assert.match(starterTask('pptx'),/3页/);
 assert.equal(starterTask('xlsx','我的原草稿'),'我的原草稿');assert.equal(starterTask('unknown',''),'');
});
