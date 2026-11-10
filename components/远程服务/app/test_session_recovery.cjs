const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function create(storage,key='pair-a'){
 const source=fs.readFileSync(__dirname+'/conversation.js','utf8');
 const start=source.indexOf('  function createSessionRecovery('),end=source.indexOf('  // end session recovery',start);
 if(start<0||end<0)throw Error('Missing recovery helper');
 const context={Map,JSON,Error};vm.runInNewContext(source.slice(start,end)+';this.factory=createSessionRecovery;',context);return context.factory(storage,key,()=> 'test-request');
}
function memory(){const rows=new Map();return {getItem:key=>rows.get(key)||null,setItem:(key,text)=>rows.set(key,text),rows};}
test('Draft text survives refresh and stays isolated by pairing and conversation',()=>{
 const storage=memory(),a=create(storage);a.remember('deepseek:a','尚未发送的完整中文');
 const b=create(storage);assert.equal(b.draft('deepseek:a'),'尚未发送的完整中文');assert.equal(b.draft('thread:other'),'');assert.equal(create(storage,'pair-b').draft('deepseek:a'),'');
});
test('A lost reply receipt uses the original ID after reload and a confirmed reply clears only its matching draft',()=>{
 const storage=memory(),a=create(storage);const id=a.prepare('deepseek:a','继续讨论');
 const b=create(storage);assert.equal(b.prepare('deepseek:a','继续讨论'),id);
 b.remember('deepseek:a','我又补写了内容');b.confirm('deepseek:a','继续讨论',id);assert.equal(create(storage).draft('deepseek:a'),'我又补写了内容');
 const c=create(storage);const next=c.prepare('deepseek:a','下一条');c.confirm('deepseek:a','下一条',next);assert.equal(create(storage).draft('deepseek:a'),'');
});
test('Unavailable storage blocks sending before any receipt can be lost',()=>{
 const storage={getItem(){return null;},setItem(){throw Error('quota');}};const a=create(storage);
 assert.equal(a.remember('deepseek:a','保留文字'),false);assert.throws(()=>a.prepare('deepseek:a','继续'),/存储|保存/);
});
test('Malformed stored state and exhausted pending capacity never silently create a fresh receipt',()=>{
 const storage=memory();storage.setItem('pair-a','{bad');assert.throws(()=>create(storage).prepare('deepseek:a','继续'),/存储|保存/);
 const good=create(memory());for(let i=0;i<40;i++)good.prepare('deepseek:'+i,'测试'+i);assert.throws(()=>good.prepare('deepseek:extra','额外'),/回执|核对/);
});

test('Long quoted and multiline input keeps the same receipt after reload without truncation',()=>{
 const storage=memory(),text='"\n'.repeat(10000),a=create(storage);const id=a.prepare('deepseek:a',text);const b=create(storage);assert.equal(b.draft('deepseek:a'),text);assert.equal(b.prepare('deepseek:a',text),id);
});
