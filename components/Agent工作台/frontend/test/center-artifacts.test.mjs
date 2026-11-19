import test from 'node:test';
import assert from 'node:assert/strict';
import {artifactGroups,validCenterLink} from '../src/center-artifacts.mjs';
test('center artifacts group by actual conversation and search owner or subtask',()=>{
 const items=[{id:'1',source_kind:'center',conversation_id:'a'.repeat(32),conversation_title:'项目',job_title:'周报',owner_name:'小紫',name:'a.docx'},{id:'2',source_kind:'external',name:'b.pdf',title:'资料'}];
 assert.equal(artifactGroups(items,'小紫','all')[0].items[0].id,'1');assert.equal(artifactGroups(items,'周报','center').length,1);assert.equal(artifactGroups(items,'','all').length,2);assert.equal(items.length,2);
});
test('back links require a recorded center and optional turn id',()=>{
 assert.equal(validCenterLink({conversation_id:'a'.repeat(32),turn_id:'b'.repeat(32)}),true);
 for(const f of [{conversation_id:'../data'},{conversation_id:'a'.repeat(32),turn_id:'wrong'},{}])assert.equal(validCenterLink(f),false);
});
test('the history view combines both prior sources and keeps individual source filtering',()=>{
 const rows=[
  {id:'old',source_kind:'station',name:'旧任务.pdf'},
  {id:'advanced',source_kind:'collaboration',name:'高级协作.svg'},
  {id:'external',source_kind:'external',name:'外部资料.txt'},
 ];
 assert.deepEqual(artifactGroups(rows,'','history').flatMap(group=>group.items.map(item=>item.id)),['old','advanced']);
 assert.deepEqual(artifactGroups(rows,'','collaboration').flatMap(group=>group.items.map(item=>item.id)),['advanced']);
});
