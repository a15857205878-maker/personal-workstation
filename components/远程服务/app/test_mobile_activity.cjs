const {test}=require('node:test'),assert=require('node:assert/strict');
const {activityState,acceptObservation,activityVisual}=require('./mobile-room.js');
const base={available:true,scene:'home',pose:'front',night:false,automatic:true,held:false,phase:'stable',observed_at:100,changed_at:90};
test('activity is unknown if absent, unavailable, stale, future or malformed',()=>{
 for(const v of [null,{}, {...base,available:false},{...base,observed_at:84},{...base,observed_at:106},{...base,scene:'bogus'},{...base,pose:'walk'}, {...base,held:'false'}])assert.equal(activityState(v,100000).kind,'unknown');
 assert.equal(activityState(base,100000,true).kind,'unknown');
});
test('server scene, pose, night and activity modes are preserved without simulation',()=>{
 assert.equal(activityState(base,100000).mode,'自动活动');
 assert.equal(activityState({...base,automatic:false},100000).mode,'当前活动');
 assert.equal(activityState({...base,held:true},100000).mode,'固定场景');
 assert.equal(activityState({...base,phase:'paused'},100000).mode,'暂停');
 for(const scene of ['room','home','plaza','orchard','desktop'])for(const pose of ['back','turn','relax','rest','front','sit']){const s=activityState({...base,scene,pose,night:true},100000);assert.equal(s.scene,scene);assert.equal(s.pose,pose);assert.equal(s.night,true);}
});
test('older receipts cannot replace newer observations',()=>{
 const latest={observed_at:100,pet_activity:base};
 assert.equal(acceptObservation(latest,{observed_at:99,pet_activity:base}),false);
 assert.equal(acceptObservation(latest,{observed_at:101,pet_activity:{...base,observed_at:99}}),false);
 assert.equal(acceptObservation(latest,{observed_at:101,pet_activity:{...base,observed_at:101}}),true);
});
test('only an exact fixed asset can claim a matched visual',()=>{
 assert.equal(activityVisual({...base,kind:'known'},{'home.front':'data:front'}),'data:front');
 assert.equal(activityVisual({...base,kind:'unknown'},{'home.front':'data:front'}),null);
 assert.equal(activityVisual({...base,kind:'known',pose:'rest'},{'home.front':'data:front'}),null);
});

