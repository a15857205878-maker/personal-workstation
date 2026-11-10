(function(root){
'use strict';
const templates=[
 ["文档", "请制作一份可下载的 DOCX 周计划。\n包括：本周目标、周一到周日安排、待办清单。每天留出学习、工作和休息时间，用简洁中文。安排作为可修改的示例，不编造我的个人经历。"],
 ["Excel", "请制作一份采购预算 Excel：牛奶2盒，每盒12元；面包3袋，每袋8元；鸡蛋1盒18元。\n列出品名、数量、单价、小计和总额，使用公式计算，检查汇总结果，实际生成可编辑的 XLSX 文件。"],
 ["PPTX", "请制作一份3页的可编辑 PPTX，主题是“我的一周工作计划”。\n第1页：本周目标；第2页：每日安排；第3页：检查清单。用简洁中文和蓝白配色，不超过5个要点/页。实际生成文件，材料不足时明确说明。"],
 ["网页设计", "请在本地创建一个适配手机的每日待办网页。\n支持新增事项、勾选完成、删除，以及刷新后保留记录。使用清爽的蓝白配色，文件保存在当前任务的工作目录，并检查功能后提供网页预览。"],
 ["取回文件", "我要调用文件"],
 ['检查文件','请检查我附上的文件，重点看：\n请说明发现的问题、对应位置和修改建议。先只读检查，不修改原文件。'],
 ['总结 / 翻译','请帮我处理以下内容。\n处理方式（总结 / 翻译 / 润色）：\n内容或附件：\n输出要求：'],
 ['排查报错','请帮我排查这个问题。\n程序名称：\n报错原文：\n触发步骤：\n请先确认原因，再说明处理方法和验证结果。']
];
function mount(){const d=root.document,models=d?.getElementById('sessionModels'),input=d?.getElementById('composerInput');if(!models||!input)return;
 const el=(tag,text)=>{const n=d.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
 const style=el('style');style.textContent='.conversation-tools-dialog{box-sizing:border-box;width:min(560px,calc(100vw - 24px));max-height:85dvh;overflow:auto;padding:18px;border:1px solid var(--line,#d4dfec);border-radius:16px;background:var(--panel,#f4f8fd);color:var(--ink,#24354c)}.conversation-tools-dialog h2{font-size:18px;margin:0}.conversation-tools-dialog p{font-size:13px;line-height:1.7;color:var(--muted,#647a92)}.conversation-tools-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:14px 0}.conversation-tools-dialog button{min-height:42px;padding:10px;font-size:14px;border:1px solid var(--line,#d4dfec);border-radius:10px;background:var(--card,#fff);color:var(--ink,#24354c)}.conversation-tools-dialog .conversation-tools-close{width:100%}';d.head.append(style);
 function dialog(id,title,hint){const box=el('dialog');box.id=id;box.className='conversation-tools-dialog';box.append(el('h2',title),el('p',hint));const choices=el('div');choices.className='conversation-tools-grid';const status=el('p');status.setAttribute('role','status');const close=el('button','关闭');close.type='button';close.className='conversation-tools-close';close.onclick=()=>box.close();box.append(choices,status,close);d.body.append(box);return {box,choices,status};}
 const shortcuts=dialog('conversationShortcuts','对话模板','先选示例，再改成你的需求。只填草稿，不自动发送；取回文件从工作站文件库查找。');
 for(const [label,text] of templates){const b=el('button',label);b.type='button';b.onclick=()=>{
  if(input.value.trim()){shortcuts.status.textContent='输入框已有草稿，已为你保留。请先处理原内容，再选择模板。';return;}
  if(d.getElementById('composer')?.hidden&&d.getElementById('emptyState')?.hidden===false)d.getElementById('emptyNew')?.click();
  if(d.getElementById('composer')?.hidden&&typeof root.remoteWorkstationPrepareDraft==='function'){
   const prepared=root.remoteWorkstationPrepareDraft(text);
   if(prepared?.accepted){shortcuts.box.close();return;}
   shortcuts.status.textContent=prepared?.reason||'请先新建或选择可继续的单模型对话。';return;
  }
  if(input.hidden||input.disabled||input.readOnly||d.getElementById('composer')?.hidden){shortcuts.status.textContent='当前记录不可输入，请先新建或选择可继续的单模型对话。';return;}
  input.value=text;input.dispatchEvent(new Event('input',{bubbles:true}));shortcuts.box.close();input.focus();
 };shortcuts.choices.append(b);}
 const shortcutButton=el('button','模板');shortcutButton.id='conversationShortcutsButton';shortcutButton.type='button';shortcutButton.onclick=()=>{shortcuts.status.textContent='';shortcuts.box.showModal();};models.append(shortcutButton);
 const selects=d.getElementById('newSelects');if(selects){const settings=el('details');settings.className='partner-send-settings';settings.append(el('summary','发送设置'));selects.before(settings);settings.append(selects);settings.hidden=selects.hidden;if(root.MutationObserver)new root.MutationObserver(()=>{settings.hidden=selects.hidden;}).observe(selects,{attributes:true,attributeFilter:['hidden']});}
 const brand=d.querySelector('.brand');if(brand){const mark=brand.querySelector('.brand-mark');if(mark){mark.textContent='';mark.classList.add('partner-sidebar-brand');}const name=brand.lastElementChild;if(name&&name!==mark)name.textContent='搭档';}
 const welcome=d.querySelector('.empty-card'),newHint=d.getElementById('newHint');
 function templateRow(host){if(!host)return;const grid=el('div');grid.className='partner-template-grid';grid.setAttribute('aria-label','文件模板');for(const [i,label]of ['文档','Excel','PPTX','网页'].entries()){const b=el('button',label);b.type='button';b.onclick=()=>{shortcuts.status.textContent='';shortcuts.choices.children[i].click();if(shortcuts.status.textContent&&!shortcuts.box.open)shortcuts.box.showModal();};grid.append(b);}host.append(grid);}
 templateRow(welcome);templateRow(newHint);
 const title=d.getElementById('emptyTitle');if(title){title.textContent='今天，一起完成什么？';title.classList.add('partner-brand');}
 const lead=d.getElementById('emptyLead');if(lead)lead.textContent='说出目标，我们从这里开始。';
 let mobile=false;try{mobile=root.parent!==root&&root.parent.location.origin===location.origin&&root.frameElement?.dataset.workstationSession==='1';}catch{}
 if(mobile){const original=d.getElementById('sessionCollaboration'),code=d.getElementById('codeProjectButton');if(original&&code){const menu=dialog('conversationCollaboration','双模型协作','选择需要的协作方式，下一步检查目标与设置。');
  for(const [title,hint,target] of [['网页与代码','实际编写文件，DeepSeek 与 Codex 分工完成。',code],['文件与讨论','Word、Excel、PPTX或文字，制作与审查一起完成。',original]]){const b=el('button');b.type='button';b.append(el('strong',title),el('p',hint));b.onclick=()=>{menu.box.close();target.click();};menu.choices.append(b);}
  const button=el('button','双模型');button.id='conversationCollaborationButton';button.type='button';button.onclick=()=>menu.box.showModal();models.insertBefore(button,shortcutButton);original.hidden=true;code.hidden=true;
  root.remoteWorkstationOpenCollaboration=()=>button.click();
 }}
}
if(typeof module!=='undefined'&&module.exports)module.exports={templates};else mount();
})(typeof window!=='undefined'?window:globalThis);
