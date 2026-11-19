import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {mkdir,copyFile,stat,cp,readFile,writeFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {resolveEsbuildBinary} from '../../个人工具中心新版/frontend/scripts/esbuild-binary.mjs';
const root=path.dirname(fileURLToPath(import.meta.url));
const center=path.resolve(root,'../../个人工具中心新版/frontend');
const dist=path.join(root,'dist');await mkdir(path.join(dist,'assets'),{recursive:true});
const result=spawnSync(await resolveEsbuildBinary(center),[path.join(root,'src/main.jsx'),'--bundle',`--outfile=${dist}/assets/app.js`,'--format=iife','--target=edge110','--jsx=automatic','--minify','--legal-comments=none','--define:process.env.NODE_ENV="production"'],{cwd:root,stdio:'inherit',env:{...process.env,NODE_PATH:path.join(center,'node_modules')}});
if(result.error||result.status!==0)throw result.error||Error('构建失败');
await copyFile(path.join(root,'src/index.html'),path.join(dist,'index.html'));
await copyFile(path.join(root,'src/index.html'),path.join(dist,'quick.html'));
await copyFile(path.join(root,'src/PHOSPHOR-LICENSE.txt'),path.join(dist,'PHOSPHOR-LICENSE.txt'));
await copyFile(path.join(center,'node_modules/lucide-react/LICENSE'),path.join(dist,'LUCIDE-LICENSE.txt'));
for(const f of ['index.html','assets/app.js','assets/app.css']){const s=await stat(path.join(dist,f));if(!s.size)throw Error('空构建文件');console.log(f,s.size,'bytes');}

// Reuse the already built sibling town UI in an isolated same-window document.
const townSource=path.resolve(root,'../../宝可梦小镇新版/frontend/dist');
const townDist=path.join(dist,'town');
await mkdir(townDist,{recursive:true});
await cp(path.join(townSource,'assets'),path.join(townDist,'assets'),{recursive:true});
await cp(path.join(townSource,'yard'),path.join(townDist,'yard'),{recursive:true});
const townHtml=await readFile(path.join(townSource,'index.html'),'utf8');
const firstBundle=/<script\b[^>]*\bsrc=["'][^"']+["'][^>]*>/i;
if(!firstBundle.test(townHtml))throw Error('小镇构建缺少脚本入口');
const shim=`(()=>{const allowed=new Set(['bootstrap','focus_state','town_action','focus_start','focus_pause','focus_resume','focus_end','set_mode','settings_save']);
const call=async(action,payload={})=>{if(!allowed.has(action))return {ok:false,error:'不支持的小镇操作'};const api=parent.pywebview?.api;if(!api||typeof api.call!=='function')return {ok:false,error:'工作台连接尚未就绪，请重试'};return api.call('workstation_town_call',{action,payload});};
const themeMap=[['--paper','--app-bg'],['--paper-deep','--app-surface-2'],['--card','--app-surface'],['--card-soft','--app-surface-2'],['--ink','--app-text'],['--ink-soft','--app-text-2'],['--muted','--app-muted'],['--line','--app-border'],['--line-strong','--app-border-strong'],['--sage','--app-jade'],['--sage-deep','--app-jade-ink'],['--sage-soft','--app-jade-soft'],['--mint','--app-jade'],['--wood','--app-amber'],['--wood-soft','--app-amber-soft'],['--berry','--app-coral'],['--berry-soft','--app-coral-soft'],['--danger','--app-danger']];
const syncTheme=()=>{try{const root=document.documentElement,host=parent.document.documentElement,style=parent.getComputedStyle(host),scheme=host.dataset.colorScheme==='dark'?'dark':'light';root.dataset.theme=scheme;root.style.colorScheme=scheme;for(const [target,source] of themeMap){const value=style.getPropertyValue(source).trim();if(value)root.style.setProperty(target,value);else root.style.removeProperty(target);}}catch{}};
syncTheme();if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',syncTheme,{once:true});try{new MutationObserver(syncTheme).observe(parent.document.documentElement,{attributes:true,attributeFilter:['data-color-scheme','color-scheme','data-palette']});}catch{}
Object.defineProperty(window,'pywebview',{value:Object.freeze({api:Object.freeze({call})}),writable:false,configurable:false});
})();`;
await writeFile(path.join(townDist,'assets/workstation-bridge.js'),shim,'utf8');
await writeFile(path.join(townDist,'index.html'),townHtml.replace(firstBundle,match=>'<script src="./assets/workstation-bridge.js"></script>\n    '+match),'utf8');
for(const file of ['index.html','assets/app.js','assets/app.css','assets/workstation-bridge.js']){
 const s=await stat(path.join(townDist,file));if(!s.size)throw Error('小镇构建文件为空');
}
console.log('town/index.html and existing assets copied; bridge shim installed');

// Bundle the original tool-center pages directly, sharing its existing React dependencies.
const toolsDist=path.join(dist,'tools');
await mkdir(path.join(toolsDist,'assets'),{recursive:true});
const toolsResult=spawnSync(await resolveEsbuildBinary(center),[path.join(root,'src/original-tools-entry.jsx'),'--bundle',`--outfile=${toolsDist}/assets/app.js`,'--format=iife','--target=edge110','--jsx=automatic','--minify','--legal-comments=none','--define:process.env.NODE_ENV="production"'],{cwd:root,stdio:'inherit',env:{...process.env,NODE_PATH:path.join(center,'node_modules')}});
if(toolsResult.error||toolsResult.status!==0)throw toolsResult.error||Error('原工具页面构建失败');
const toolActions=['bootstrap','game_list','game_favorite','game_save','game_add','game_add_tool','game_open','materials_choose','materials_open','pick_files','pick_output','pack_previous','pack_start','pack_materials','job_status','job_open','wheel_get','wheel_save','wheel_add','wheel_import','wheel_draw','steam_open'];
const toolsShim=`(()=>{'use strict';const allowed=new Set(${JSON.stringify(toolActions)});
const call=async(action,payload={})=>{if(!allowed.has(action))return {ok:false,error:'不支持的工具操作'};try{const api=parent!==window&&parent.location.origin===location.origin?parent.pywebview?.api:null;if(!api||typeof api.call!=='function')return {ok:false,error:'工作台连接尚未就绪，请重试'};return await api.call('workstation_tool_call',{action,payload});}catch{return {ok:false,error:'工作台连接尚未就绪，请重试'};}};
Object.defineProperty(window,'pywebview',{value:Object.freeze({api:Object.freeze({call})}),writable:false,configurable:false});
})();`;
await writeFile(path.join(toolsDist,'assets/workstation-bridge.js'),toolsShim,'utf8');
await writeFile(path.join(toolsDist,'index.html'),`<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'self' data:; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'none'; object-src 'none'; frame-src 'none'; base-uri 'none'"><title>工具页面</title><link rel="stylesheet" href="./assets/app.css"></head><body><div id="root"></div><script src="./assets/workstation-bridge.js"></script><script src="./assets/app.js"></script></body></html>`,'utf8');
for(const file of ['index.html','assets/app.js','assets/app.css','assets/workstation-bridge.js']){
 const s=await stat(path.join(toolsDist,file));if(!s.size)throw Error('原工具构建文件为空');
}
console.log('tools/index.html and original pages bundled; restricted bridge shim installed');
