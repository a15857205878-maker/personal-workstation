// Parse a small display-only Markdown subset. React renders all text escaped.
export function replyBlocks(text=''){
 const blocks=[],lines=text.replace(/\r\n?/g,'\n').split('\n');let paragraph=[];
 const flush=()=>{if(paragraph.length){blocks.push({type:'paragraph',text:paragraph.join('\n')});paragraph=[];}};
 for(let i=0;i<lines.length;i++){
  const line=lines[i];
  if(/^\s*```/.test(line)){flush();const code=[];while(++i<lines.length&&!/^\s*```/.test(lines[i]))code.push(lines[i]);blocks.push({type:'code',text:code.join('\n')});continue;}
  if(!line.trim()){flush();continue;}
  const heading=/^#{1,4}\s+(.+)$/.exec(line);if(heading){flush();blocks.push({type:'heading',text:heading[1]});continue;}
  const item=/^\s*(?:([-*])|\d+[.)])\s+(.+)$/.exec(line);
  if(item){flush();const ordered=!item[1],last=blocks.at(-1);if(last?.type==='list'&&last.ordered===ordered)last.items.push(item[2]);else blocks.push({type:'list',ordered,items:[item[2]]});continue;}
  paragraph.push(line);
 }
 flush();return blocks;
}
export function conversationRows(run){const rows=(run?.messages||[]).filter(m=>m.seat!=='U');return {primary:rows.at(-1)||null,earlier:rows.slice(0,-1)};}
export function groupMessages(run){return (run?.messages||[]).filter(m=>['A','B','C'].includes(m.seat));}
export const isTaskTurn=turn=>turn?.kind==='execute'||!!turn?.jobs?.length;
export const finalTaskStep=run=>run?.status==='completed'?run.steps?.findLast(step=>step.state==='completed'&&step.content?.trim()):undefined;
export const hasTaskDelivery=run=>!!(run?.files?.length||finalTaskStep(run));
export function turnHasDelivery(turn){
 return turn.jobs?.length?turn.jobs.some(job=>hasTaskDelivery(job.run)):hasTaskDelivery(turn.run);
}
export const taskNeedsAttention=turn=>['failed','interrupted'].includes(turn?.state)||!!turn?.error||!!turn?.failures?.length;
export function turnFileCount(turn){
 return turn.jobs?.length
  ? turn.jobs.reduce((count,job)=>count+(job.run?.files?.length||0),0)
  : turn.run?.files?.length||0;
}
export function completionSummary(turn){
 const jobs=turn.jobs?.length?turn.jobs:turn.kind==='execute'?[{state:turn.run?.status||turn.state}]:[],done=jobs.filter(j=>(j.run?.status||j.state)==='completed').length;
 if(['starting','running','stopping'].includes(turn.state))return `进行中 · 已完成 ${done}/${jobs.length} 项`;
 const legacyPrefix=!turn.jobs?.length?({failed:'失败 · ',cancelled:'已取消 · ',interrupted:'已中断 · '}[turn.state]||''):'';
 return legacyPrefix+`已完成 ${done}/${jobs.length} 项`+(done<jobs.length?`，${jobs.length-done} 项未完成`:'');
}

// Display only: never infer a delivery from a model's prose or a completed turn alone.
export function compactDeliveries(turn={}){
 const jobs=turn.jobs||[];
 return turn.state==='completed'&&!turn.error&&!turn.failures?.length&&jobs.length>0&&jobs.every(job=>job.run?.status==='completed'&&!job.run.error&&job.run.files?.length>0&&job.run.files.every(file=>typeof file.name==='string'&&file.name.trim()));
}
