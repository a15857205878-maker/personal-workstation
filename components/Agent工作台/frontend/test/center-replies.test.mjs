import test from 'node:test';
import assert from 'node:assert/strict';
import {replyBlocks,conversationRows,completionSummary,groupMessages,compactDeliveries} from '../src/center-replies.mjs';

test('conclusion, bullets and fenced content have distinct readable blocks',()=>{
 const blocks=replyBlocks('结论：可行。\n\n- 先整理资料\n- 再制作文件\n\n```html\n<script>alert(1)</script>\n```');
 assert.deepEqual(blocks.map(b=>b.type),['paragraph','list','code']);assert.equal(blocks[1].items.length,2);assert.equal(blocks[2].text,'<script>alert(1)</script>');
});
test('main response is the actual last speaker, earlier replies stay available',()=>{
 const rows=conversationRows({messages:[{seat:'U',content:'ask'},{seat:'A',content:'A原文'},{seat:'B',content:'B原文'}]});
 assert.equal(rows.primary.content,'B原文');assert.equal(rows.earlier[0].content,'A原文');
 const failed=conversationRows({messages:[{seat:'A',state:'completed'},{seat:'B',state:'failed',content:''}]});assert.equal(failed.primary.state,'failed');
});
test('completion summary reflects failed or missing jobs instead of model success claims',()=>{
 assert.equal(completionSummary({state:'completed',jobs:[{state:'completed'},{state:'failed'}]}),'已完成 1/2 项，1 项未完成');
 assert.equal(completionSummary({state:'running',jobs:[{state:'completed'},{state:'running'}]}),'进行中 · 已完成 1/2 项');
 assert.equal(completionSummary({state:'interrupted',jobs:[{state:'interrupted'}]}),'已完成 0/1 项，1 项未完成');
});
test('legacy single-run execution is counted and preserves failed and cancelled status',()=>{
 assert.equal(completionSummary({kind:'execute',state:'completed',run:{status:'completed'}}),'已完成 1/1 项');
 assert.equal(completionSummary({kind:'execute',state:'failed',run:{status:'failed'}}),'失败 · 已完成 0/1 项，1 项未完成');
 assert.equal(completionSummary({kind:'execute',state:'cancelled',run:{status:'cancelled'}}),'已取消 · 已完成 0/1 项，1 项未完成');
});
test('group view keeps every actual speaker in chronological order including incomplete messages',()=>{
 const messages=[{id:'u',seat:'U'},{id:'b1',seat:'B',state:'completed'},{id:'a1',seat:'A',state:'completed'},{id:'b2',seat:'B',state:'running',content:''}];
 assert.deepEqual(groupMessages({messages}),messages.slice(1));assert.deepEqual(groupMessages(null),[]);
});

test('collapse production chatter only after every job has registered successful files',()=>{
 const job={state:'completed',run:{status:'completed',files:[{name:'result.docx'}]}};
 const turn={state:'completed',jobs:[job,job,job]};assert.equal(compactDeliveries(turn),true);
 for(const state of ['prepared','running','failed','interrupted','cancelled'])assert.equal(compactDeliveries({...turn,state}),false);
 assert.equal(compactDeliveries({...turn,error:'需核对'}),false);assert.equal(compactDeliveries({...turn,failures:[{item:'A'}]}),false);
 for(const run of [{status:'completed',files:[]},{status:'failed',files:[{name:'partial.docx'}]},{status:'completed',files:[{}]},{status:'completed',error:'不完整',files:[{name:'a.docx'}]}])assert.equal(compactDeliveries({...turn,jobs:[job,{run}]}),false);
 assert.equal(compactDeliveries({state:'completed',jobs:[]}),false);assert.equal(compactDeliveries({state:'completed'}),false);
});
