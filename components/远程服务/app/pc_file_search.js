(function(root){
'use strict';
function fileQuery(text){const value=String(text||'').trim();if(['我要调用文件','调用文件','打开文件库','查看文件库'].includes(value))return '';const library=/^(?:我要|帮我|请)?调用文件[：:\s]+(.{1,120})$/.exec(value);if(library)return library[1].trim();const match=/^(?:(?:请|帮我)\s*)?(?:找电脑文件|查找电脑文件|找文件)[：:\s]+(.{1,120})$/.exec(value)||/^(?:(?:请|帮我)\s*)?(?:找|查找|搜索)(?:一下)?电脑(?:里|上|中)(?:的)?(?:叫|名为)?[：:\s]*(.{1,120}?)(?:这个文件|的文件|文件)?$/.exec(value);return match?match[1].trim():null;}
const REPLAY_MANIFEST = 'PYNQ_manifest.json';
const REPLAY_LABEL = '数据来源：模拟 ECG/PPG CSV 回放';
const REPLAY_UNKNOWN = '数据来源：待核对';
const REPLAY_CASE = /^PYNQ_(first|second)_fpga_waveform[.]png$/;
const FILE_TICKET = /^[a-f0-9]{32}$/;

function archivePath(row) {
 const relative=String(row.relative||'');
 const slash=relative.lastIndexOf('/');
 return slash<0?'':relative.slice(0,slash+1);
}

function replaySource(row,manifest) {
 const matched=REPLAY_CASE.exec(row.name||'');
 if(!matched||manifest?.version!==1||manifest.case!==matched[1]||manifest.provenance!=='simulated CSV replay')return REPLAY_UNKNOWN;
 const fingerprint=String(manifest.bundle_sha256||'');
 const folder=archivePath(row).split('/').at(-2);
 const hash=/^[a-f0-9]{64}$/;
 if(!hash.test(fingerprint)||folder!=='PYNQ_'+matched[1]+'_'+fingerprint.slice(0,16)||
    !hash.test(String(manifest.sha256?.[row.name]||'')))return REPLAY_UNKNOWN;
 return REPLAY_LABEL;
}

let resume=()=>{};
function mount(){
 if(!root.document||document.getElementById('pcFileSearch'))return;
 const composer=document.getElementById('composer'),attach=document.getElementById('attachButton'),folderHost=document.getElementById('mcFileLibrary')||document.getElementById('mcSettings');if(!attach&&!folderHost)return;
 const token=new URLSearchParams(location.search).get('token')||'';
 function el(tag,text,cls){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;}
 const style=el('style');style.textContent='.pc-find-button{font:inherit;font-size:12px;min-height:36px;padding:6px 9px;border:1px solid var(--line,#d4dfec);border-radius:9px;background:var(--card,#fff);color:var(--ink,#24354c);flex:none}#pcFileSearch{box-sizing:border-box;width:min(560px,calc(100vw - 24px));max-height:84dvh;overflow:auto;border:1px solid #d4dfec;border-radius:16px;padding:18px;color:#24354c;background:#f8fbff;font-family:inherit}#pcFileSearch::backdrop{background:#182b4355}.pc-find-head{display:flex;align-items:center;gap:12px}.pc-find-head h2{flex:1;font-size:18px;margin:0}.pc-find-form{display:flex;gap:8px;margin:16px 0}.pc-find-form select{max-width:110px;min-width:0;border:1px solid #bdcede;border-radius:9px;background:#fff;color:#24354c;font:inherit;font-size:12px}.pc-find-form input{box-sizing:border-box;min-width:0;flex:1;font:inherit;font-size:16px;padding:9px;border:1px solid #bdcede;border-radius:9px}.pc-find-row{padding:12px 0;border-top:1px solid #d4dfec;overflow-wrap:anywhere}.pc-find-row strong,.pc-find-row small{display:block}.pc-find-row small{color:#647a92;font-size:12px;margin:5px 0}.pc-find-row a{display:inline-block;color:#2f6fcf;padding:8px 0}.pc-find-hint{font-size:13px;line-height:1.6;color:#647a92}';style.textContent+=
  '#pcFileSearch .pc-find-all{display:flex;align-items:center;gap:8px}' +
  '#pcFileSearch #pcFileShowAll{width:auto;min-width:0;flex:none;margin:0}' +
  '#pcFileSearch .pc-replay-source[data-verified=true]{display:table;padding:4px 8px;border-radius:8px;background:#e4f2f4;color:#2e5360;font-weight:600}';
 document.head.append(style);
 const inline=folderHost?.id==='mcFileLibrary';const dialog=el(inline?'section':'dialog');if(inline){dialog.open=true;dialog.className='mc-inline-library';}dialog.id='pcFileSearch';dialog.setAttribute('aria-labelledby','pcFileTitle');
 const previewUrls=new Set();function clearPreviewUrls(){for(const url of previewUrls)URL.revokeObjectURL(url);previewUrls.clear();}dialog.addEventListener('close',clearPreviewUrls);
 const head=el('div',undefined,'pc-find-head'),title=el('h2','手机文件库');title.id='pcFileTitle';const close=el('button','关闭','pc-find-button');close.type='button';close.onclick=()=>dialog.close();head.append(title,close);
 const form=el('form',undefined,'pc-find-form'),input=el('input');input.type='search';input.maxLength=120;input.placeholder='文件名关键词，例如预算、报告.pdf';input.setAttribute('aria-label','电脑文件名关键词');input.id='pcFileQuery';const search=el('button','查找','pc-find-button');search.type='submit';form.append(input,search);
 const mode=el('select');mode.id='pcFileSearchMode';mode.setAttribute('aria-label','文件检索方式');for(const [value,label] of [['filename','文件名'],['content','正文与出处']]){const option=el('option',label);option.value=value;mode.append(option);}form.prepend(mode);mode.onchange=()=>{input.placeholder=mode.value==='content'?'正文关键词（TXT、MD、文本PDF）':'文件名关键词，例如预算、报告.pdf';input.setAttribute('aria-label',mode.value==='content'?'文件正文关键词':'电脑文件名关键词');};
 const allLabel=el('label','显示全部文件（CSV、JSON、说明等）','pc-find-hint pc-find-all'),allFiles=el('input');allFiles.type='checkbox';allFiles.id='pcFileShowAll';allLabel.prepend(allFiles);
 const status=el('p','', 'pc-find-hint');status.id='pcFileStatus';status.setAttribute('role','status');const results=el('div');results.id='pcFileResults';dialog.append(head,el('p','直接读取电脑当前共享文件夹。图片、文字和 CSV 可预览；原件可下载。在电脑“手机连接与任务”中可更换文件夹。','pc-find-hint'),form,status,results);(inline?folderHost:document.body).append(dialog);if(inline)close.hidden=true;
 let busy=false,revision=0;
 form.after(allLabel);allFiles.onchange=()=>find();
 async function request(path){const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),15000);try{const response=await fetch(path+(path.includes('?')?'&':'?')+'token='+encodeURIComponent(token),{cache:'no-store',credentials:'same-origin',signal:abort.signal});const data=await response.json();if(!response.ok)throw Error(data.error||'查找未完成，请稍后重试。');return data;}finally{clearTimeout(timer);}}
 const fileUrl=id=>'/api/pc-files/download?id='+encodeURIComponent(id)+'&token='+encodeURIComponent(token);
 function sourceReader(rows){
  let additional;
  const reads=new Map();
  async function lookup(row){
   const folder=archivePath(row);
   if(!folder)return null;
   const matches=item=>item.name===REPLAY_MANIFEST&&item.folder===row.folder&&archivePath(item)===folder;
   let item=rows.find(matches);
   if(!item){
    additional??=request('/api/pc-files/library?q='+encodeURIComponent(REPLAY_MANIFEST))
     .then(data=>data.files||[]).catch(error=>{additional=undefined;throw error;});
    item=(await additional).find(matches);
   }
   if(!item?.downloadable||!FILE_TICKET.test(item.id)||!Number.isFinite(item.size)||item.size<1||item.size>8192)return null;
   const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),8000);
   try{
    const response=await fetch(fileUrl(item.id),{cache:'no-store',credentials:'same-origin',signal:abort.signal});
    if(!response.ok)return null;
    const raw=await response.arrayBuffer();
    return raw.byteLength<=8192?JSON.parse(new TextDecoder().decode(raw)):null;
   }finally{clearTimeout(timer);}
  }
  return async row=>{
   const key=JSON.stringify([row.folder,archivePath(row)]);
   if(!reads.has(key))reads.set(key,lookup(row).catch(()=>null));
   const manifest=await reads.get(key);
   if(!manifest)reads.delete(key);
   return replaySource(row,manifest);
  };
 }
 function scopes(data){return (data.roots||[]).length?'可查目录：'+data.roots.map(r=>r.label).join('、'):'文件库尚未就绪，请在电脑个人工作站 → 远程 → 打开手机文件库。';}
 let previousQuery=null,refreshNeeded=false;
 async function find(){if(busy)return;const value=input.value.trim();if(mode.value==='content'&&!value){status.textContent='请输入正文关键词。';input.focus();return;}busy=true;search.disabled=true;const seq=++revision;previousQuery={value,mode:mode.value};status.textContent='正在电脑查找…';try{const data=await request('/api/pc-files/library?q='+encodeURIComponent(value)+'&mode='+encodeURIComponent(mode.value));if(seq!==revision)return;if(root.navigator.onLine===false)throw Error('手机网络已断开。');refreshNeeded=false;clearPreviewUrls();results.replaceChildren();status.textContent=(data.roots||[]).length?'共享文件夹：'+data.roots.map(r=>r.label).join('、')+' · '+(data.files.length?'找到 '+data.files.length+' 个文件。':value?'没有找到匹配文件。':'文件夹还是空的。')+' 新文件保存后点“查找”刷新。'+(data.limited?'本次搜索达到范围或数量上限，可换更具体的关键词。':'')+(data.unavailable?'部分目录暂不可读取。':''):scopes(data);
 const readSource=sourceReader(data.files||[]);
 const rows=visibleFiles(data.files||[],allFiles.checked||mode.value==='content');if(!allFiles.checked&&mode.value!=='content')status.textContent='波形与图片：'+rows.length+' 张。文字和原始数据已隐藏；新结果保存后点“查找”刷新。'+(data.limited?'列表已达上限，可按图片文件名搜索。':'');
 if(mode.value==='content')status.textContent+=' 正文检索：TXT/MD行号、文本PDF页码。'+(data.warnings||[]).join(' ');
 for(const row of rows.sort((a,b)=>Number(b.modified)-Number(a.modified))){if(!/^[a-f0-9]{32}$/.test(row.id||''))continue;const item=el('div',undefined,'pc-find-row');item.append(el('strong',row.name),el('small',row.folder+' / '+row.relative+' · '+(Number(row.size)/1024).toFixed(1)+' KiB'));if(row.excerpt)item.append(el('p',row.location+' · '+row.excerpt,'pc-find-hint'));const source=REPLAY_CASE.test(row.name)?el('small',REPLAY_UNKNOWN,'pc-replay-source'):null;if(source)item.append(source);if(row.downloadable){const link=el('a','下载到手机');link.href=fileUrl(row.id);link.download=row.name;item.append(link);const kind=previewKind(row.name,row.size);if(kind){const button=el('button','预览','pc-find-button'),area=el('div');button.type='button';button.style.marginLeft='16px';button.onclick=async()=>{button.disabled=true;area.replaceChildren(el('p','正在读取电脑文件…','pc-find-hint'));const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),15000);try{const response=await fetch(link.href,{cache:'no-store',signal:abort.signal});if(!response.ok)throw Error('文件已变化或连接中断，请重新查找。');const raw=await response.arrayBuffer();if(!area.isConnected||!dialog.open)return;if(raw.byteLength>previewLimit(kind))throw Error('文件超过预览大小，请下载原件。');if(kind==='text'){const pre=el('pre',new TextDecoder().decode(raw));pre.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere;max-height:45dvh;overflow:auto;font-size:12px';area.replaceChildren(pre);}else{const image=el('img'),url=URL.createObjectURL(new Blob([raw],{type:kind}));previewUrls.add(url);image.src=url;image.alt=row.name;if(source)void readSource(row).then(label=>{if(!source.isConnected)return;source.textContent=label;source.dataset.verified=String(label===REPLAY_LABEL);if(label===REPLAY_LABEL)image.alt=row.name+' · '+label;});image.style.cssText='display:block;max-width:100%;height:auto;margin-top:10px';area.replaceChildren(image);}}catch(error){if(area.isConnected)area.replaceChildren(el('p',error.name==='AbortError'?'读取超时，请重试。':error.message,'pc-find-hint'));}finally{clearTimeout(timer);button.disabled=false;}};item.append(button,area);}}else item.append(el('small','超过100MiB，请在电脑取用。'));results.append(item);}
 if(!allFiles.checked&&mode.value!=='content')for(const b of [...results.querySelectorAll('button')].slice(0,3))b.click();
 }catch(error){if(seq===revision){refreshNeeded=true;status.textContent='查找未完成，已保留上次结果。'+(error.name==='AbortError'?'查找超时，可缩小范围后重试。':error.message||'');}}finally{busy=false;search.disabled=false;}}
 async function open(query=''){if(!inline&&!dialog.open)dialog.showModal();input.value=query;input.focus();await find();}
 form.onsubmit=event=>{event.preventDefault();find();};const button=el('button',attach?'文件库':'电脑共享文件夹','pc-find-button');button.id='pcFileButton';button.type='button';button.setAttribute('aria-label','打开手机文件库');button.onclick=()=>open();if(attach)attach.after(button);else if(!inline){folderHost.prepend(button);const heading=document.getElementById('mcTaskHeading');if(heading){const shortcut=el('button','电脑文件夹','pc-find-button');shortcut.id='pcFileResultsButton';shortcut.type='button';shortcut.onclick=()=>open();heading.append(shortcut);}}
 if(inline){
  resume=()=>{if(refreshNeeded&&previousQuery?.value===input.value.trim()&&previousQuery.mode===mode.value)find();};
  root.addEventListener('offline',()=>{refreshNeeded=true;status.textContent='手机网络已断开，已保留上次结果。';});
  find();
 }
 composer?.addEventListener('submit',event=>{const query=fileQuery(document.getElementById('composerInput')?.value);if(query!==null){event.preventDefault();event.stopImmediatePropagation();open(query);}},true);
}
function previewKind(name,size){const extension=String(name).toLowerCase().split('.').pop();const kind={png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',webp:'image/webp',txt:'text',csv:'text',json:'text',md:'text',log:'text'}[extension];return kind&&Number.isFinite(Number(size))&&Number(size)>=0&&Number(size)<=previewLimit(kind)?kind:null;}
function previewLimit(kind){return kind==='text'?512*1024:10*1024*1024;}
function visibleFiles(rows,all=false){return all?rows:rows.filter(r=>/\.(png|jpe?g|webp)$/i.test(r.name));}
const api={fileQuery,mount,resume:()=>resume(),previewKind,visibleFiles,replaySource};if(typeof module!=='undefined'&&module.exports)module.exports=api;else{root.PCFileSearch=api;mount();}
})(typeof window!=='undefined'?window:globalThis);
