import test from 'node:test';
import assert from 'node:assert/strict';
import {NAV_SECTIONS,filterNavigation,pageInfo,resolvePage} from '../src/workstation-navigation.mjs';

test('all navigation destinations resolve to an existing software page',()=>{
 for(const section of NAV_SECTIONS)for(const item of section.items)assert.equal(pageInfo(item.id).id,item.id);
 assert.equal(resolvePage('tasks'),'artifacts');
 assert.equal(pageInfo('tasks').id,'artifacts');
 assert.equal(pageInfo('chat').section,'交流与陪伴');
 assert.equal(pageInfo('not-a-page').id,'overview');
});
test('function search matches labels, aliases and whole categories',()=>{
 assert.deepEqual(filterNavigation('游戏')[0].items.map(i=>i.id),['games']);
 assert.ok(!filterNavigation('独立任务').flatMap(s=>s.items).some(i=>i.id==='tasks'));
 assert.equal(filterNavigation('工作区')[0].items.length,2);
 assert.deepEqual(filterNavigation('实验聊天')[0].items.map(i=>i.id),['chat']);
 assert.deepEqual(filterNavigation('交流与陪伴')[0].items.map(i=>i.id),['chat','companion']);
 assert.equal(filterNavigation('不存在的功能').length,0);
 assert.deepEqual(filterNavigation('  '),NAV_SECTIONS);
});
test('filtering never modifies the shared navigation catalogue',()=>{
 const before=JSON.stringify(NAV_SECTIONS);filterNavigation('游戏');
 assert.equal(JSON.stringify(NAV_SECTIONS),before);
});

test('icon studio belongs to tools instead of system and remains searchable by old name',()=>{
 assert.equal(pageInfo('icons').section,'工具');assert.equal(pageInfo('pack').section,'工具');
 assert.ok(!NAV_SECTIONS.find(s=>s.id==='system').items.some(i=>i.id==='icons'));
 assert.ok(filterNavigation('桌宠换装台').flatMap(s=>s.items).some(i=>i.id==='icons'));
});
