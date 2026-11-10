const test=require('node:test'),assert=require('node:assert/strict');
const {collaborationGoal}=require('./session_actions.js');
test('Explicit dual-model goals prepare UI and ordinary chat remains native',()=>{
 assert.equal(collaborationGoal('用双模型写一份方案'),'写一份方案');
 assert.equal(collaborationGoal('我要双模型给我设计一个网页'),'给我设计一个网页');assert.equal(collaborationGoal('双模型：检查这段代码'),'检查这段代码');assert.equal(collaborationGoal('双模型'),'');
 for(const text of ['你好','不要用双模型','请问双模型是什么','我要调用文件'])assert.equal(collaborationGoal(text),null);
});
