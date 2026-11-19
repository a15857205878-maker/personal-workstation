const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
test('single model choice follows submission state and becomes available again',()=>{
 const code=fs.readFileSync(__dirname+'/conversation.js','utf8');
 const body=code.slice(code.indexOf('  function updateInteraction()'),code.indexOf('  function syncPartitionUI()'));
 const nodes=new Map(),state={phase:'creating'},view={busy:false};
 const context={state,activeView:()=>view,$:id=>{if(!nodes.has(id))nodes.set(id,{disabled:false});return nodes.get(id);},document:{querySelectorAll:()=>[]}};
 vm.createContext(context);vm.runInContext(body,context);
 context.updateInteraction();assert.equal(nodes.get('singleModelChoice')?.disabled,true);
 state.phase='idle';context.updateInteraction();assert.equal(nodes.get('singleModelChoice').disabled,false);
 assert.equal(nodes.get('newConversation').disabled,false);
});
