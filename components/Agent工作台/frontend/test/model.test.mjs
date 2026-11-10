import test from 'node:test';
import assert from 'node:assert/strict';
import {filterMessages,groupRounds} from '../src/model.mjs';
test('filters preserve filename order and search Chinese/model/body',()=>{
 const messages=[{seat:'A',model:'one',body:'中文提案',role:'创作'},{seat:'B',model:'two',body:'意见',role:'评审'}];
 assert.deepEqual(filterMessages(messages,'A','中文'),[messages[0]]);
 assert.deepEqual(filterMessages(messages,'all','TWO'),[messages[1]]);
 assert.deepEqual(filterMessages(messages,'B','中文'),[]);
});
test('round changes remain chronological, including a repeated round',()=>{
 const rows=[{round:1},{round:2},{round:1}];
 assert.deepEqual(groupRounds(rows).map(g=>g.round),[1,2,1]);
 assert.deepEqual(groupRounds([]),[]);
});
