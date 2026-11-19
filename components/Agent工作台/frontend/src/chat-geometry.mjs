export function historyWidth(value,available=1000){
 const n=Number.isFinite(value)?value:248,space=Number.isFinite(available)&&available>0?available:1000;
 return Math.round(Math.max(180,Math.min(Math.min(360,Math.max(180,space-340)),n)));
}
export function inputHeight(value,available=800){
 const n=Number.isFinite(value)?value:72,space=Number.isFinite(available)&&available>0?available:800;
 return Math.round(Math.max(48,Math.min(Math.min(300,Math.max(48,Math.floor(space*.36))),n)));
}
