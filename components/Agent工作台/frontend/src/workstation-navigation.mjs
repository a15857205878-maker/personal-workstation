export const NAV_SECTIONS=[
 {id:'home',label:'总览',items:[{id:'overview',label:'工作概览',hint:'任务与协作动态',icon:'overview',aliases:'首页 总览'}]},
 {id:'work',label:'工具',defaultPage:'work',items:[
  {id:'work',label:'双模型协作',hint:'执行、审查与修订',icon:'work',aliases:'高级协作 agent 工作区'},
  {id:'pack',label:'资料与打包',hint:'素材整理与文件交付',icon:'pack',aliases:'资料 文件 zip 工作区'},{id:'icons',label:'图标换装台',hint:'预览、添加与还原图标',icon:'icons',aliases:'图标 换装台 桌宠换装台 添加图标 ico png 桌面 快捷方式'}]},
 {id:'social',label:'交流与陪伴',items:[
  {id:'chat',label:'聊天实验室',hint:'多席对话、风格与记忆',icon:'chat',aliases:'实验聊天 实验群聊 聊天 人格 长期记忆'},
  {id:'companion',label:'个人管家',hint:'工作概况、提醒与桌面陪伴',icon:'companion',aliases:'管家 个人中心 桌宠与提醒 桌宠 通知 陪伴 收件箱'}]},
 {id:'leisure',label:'休闲区',defaultPage:'leisure',items:[
  {id:'leisure',label:'休闲起点',hint:'继续阅读与休息选择',icon:'leisure',aliases:'放松起点 休息'},
  {id:'games',label:'游戏资料库',hint:'游戏与工具管理',icon:'games',aliases:'新增游戏 修改器 收藏'},
  {id:'wheel',label:'休闲轮盘',hint:'从候选中随机选择',icon:'wheel',aliases:'抽签 随机 steam'},
  {id:'reading',label:'书房与放松',hint:'取书、阅读与环境音',icon:'artifacts',aliases:'书架 阅读 小说 PDF Markdown 音乐 白噪音 放松角'},
  {id:'town',label:'小镇与专注',hint:'小镇、计时与休息',icon:'town',aliases:'番茄钟 专注'}]},
 {id:'services',label:'连接与成果',items:[
  {id:'remote',label:'远程',hint:'原配对页、聊天、成果与文件',icon:'remote',aliases:'tailscale 网络 手机 配对 传输'},
  {id:'artifacts',label:'成果',hint:'查找任务交付文件',icon:'artifacts',aliases:'下载 结果 文稿'},
  {id:'site-materials',label:'网站素材台',hint:'项目记录、资料出处与展示分镜',icon:'artifacts',aliases:'网站 素材 正文 检索 成长档案 更新摘要 演示 分镜'}]},
 {id:'system',label:'系统',items:[{id:'settings',label:'设置与维护',hint:'连接、外观与接口检查',icon:'settings',aliases:'模型 主题 接口 诊断'}]},
];
const pages=Object.fromEntries(NAV_SECTIONS.flatMap(section=>section.items.map(item=>[item.id,{...item,section:section.label}])));
const functionDestinations={
 partner:{id:'partner',label:'搭档群聊',hint:'和搭档讨论想法、交办任务或继续对话',aliases:'聊天 对话 提问 工作'},
 quick:{id:'quick',label:'快速交办（快捷栏）',hint:'从小窗口写下任务 · Ctrl + Alt + Space',aliases:'快捷指令 快捷栏 草稿',action:'quick'},
 replay:{id:'replay',label:'重播开场',hint:'再次查看工作站的开场动画',aliases:'动画 展示 演示 启动画面',action:'replay'},
 work:{...pages.work,label:'协作中心',hint:'分工、查看执行进度和交付',aliases:'高级协作 双模型协作 多模型 交办 任务'},
 remote:{...pages.remote,label:'手机连接',hint:'扫码配对，从手机继续聊天或取文件'},
 artifacts:{...pages.artifacts,hint:'查看任务交付、预览文件及回到原记录'},
};
export const FUNCTION_GROUPS=[
 {id:'work',label:'工作与交付',items:['partner','work','artifacts','overview','quick']},
 {id:'tools',label:'资料与工具',items:['pack','icons','site-materials']},
 {id:'leisure',label:'休闲与陪伴',items:['companion','town','reading','leisure','games','wheel']},
 {id:'settings',label:'连接与设置',items:['remote','settings','chat','replay']},
].map(group=>({...group,items:group.items.map(id=>functionDestinations[id]||pages[id])}));

export function findFunctions(query){
 const tokens=String(query||'').trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
 return FUNCTION_GROUPS.map(group=>({...group,items:group.items.filter(item=>{
  const text=[group.label,item.label,item.hint,item.aliases].join(' ').toLocaleLowerCase();
  return tokens.every(token=>text.includes(token));
 })})).filter(group=>group.items.length);
}

export const resolvePage=id=>id==='tasks'?'artifacts':id;
export function pageInfo(id){return id==='partner'?{id:'partner',label:'搭档',section:'个人工作站'}:pages[resolvePage(id)]||pages.overview;}
export function filterNavigation(query){
 const value=String(query||'').trim().toLocaleLowerCase();
 if(!value)return NAV_SECTIONS;
 return NAV_SECTIONS.map(section=>({...section,items:section.items.filter(item=>`${section.label} ${item.label} ${item.hint} ${item.aliases}`.toLocaleLowerCase().includes(value))})).filter(section=>section.items.length);
}
