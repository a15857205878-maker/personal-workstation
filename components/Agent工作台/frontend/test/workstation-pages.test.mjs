import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createRequire} from 'node:module';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import vm from 'node:vm';
import {resolveEsbuildBinary} from '../../../个人工具中心新版/frontend/scripts/esbuild-binary.mjs';

const here=path.dirname(fileURLToPath(import.meta.url));
const center=path.resolve(here,'../../../个人工具中心新版/frontend');
const result=spawnSync(await resolveEsbuildBinary(center),[path.resolve(here,'../src/workstation-pages.jsx'),'--bundle','--platform=node','--format=cjs','--external:react','--external:lucide-react','--loader:.css=empty','--jsx=automatic'],{encoding:'utf8',env:{...process.env,NODE_PATH:path.join(center,'node_modules')}});
assert.equal(result.status,0,result.stderr);
const calls=[],context={module:{exports:{}},exports:{},require:createRequire(path.join(center,'package.json')),window:{pywebview:{api:{call:async(action,payload)=>{calls.push({action,payload});return {ok:true,data:{value:1}};}}}}};
vm.runInNewContext(result.stdout,context);
const {desktopCall,toolCall,packPayload,selectedOutput,activeJob}=context.module.exports;
const plain=value=>JSON.parse(JSON.stringify(value));

test('tool calls retain the desktop wrapper and exact nested payload',async()=>{
 await toolCall('materials_choose',{id:'charts'});
 assert.deepEqual(plain(calls.at(-1)),{action:'workstation_tool_call',payload:{action:'materials_choose',payload:{id:'charts'}}});
 await toolCall('pack_start',packPayload([{path:'C:/chosen/a.txt',name:'a.txt',size:4}], 'C:/chosen/output'));
 assert.deepEqual(plain(calls.at(-1)),{action:'workstation_tool_call',payload:{action:'pack_start',payload:{files:['C:/chosen/a.txt'],output_dir:'C:/chosen/output'}}});
 await desktopCall('station_open_file',{id:'task-1',name:'result.txt'});
 assert.deepEqual(plain(calls.at(-1)),{action:'station_open_file',payload:{id:'task-1',name:'result.txt'}});
});
test('native directory response uses path and cancellation preserves the draft',()=>{
 assert.equal(selectedOutput({path:'C:/output',cancelled:false}),'C:/output');
 assert.equal(selectedOutput({output_dir:'C:/future'}),'C:/future');
 assert.equal(selectedOutput({path:'',cancelled:true}),null);
});
test('only queued and running jobs continue polling and block another pack',()=>{
 for(const status of ['queued','running'])assert.equal(activeJob({status}),true);
 for(const status of ['completed','failed','uncertain'])assert.equal(activeJob({status}),false);
 assert.equal(activeJob(null),false);
});
test('bridge failures surface without pretending the action succeeded',async()=>{
 context.window.pywebview.api.call=async()=>({ok:false,error:'目录选择器未就绪'});
 await assert.rejects(()=>toolCall('pick_output'),/目录选择器未就绪/);
 delete context.window.pywebview;
 await assert.rejects(()=>desktopCall('workstation_overview'),/等待本地桌面服务/);
});
