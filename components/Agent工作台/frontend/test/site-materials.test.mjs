import test from 'node:test';
import assert from 'node:assert/strict';
import {moveEntry,exportable,mergeSnapshot} from '../src/site-materials-model.mjs';
test('moving steps preserves metadata and cannot wrap at boundaries',()=>{
 const entries=[{id:'a',notes:'keep'},{id:'b'},{id:'c'}];
 assert.deepEqual(moveEntry(entries,'a',-1),entries);
 assert.deepEqual(moveEntry(entries,'b',1).map(e=>e.id),['a','c','b']);
 assert.equal(entries[0].notes,'keep');assert.deepEqual(entries.map(e=>e.id),['a','b','c']);
});
test('export only selects public and available references in visual order',()=>{
 const rows=[{id:'a',public:false},{id:'b',public:true,file_status:'changed'},{id:'c',public:true,file_status:'none'},{id:'d',public:true,file_status:'ready'}];
 assert.deepEqual(exportable(rows,['a','b','d','c']).map(e=>e.id),['c','d']);
});
test('incoming refresh keeps unsaved project until explicitly discarded',()=>{
 const local={id:'a',title:'draft'},remote={revision:'new',projects:[{id:'a',title:'saved'}]};
 assert.equal(mergeSnapshot(local,remote,true).title,'draft');
 assert.equal(mergeSnapshot(local,remote,false).title,'saved');
 assert.equal(mergeSnapshot({id:'gone'},remote,false),null);
});
