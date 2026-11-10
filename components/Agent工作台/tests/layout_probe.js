(async()=>{
 const wait=async fn=>{for(let i=0;i<100;i++){if(fn())return;await new Promise(r=>setTimeout(r,80));}throw Error('布局页面未就绪');};
 const select=async label=>{const button=[...document.querySelectorAll('.app-navigation button')].find(b=>b.textContent.trim()===label);if(!button)throw Error('缺少导航 '+label);button.click();await new Promise(r=>setTimeout(r,350));};
 const checks={};
 for(const [label,selector] of [['工作概览','.ws-dashboard-grid'],['独立任务','.station-shell'],['双模型协作','.auto-shell'],['游戏资料库','iframe[title="个人工具中心原生页面"]'],['远程','.remote-workspace'],['聊天实验室','.group-chat'],['个人管家','.companion-page'],['图标换装台','.icon-studio-page'],['设置与维护','.ws-setup-grid']]){
  await select(label);await wait(()=>document.querySelector(selector));
  const pane=[...document.querySelectorAll('.app-content>.mode-pane')].find(p=>!p.hidden);
  checks[label]={root_overflow:document.documentElement.scrollWidth>innerWidth,pane_overflow:pane.scrollWidth>pane.clientWidth+1,content_width:document.querySelector('.app-content').clientWidth};
  if(label==='聊天实验室'){
   const composer=document.querySelector('.chat-composer');
   checks[label].composer_visible=!!composer&&composer.getBoundingClientRect().bottom<=document.querySelector('.app-content').getBoundingClientRect().bottom+2;
  }
 }
 await select('工作概览');
 return checks;
})()
