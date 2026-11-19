export function filterConversations(rows,query='',mode='active'){
 const q=query.trim().toLocaleLowerCase();
 return rows.filter(s=>(mode==='all'||(mode==='archived'?!!s.archived:!s.archived))&&s.title.toLocaleLowerCase().includes(q));
}
export function conversationBlock(session,target,rounds,manual=false,jobCount=1){
 if(session?.archived)return '这条会话已归档。可在会话管理中恢复，记录和成果都保留。';
 const needed=manual?jobCount:target.length*Number(rounds);
 if(session&&needed>session.call_limit-session.call_count)return '本轮所需调用次数不足，请减少回应成员或轮数，或新建会话。';
 return '';
}
