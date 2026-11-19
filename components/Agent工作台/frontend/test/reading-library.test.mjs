import test from 'node:test';
import assert from 'node:assert/strict';
import {filterBooks,adjacentTrack} from '../src/reading-library.mjs';
test('search matches literal saved notes and keeps archive/state boundaries',()=>{
 const items=[{id:'a',kind:'book',title:'书',notes:'[重点] 笔记',state:'reading',archived:false},{id:'b',kind:'book',title:'另一本',notes:'',state:'unread',archived:false},{id:'c',kind:'book',title:'书',notes:'[重点]',state:'reading',archived:true}];
 assert.deepEqual(filterBooks(items,'[重点]','all').map(x=>x.id),['a']);assert.deepEqual(filterBooks(items,'','noted').map(x=>x.id),['a']);assert.deepEqual(filterBooks(items,'','archived').map(x=>x.id),['c']);assert.equal(items.length,3);
});
test('music navigation wraps only within the current nonarchived list',()=>{
 const rows=[{id:'a'},{id:'b'}];assert.equal(adjacentTrack(rows,'b',1).id,'a');assert.equal(adjacentTrack(rows,'a',-1).id,'b');assert.equal(adjacentTrack([],null,1),null);assert.equal(adjacentTrack(rows,'missing',1).id,'a');
});
