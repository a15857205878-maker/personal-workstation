export const STATUS={draft:'草稿',queued:'排队中',running:'执行中',waiting_handoff:'等待交接',needs_user:'需要用户处理',awaiting_confirmation:'结果待确认',completed:'已完成',failed:'失败',cancelled:'已取消',needs_check:'需要检查'};
const WIRE=Object.fromEntries(Object.entries(STATUS).map(([key,value])=>[value,key]));
export function normalizeStationData(value){
  if(Array.isArray(value))return value.map(normalizeStationData);
  if(value&&typeof value==='object'&&typeof value.id==='string'&&typeof value.status==='string')return {...value,status:WIRE[value.status]||value.status};
  return value;
}
export const active=task=>['queued','running'].includes(task?.status);
export const canStart=(task,ready,archived)=>Boolean(task&&task.execution_mode!=='external'&&ready&&!archived&&!active(task)&&task.status!=='completed'&&!task.workflow?.started);
export const canComplete=(task,archived)=>Boolean(task&&!archived&&!active(task)&&task.status!=='completed'&&(task.result?.trim()||task.files?.length));
export const canHandoff=(task,archived)=>Boolean(task&&task.execution_mode!=='api'&&(task.execution_mode!=='external'||task.status==='draft')&&!archived&&!active(task));
export const canReviewRole=role=>Boolean(role?.can_run&&(role.can_review??['codex_text','api'].includes(role.mode)));

// Only new type selection uses this; saved tasks and explicit role choices stay intact.
export function initialTaskRole(task,roles={}){
 const agents=task?.agents||[],fallback=task?.default_role_ref||agents[0]?.role_ref||'';
 if(task?.id!=='xlsx'||roles[fallback]?.can_run===true)return fallback;
 return agents.find(agent=>roles[agent.role_ref]?.can_run===true)?.role_ref||fallback;
}
