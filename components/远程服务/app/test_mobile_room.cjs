const {test}=require('node:test'),assert=require('node:assert/strict');
const {roomState,shouldRead}=require('./mobile-room.js');
const base={version:1,overview_state:'ready',observed_at:100,counts:{tasks:3,collaborations:2,active:1,attention:1},recent_completed_at:99};
test('room status priority is attention, working, recently done, idle',()=>{
 assert.equal(roomState(base,100000).kind,'attention');
 assert.equal(roomState({...base,counts:{...base.counts,attention:0}},100000).kind,'working');
 const idle={...base,counts:{...base.counts,attention:0,active:0}};assert.equal(roomState(idle,100000).kind,'done');
 assert.equal(roomState({...idle,recent_completed_at:0},100000).kind,'idle');
});
test('offline, partial, stale, absent or malformed data never imply idle',()=>{
 for(const v of [null,{}, {...base,overview_state:'unavailable'}, {...base,observed_at:null}, {...base,observed_at:80}, {...base,counts:{active:0}}, {...base,counts:{...base.counts,attention:true}}, {...base,observed_at:110}])assert.equal(roomState(v,100000).kind,'unknown');
 assert.equal(roomState(base,100000,true).kind,'unknown');
});
test('phone room polling only runs while expanded and visible in More',()=>{
 assert.equal(shouldRead(true,'visible','connection'),true);
 for(const args of [[false,'visible','connection'],[true,'hidden','connection'],[true,'visible','tasks'],[true,'visible','sessions']])assert.equal(shouldRead(...args),false);
});
