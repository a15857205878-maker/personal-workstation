import React from 'react';
import {ListChecks,MessageCircle,NotebookPen} from 'lucide-react';
import ChatAvatar from './chat-avatar.jsx';

const starters = [
 {label:'理清一个想法',icon:MessageCircle,text:'我有一个还没理清的想法。请先问我三个问题，帮我把目标和约束想清楚。'},
 {label:'排好手头的待办',icon:ListChecks,text:'帮我把手头的待办按轻重缓急排一排。先问我有哪些事项、截止时间和今天能用的时间。'},
 {label:'起草一份提纲',icon:NotebookPen,text:'我想写一份简短的工作计划。先和我讨论目标、步骤和检查点，再给一个文字提纲。'},
];

export function ConversationStart({ready,error,loading,hasProfiles,members,onCreate,onModels,onTryExample,onRetry,onBack,children}){
 const canCreate=hasProfiles&&members.every(member=>member.profile);
 const sameModel=canCreate&&members.length>1&&members.every(member=>member.profile.id===members[0].profile.id);
 return <div className="center-create">
  <div className="center-start">
   <MessageCircle className="center-start-icon" size={24} aria-hidden="true"/>
   <h2>开始一段新对话</h2>
   {!ready?<p role="status">{error?'本地会话暂时没有读到。':'正在连接本地会话…'}</p>:
    hasProfiles?<p>用这组搭档先聊起来。{sameModel?'当前成员使用同一个模型配置。':''}</p>:
    <p>先试一条内置任务，熟悉分工、进度和成果。开始自己的对话前再连接模型。</p>}
   {hasProfiles&&<ul className="center-start-members" aria-label="本次群聊成员">
    {members.map(({seat,profile})=><li key={seat}>
     <ChatAvatar member={seat} name={profile?.name||('搭档 '+seat)}/>
     <span><strong>{profile?.name||'待选择'}</strong>{profile?.model&&profile.model!==profile.name&&<small>{profile.model}</small>}</span>
    </li>)}
   </ul>}
   <div className="center-start-actions">
    {!ready&&error&&<button className="auto-button auto-primary" disabled={loading} onClick={onRetry}>重试连接</button>}
    {ready&&hasProfiles&&<button className="auto-button auto-primary" disabled={loading||!canCreate} onClick={onCreate}>开始群聊</button>}
    {onTryExample&&<button type="button" className={'auto-button'+(ready&&!hasProfiles?' auto-primary':'')} aria-haspopup="dialog" onClick={onTryExample}>体验示例任务</button>}
    {ready&&!hasProfiles&&<button className="auto-button" disabled={loading} onClick={onModels}>连接模型</button>}
    {onBack&&<button className="auto-button" onClick={onBack}>返回对话</button>}
   </div>
   {hasProfiles&&<details className="center-start-options"><summary>自选成员与风格</summary>{children}</details>}
  </div>
 </div>;
}

export function ConversationStarters({disabled,onChoose}){
 return <div className="center-starters">
  <h1>想和搭档聊什么？</h1>
  <p>写下想法，或选一条示例填入输入框。</p>
  <div className="center-starter-grid" role="group" aria-label="首条消息示例">
   {starters.map(({label,icon:Icon,text})=><button key={label} type="button" className="auto-button" disabled={disabled}
    onClick={()=>onChoose(text)}><Icon size={17} aria-hidden="true"/>{label}</button>)}
  </div>
 </div>;
}
