import test from 'node:test';
import assert from 'node:assert/strict';
import {responseOptions,memberNames} from '../src/group-members.mjs';
import {groupMessages} from '../src/center-replies.mjs';
test('three identities stay visible and response sets only contain actual members',()=>{
 const roles={A:{name:'DeepSeek'},B:{name:'Codex'},C:{name:'Gemini'}};
 const opts=responseOptions(roles);
 for(const key of ['ABC','CBA','A','B','C','AB','AC','BC'])assert.ok(opts.some(([v])=>v===key));
 assert.equal(memberNames(roles),'DeepSeek · Codex · Gemini');
 const rows=[{seat:'U'},{seat:'A'},{seat:'C',state:'running'},{seat:'B'},{seat:'D'}];
 assert.deepEqual(groupMessages({messages:rows}),rows.slice(1,4));
});
test('old two-member options never mention absent C',()=>{
 const opts=responseOptions({A:{name:'A'},B:{name:'B'}});
 assert.deepEqual(opts.map(([v])=>v),['AB','BA','A','B']);
 assert.ok(opts.every(([v])=>!v.includes('C')));
});
