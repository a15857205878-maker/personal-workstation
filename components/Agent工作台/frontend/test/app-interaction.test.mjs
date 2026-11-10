import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const base=new URL('../src/',import.meta.url);
test('PC navigation trail collapses duplicates and backtracks while staying bounded',async()=>{
 const {navigateTrail}=await import('../src/app-interaction.mjs');
 assert.deepEqual(navigateTrail(['overview'],'overview'),['overview']);
 assert.deepEqual(navigateTrail(['overview','tasks'],'work'),['overview','tasks','work']);
 assert.deepEqual(navigateTrail(['overview','tasks','work'],'tasks'),['overview','tasks']);
 assert.equal(navigateTrail(Array.from({length:40},(_,i)=>String(i)),'tasks').length,30);
});
test('Remote disconnected refresh retains last valid frame routes',async()=>{
 const {remoteSurface}=await import('../src/app-interaction.mjs');
 const good={online:true,session_url:'http://127.0.0.1:8765/?token=fixture',collaboration_url:'http://127.0.0.1:8765/collaboration?token=fixture',transfer_url:'http://127.0.0.1:8765/transfer?token=fixture'};
 assert.equal(remoteSurface(good,null),good);assert.equal(remoteSurface({online:false},good),good);assert.equal(remoteSurface(null,null),null);
});

test('Rejected tool destination is replaced by the actual page, never kept in back history',async()=>{
 const {correctTrail}=await import('../src/app-interaction.mjs');assert.deepEqual(correctTrail(['overview','pack','tasks','games'],'pack'),['overview','pack','tasks','pack']);assert.deepEqual(correctTrail(['overview','pack','games'],'pack'),['overview','pack']);
});
