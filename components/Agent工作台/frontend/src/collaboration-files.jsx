import React from 'react';

export default function CollaborationFiles({session,onOpen,onDownload,disabled}){
 const files=session?.files||[],preview=session?.artifact_preview;if(!files.length)return null;
 return <section className="auto-delivery" aria-label="协作成果文件"><h3>成果文件</h3><p className="auto-small">两席完成内容制作与复核，工作站已生成文件并校验结构。可在这里预览内容，或用本机软件检查原件排版。</p>
  {files.map(file=><div className="auto-delivery-file" key={file.name}><div className="partner-file-title"><i className={"partner-icon partner-icon-"+(file.format||"docx")} aria-hidden="true"/><div><strong>{file.format?.toUpperCase()} · {file.name}</strong><small>{Math.ceil(file.size/1024)} KB · 已保存在电脑</small></div></div><div className="partner-file-actions">{onDownload&&<button className="auto-button auto-primary" disabled={disabled} onClick={()=>onDownload(file.name)}>下载原件</button>}<button className="auto-button" disabled={disabled} onClick={()=>onOpen(file.name)}>本机打开</button></div></div>)}
  {preview&&<details className="auto-delivery-preview" open><summary>预览成果内容</summary><p className="auto-small">内容预览用于核对文字与数据，不等同于 Office 原件的完整排版。</p>
   {preview.type==='pptx'&&preview.image_count>0&&<p className="auto-small">PPTX 已嵌入 {preview.image_count} 张配图。请打开原文件检查图文排版。</p>}
   {preview.type==='docx'&&<div className="auto-delivery-document">{preview.text}</div>}
   {preview.type==='xlsx'&&(preview.sheets||[]).map(sheet=><section key={sheet.name}><h4>{sheet.name} · {sheet.total_rows} 行</h4><div className="auto-delivery-table"><table><thead><tr>{sheet.columns.map((c,i)=><th key={i}>{c}</th>)}</tr></thead><tbody>{sheet.rows.map((row,r)=><tr key={r}>{row.map((value,c)=><td key={c}>{value===null?'':String(value)}</td>)}</tr>)}</tbody></table></div>{sheet.total_rows>20&&<small>仅预览前20行，全部数据在原文件中。</small>}</section>)}
   {preview.type==='pptx'&&(preview.slides||[]).map((slide,i)=><article className="auto-delivery-slide" key={i}><small>{i+1} / {preview.slides.length}</small><h3>{slide.title}</h3><p>{slide.subtitle}</p><ul>{slide.bullets.map((line,j)=><li key={j}>{line}</li>)}</ul></article>)}
  </details>}
 </section>;
}
