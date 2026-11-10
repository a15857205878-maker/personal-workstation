import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const path=new URL('../../../远程服务/app/desktop-embed.js',import.meta.url);
test('embedded theme accepts only its loopback parent and fixed scheme, without changing standalone pages',()=>{
 const listeners={},values={},dataset={},parent={postMessage(){}};
 const context={parent,window:{},location:{search:'?desktop_embed=1',href:'http://127.0.0.1:8765/bot'},URL,URLSearchParams,
 document:{documentElement:{dataset,style:{setProperty:(k,v)=>values[k]=v}},head:{appendChild(){}},createElement:()=>({}),addEventListener(){}}};
 context.window.addEventListener=(type,fn)=>listeners[type]=fn;
 vm.runInNewContext(readFileSync(path,'utf8'),context);
 assert.equal(typeof listeners.message,'function');
 const send=(origin,source,data)=>listeners.message({origin,source,data});
 send('https://example.com',parent,{type:'workstation-visual-theme',scheme:'dark'});assert.equal(dataset.workstationScheme,undefined);
 send('http://127.0.0.1:5555',{}, {type:'workstation-visual-theme',scheme:'dark'});assert.equal(dataset.workstationScheme,undefined);
 send('http://127.0.0.1:5555',parent,{type:'workstation-visual-theme',scheme:'dark'});assert.equal(dataset.workstationScheme,'dark');assert.equal(values['--bg'],'#151c27');
 send('http://127.0.0.1:5555',parent,{type:'workstation-visual-theme',scheme:'bad'});assert.equal(dataset.workstationScheme,'dark');
 send('http://127.0.0.1:5555',parent,{type:'workstation-visual-theme',scheme:'light'});assert.equal(dataset.workstationScheme,'light');
 send('https://example.com',parent,{type:'workstation-visual-theme',scheme:'light',scenery:{offset:212,bottom:0}});assert.equal(dataset.workstationScenery,undefined);
 send('http://127.0.0.1:5555',parent,{type:'workstation-visual-theme',scheme:'light',scenery:{offset:'url(x)',bottom:0}});assert.equal(dataset.workstationScenery,undefined);
 send('http://127.0.0.1:5555',parent,{type:'workstation-visual-theme',scheme:'light',scenery:{offset:212,bottom:0}});assert.equal(dataset.workstationScenery,'joined');assert.equal(values['--joined-offset'],'212px');assert.equal(values['--joined-bottom'],'0px');
 send('http://127.0.0.1:5555',parent,{type:'workstation-visual-theme',scheme:'dark',scenery:{offset:184,bottom:7.5}});assert.equal(values['--joined-offset'],'184px');assert.equal(values['--joined-bottom'],'7.5px');
 send('http://127.0.0.1:5555',parent,{type:'workstation-visual-theme',scheme:'light',scenery:{offset:Infinity,bottom:0}});assert.equal(values['--joined-offset'],'184px');
 const standalone={...context};standalone.parent=standalone.window;delete listeners.message;
 vm.runInNewContext(readFileSync(path,'utf8'),standalone);assert.equal(listeners.message,undefined);
});
