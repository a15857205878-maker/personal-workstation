import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
const base=new URL('../dist/tools/',import.meta.url);
const source=await readFile(new URL('assets/workstation-bridge.js',base),'utf8');
const html=await readFile(new URL('index.html',base),'utf8');
const css=await readFile(new URL('assets/app.css',base),'utf8');
assert.match(html,/script-src 'self';/);
assert.doesNotMatch(html,/https?:|<script(?![^>]*src=)/);
assert.doesNotMatch(css,/@import|url\(\s*['"]?https?:/);
const calls=[];
const location={origin:'http://127.0.0.1:48900'};
const parent={location,pywebview:{api:{call:async(...args)=>{calls.push(args);return {ok:true,data:{}};}}}};
const window={};
vm.runInNewContext(source,{window,parent,location});
const call=window.pywebview.api.call;
for(const action of ['bootstrap','game_add','game_save','game_add_tool','pick_files','pick_output','pack_start','job_status','wheel_draw']){
  assert.equal((await call(action,{id:'test'})).ok,true);
  assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1))),['workstation_tool_call',{action,payload:{id:'test'}}]);
}
const count=calls.length;
for(const action of ['launch_tool','pet_launch','settings_save','open_folder','system','job_cancel','__proto__'])assert.equal((await call(action)).ok,false);
assert.equal(calls.length,count);
parent.location={origin:'https://other.invalid'};
assert.equal((await call('bootstrap')).ok,false);
assert.equal(calls.length,count);
console.log('Original-tools shim: precise allowed delegation, denied general actions, origin guard, CSP and no external assets passed.');
