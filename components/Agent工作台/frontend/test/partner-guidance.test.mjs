import test from 'node:test';
import assert from 'node:assert/strict';
const load=()=>import('../src/partner-guidance.mjs');
test('Partner guidance describes actual states without promising hidden execution',async()=>{
 const {partnerGuidance}=await load();assert.match(partnerGuidance('draft'),/检查/);assert.match(partnerGuidance('running'),/不要重复提交/);assert.match(partnerGuidance('awaiting_confirmation'),/确认/);assert.match(partnerGuidance('failed'),/错误/);assert.match(partnerGuidance('future'),/核对/);assert.doesNotMatch(partnerGuidance('future'),/已完成|正在处理/);
});
test('Manual handoff and read-only records do not suggest starting here',async()=>{
 const {partnerGuidance}=await load();assert.match(partnerGuidance('draft',{manual:true}),/电脑客户端/);assert.match(partnerGuidance('completed',{readOnly:true}),/只读/);assert.match(partnerGuidance('running',{manual:true}),/正在处理/);assert.match(partnerGuidance('completed',{archived:true}),/归档/);
});

test('Historical sessions do not falsely disable an available manual retry in the wording',async()=>{const {partnerGuidance}=await load();assert.match(partnerGuidance('failed',{history:true}),/记录/);assert.doesNotMatch(partnerGuidance('failed',{history:true}),/只读/);});
