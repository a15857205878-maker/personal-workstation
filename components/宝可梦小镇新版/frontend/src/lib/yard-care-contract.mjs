import {isTownToolAction} from './town-tools-contract.mjs';
export function isYardCareRequest(d){
 if(!d||typeof d!=='object'||Array.isArray(d)||Object.keys(d).sort().join(',')!=='action,id,payload,t'||d.t!=='room-town-call'||typeof d.id!=='string'||!/^care_[a-z0-9_]{1,50}$/i.test(d.id))return false;
 const p=d.payload;if(!p||typeof p!=='object'||Array.isArray(p))return false;
 if(d.action==='bootstrap')return Object.keys(p).length===0;
 return d.action==='town_action'&&exactToolPayload(p);
}
function exactToolPayload(p){return Object.keys(p).sort().join(',')==='action,args'&&isTownToolAction(p.action,p.args)}
