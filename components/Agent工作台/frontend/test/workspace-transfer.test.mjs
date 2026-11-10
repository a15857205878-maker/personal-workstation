import test from 'node:test';
import assert from 'node:assert/strict';
import {advancedBrief,acceptBrief,importTask} from '../src/workspace-transfer.mjs';
test('advanced brief preserves request, error and result, never claims attached files read',()=>{
 const text=advancedBrief({task:{title:'例子',instruction:'原需求',materials:'资料',requirements:'要求',result:'已有正文',error:'通道失败'}});
 for(const word of ['原需求','资料','要求','已有正文','通道失败'])assert.ok(text.includes(word));
 assert.ok(text.includes('未读取附件'));
});
test('limits reject oversized input instead of truncating',()=>{
 assert.equal(acceptBrief('  内容\r\n',8000),'  内容\r\n');
 for(const text of ['', '字'.repeat(8001),null])assert.throws(()=>acceptBrief(text,8000));
});
test('incoming task never overwrites unsaved draft without explicit consent',()=>{
 const form={task_type:'pptx',role:'presentation',instruction:'旧需求',materials:'旧资料',requirements:'旧限制'};
 assert.throws(()=>importTask(form,'新需求',false));
 assert.equal(form.instruction,'旧需求');
 const changed=importTask(form,'新需求',true);
 assert.equal(changed.task_type,'pptx');assert.equal(changed.instruction,'新需求');assert.equal(changed.materials,'');assert.equal(changed.requirements,'');
 assert.equal(importTask({...form,instruction:'',materials:'',requirements:''},'新需求',false).instruction,'新需求');
});
