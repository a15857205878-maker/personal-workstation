const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{createRequire}=require('node:module');
const {chromium}=require('playwright');
test('readonly mobile observer renders exact scenes, preserves history, pauses hidden views and rejects late receipts at 320px',async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const page=await browser.newPage({viewport:{width:320,height:800}});await page.setContent('<html><head><meta charset="utf-8"></head><body data-mobile-view="connection"><main id="host"></main></body></html>');
 await page.addStyleTag({content:fs.readFileSync(path.join(__dirname,'mobile-room.css'),'utf8')});
 await page.addScriptTag({content:fs.readFileSync(path.join(__dirname,'mobile-room.js'),'utf8').replace('__PET_ACTIVITY_ASSETS__','{}')});
 const result=await page.evaluate(async()=>{
  const wait=()=>new Promise(r=>setTimeout(r,30)),now=()=>Date.now()/1000;let value,delayed=null,calls=[];
  const pet=(scene='home',pose='front')=>({available:true,scene,pose,night:false,automatic:true,held:false,phase:'stable',observed_at:now(),changed_at:now()});
  const data=p=>({version:1,overview_state:'ready',observed_at:now(),counts:{tasks:2,collaborations:0,active:0,attention:0},pet_activity:p});
  value=data(pet());const fetcher=async(url,options)=>{calls.push([url,options.method||'GET']);if(delayed)return new Promise(r=>delayed=r);return {ok:true,json:async()=>({ok:true,data:value})}};
  const assets=Object.fromEntries(['home.front','plaza.sit','room.rest'].map(k=>[k,'data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="478"/>')+'#'+k]));
  const view=WorkstationMobileRoom.mount(document.getElementById('host'),{token:'fixture',fetcher,activityAssets:assets,preview:'data:preview'});view.element.open=true;await wait();
  const activity=()=>view.element.querySelector('.mobile-room-activity').textContent,image=()=>view.element.querySelector('img').getAttribute('src'),caption=()=>view.element.querySelector('.mobile-room-caption').textContent;
  const first=activity();value=data(pet('plaza','sit'));await view.refresh();await wait();const second=[activity(),image()];
  value=data(pet('room','rest'));value.pet_activity.phase='paused';await view.refresh();await wait();const paused=activity(),lastImage=image();
  value=data({...pet(),available:false,observed_at:0});await view.refresh();const unknown=[activity(),caption()];if(image()!==lastImage)throw Error('unknown status must keep last observed image');
  value=data({...pet(),observed_at:now()-20});await view.refresh();const stale=activity();
  delayed=true;const pending=view.refresh();await wait();document.body.dataset.mobileView='tasks';await wait();delayed({ok:true,json:async()=>({ok:true,data:data(pet('orchard','back'))})});await pending;const late=activity();
  const before=calls.length;await view.refresh();const hiddenRequests=calls.length-before;const overflow=document.documentElement.scrollWidth>320;view.dispose();return {first,second,paused,unknown,stale,late,calls,hiddenRequests,overflow,buttons:[...view.element.querySelectorAll('button')].map(b=>b.textContent)};
 });
 assert.match(result.first,/庭院.*面朝/);assert.match(result.second[0],/广场.*长椅.*歇/);assert.match(result.second[1],/#plaza.sit$/);assert.match(result.paused,/小屋.*休息/);assert.match(result.unknown[0],/未知.*上次：.*小屋/);assert.match(result.unknown[1],/未确认/);assert.match(result.stale,/未知/);assert.equal(result.late,result.stale);assert.equal(result.hiddenRequests,0);assert.equal(result.overflow,false);assert.deepEqual(result.buttons,['刷新概况','查看任务与成果']);assert.ok(result.calls.every(([url,method])=>url.startsWith('/api/workbench?action=room_status&token=')&&method==='GET'));
 }finally{await browser.close()}
});
