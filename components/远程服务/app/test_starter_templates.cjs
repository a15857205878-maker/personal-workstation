const test=require('node:test'),assert=require('node:assert/strict');
const {templates}=require('./conversation_tools.js');
const {fileQuery}=require('./pc_file_search.js');
test('five starter commands cover files and bounded retrieval without a new execution path',()=>{
 assert.deepEqual(templates.slice(0,5).map(x=>x[0]),['文档','Excel','PPTX','网页设计','取回文件']);
 assert.match(templates[0][1],/DOCX/);assert.match(templates[1][1],/公式/);assert.match(templates[2][1],/3页/);assert.match(templates[3][1],/本地/);
 assert.equal(fileQuery(templates[4][1]),'');
});
