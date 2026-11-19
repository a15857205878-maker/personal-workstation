import React from 'react';

// Original inline SVG portraits; no remote images or character assets.
export default function ChatAvatar({member='task',name='',avatar=''}){
 if(avatar.startsWith('data:image/webp;base64,')&&avatar.length<=24000)return <span className="center-chat-avatar avatar-custom"><img src={avatar} alt={`${name||'发言人'}的头像`} draggable="false"/></span>;
 const variant=member==='A'?'a':member==='B'?'b':member==='C'?'c':member==='user'?'user':'task';
 const hair=variant==='c'?'#a98156':variant==='b'?'#8179ad':variant==='user'?'#776a67':variant==='a'?'#527ba3':'#738594';
 return <span className={'center-chat-avatar avatar-'+variant}>
  <svg viewBox="0 0 48 48" role="img" aria-label={`${name||'发言人'}的头像`} focusable="false">
   <rect x="1" y="1" width="46" height="46" rx="15" className="chat-avatar-back"/>
   <path d="M9 47c0-10 5-16 15-16s15 6 15 16" fill={variant==='c'?'#d1b38b':variant==='b'?'#b0a6d1':variant==='user'?'#9caab9':'#92b4d7'}/>
   <path d="M20 30h8v7c-2 2-6 2-8 0z" fill="#ead4c4"/>
   <ellipse cx="24" cy="22" rx="11" ry="13" fill="#f6e3d3"/>
   {variant==='b'?<path d="M12 25V16C12 4 36 3 36 17v10l-5-7-3-8-6 7-8 1z" fill={hair}/>:variant==='user'?<path d="M12 21v-6C12 5 34 5 36 16l-2 9-4-10-8 3-7-1-1 7z" fill={hair}/>:<path d="M12 25V15C14 5 34 4 36 16l-2 8-4-8c-4 3-8 4-13 3l-3 7z" fill={hair}/>}
   <circle cx="20" cy="23" r="1.25" fill="#374b60"/><circle cx="28" cy="23" r="1.25" fill="#374b60"/>
   <path d="M21 28q3 2.5 6 0" fill="none" stroke="#bc8e83" strokeWidth="1.5" strokeLinecap="round"/>
   {variant==='b'&&<g fill="none" stroke="#60668c" strokeWidth="1.2"><rect x="16.5" y="20.5" width="7" height="5" rx="2"/><rect x="24.5" y="20.5" width="7" height="5" rx="2"/><path d="M23.5 22h1"/></g>}
   <path d="m17 37 7 4 7-4" fill="none" stroke="#fff" strokeOpacity=".65" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
 </span>;
}
