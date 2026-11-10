export function moveEntry(rows,id,delta){
 const index=rows.findIndex(e=>e.id===id),target=index+delta;
 if(index<0||target<0||target>=rows.length)return rows;
 const next=[...rows];[next[index],next[target]]=[next[target],next[index]];return next;
}
export function exportable(rows,selected){
 const ids=new Set(selected);return rows.filter(e=>ids.has(e.id)&&e.public&&!['missing','changed'].includes(e.file_status));
}
export function mergeSnapshot(local,snapshot,dirty){
 if(dirty)return local;
 return snapshot.projects.find(p=>p.id===local?.id)||null;
}
