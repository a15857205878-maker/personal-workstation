export function roomTaskState(value,now=Date.now()){
 const at=Number(value?.observed_at)*1000,c=value?.counts;
 if(value?.overview_state!=='ready'||!Number.isFinite(at)||now-at<0||now-at>15000||!Number.isInteger(c?.active)||!Number.isInteger(c?.attention))return {kind:'unknown',label:'状态未知',hint:'工作概况暂不可用，请刷新查看。'};
 if(c.attention>0)return {kind:'attention',label:'需要处理',hint:`有 ${c.attention} 项工作需要关注。`};
 if(c.active>0)return {kind:'working',label:'正在工作',hint:`有 ${c.active} 项任务或协作正在进行。`};
 if(value.notices?.some(n=>n.kind==='done'&&Number.isFinite(n.at)&&now-n.at*1000>=0&&now-n.at*1000<60000))return {kind:'done',label:'最近有工作完成',hint:'结果以原任务与协作记录为准。'};
 return {kind:'idle',label:'当前无进行中任务',hint:'角色活动与电脑任务状态分开显示。'};
}
