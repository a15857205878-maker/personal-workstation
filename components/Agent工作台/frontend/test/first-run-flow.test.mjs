import assert from 'node:assert/strict';
import test from 'node:test';
import {examplePhase,exampleTurn} from '../src/first-run-flow.mjs';

const sample={
 goal:'整理三个日程',file_name:'计划.docx',title:'周计划',table:{columns:['日期'],rows:[['周一']]},
 jobs:[
  {title:'整理安排',instruction:'按日期整理',owner:'整理搭档',output_format:'text'},
  {title:'生成 Word',instruction:'填写表格',owner:'文档搭档',output_format:'docx'},
 ],
};

test('the example advances only after confirmation and shows completion in order',()=>{
 assert.equal(examplePhase('prepared','step'),'prepared');
 const initial=exampleTurn(sample,'prepared');
 assert.equal(initial.state,'prepared');
 assert.equal(initial.jobs[1].run,undefined);
 const first=examplePhase('prepared','confirm');
 const running=exampleTurn(sample,first);
 assert.equal(running.state,'running');
 assert.deepEqual(running.jobs.map(x=>x.state),['running','queued']);
 const second=examplePhase(first,'step');
 assert.deepEqual(exampleTurn(sample,second).jobs.map(x=>x.state),['completed','running']);
 const done=exampleTurn(sample,examplePhase(second,'step'));
 assert.equal(done.state,'completed');
 assert.equal(done.jobs[1].run.files[0].name,sample.file_name);
 assert.equal(done.call_count,0);
});

test('cancelled progress cannot deliver a file and a replay returns to confirmation',()=>{
 const cancelled=examplePhase('writing','cancel');
 assert.equal(examplePhase(cancelled,'step'),'cancelled');
 assert.equal(exampleTurn(sample,cancelled).jobs[1].run,undefined);
 assert.equal(examplePhase(cancelled,'restart'),'prepared');
});
