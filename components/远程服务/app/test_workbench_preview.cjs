const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const mobile=require('./mobile-controller.js');
test('Preview eligibility covers Office and readable files while archives keep original download',()=>{
 for(const name of ['报告.docx','数据.xlsx','方案.pptx','图.png','正文.md','附件.pdf'])assert.equal(mobile.workbenchPreviewable(name),true,name);
 for(const name of ['打包.zip','程序.exe','unknown'])assert.equal(mobile.workbenchPreviewable(name),false,name);
});
test('Shared history PDF viewer accepts exact workbench download and rejects foreign URLs and paths',()=>{
 const html=fs.readFileSync(__dirname+'/pdf_viewer.html','utf8');const code=html.slice(html.indexOf('  function originalUrlFrom('),html.indexOf('  function titleFromOriginal('));const context={URL,location:{origin:'http://paired'},token:'fixture'};
 vm.runInNewContext(code,context);const parse=context.originalUrlFrom;
 const url=new URL(parse('/api/workbench-artifact?id='+ 'a'.repeat(32)+'&name='+encodeURIComponent('中文 文档.docx')),'http://paired');assert.equal(url.searchParams.get('token'),'fixture');assert.equal(url.searchParams.get('name'),'中文 文档.docx');
 for(const value of ['https://outside/api/workbench-artifact?id='+ 'a'.repeat(32)+'&name=x.docx','/api/workbench-artifact?id=bad&name=x.docx','/api/workbench-artifact?id='+ 'a'.repeat(32)+'&name=..%2Fx.docx'])assert.equal(parse(value),'');
 const collab=new URL(parse('/api/workbench-artifact?id='+ 'a'.repeat(32)+'&name=x.pptx&kind=collaboration'),'http://paired');assert.equal(collab.searchParams.get('kind'),'collaboration');assert.equal(parse('/api/workbench-artifact?id='+ 'a'.repeat(32)+'&name=x.pptx&kind=invalid'),'');
 assert.match(parse('/artifact/'+ 'b'.repeat(32)+'/report.pdf'),/^\/artifact\//);
});


test('XLSX opens the existing native worksheet viewer before any PDF conversion',()=>{
 const html=fs.readFileSync(__dirname+'/collaboration.html','utf8');const code=html.slice(html.indexOf('async function previewArtifact('),html.indexOf('function ask(',html.indexOf('async function previewArtifact(')));let target,requests=0;
 const context={URL,URLSearchParams,location:{origin:'http://paired'},token:'fixture',mobile:{preview:value=>target=value},message:()=>{},fetch:()=>{requests++;throw Error('PDF must not be requested');}};vm.runInNewContext(code,context);
 return context.previewArtifact('a'.repeat(32),'预算.xlsx').then(()=>{const url=new URL(target);assert.equal(url.pathname,'/file-viewer');assert.equal(url.searchParams.get('owner'),'workbench');assert.equal(url.searchParams.get('task_id'),'a'.repeat(32));assert.equal(url.searchParams.get('path'),'预算.xlsx');assert.equal(requests,0);});
});
