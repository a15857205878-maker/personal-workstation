/* Read-only v4 Harness public transcript projection. No Harness bootstrap or credentials. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const zlib = require('node:zlib');
const MAX_LOG = 64 * 1024 * 1024;
const MAX_LINE = 2 * 1024 * 1024;
const text = value => typeof value === 'string' ? value : '';
function publicText(content) {
  if (typeof content === 'string') return content;
  if (!Array.isArray(content)) return '';
  return content.map(part => {
    if (!part || typeof part !== 'object') return '';
    if (part.type === 'text') return text(part.text);
    if (part.type === 'image' || part.type === 'image-url') return '[图片]';
    return '';
  }).filter(Boolean).join('\n');
}
function safeChild(root, candidate, directory) {
  const stat = fs.lstatSync(candidate);
  if (stat.isSymbolicLink() || (directory ? !stat.isDirectory() : !stat.isFile())) return false;
  const rel = path.relative(root, fs.realpathSync(candidate));
  return rel !== '' && !rel.startsWith('..') && !path.isAbsolute(rel);
}
function files(root) {
  if (!fs.existsSync(root)) return {items: [], skipped: 0};
  root = fs.realpathSync(root);
  const items = []; let skipped = 0;
  for (const project of fs.readdirSync(root, {withFileTypes:true})) {
    const projectPath = path.join(root, project.name);
    if (!safeChild(root, projectPath, true)) continue;
    for (const session of fs.readdirSync(projectPath, {withFileTypes:true})) {
      const sessionPath = path.join(projectPath, session.name);
      if (!safeChild(root, sessionPath, true)) continue;
      const generations = fs.readdirSync(sessionPath).map(name => {
        const match = /^session(?:\.v(\d+))?\.jsonl(\.zstd)?$/.exec(name);
        return match ? {name, version:Number(match[1] || 0)} : null;
      }).filter(Boolean).sort((a,b) => b.version-a.version);
      if (!generations.length) continue;
      const selected = generations[0];
      if (selected.version !== 4) { skipped++; continue; }
      const file = path.join(sessionPath, selected.name);
      if (!safeChild(root, file, false)) { skipped++; continue; }
      const stat = fs.statSync(file);
      if (stat.size > MAX_LOG) { skipped++; continue; }
      const id = crypto.createHash('sha256').update(project.name+'/'+session.name).digest('hex');
      items.push({id, file, updated:stat.mtimeMs/1000});
    }
    if (items.length >= 1000) { skipped++; break; }
  }
  return {items:items.sort((a,b) => b.updated-a.updated).slice(0,1000), skipped};
}
async function read(file, visitor, limit = MAX_LOG) {
  const source = fs.createReadStream(file);
  const stream = file.endsWith('.zstd') ? source.pipe(zlib.createZstdDecompress()) : source;
  if (source !== stream) source.on('error', error => stream.destroy(error));
  const decoder = new TextDecoder('utf-8', {fatal:true});
  let pending = '', size = 0, partial = false;
  try {
    for await (const chunk of stream) {
      size += chunk.length;
      if (size > limit) { partial = true; break; }
      pending += decoder.decode(chunk, {stream:true});
      let index;
      while ((index = pending.indexOf('\n')) >= 0) {
        const line = pending.slice(0,index); pending = pending.slice(index+1);
        if (line.length > MAX_LINE) throw Error('oversized record');
        if (line.trim()) visitor(JSON.parse(line));
      }
      if (pending.length > MAX_LINE) throw Error('oversized record');
    }
    if (pending.trim()) partial = true; // An append in progress never becomes a message.
  } catch (error) {
    if (error.code === 'Z_BUF_ERROR') partial = true;
    else throw error;
  } finally { stream.destroy(); source.destroy(); }
  return partial;
}
async function project(item, detail, before) {
  let header = null, title = '', fallback = '', status = 'unconfirmed';
  const messages = []; let hadMore = false, lastSeq = -1;
  const partial = await read(item.file, row => {
    if (!header) {
      if (row.type !== 'session' || row.version !== 4 || typeof row.id !== 'string') throw Error('unsupported header');
      header = row; return;
    }
    const data = row.data;
    if (!data || typeof data !== 'object') return;
    if (row.type === 'session/title') title = text(data.title).trim().slice(0,200);
    if (!detail && title) return;
    if (row.type === 'turn/start') status = 'unconfirmed';
    if (row.type === 'turn/end') status = data.reason?.kind === 'completed' ? 'completed' : 'interrupted';
    let content, role;
    if (row.type === 'user/message' && data.role === 'user') { content = data.content; role = 'user'; }
    else if (row.type === 'assistant/message' && data.message?.role === 'assistant') { content = data.message.content; role = 'assistant'; }
    else return;
    if (!Number.isSafeInteger(row.seq) || row.seq < 0) throw Error('invalid sequence');
    if (detail && row.seq <= lastSeq) throw Error('invalid order');
    lastSeq = row.seq;
    const body = publicText(content).trim();
    if (!body) return;
    if (role === 'user' && !fallback) fallback = body.replace(/\s+/g,' ').slice(0,80);
    if (!detail || (before !== null && row.seq >= before)) return;
    messages.push({id:row.seq,offset:row.seq,role,text:body.slice(0,12000),truncated:body.length>12000,time:row.time || ''});
    if (messages.length > 30) { messages.shift(); hadMore = true; }
  }, detail ? MAX_LOG : 512*1024);
  if (!header) throw Error('missing header');
  const base = {id:item.id,session_id:header.id,title:title || fallback || '未命名 DeepSeek 会话',updated:item.updated,provider:'deepseek-harness',status:'unconfirmed'};
  if (!detail) return base;
  if (partial) status = 'unconfirmed';
  const hint = partial ? '只读取到完整记录前缀；最新一轮状态待确认。' : status === 'completed' ? '本机日志记录本轮已结束。' : status === 'interrupted' ? '本机日志记录本轮已中断。' : '本机历史为只读，当前执行状态待确认。';
  return {...base,status,status_hint:hint,messages,next_before:hadMore ? messages[0].id : null,scan_limited:partial,observed_at:Date.now()/1000};
}
async function resolve(item) {
 let header=null,preset,selection=null,pending=null,last=null,status='unknown',title='DeepSeek会话';
 const partial=await read(item.file,row=>{
  if(!header){if(row.type!=='session'||row.version!==4)throw Error('invalid header');header=row;preset=row.agentPreset;return;}
  if(row.type==='session/title')title=text(row.data?.title).slice(0,200)||title;
  if(row.type==='agent-preset/selected')preset=row.data?.agentPreset;
  if(row.type==='model/selection'){const c=row.data;pending=c?{provider:c.provider,model:c.model,...(c.reasoningEffort===undefined?{}:{reasoningEffort:String(c.reasoningEffort)})}:null;}
  if(row.type==='request/header'){
   const c=row.data?.header?.config;
   if(c){last={provider:c.provider,model:c.model,...(c.reasoningEffort===undefined?{}:{reasoningEffort:String(c.reasoningEffort)})};if(pending&&pending.provider===last.provider&&pending.model===last.model&&pending.reasoningEffort===last.reasoningEffort)pending=null;}
  }
  if(row.type==='turn/start')status='running';if(row.type==='turn/end')status='ended';
 });
 selection=pending||last;
 let reason=partial?'记录不完整，暂时只读':preset!==undefined?'此会话使用特殊Agent预设，暂时只读':header.origin==='subagent'||header.parentSession!==undefined?'分支或子Agent会话暂时只读':typeof header.cwd!=='string'||!path.isAbsolute(header.cwd)||!fs.existsSync(header.cwd)||!fs.statSync(header.cwd).isDirectory()?'原工作目录不可用，暂时只读':!selection||typeof selection.provider!=='string'||typeof selection.model!=='string'||(selection.reasoningEffort!==undefined&&(typeof selection.reasoningEffort!=='string'||!selection.reasoningEffort||selection.reasoningEffort.length>100))?'无法完整恢复原模型设置，暂时只读':'';
 if(typeof header.id!=='string'||!/^session-[a-zA-Z0-9_-]{1,150}$/.test(header.id)||path.basename(path.dirname(item.file))!==header.id)reason='原会话标识不可用，暂时只读';
 return {allowed:!reason,reason,title,id:item.id,native_id:header.id,cwd:header.cwd,model:selection,status};
}
async function main() {
  const [mode,root,id,beforeArg] = process.argv.slice(2);
  const scan = files(root);
  if (mode === 'list') {
    const sessions = [];
    for (const item of scan.items) {
      try { sessions.push(await project(item,false,null)); } catch { scan.skipped++; }
    }
    return {sessions,warning:scan.skipped ? '部分本机会话格式不支持或暂时无法读取，已跳过。' : ''};
  }
  if (!['history','resolve'].includes(mode) || !/^[a-f0-9]{64}$/.test(id || '')) throw Error('invalid target');
  const item = scan.items.find(item => item.id === id);
  if (!item) return {missing:true};
  if(mode==='resolve')return resolve(item);
  return project(item,true,beforeArg === '' ? null : Number(beforeArg));
}
main().then(value => process.stdout.write(JSON.stringify(value))).catch(() => {
  process.stderr.write('Native history unavailable'); process.exitCode = 1;
});
