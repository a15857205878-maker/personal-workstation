const stepStates={
 prepared:['prepared','prepared'],
 organizing:['running','queued'],
 writing:['completed','running'],
 completed:['completed','completed'],
 cancelled:['cancelled','cancelled'],
};
const active=new Set(['organizing','writing']);

export function examplePhase(phase,action){
 if(action==='restart')return 'prepared';
 if(action==='confirm'&&phase==='prepared')return 'organizing';
 if(action==='cancel'&&(phase==='prepared'||active.has(phase)))return 'cancelled';
 if(action==='step'&&phase==='organizing')return 'writing';
 if(action==='step'&&phase==='writing')return 'completed';
 return phase;
}

export function exampleTurn(sample,phase){
 const jobs=sample.jobs.map((job,index)=>{
  const owner={id:'sample-'+index,name:job.owner,model:''};
  const result={...job,state:stepStates[phase][index],roles:{A:owner}};
  if(phase==='completed'&&job.output_format==='docx'){
   const preview={type:'docx',text:sample.title,table:sample.table};
   result.run={id:'sample-document',status:'completed',
    files:[{name:sample.file_name,format:'docx'}],artifact_preview:preview};
  }
  return result;
 });
 return {id:'sample-turn',kind:'execute',state:active.has(phase)?'running':phase,
  text:sample.goal,jobs,call_count:0};
}
