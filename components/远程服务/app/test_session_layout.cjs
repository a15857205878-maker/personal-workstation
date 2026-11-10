const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const page=fs.readFileSync(__dirname+'/mobile_bot.html','utf8'),script=fs.readFileSync(__dirname+'/conversation.js','utf8');
test('Session surface keeps history, both partitions, refresh and composer without outbound navigation',()=>{
 for(const id of ['sessionCodex','sessionDeepSeek','sessionModels','menuButton','searchInput','conversationList','messageList','composerInput','sendButton'])assert.match(page,new RegExp('id="'+id+'"'));
 for(const id of ['menuOpenCodex','menuTransfer','menuCollaboration','menuDialog'])assert.doesNotMatch(page,new RegExp('id="'+id+'"'));
 assert.doesNotMatch(page,/<a[^>]+href="https?:/);assert.doesNotMatch(page,/class="personal-site-link"/);
 assert.match(script,/\$\('menuButton'\)\.addEventListener\('click', refreshAll\)/);
});
test('Existing file, review, read-only and draft controls survive a layout-only edit',()=>{
 for(const id of ['attachButton','fileInput','attachmentTray','modeSelect','agentSelect','progressPanel','jobsPanel'])assert.match(page,new RegExp('id="'+id+'"'));
 assert.match(page,/<option value="review">只读审查<\/option>/);
 assert.match(script,/const deepSeekReadOnly = !!target && target.kind !== 'new' && target.partition === 'deepseek'/);
 assert.match(script,/else sendReply\(\)/);assert.match(script,/state.drafts.set/);
});

test('An old receiver is labeled update-needed instead of treating every DeepSeek session as readonly',()=>{
 const vm=require('node:vm');const source=script.slice(script.indexOf('  function deepSeekCapability('),script.indexOf('  function applyConversation('));const context={};vm.runInNewContext(source,context);
 assert.equal(context.deepSeekCapability({can_reply:false,reply_hint:'旧版只读'}).label,'需更新');
 assert.equal(context.deepSeekCapability({resume_supported:false,can_reply:false,reply_hint:'特殊预设'}).label,'只读');
 assert.equal(context.deepSeekCapability({resume_supported:true,can_reply:true}).label,'可继续');
 assert.equal(context.deepSeekCapability({resume_supported:true,can_reply:false}).label,'处理中');
});
