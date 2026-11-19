const test=require('node:test'),assert=require('node:assert/strict');
const {normalize,view}=require('./mobile-messenger.js');
test('mobile visual projection accepts only fixed appearance fields',()=>{
 assert.deepEqual(normalize({color_scheme:'dark',chat_background:'coast',background_strength:45,path:'secret'}),{color_scheme:'dark',chat_background:'coast',background_strength:45});
 assert.deepEqual(normalize({color_scheme:'evil',chat_background:'https://invalid',background_strength:NaN}),{color_scheme:'light',chat_background:'auto',background_strength:35});
 assert.equal(normalize({background_strength:0}).background_strength,0);
 assert.equal(normalize({background_strength:61}).background_strength,35);
});
test('temporary phone theme retains fixed background and follow restores desktop scheme',()=>{
 const pc={color_scheme:'dark',chat_background:'coast',background_strength:50};
 assert.deepEqual(view(pc,'light'),{scheme:'light',scene:'coast',strength:50});
 assert.deepEqual(view({...pc,chat_background:'auto'},'light'),{scheme:'light',scene:'coast',strength:50});
 assert.deepEqual(view(pc,null),{scheme:'dark',scene:'coast',strength:50});
});
const fs=require('node:fs'),vm=require('node:vm');
test('cached page return restarts exactly one visual poller',()=>{
 const timers=new Set(),events={},docEvents={};let count=0;
 const element=()=>({append(){},prepend(){},after(){},setAttribute(){},style:{setProperty(){}},dataset:{}}),section=element();
 const doc={readyState:'complete',hidden:false,documentElement:element(),getElementById(id){return id==='partner-app'?section:null;},querySelector(){return null;},querySelectorAll(){return [];},createElement:element,addEventListener(k,v){docEvents[k]=v;},removeEventListener(k){delete docEvents[k];}};
 const browser={document:doc,location:{search:'?token=fixture',origin:'https://fixture.invalid'},innerHeight:800,fetch:async()=>({ok:true,json:async()=>({ok:true,data:{appearance:{}}})}),addEventListener(k,v){events[k]=v;}};
 const context={window:browser,URLSearchParams,AbortController,setInterval(){const id=++count;timers.add(id);return id;},clearInterval(id){timers.delete(id);},setTimeout(){return 1;},clearTimeout(){}};
 vm.runInNewContext(fs.readFileSync(__dirname+'/mobile-messenger.js','utf8'),context);
 assert.equal(timers.size,1);events.pagehide();assert.equal(timers.size,0);assert.equal(typeof events.pageshow,'function');events.pageshow();assert.equal(timers.size,1);events.pageshow();assert.equal(timers.size,1);
});
