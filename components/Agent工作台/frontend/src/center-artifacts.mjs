export const validCenterLink=f=>typeof f?.conversation_id==='string'&&/^[a-f0-9]{32}$/.test(f.conversation_id)&&(!f.turn_id||typeof f.turn_id==='string'&&/^[a-f0-9]{32}$/.test(f.turn_id));
export function artifactGroups(items=[],query='',source='all'){
 const q=query.trim().toLocaleLowerCase(),groups=new Map();
 for(const f of items){
  if(source==='history'?!['station','collaboration'].includes(f.source_kind):source!=='all'&&f.source_kind!==source)continue;
  if(![f.name,f.title,f.source_label,f.conversation_title,f.job_title,f.owner_name,f.owner_model].join(' ').toLocaleLowerCase().includes(q))continue;
  const key=f.source_kind==='center'?f.conversation_id:'other:'+f.source_kind;
  if(!groups.has(key))groups.set(key,{id:key,title:f.source_kind==='center'?f.conversation_title:f.source_label||'其他成果',link:validCenterLink(f)?f:null,archived:f.conversation_archived,items:[]});
  groups.get(key).items.push(f);
 }
 return [...groups.values()];
}
