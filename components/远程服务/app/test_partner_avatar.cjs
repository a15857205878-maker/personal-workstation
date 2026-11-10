const {test}=require('node:test'),assert=require('node:assert/strict');
const {taskVoice}=require('./partner-theme.js');
test('partner voice describes real states without inventing delivery or model replies',()=>{
 assert.match(taskVoice({status:'running',stage:'第1轮·审查'}),/审查/);
 assert.match(taskVoice({status:'completed',output_format:'pptx',files:[]}),/未收到.*文件/);
 assert.match(taskVoice({status:'completed',files:[{name:'real.pptx'}]}),/预览/);
 assert.match(taskVoice({status:'failed'}),/需要处理/);
 assert.match(taskVoice({status:'completed',files:[{name:'real.pptx'}]},false),/上次/);
 assert.match(taskVoice({status:'stopping'}),/停止/);
 assert.match(taskVoice({status:'completed',steps:[{content:'old text'}]}),/文字已完成/);
});
