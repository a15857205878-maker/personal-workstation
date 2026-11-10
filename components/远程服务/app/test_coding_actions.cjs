const test=require('node:test'),assert=require('node:assert/strict');
const {codingGoal,requestRecord}=require('./coding_actions.js');
test('Only explicit coding commands leave native chat',()=>{assert.equal(codingGoal('代码协作：做一个预算网页'),'做一个预算网页');assert.equal(codingGoal('你好'),null);assert.equal(codingGoal('不要代码协作'),null);});
test('An uncertain creation keeps its identity and blocks a different project',()=>{const first=requestRecord(null,'做预算','one');assert.equal(requestRecord({...first,state:'pending'},'做预算','two').id,'one');assert.throws(()=>requestRecord({...first,state:'pending'},'做游戏','two'));assert.equal(requestRecord({...first,state:'done'},'做游戏','two').id,'two');});

test('Project kind and reference URL are part of the persisted request identity',()=>{const record=requestRecord(null,'目标','one',{project_kind:'web',reference_url:'https://example.com'});assert.throws(()=>requestRecord(record,'目标','two',{project_kind:'local-tool'}));assert.throws(()=>requestRecord(record,'目标','two',{project_kind:'web',reference_url:'https://example.org'}));assert.equal(requestRecord(record,'目标','two',{project_kind:'web',reference_url:'https://example.com'}).id,'one');});

const {newRequestId,consumeSource,rejectedRecord}=require('./coding_actions.js');
test('Phone HTTP without randomUUID can still create a stable request ID',()=>{assert.ok(newRequestId({}).length>10);});
test('Inspecting old tasks or editing goal never consumes an unrelated native draft',()=>{assert.equal(consumeSource('草稿','草稿','其他目标',true),false);assert.equal(consumeSource('草稿','草稿','草稿',false),false);assert.equal(consumeSource('代码协作：做网页','代码协作：做网页','做网页',true),true);});
test('Definite HTTP rejection unlocks a new goal while network uncertainty keeps identity',()=>{const record=requestRecord(null,'目标','one');assert.equal(rejectedRecord(record,400).state,'rejected');assert.equal(rejectedRecord(record,503).state,'pending');assert.doesNotThrow(()=>requestRecord(rejectedRecord(record,400),'新目标','two'));});
