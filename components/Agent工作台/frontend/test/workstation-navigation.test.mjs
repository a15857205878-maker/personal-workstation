import test from 'node:test';
import assert from 'node:assert/strict';
import {NAV_SECTIONS,filterNavigation,pageInfo} from '../src/workstation-navigation.mjs';

test('all navigation destinations resolve to an existing software page',()=>{
 for(const section of NAV_SECTIONS)for(const item of section.items)assert.equal(pageInfo(item.id).id,item.id);
 assert.equal(pageInfo('tasks').section,'工作区');
 assert.equal(pageInfo('chat').section,'交流与陪伴');
 assert.equal(pageInfo('not-a-page').id,'overview');
});
test('function search matches labels, aliases and whole categories',()=>{
 assert.deepEqual(filterNavigation('游戏')[0].items.map(i=>i.id),['games']);
 assert.deepEqual(filterNavigation('ppt')[0].items.map(i=>i.id),['tasks']);
 assert.equal(filterNavigation('工作区')[0].items.length,3);
 assert.deepEqual(filterNavigation('实验聊天')[0].items.map(i=>i.id),['chat']);
 assert.deepEqual(filterNavigation('交流与陪伴')[0].items.map(i=>i.id),['chat','companion']);
 assert.equal(filterNavigation('不存在的功能').length,0);
 assert.deepEqual(filterNavigation('  '),NAV_SECTIONS);
});
test('filtering never modifies the shared navigation catalogue',()=>{
 const before=JSON.stringify(NAV_SECTIONS);filterNavigation('游戏');
 assert.equal(JSON.stringify(NAV_SECTIONS),before);
});
