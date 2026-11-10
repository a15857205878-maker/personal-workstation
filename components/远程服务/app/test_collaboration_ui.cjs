'use strict';
// Pure-function and frontend contract checks. Does not contact the workstation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, 'collaboration.html'), 'utf8');
const scripts = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].filter(x=>!x[0].startsWith('<script id="mobile-controller-script"'));
assert.equal(scripts.length, 1);
const context = { module: { exports: {} } };
vm.createContext(context);
new vm.Script(scripts[0][1], { filename: 'collaboration.html' }).runInContext(context);
const { canonical, digest, requestEntry, collaborationPayload, budgetText,restoredChoice } = context.module.exports;
assert.equal(restoredChoice('b',[{value:'a'},{value:'b'}]),'b');
assert.equal(restoredChoice('b',[{value:'a'}]),null);
assert.equal(restoredChoice('b',[{value:'b',disabled:true}]),null);
assert.equal(restoredChoice(undefined,[{value:'a'}]),undefined);
assert.equal(canonical({b:2,a:{d:4,c:3}}), canonical({a:{c:3,d:4},b:2}));
let next = 0;
const entries = [], fresh = () => 'request-' + (++next);
const first = requestEntry(entries,'task_create',{instruction:'hello',role:'text_1'},fresh);
assert.equal(requestEntry(entries,'task_create',{role:'text_1',instruction:'hello'},fresh),first);
assert.notEqual(requestEntry(entries,'task_create',{instruction:'changed',role:'text_1'},fresh).id,first.id);
assert.notEqual(requestEntry(entries,'task_submit',{id:'one'},fresh).id,requestEntry(entries,'task_cancel',{id:'one'},fresh).id);
const recovered=JSON.parse(JSON.stringify(entries));
assert.equal(requestEntry(recovered,'task_create',{instruction:'hello',role:'text_1'},fresh).id,first.id);
// Even a digest collision must not reuse another payload's request ID.
const payload={id:'other'};
const collision=[{key:digest(canonical({action:'task_cancel',payload})),signature:'different',id:'wrong'}];
assert.notEqual(requestEntry(collision,'task_cancel',payload,fresh).id,'wrong');
const base={task:'  Write a brief  ',primary:'a',reviewer:'b',rounds:1,calls:3,tokens:1024,maxRounds:10,maxCalls:30,maxTokens:4096};
const valid=collaborationPayload(base);
assert.equal(valid.task,'Write a brief');
assert.equal(valid.context_count,0);
assert.equal(valid.persona,'conductor');
assert.match(budgetText(valid,600),/计划 3 次/);
assert.match(budgetText(valid,600),/3072/);
for(const change of [{task:''},{rounds:2,calls:3},{calls:31},{tokens:4097},{rounds:1.5},{reviewer:''}])assert.throws(()=>collaborationPayload({...base,...change}));
assert.doesNotMatch(html,/\.innerHTML\b|insertAdjacentHTML|eval\(/);
assert.match(html,/await refresh\(\);catalog=await api\('catalog'\)/);
assert.match(html,/request_id:item\.id/);
assert.match(html,/api\('task_create'/);
assert.match(html,/api\('task_submit',\{id\}\)/);
assert.match(html,/api\('collaboration_start',payload\)/);
assert.match(html,/不会自动重试/);
assert.match(html,/未自动重发模型/);
assert.match(html,/\/api\/workbench-artifact\?token=/);
assert.match(html,/readOnly=\['task_get','collaboration_get'\]/);
assert.match(html,/viewport.*width=device-width/);
assert.match(html,/@media\(max-width:420px\)/);
// Every static ID referenced by $ must exist; dynamic IDs are checked separately.
const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(x=>x[1]));
for(const m of scripts[0][1].matchAll(/\$\('([^']+)'\)/g))assert.ok(ids.has(m[1]),'Missing element: '+m[1]);


const {taskAttachmentText}=context.module.exports;
assert.match(taskAttachmentText(undefined),/没有该草稿的附件清单/);
assert.equal(taskAttachmentText([]),'附件：无附件');
assert.equal(taskAttachmentText([{name:'参考.pdf'}]),'附件：参考.pdf');

console.log('PASS: frontend syntax, request identity/recovery, budget validation, DOM safety, explicit submission, and API contracts');

const deliveryValues={task:'预算',primary:'a',reviewer:'b',rounds:1,calls:3,tokens:1024,maxRounds:10,maxCalls:30,maxTokens:4096};
for(const format of ['xlsx','pptx','docx']){const payload=collaborationPayload({...deliveryValues,output_format:format});assert.equal(payload.output_format,format);assert.ok(budgetText(payload,600).includes(format.toUpperCase()));}
assert.equal('output_format' in collaborationPayload(deliveryValues),false);
assert.throws(()=>collaborationPayload({...deliveryValues,output_format:'exe'}));
