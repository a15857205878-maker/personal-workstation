const exact=(o,keys)=>!!o&&typeof o==='object'&&!Array.isArray(o)&&Object.keys(o).sort().join(',')===[...keys].sort().join(',');
const id=x=>typeof x==='string'&&x.length>0&&x.length<=80&&!/[\x00-\x1f/\\]/.test(x);
export function isTownToolAction(action,args){
 if(action==='redeem')return exact(args,['kind'])&&['sprout_bear','moon_bunny','dragon_plush','sunshine_medal','companion_medal','cottage_globe'].includes(args.kind);
 if(['water','harvest','view_collection'].includes(action))return exact(args,[]);
 if(action==='unlock')return exact(args,['area'])&&args.area==='orchard';
 if(action==='buy')return exact(args,['kind'])&&['plant','rug','bookshelf','bench','flowerbed','lamp'].includes(args.kind);
 if(action==='recall')return exact(args,['item_id'])&&id(args.item_id);
 if(['place','move'].includes(action))return exact(args,['item_id','area','x','y'])&&id(args.item_id)&&['home','plaza','orchard'].includes(args.area)&&Number.isInteger(args.x)&&args.x>=0&&args.x<16&&Number.isInteger(args.y)&&args.y>=0&&args.y<10;
 if(action==='claim')return exact(args,['task'])&&['greet','water','arrange'].includes(args.task);
 if(action==='greet')return exact(args,['partner'])&&typeof args.partner==='string'&&args.partner.length>0&&args.partner.length<=80&&!/[\x00-\x1f/\\]/.test(args.partner);
 return false;
}
