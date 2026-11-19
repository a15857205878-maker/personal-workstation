export const memberNames=roles=>Object.values(roles||{}).map(p=>p.name).join(' · ');
export function responseOptions(roles){
 const seats=Object.keys(roles||{}),all=seats.join(''),names=order=>[...order].map(s=>roles[s].name).join(' → ');
 const opts=[[all,'大家 · '+names(all)],[seats.toReversed().join(''),'逆序 · '+names(seats.toReversed().join(''))],...seats.map(s=>[s,'只请 '+roles[s].name])];
 if(seats.length===3)for(let i=0;i<seats.length;i++)for(let j=i+1;j<seats.length;j++){const pair=seats[i]+seats[j];opts.push([pair,'两位 · '+names(pair)]);}
 return opts;
}
