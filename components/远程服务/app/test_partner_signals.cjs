const test=require('node:test'),assert=require('node:assert/strict');
const {collaborationSignals,setHistoryCollapsed}=require('./partner-theme.js');
test('stage lamps follow actual current-round receipts and never invent completion',()=>{
 assert.deepEqual(collaborationSignals({status:'completed'}).map(s=>s.state),['waiting','waiting','waiting']);
 const task={status:'running',steps:[{stage:'提案',state:'completed',round:1},{stage:'审查',state:'running',round:1}]};
 assert.deepEqual(collaborationSignals(task).map(s=>s.state),['done','running','waiting']);
 task.status='failed';task.steps[1].state='failed';assert.equal(collaborationSignals(task)[1].state,'error');
 task.status='running';task.steps.push({stage:'提案',state:'running',round:2});
 assert.deepEqual(collaborationSignals(task).map(s=>s.state),['running','waiting','waiting']);
});
test('history folds and restores without replacing conversation DOM or draft',()=>{
 const nodes=Object.fromEntries(['partnerHistoryToggle','partnerHistoryRestore'].map(id=>[id,{attrs:{},setAttribute(k,v){this.attrs[k]=v},focus(){this.focused=true}}]));
 const d={documentElement:{dataset:{}},getElementById:id=>nodes[id]};
 setHistoryCollapsed(d,true);assert.equal(d.documentElement.dataset.historyCollapsed,'true');assert.equal(nodes.partnerHistoryToggle.attrs['aria-expanded'],'false');assert.ok(nodes.partnerHistoryRestore.focused);
 setHistoryCollapsed(d,false);assert.equal(nodes.partnerHistoryToggle.attrs['aria-expanded'],'true');assert.ok(nodes.partnerHistoryToggle.focused);
});
