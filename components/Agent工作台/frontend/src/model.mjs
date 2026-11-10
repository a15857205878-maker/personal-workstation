export function filterMessages(messages,seat,query='') {
 const search=query.trim().toLocaleLowerCase();
 return messages.filter(m=>(seat==='all'||m.seat===seat)&&(!search||[m.body,m.model,m.role,m.seat,m.id].join(' ').toLocaleLowerCase().includes(search)));
}
export function groupRounds(messages) {
 const groups=[];
 for(const m of messages){if(groups.at(-1)?.round!==m.round)groups.push({round:m.round,messages:[]});groups.at(-1).messages.push(m);}
 return groups;
}
