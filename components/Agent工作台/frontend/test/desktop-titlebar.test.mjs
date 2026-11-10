import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createRequire} from 'node:module';
import {existsSync,mkdtempSync,readFileSync,rmSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import vm from 'node:vm';

const here=path.dirname(fileURLToPath(import.meta.url));
const center=process.env.WORKSTATION_CENTER||path.resolve(here,'../../../个人工具中心新版/frontend');
assert.ok(existsSync(path.join(center,'scripts/esbuild-binary.mjs')),'tool-center esbuild helper not found: '+center);
const {resolveEsbuildBinary}=await import(pathToFileURL(path.join(center,'scripts/esbuild-binary.mjs')).href);
const outDir=mkdtempSync(path.join(os.tmpdir(),'workstation-titlebar-'));
const outfile=path.join(outDir,'bundle.cjs');
const result=spawnSync(await resolveEsbuildBinary(center),[path.resolve(here,'../src/desktop-titlebar.jsx'),'--bundle','--platform=node','--format=cjs',`--outfile=${outfile}`,'--external:react','--external:react/jsx-runtime','--external:lucide-react','--loader:.css=empty','--jsx=automatic'],{stdio:'ignore',env:{...process.env,NODE_PATH:path.join(center,'node_modules')}});
assert.equal(result.status,0,'esbuild failed for desktop-titlebar.jsx');
const source=readFileSync(outfile,'utf8');
rmSync(outDir,{recursive:true,force:true});
const calls=[];
const context={module:{exports:{}},exports:{},console,window:{addEventListener(){},removeEventListener(){},pywebview:{api:{call:async(action,payload)=>{calls.push({action,payload});return {ok:true,data:{maximized:true,requested:payload.action}};}}}},require:createRequire(path.join(center,'package.json'))};
vm.runInNewContext(source,context);
const {windowAction,maximizedFrom}=context.module.exports;
const plain=value=>JSON.parse(JSON.stringify(value));

test('native window actions use the fixed bridge and exact payload',async()=>{
 const state=await windowAction('state');
 assert.deepEqual(plain(state),{maximized:true,requested:'state'});
 assert.deepEqual(plain(calls.at(-1)),{action:'api_window_action',payload:{action:'state'}});
 await windowAction('toggle_maximize');
 assert.deepEqual(plain(calls.at(-1)),{action:'api_window_action',payload:{action:'toggle_maximize'}});
 for(const action of ['minimize','close']){
  await windowAction(action);
  assert.deepEqual(plain(calls.at(-1)),{action:'api_window_action',payload:{action}});
 }
});

test('window state accepts bridge data and native event detail without inventing success',()=>{
 assert.equal(maximizedFrom({maximized:true},false),true);
 assert.equal(maximizedFrom({maximized:false},true),false);
 assert.equal(maximizedFrom({requested:'minimize'},true),true);
 assert.equal(maximizedFrom(undefined,false),false);
 assert.equal(maximizedFrom(null,true),true);
});

test('window API errors and missing bridge reject',async()=>{
 context.window.pywebview.api.call=async()=>({ok:false,error:'窗口控制不可用'});
 await assert.rejects(()=>windowAction('close'),/窗口控制不可用/);
 delete context.window.pywebview;
 await assert.rejects(()=>windowAction('state'),/原生窗口服务未就绪/);
});
