import React from 'react';

export function saveCollaborationFile(file){
 const bytes=Uint8Array.from(atob(file.content_base64),c=>c.charCodeAt(0));
 const url=URL.createObjectURL(new Blob([bytes],{type:file.mime||'application/octet-stream'}));
 const link=document.createElement('a');
 link.href=url;link.download=file.name;document.body.appendChild(link);
 try{link.click();}
 finally{link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);}
}

export function runFilePreview(run,name){
 const preview=run?.artifact_preview;
 const file=run?.files?.find(entry=>entry.name===name);
 const format=entry=>entry.format||entry.name.split('.').pop().toLowerCase();
 if(!preview||!file||preview.type!==format(file))return null;
 return run.files.filter(entry=>format(entry)===preview.type).length===1?preview:null;
}

export function DeliveryPreview({preview}){
 return <>
   {preview.type==='pptx'&&preview.image_count>0&&<p className="auto-small">PPTX 已嵌入 {preview.image_count} 张配图。请打开原文件检查图文排版。</p>}
   {preview.type==='docx'&&<><div className="auto-delivery-document">{preview.text}</div>
    {preview.table&&<div className="auto-delivery-table"><table><thead><tr>
     {preview.table.columns.map((label,index)=><th scope="col" key={index}>{label}</th>)}
    </tr></thead><tbody>{preview.table.rows.map((row,index)=><tr key={index}>
     {row.map((cell,column)=><td key={column}>{cell}</td>)}
    </tr>)}</tbody></table></div>}
   </>}
   {preview.type==='svg'&&<div><p>{preview.text}</p>{preview.svg&&<img className="center-svg-preview" src={'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(preview.svg)} alt="本任务实际生成的SVG示意图"/>}</div>}
   {preview.type==='xlsx'&&(preview.sheets||[]).map(sheet=><section key={sheet.name}><h4>{sheet.name} · {sheet.total_rows} 行</h4><div className="auto-delivery-table"><table><thead><tr>{sheet.columns.map((c,i)=><th key={i}>{c}</th>)}</tr></thead><tbody>{sheet.rows.map((row,r)=><tr key={r}>{row.map((value,c)=><td key={c}>{value===null?'':String(value)}</td>)}</tr>)}</tbody></table></div>{sheet.total_rows>20&&<small>仅预览前20行，全部数据在原文件中。</small>}</section>)}
   {preview.type==='pptx'&&(preview.slides||[]).map((slide,i)=><article className="auto-delivery-slide" key={i}><small>{i+1} / {preview.slides.length}</small><h3>{slide.title}</h3><p>{slide.subtitle}</p><ul>{slide.bullets.map((line,j)=><li key={j}>{line}</li>)}</ul></article>)}
 </>;
}

export default function CollaborationFiles({session,onOpen,onDownload,disabled,compact=false,tile=false,title=''}){
 const files=session?.files||[],preview=session?.artifact_preview;if(!files.length)return null;
 return <section className={"auto-delivery"+(tile?" auto-delivery-tile":"")} aria-label="协作成果文件">{!compact&&<><h3>成果文件</h3><p className="auto-small">工作站已生成文件并校验格式，可打开原件检查内容和排版。</p></>}
  {files.map(file=><div className="auto-delivery-file" key={file.name} data-artifact-run={compact?session.id:undefined} data-artifact-name={compact?file.name:undefined} tabIndex={compact?-1:undefined}><div className="partner-file-title"><i className={"partner-icon partner-icon-"+(file.format||"docx")} aria-hidden="true"/><div><strong title={file.name}>{file.format?.toUpperCase()} · {tile?'原件':compact?(title||'成果文件'):file.name}</strong><small>{Math.ceil(file.size/1024)} KB{!tile&&' · 已保存在电脑'}</small></div></div><div className="partner-file-actions">
   {!compact&&onDownload&&<button className="auto-button auto-primary" disabled={disabled} onClick={()=>onDownload(file.name)}>下载原件</button>}
   <button className="auto-button" disabled={disabled} onClick={()=>onOpen(file.name)}>本机打开</button>
   {compact&&onDownload&&<button className="auto-button" disabled={disabled} onClick={()=>onDownload(file.name)}>保存副本</button>}
  </div></div>)}
  {preview&&<details className="auto-delivery-preview" open={!compact}><summary>{compact?'在对话中预览':'预览成果内容'}</summary><p className="auto-small">{compact?'打开原件可查看完整版式。':'内容预览用于核对文字与数据，不等同于 Office 原件的完整排版。'}</p>
   <DeliveryPreview preview={preview}/>
  </details>}
 </section>;
}
