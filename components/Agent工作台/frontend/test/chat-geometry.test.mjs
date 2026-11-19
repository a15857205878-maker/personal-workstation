import test from 'node:test';
import assert from 'node:assert/strict';
import {historyWidth,inputHeight} from '../src/chat-geometry.mjs';
test('history bounds reserve readable conversation width and reject nonfinite values',()=>{
 assert.equal(historyWidth(999,900),360);assert.equal(historyWidth(-40,900),180);
 assert.equal(historyWidth(350,600),260);assert.equal(historyWidth(NaN,900),248);
 assert.equal(historyWidth(Infinity,900),248);
});
test('input height stays within available chat space and accepts reset',()=>{
 assert.equal(inputHeight(400,900),300);assert.equal(inputHeight(-20,900),48);
 assert.equal(inputHeight(300,400),144);assert.equal(inputHeight(undefined,800),72);
 assert.equal(inputHeight(72,800),72);
});
