import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeStationData,canStart,canComplete,canHandoff} from '../src/station-model.mjs';

test('Chinese task states from the real bridge drive UI execution and polling',()=>{
  const task=normalizeStationData({id:'x',status:'草稿',workflow:{stage:'待开始'}});
  assert.equal(task.status,'draft');
  assert.equal(canStart(task,true,false),true);
  assert.equal(task.workflow.stage,'待开始');
  assert.equal(normalizeStationData([{id:'x',status:'排队中'}])[0].status,'queued');
  assert.equal(normalizeStationData({id:'x',status:'执行中'}).status,'running');
});
test('file-only deliverables can be confirmed and queued jobs cannot hand off',()=>{
  assert.equal(canComplete({status:'awaiting_confirmation',result:'',files:[{name:'x.pptx'}]},false),true);
  assert.equal(canComplete({status:'running',result:'partial'},false),false);
  assert.equal(canHandoff({status:'queued'},false),false);
});
test('a recorded review cannot overwrite its existing round',()=>{
  assert.equal(canStart({status:'awaiting_confirmation',workflow:{started:true}},true,false),false);
  assert.equal(canStart({status:'failed'},true,false),true);
  assert.equal(canStart({status:'draft'},true,true),false);
});


test('New Excel drafts prefer an available executable role while preserving manual choice configuration',async()=>{
 const {initialTaskRole}=await import('../src/station-model.mjs');
 const task={id:'xlsx',default_role_ref:'excel',agents:[{role_ref:'excel'},{role_ref:'text_1'}]};
 const roles={excel:{can_run:false},text_1:{can_run:true}};
 assert.equal(initialTaskRole(task,roles),'text_1');assert.equal(task.default_role_ref,'excel');
 assert.equal(initialTaskRole(task,{excel:{can_run:false},text_1:{can_run:false}}),'excel');
 assert.equal(initialTaskRole({...task,agents:[{role_ref:'excel'}]},roles),'excel');
 assert.equal(initialTaskRole({...task,id:'pptx'},roles),'excel');
 assert.equal(initialTaskRole({...task,default_role_ref:'text_1'},roles),'text_1');
 assert.equal(initialTaskRole(undefined,roles),'');
});

test('explicit client tasks cannot start API and attempted handoffs cannot paste again',()=>{
 assert.equal(canStart({status:'draft',execution_mode:'external'},true,false),false);
 assert.equal(canStart({status:'draft',execution_mode:'api'},true,false),true);
 assert.equal(canHandoff({status:'draft',execution_mode:'api'},false),false);
 assert.equal(canHandoff({status:'draft',execution_mode:'external'},false),true);
 assert.equal(canHandoff({status:'waiting_handoff',execution_mode:'external'},false),false);
 assert.equal(canHandoff({status:'needs_check',execution_mode:'external'},false),false);
});
