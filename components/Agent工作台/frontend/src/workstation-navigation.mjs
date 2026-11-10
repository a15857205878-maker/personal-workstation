export const NAV_SECTIONS=[
 {id:'home',label:'总览',items:[{id:'overview',label:'工作概览',hint:'任务与协作动态',icon:'overview',aliases:'首页 总览'}]},
 {id:'work',label:'工作区',defaultPage:'tasks',items:[
  {id:'tasks',label:'独立任务',hint:'创建、执行与交接',icon:'tasks',aliases:'文档 ppt 文字 审查'},
  {id:'work',label:'双模型协作',hint:'执行、审查与修订',icon:'work',aliases:'高级协作 agent'},
  {id:'pack',label:'资料与打包',hint:'素材整理与文件交付',icon:'pack',aliases:'资料 文件 zip'}]},
 {id:'social',label:'交流与陪伴',items:[
  {id:'chat',label:'聊天实验室',hint:'多席对话、风格与记忆',icon:'chat',aliases:'实验聊天 实验群聊 聊天 人格 长期记忆'},
  {id:'companion',label:'个人管家',hint:'工作概况、提醒与桌面陪伴',icon:'companion',aliases:'管家 个人中心 桌宠与提醒 桌宠 通知 陪伴 收件箱'}]},
 {id:'leisure',label:'休闲区',defaultPage:'games',items:[
  {id:'games',label:'游戏资料库',hint:'游戏与工具管理',icon:'games',aliases:'新增游戏 修改器 收藏'},
  {id:'wheel',label:'休闲轮盘',hint:'从候选中随机选择',icon:'wheel',aliases:'抽签 随机 steam'},
  {id:'reading',label:'书房与放松',hint:'取书、阅读与环境音',icon:'artifacts',aliases:'书架 阅读 小说 PDF Markdown 音乐 白噪音 放松角'},
  {id:'town',label:'小镇与专注',hint:'小镇、计时与休息',icon:'town',aliases:'番茄钟 专注'}]},
 {id:'services',label:'连接与成果',items:[
  {id:'remote',label:'远程',hint:'手机、会话与连接',icon:'remote',aliases:'tailscale 网络 手机 配对 传输'},
  {id:'artifacts',label:'成果',hint:'查找任务交付文件',icon:'artifacts',aliases:'下载 结果 文稿'},
  {id:'site-materials',label:'网站素材台',hint:'项目记录、资料出处与展示分镜',icon:'artifacts',aliases:'网站 素材 正文 检索 成长档案 更新摘要 演示 分镜'}]},
 {id:'system',label:'系统',items:[{id:'icons',label:'图标换装台',hint:'预览、添加与还原图标',icon:'icons',aliases:'图标 换装台 添加图标 ico png 桌面 快捷方式'},{id:'settings',label:'设置与维护',hint:'连接、外观与接口检查',icon:'settings',aliases:'模型 主题 接口 诊断'}]},
];
const pages=Object.fromEntries(NAV_SECTIONS.flatMap(section=>section.items.map(item=>[item.id,{...item,section:section.label}])));
export function pageInfo(id){return id==='partner'?{id:'partner',label:'搭档',section:'个人工作站'}:pages[id]||pages.overview;}
export function filterNavigation(query){
 const value=String(query||'').trim().toLocaleLowerCase();
 if(!value)return NAV_SECTIONS;
 return NAV_SECTIONS.map(section=>({...section,items:section.items.filter(item=>`${section.label} ${item.label} ${item.hint} ${item.aliases}`.toLocaleLowerCase().includes(value))})).filter(section=>section.items.length);
}
