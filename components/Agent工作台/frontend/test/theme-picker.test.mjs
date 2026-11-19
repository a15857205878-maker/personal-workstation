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
const outDir=mkdtempSync(path.join(os.tmpdir(),'workstation-theme-picker-'));
const outfile=path.join(outDir,'bundle.cjs');
const result=spawnSync(await resolveEsbuildBinary(center),[path.resolve(here,'../src/theme-picker.jsx'),'--bundle','--platform=node','--format=cjs',`--outfile=${outfile}`,'--external:react','--external:react/jsx-runtime','--external:lucide-react','--loader:.css=empty','--jsx=automatic'],{stdio:'ignore',env:{...process.env,NODE_PATH:path.join(center,'node_modules')}});
assert.equal(result.status,0,'esbuild failed for theme-picker.jsx');
const source=readFileSync(outfile,'utf8');
rmSync(outDir,{recursive:true,force:true});
const calls=[];
const context={module:{exports:{}},exports:{},console,window:{pywebview:{api:{call:async(action,payload)=>{calls.push({action,payload});return {ok:true,data:{theme:'blue',color_scheme:'dark'}};}}}},require:createRequire(path.join(center,'package.json'))};
vm.runInNewContext(source,context);
const {PALETTES,normalizeAppearance,mergeAppearance,nextColorScheme,applyAppearance,appearanceRequest}=context.module.exports;
const plain=value=>JSON.parse(JSON.stringify(value));

test('appearance values are normalized without dropping a valid previous state',()=>{
 assert.deepEqual(plain(normalizeAppearance({theme:'coastal',color_scheme:'dark'})),{chat_background:'auto',background_strength:35,theme:'coastal',color_scheme:'dark'});
 assert.deepEqual(plain(normalizeAppearance({theme:'neon',color_scheme:'sepia'})),{chat_background:'auto',background_strength:35,theme:'mint',color_scheme:'light'});
 assert.deepEqual(plain(normalizeAppearance({theme:'lavender'},{theme:'blue',color_scheme:'dark'})),{chat_background:'auto',background_strength:35,theme:'lavender',color_scheme:'dark'});
 assert.deepEqual(plain(normalizeAppearance(undefined,{theme:'apricot',color_scheme:'dark'})),{chat_background:'auto',background_strength:35,theme:'apricot',color_scheme:'dark'});
 assert.equal(PALETTES.length,5);
 assert.equal(nextColorScheme('light'),'dark');
 assert.equal(nextColorScheme('dark'),'light');
});

test('a partial save keeps the last successful field and prefers the returned record',()=>{
 assert.deepEqual(plain(mergeAppearance({theme:'mint',color_scheme:'dark'},{color_scheme:'light'},{color_scheme:'light'})),{chat_background:'auto',background_strength:35,theme:'mint',color_scheme:'light'});
 assert.deepEqual(plain(mergeAppearance({theme:'mint',color_scheme:'dark'},{theme:'blue'},{theme:'blue',color_scheme:'dark'})),{chat_background:'auto',background_strength:35,theme:'blue',color_scheme:'dark'});
 assert.deepEqual(plain(mergeAppearance({theme:'mint',color_scheme:'dark'},{theme:'blue'},{color_scheme:'light'})),{chat_background:'auto',background_strength:35,theme:'blue',color_scheme:'light'});
});

test('DOM attributes cover palette, color-scheme and the native color-scheme hint',()=>{
 const attrs={};
 const root={dataset:{},style:{setProperty(name,value){this[name]=value;}},setAttribute:(name,value)=>{attrs[name]=value;}};
 applyAppearance({theme:'coastal',color_scheme:'dark'},root);
 assert.equal(root.dataset.palette,'coastal');
 assert.equal(root.dataset.colorScheme,'dark');
 assert.equal(root.style.colorScheme,'dark');
 assert.equal(attrs['color-scheme'],'dark');
});

test('partial API payloads are exact and failures reject instead of pretending',async()=>{
 const saved=await appearanceRequest('api_appearance_save',{color_scheme:'dark'});
 assert.deepEqual(plain(saved),{theme:'blue',color_scheme:'dark'});
 assert.deepEqual(plain(calls.at(-1)),{action:'api_appearance_save',payload:{color_scheme:'dark'}});
 await appearanceRequest('api_appearance_save',{theme:'blue'});
 assert.deepEqual(plain(calls.at(-1)),{action:'api_appearance_save',payload:{theme:'blue'}});
 context.window.pywebview.api.call=async()=>({ok:false,error:'主题保存失败'});
 await assert.rejects(()=>appearanceRequest('api_appearance_save',{color_scheme:'light'}),/主题保存失败/);
 delete context.window.pywebview;
 await assert.rejects(()=>appearanceRequest('api_appearance_get'),/等待本地桌面服务/);
});

test('background survives theme changes and zero strength is meaningful',()=>{
 const old={theme:'blue',color_scheme:'dark',chat_background:'coast',background_strength:0};
 const merged=mergeAppearance(old,{color_scheme:'light'},{theme:'blue',color_scheme:'light'});
 assert.equal(merged.chat_background,'coast');assert.equal(merged.background_strength,0);
 const root={dataset:{},style:{setProperty(name,value){this[name]=value;}},setAttribute(){}};
 applyAppearance({...old,chat_background:'auto',background_strength:50},root);
 assert.equal(root.style['--chat-bg-image'],'var(--partner-aurora)');assert.equal(root.style['--chat-bg-opacity'],'0.5');
 applyAppearance({...old,chat_background:'none'},root);assert.equal(root.style['--chat-bg-image'],'none');
});
