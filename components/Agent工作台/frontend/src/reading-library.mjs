export function filterBooks(items,query='',state='all'){
 const q=query.trim().toLocaleLowerCase();
 return items.filter(x=>x.kind==='book'&&(state==='archived'?x.archived:!x.archived&&(state==='all'||state==='noted'?state!=='noted'||!!x.notes.trim():x.state===state))&&[x.title,x.notes].join('\n').toLocaleLowerCase().includes(q));
}
export function adjacentTrack(rows,currentId,direction){
 if(!rows.length)return null;const index=rows.findIndex(r=>r.id===currentId);
 return rows[index<0?0:(index+direction+rows.length)%rows.length];
}
export function downloadNotes(value){
 if(typeof value?.text!=='string'||typeof value?.filename!=='string'||!value.filename.endsWith('.md'))throw Error('笔记导出内容无效。');
 const url=URL.createObjectURL(new Blob([value.text],{type:'text/markdown;charset=utf-8'}));
 const anchor=document.createElement('a');anchor.href=url;anchor.download=value.filename;anchor.click();
 setTimeout(()=>URL.revokeObjectURL(url),60000);
}
