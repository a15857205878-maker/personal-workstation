import test from 'node:test';
import assert from 'node:assert/strict';
import {roomTaskState} from '../src/companion-room-model.mjs';
test('room state is unknown when disconnected, stale or partial',()=>{
 for(const d of [null,{overview_state:'unavailable'},{overview_state:'ready',observed_at:10,counts:{active:0,attention:0}}])assert.equal(roomTaskState(d,100000).kind,'unknown');
});
test('attention takes priority over activity and recent completion',()=>{
 const d={overview_state:'ready',observed_at:100,counts:{attention:1,active:2},notices:[{kind:'done',at:100}]};
 assert.equal(roomTaskState(d,100000).kind,'attention');d.counts.attention=0;assert.equal(roomTaskState(d,100000).kind,'working');
 d.counts.active=0;assert.equal(roomTaskState(d,100000).kind,'done');d.notices[0].at=1;assert.equal(roomTaskState(d,100000).kind,'idle');
});
