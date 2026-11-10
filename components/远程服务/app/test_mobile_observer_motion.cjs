const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{createRequire}=require('node:module');
const {chromium}=require('playwright');
test('image loading never lets an older pose replace the latest one; repeated reports do not replay fades',async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});try{
  const page=await browser.newPage({viewport:{width:320,height:700}});await page.emulateMedia({reducedMotion:'reduce'});await page.setContent('<meta charset="utf-8"><body data-mobile-view="connection"><main id="host"></main>');await page.addStyleTag({content:fs.readFileSync(path.join(__dirname,'mobile-room.css'),'utf8')});await page.addScriptTag({content:fs.readFileSync(path.join(__dirname,'mobile-room.js'),'utf8').replace('__PET_ACTIVITY_ASSETS__','{}')});
  const result=await page.evaluate(async()=>{
   const wait=()=>new Promise(r=>setTimeout(r,30));window.loading=[];window.Image=class{set src(value){this.value=value;loading.push(this)}};
   let scene='home';const asset=k=>'data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="820" height="590"/>')+'#'+k;
   const fetcher=async()=>({ok:true,json:async()=>({ok:true,data:{version:1,overview_state:'ready',observed_at:Date.now()/1000,counts:{tasks:0,collaborations:0,active:0,attention:0},pet_activity:{available:true,scene,pose:'front',night:false,automatic:true,held:false,phase:'stable',observed_at:Date.now()/1000,changed_at:Date.now()/1000}}})});
   const view=WorkstationMobileRoom.mount(document.getElementById('host'),{fetcher,preview:asset('preview'),activityAssets:{'home.front':asset('home'),'plaza.front':asset('plaza')}});view.element.open=true;await wait();scene='plaza';await view.refresh();const image=view.element.querySelector('img');loading[0].onload();const afterOld=image.src;loading[1].onload();const afterNew=image.src;const opacity=image.style.opacity,duration=getComputedStyle(image).transitionDuration;await view.refresh();const sameLoadCount=loading.length;scene='home';await view.refresh();view.dispose();loading.at(-1).onload();return {afterOld,afterNew,afterDisposed:image.src,opacity,duration,sameLoadCount};
  });
  assert.match(result.afterOld,/#preview$/);assert.match(result.afterNew,/#plaza$/);assert.equal(result.afterDisposed,result.afterNew);assert.equal(result.sameLoadCount,2);assert.equal(result.opacity,'1');assert.equal(result.duration,'0s');
 }finally{await browser.close()}
});
