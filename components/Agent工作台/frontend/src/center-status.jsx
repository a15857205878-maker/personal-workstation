import React from 'react';
export const centerState={running:'正在进行',attention:'需要处理',completed:'已完成',cancelled:'已停止',idle:'尚未开始',prepared:'待确认',interrupted:'需核对'};
export function CenterMetrics({counts,unknown=false}){
 return <div className="ws-stats" aria-label="当前搭档概况">{[['conversations','搭档会话'],['active','正在进行'],['attention','需要处理'],['deliveries','已登记成果']].map(([key,label])=><div className="ws-card" key={key}><strong>{unknown?'—':counts?.[key]??'—'}</strong><span>{label}</span></div>)}</div>;
}
export function RecentCenter({rows=[],onConversation}){
 const current=rows.filter(r=>!r.archived).slice(0,8);
 return <div className="ws-current-conversations">{!current.length&&<p className="ws-empty">还没有搭档会话，可以从搭档开始。</p>}{current.map(r=><div className="ws-task-row" key={r.id}><div><strong>{r.title}</strong><small>{centerState[r.status]||'需核对'} · {r.file_count} 个登记成果</small></div><button disabled={r.can_open===false} onClick={()=>onConversation?.(r)}>回到会话</button></div>)}</div>;
}
