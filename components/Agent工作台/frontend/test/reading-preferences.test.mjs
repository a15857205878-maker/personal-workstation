import test from 'node:test';
import assert from 'node:assert/strict';
import {preferenceWriter,whenBridgeReady} from '../src/reading-preferences.mjs';
test('older preference write finishes before newer leave-page snapshot is sent',async()=>{
 const sent=[];let release;
 const writer=preferenceWriter(v=>{sent.push(v);return sent.length===1?new Promise(r=>release=r):Promise.resolve();});
 const first=writer.save({font:20}),last=writer.save({font:24});await Promise.resolve();assert.equal(sent.length,1);release();await Promise.all([first,last]);assert.deepEqual(sent,[{font:20},{font:24}]);
});
test('failed writes allow another explicit save and initial restored settings are not rewritten',async()=>{
 let count=0;const errors=[];const w=preferenceWriter(async()=>{if(++count===1)throw Error('fail');},e=>errors.push(e.message));
 w.markSaved({font:18});await w.save({font:18});assert.equal(count,0);await w.save({font:20});await w.save({font:20});assert.equal(count,2);assert.deepEqual(errors,['fail']);
});

test('preference initialization waits for the desktop bridge and can be cancelled',()=>{
 const root=new EventTarget();let calls=0;const cancel=whenBridgeReady(root,()=>calls++);assert.equal(calls,0);root.pywebview={api:{call(){}}};root.dispatchEvent(new Event('pywebviewready'));assert.equal(calls,1);cancel();
 const other=new EventTarget();whenBridgeReady(other,()=>calls++)();other.dispatchEvent(new Event('pywebviewready'));assert.equal(calls,1);
});
