import test from 'node:test';
import assert from 'node:assert/strict';
import {filterConversations,conversationBlock} from '../src/conversation-operations.mjs';
test('search is literal and archived records remain recoverable',()=>{
 const rows=[{title:'研究 [A]',archived:false},{title:'旧研究',archived:true}];
 assert.deepEqual(filterConversations(rows,'[A]','active'),[rows[0]]);
 assert.deepEqual(filterConversations(rows,'研究','archived'),[rows[1]]);
 assert.equal(rows.length,2);
});
test('send budget matches actual responder count and archived state',()=>{
 assert.equal(conversationBlock({call_count:25,call_limit:30},'ABC',2).includes('不足'),true);
 assert.equal(conversationBlock({call_count:25,call_limit:30},'AC',2),'');
 assert.equal(conversationBlock({archived:true,call_count:0,call_limit:30},'A',1).includes('归档'),true);
});
