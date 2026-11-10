import test from 'node:test';
import assert from 'node:assert/strict';
import {catalog,toggleTrait,customFromTraits} from '../src/style-catalog.mjs';
test('catalog contains both full personas and all library dimensions',()=>{
 assert.deepEqual(catalog.presets.map(p=>p.name),['协作助手','审阅助手']);assert.equal(catalog.dimensions.length,9);
 assert.ok(catalog.presets[0].text.includes('不虚构记忆或执行结果'));
 assert.ok(catalog.presets[1].text.includes('不虚构记忆或执行结果'));
});
test('unfenced persona keeps behavioral rules when using the word library',()=>{
 const result=customFromTraits({preset:'lele'},[{dimension:'幽默',value:'冷幽默'}]);
 assert.ok(result.text.includes('不虚构记忆或执行结果'));
 assert.ok(result.text.includes('禁用句'));
});
test('trait choices replace within one dimension, toggle off, and cap at four',()=>{
 let picks=toggleTrait([],'温度','温和');picks=toggleTrait(picks,'温度','清冷');assert.equal(picks.length,1);
 assert.deepEqual(toggleTrait(picks,'温度','清冷'),[]);
 for(const d of ['能量','幽默','节奏'])picks=toggleTrait(picks,d,'适中');
 assert.throws(()=>toggleTrait(picks,'锋芒','直给'),/4/);
});
test('traits generate editable custom style without silently truncating text',()=>{
 const picks=[{dimension:'温度',value:'温和'}];
 assert.match(customFromTraits({preset:'lele'},picks).text,/协作助手/);
 assert.match(customFromTraits({preset:'custom',text:'保留这段'},picks).text,/保留这段/);
 assert.throws(()=>customFromTraits({preset:'custom',text:'字'.repeat(3000)},picks),/3000/);
});
