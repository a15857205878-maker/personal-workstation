/* Unified conversation workspace for app/mobile_bot.html.
 * All server data is rendered with textContent; no HTML strings are injected.
 */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const token = new URLSearchParams(location.search).get('token') || '';
  const simpleSingle=parent!==window&&new URLSearchParams(location.search).get('desktop_embed')==='1'&&new URLSearchParams(location.search).get('single_simple')==='1';
  const api = (path) => path + (path.indexOf('?') >= 0 ? '&' : '?') + 'token=' + encodeURIComponent(token);
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  };
  const clear = (node) => {
    if (!node) return;
    while (node.firstChild) node.removeChild(node.firstChild);
  };
  const disclosureKey = (details) => {
    const owner = details.closest('.job, .msg');
    if (!owner) return null;
    const identity = owner.classList.contains('job') ? 'job:' + owner.dataset.jobId
      : owner.dataset.taskId ? 'task:' + owner.dataset.taskId
      : owner.dataset.messageId ? 'message:' + owner.dataset.messageId
      : owner.dataset.targetKey ? 'goal:' + owner.dataset.targetKey : null;
    if (!identity) return null;
    const label = details.className || String((details.querySelector('summary') || {}).textContent || '').replace(/[（(]\d+[）)]/g, '');
    return identity + '|' + label;
  };
  const rememberDisclosures = (box) => {
    const values = new Map();
    if (box.dataset.disclosureScope !== String((state.target || {}).key || '')) return values;
    for (const details of box.querySelectorAll('details')) {
      const key = disclosureKey(details);
      if (key) values.set(key, details.open);
    }
    return values;
  };
  const restoreDisclosures = (box, values) => {
    for (const details of box.querySelectorAll('details')) {
      const key = disclosureKey(details);
      if (values.has(key)) details.open = values.get(key);
    }
    box.dataset.disclosureScope = String((state.target || {}).key || '');
  };
  const isMobile = () => window.matchMedia('(max-width: 760px)').matches;
  const normalise = (value) => String(value === undefined || value === null ? '' : value).replace(/\r\n/g, '\n');
  const errText = (error) => (error && error.message) ? error.message : '未知错误';
  const MAX_FILE = 100 * 1024 * 1024;
  const MAX_FILES = 10;
  const PDF_PREVIEW_EXTS = new Set([
    'pdf', 'png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif', 'tif', 'tiff',
    'docx', 'pptx', 'xlsx', 'odt', 'odp', 'ods', 'txt', 'md', 'csv',
    'json', 'py', 'js', 'log'
  ]);
  const SOURCE_KEY = 'sessionBot.sourceId.v1';
  const FLASH_AGENT = 'deepseek-flash';
  const FLASH_NAME = 'DeepSeek Flash';
  const DEEPSEEK_PROVIDER = 'deepseek-harness';
  const DEEPSEEK_NAME = 'DeepSeek';
  const DEEPSEEK_REPLY_HINT = '本机Harness历史目前只读；需要执行请新建Flash任务。';
  const PARTITIONS = {
    codex: { id: 'codex', label: 'Codex', agent: 'codex' },
    deepseek: { id: 'deepseek', label: 'DeepSeek', agent: FLASH_AGENT }
  };
  const FLASH_REPLY_HINT = 'Flash首版为独立任务通道；后续请新建Flash任务。';
  const FLASH_IMAGE_NOTE = '图片理解依赖本机Harness读取，首版待实测。';
  const MENU_OPEN_CODEX_NOTE = '电脑端确认后打开；后台执行或占用时暂不打开。同一时间只处理一个请求，退出电脑端 Codex 后释放占用。';
  const MENU_OPEN_FLASH_NOTE = 'Flash 任务在本工作台查看，不支持在电脑 Codex 中打开；后续请新建 Flash 任务。';
  const MENU_OPEN_DEEPSEEK_NOTE = '本机 Harness 历史目前只读，不支持在电脑 Codex 中打开，也不能从本页继续发送。';
  const NEW_HINT_TEXT = '写下目标，可附图片或文件；发送后开始新会话。';
  const NEW_HINT_TIP = 'PNG / JPEG / WebP · 最多 10 个附件，每个 ≤100 MB · 只读审查需附件。';
  const NEW_HINT_FLASH_TEXT = '写下 Flash 任务目标，可附图片或文件；首版为独立任务，不支持在此续聊。';
  const NEW_HINT_FLASH_TIP = 'PNG / JPEG / WebP · 最多 10 个附件，每个 ≤100 MB；' + FLASH_IMAGE_NOTE;
  const CODE_REFERENCE_PREFIX = 'workbench.codeReference.v1.';
  const CODE_REFERENCE_TTL = 10 * 60 * 1000;
  const CODE_REFERENCE_HEX = /^[a-f0-9]{32}$/i;
  const CODE_REFERENCE_DEFAULT_INSTRUCTION = '请解释这段代码，并指出需要注意的问题。';

  function uid() {
    try {
      if (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') {
        return globalThis.crypto.randomUUID();
      }
    } catch (error) { /* fall through */ }
    return 'req-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
  }

  function loadSourceId() {
    const fallback = 'web-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
    try {
      const stored = localStorage.getItem(SOURCE_KEY);
      if (stored) return stored;
      localStorage.setItem(SOURCE_KEY, fallback);
      return fallback;
    } catch (error) {
      return fallback;
    }
  }
  const sourceId = loadSourceId();

  function normalizeAgent(value) {
    return String(value || '') === FLASH_AGENT ? FLASH_AGENT : 'codex';
  }

  function hashText(text) {
    let hash = 5381;
    const value = String(text || '');
    for (let i = 0; i < value.length; i += 1) hash = ((hash * 33) ^ value.charCodeAt(i)) | 0;
    return (hash >>> 0).toString(36);
  }
  function stableStringify(value) {
    if (value === null || value === undefined) return String(value);
    if (Array.isArray(value)) return '[' + value.map(stableStringify).join(',') + ']';
    if (typeof value === 'object') {
      return '{' + Object.keys(value).sort().map((key) => JSON.stringify(key) + ':' + stableStringify(value[key])).join(',') + '}';
    }
    return JSON.stringify(value);
  }

  function parseStamp(value) {
    if (value === null || value === undefined || value === '') return null;
    if (typeof value === 'number' && isFinite(value)) {
      return new Date(value < 1e12 ? value * 1000 : value);
    }
    const text = String(value).trim();
    if (!text) return null;
    if (/^\d+(\.\d+)?$/.test(text)) {
      const number = Number(text);
      return new Date(number < 1e12 ? number * 1000 : number);
    }
    const date = new Date(text);
    return isNaN(date.getTime()) ? null : date;
  }
  function stampText(value) {
    const date = parseStamp(value);
    if (!date) return value === null || value === undefined ? '' : String(value).slice(0, 40);
    return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  }
  function sizeText(value) {
    const number = Number(value) || 0;
    if (number >= 1024 * 1024) return (number / (1024 * 1024)).toFixed(1) + ' MB';
    if (number >= 1024) return Math.ceil(number / 1024) + ' KB';
    return number + ' B';
  }

  const TASK_LABELS = {
    waiting: '等待发送',
    sending: '正在续接',
    unknown: '状态待确认',
    queued: '已入队 · 排队中',
    pending: '已入队',
    running: '执行中',
    active: '进行中',
    idle: '空闲',
    completed: '已完成',
    needs_attention: '需要处理',
    failed: '执行失败',
    cancelled: '已停止',
    interrupted: '本轮已中断',
    unconfirmed: '状态待确认'
  };
  const JOB_LABELS = {
    queued: '待发送',
    waiting: '等待当前轮结束',
    sending: '正在续接原会话',
    completed: '回复完成',
    needs_attention: '需要处理',
    failed: '发送失败',
    cancelled: '已取消'
  };
  const DESKTOP_OPEN_TERMINAL = ['opened', 'background', 'blocked', 'expired', 'failed', 'cancelled'];
  const DESKTOP_OPEN_FALLBACK = {
    pending: '电脑确认中…',
    blocked: '电脑端正忙，暂时不能打开。',
    opened: '已向电脑发出打开请求。',
    background: '已取消打开。',
    expired: '等待电脑确认超时，可重新尝试。',
    failed: '打开未完成，可重新尝试。',
    cancelled: '打开已取消。'
  };
  const isDesktopOpenTerminal = (status) => DESKTOP_OPEN_TERMINAL.indexOf(String(status || '')) >= 0;
  const DIAGNOSTICS_LABELS = { ok: '正常', warn: '注意', unknown: '未知', info: '信息' };
  const DIAGNOSTICS_TONES = { ok: 'ok', warn: 'warn', unknown: 'muted', info: 'info' };
  const DIAGNOSTICS_FAILURE_SUMMARY = '本次自检未完成，没有读取到电脑状态。\n请确认电脑已开机、接收窗口仍在运行；手机和电脑的 Tailscale 均已连接，当前主屏幕使用 100.x 入口；也可改用同一 Wi-Fi 的局域网链接。\n切换网络后稍候再检查；若提示授权失效，请从电脑重新配对。';
  const USAGE_UNAVAILABLE_TEXT = '电脑端当前未读取到 Codex 额度（未登录、暂不支持或暂时不可用）。这不代表额度已经用完，请确认电脑端 Codex 登录后刷新。';
  const USAGE_FAILURE_TEXT = '本次未能读取 Codex 额度。请确认电脑在线、手机与电脑保持连接，并确认电脑端 Codex 已登录后刷新。';
  const USAGE_AUTH_TEXT = '授权已失效，未能读取 Codex 额度。请从电脑重新配对并打开新链接，不要只当作网络离线。';
  const USAGE_INCOMPLETE_TEXT = '电脑返回的额度内容不完整，本次结果未采用，请稍后刷新。';
  const BALANCE_UNAVAILABLE_TEXT = '电脑端当前未读取到 DeepSeek 余额（未配置、暂不支持或暂时不可用）。这不代表余额不足，请确认电脑端已配置官方 API Key 后刷新。';
  const BALANCE_FAILURE_TEXT = '本次未能读取 DeepSeek 余额，当前不可用。请确认电脑在线、手机与电脑保持连接后刷新。';
  const BALANCE_AUTH_TEXT = '授权已失效，未能读取 DeepSeek 余额，当前不可用。请从电脑重新配对并打开新链接，不要只当作网络离线。';
  const BALANCE_INCOMPLETE_TEXT = '电脑返回的 DeepSeek 余额内容不完整，本次结果未采用，请稍后刷新。';
  const BALANCE_LOW_TEXT = '当前 DeepSeek 账户余额不足，模型调用不可用。';
  const labelFor = (map, status) => map[String(status || '')] || (status ? String(status) : '状态未知');
  function toneFor(status) {
    const key = String(status || '');
    if (key === 'running' || key === 'sending' || key === 'completed') return 'ok';
    if (key === 'queued' || key === 'waiting' || key === 'needs_attention') return 'warn';
    if (key === 'failed') return 'bad';
    return 'muted';
  }
  function dotClass(status) {
    const tone = toneFor(status);
    if (tone === 'ok') return 'done';
    if (tone === 'warn') return 'waiting';
    if (tone === 'bad') return 'bad';
    return '';
  }
  function isFlashTask(task) {
    return !!task && task.agent === FLASH_AGENT;
  }
  function partitionOfTask(task) {
    if (!task) return '';
    if (task.agent === FLASH_AGENT) return 'deepseek';
    if (task.agent === 'codex' || task.agent === 'codex-deepseek-code') return 'codex';
    return '';
  }
  function defaultAgentForPartition(partition) {
    return partition === 'deepseek' ? FLASH_AGENT : 'codex';
  }
  function isDeepSeekNative() {
    return !!state.target && state.target.kind === 'deepseek';
  }
  function isFlashConversation() {
    const target = state.target;
    if (!target) return false;
    if (target.kind === 'deepseek') return false;
    if (target.partition === 'deepseek' || target.agent === FLASH_AGENT) return true;
    const conversation = state.conversation;
    if (!conversation) return false;
    if (conversation.provider === FLASH_AGENT) return true;
    return isFlashTask(conversation.task);
  }
  function isDeepSeekConversation() {
    const target = state.target;
    if (!target) return false;
    if (target.partition === 'deepseek' || target.kind === 'deepseek') return true;
    const conversation = state.conversation;
    return !!(conversation && (conversation.provider === FLASH_AGENT || conversation.provider === DEEPSEEK_PROVIDER || isFlashTask(conversation.task)));
  }
  function agentName(id) {
    if(id==='codex-deepseek-code')return '代码协作 · Codex后端 / DeepSeek前端';
    const key = normalizeAgent(id);
    return state.agentNames[key] || (key === FLASH_AGENT ? FLASH_NAME : 'Codex');
  }
  function replyAgentName() {
    const target = state.target;
    if (target && target.kind === 'deepseek') return DEEPSEEK_NAME;
    if (isFlashConversation()) return agentName(FLASH_AGENT);
    const conversation = state.conversation;
    if (conversation) {
      if (conversation.provider === FLASH_AGENT) return agentName(FLASH_AGENT);
      if (conversation.task && conversation.task.agent) return taskAgentName(conversation.task);
      if (conversation.provider === 'codex') return agentName('codex');
    }
    if (target && target.agent) return agentName(target.agent);
    return agentName('codex');
  }
  function taskAgentName(task) {
    if(task?.agent==='codex-deepseek-code'&&task.code_route==='static')return '代码协作 · DeepSeek前端 / Codex验收';
    return isFlashTask(task) ? agentName(FLASH_AGENT) : agentName(task && task.agent ? task.agent : 'codex');
  }
  function agentAvailable(id) {
    const key = normalizeAgent(id);
    if (key === FLASH_AGENT) return state.agentsAvailable[FLASH_AGENT] === true;
    return state.agentsAvailable.codex !== false;
  }

  function newListView(id) {
    return {
      id: id,
      query: '',
      sessions: [],
      list: [],
      nextOffset: null,
      loaded: false,
      busy: false,
      revision: 0,
      sig: '',
      lastActiveKey: '',
      statusText: '',
      statusTone: '',
      warning: ''
    };
  }

  const state = {
    partition: 'codex',
    target: null,
    conversation: null,
    connected: null,
    authError: false,
    lastOfflineDetail: '',
    canReply: false,
    codexAvailable: null,
    selectedAgent: 'codex',
    agentsAvailable: { codex: null, 'deepseek-flash': null },
    agentNames: { codex: 'Codex', 'deepseek-flash': FLASH_NAME },
    tasks: [],
    tasksRevision: 0,
    views: { codex: newListView('codex'), deepseek: newListView('deepseek') },
    listDomPartition: '',
    searchPartition: '',
    viewRevision: 0,
    readBusy: false,
    pollBusy: false,
    pollQueued: false,
    probeBusy: false,
    loading: false,
    messages: new Map(),
    nextBefore: null,
    lastEmptyCursor: null,
    messagesDomSig: null,
    historySig: '',
    historyObserved: null,
    historyHint: '',
    historyScanLimited: false,
    historyError: '',
    assistantTexts: [],
    resultTokens: new Set(),
    progressSig: '',
    jobsSig: '',
    jobs: [],
    cancelling: new Set(),
    cancellingTask: '',
    taskCancelError: '',
    phase: 'idle',
    files: [],
    filesSig: '',
    fileDrafts: new Map(),
    drafts: new Map(),
    pendingRequests: new Map(),
    codeReference: null,
    scrollPending: false,
    desktopOpen: {
      posting: false,
      polling: false,
      unresolved: false,
      pollError: false,
      requestId: '',
      status: '',
      message: '',
      threadId: '',
      title: '',
      deadline: 0,
      timer: null,
      expiryTimer: null
    },
    diagnostics: {
      busy: false,
      revision: 0,
      wantRun: false,
      summary: ''
    },
    usage: {
      provider: 'codex',
      busy: false,
      revision: 0,
      wantRun: false
    },
    balance: {
      busy: false,
      revision: 0,
      wantRun: false
    }
  };

  /* ---------- transport ---------- */

  function markOnline() {
    if (state.connected === true && !state.authError) return;
    state.connected = true;
    state.authError = false;
    state.lastOfflineDetail = '';
    updateConnectionUI();
  }
  function markOffline(detail) {
    state.connected = false;
    state.lastOfflineDetail = detail || '';
    updateConnectionUI();
  }
  function updateConnectionUI() {
    const banner = $('connectionBanner');
    if (!banner) return;
    let text = '';
    if (state.authError) {
      text = '链接已失效，请从电脑重新打开二维码链接。';
    } else if (state.connected === false) {
      text = '连接中断，显示上次内容；发送已暂停，恢复后会自动刷新。';
      if (state.lastOfflineDetail) text += ' ' + state.lastOfflineDetail;
    }
    banner.hidden = !text;
    banner.textContent = text;
    renderHeader();
    renderEmpty();
    updateComposer();
    updateOpenCodexButton();
  }

  async function fetchText(url, options, timeoutMs, label, isSubmit) {
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      try { controller.abort(); } catch (error) { /* ignore */ }
    }, timeoutMs);
    try {
      let response;
      try {
        response = await fetch(url, Object.assign({}, options || {}, { signal: controller.signal }));
      } catch (error) {
        markOffline(timedOut ? (label + '超时。') : '请检查 Wi-Fi 和电脑是否保持运行。');
        const failure = new Error(timedOut
          ? label + '超时，' + (isSubmit ? '未确认送达，请检查后手动重试' : '请检查网络后重试')
          : label + '中断，请检查 Wi-Fi 和电脑是否保持运行');
        failure.network = true;
        throw failure;
      }
      let raw;
      try {
        raw = await response.text();
      } catch (error) {
        markOffline(timedOut ? (label + '超时。') : '读取电脑响应时连接中断。');
        const failure = new Error(timedOut
          ? label + '超时，' + (isSubmit ? '未确认送达，请检查后手动重试' : '请检查网络后重试')
          : label + '中断，电脑响应未读取完整' + (isSubmit ? '，未确认送达，请检查后手动重试' : '，请检查网络后重试'));
        failure.network = true;
        throw failure;
      }
      return { response: response, raw: raw };
    } finally {
      clearTimeout(timer);
    }
  }

  async function request(path, options) {
    const method = String((options && options.method) || 'GET').toUpperCase();
    const isSubmit = method !== 'GET' && method !== 'HEAD';
    const result = await fetchText(
      api(path),
      Object.assign({ headers: { Accept: 'application/json' } }, options || {}),
      20000,
      isSubmit ? '提交' : '请求',
      isSubmit
    );
    const response = result.response;
    const raw = result.raw;
    let data = null;
    if (raw) {
      try { data = JSON.parse(raw); } catch (error) {
        if (response.ok) throw new Error('电脑返回了无效响应（HTTP ' + response.status + '）');
      }
    }
    if (response.status === 401 || response.status === 403) {
      state.authError = true;
      state.connected = false;
      updateConnectionUI();
      throw new Error((data && data.error) || '访问令牌无效，请从电脑重新打开链接。');
    }
    markOnline();
    if (!response.ok) {
      throw new Error((data && data.error) || ('请求失败（HTTP ' + response.status + '）'));
    }
    return data;
  }
  const postJson = (value) => ({
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(value)
  });

  async function uploadFile(item) {
    const result = await fetchText(
      api('/api/task-upload?name=' + encodeURIComponent(item.name)),
      { method: 'POST', headers: { Accept: 'application/json' }, body: item.file },
      120000,
      '附件上传',
      true
    );
    const response = result.response;
    const raw = result.raw;
    let data = null;
    if (raw) {
      try { data = JSON.parse(raw); } catch (error) { data = null; }
    }
    if (response.status === 401 || response.status === 403) {
      state.authError = true;
      state.connected = false;
      updateConnectionUI();
      throw new Error((data && data.error) || '访问令牌无效，请从电脑重新打开链接。');
    }
    markOnline();
    if (!response.ok) throw new Error((data && data.error) || ('上传失败（HTTP ' + response.status + '）'));
    if (!data || !data.name) throw new Error('上传返回格式不正确');
    return data;
  }

  /* ---------- text helpers ---------- */

  function workbenchGoal(text) {
    const value = normalise(text);
    if (!value.startsWith('这是用户从个人任务工作台提交的独立任务。')) return null;
    const marker = '\n\n任务目标：\n';
    const start = value.indexOf(marker);
    const end = value.indexOf('\n\n最终结果请按指定 JSON schema 返回。', start);
    return start >= 0 && end > start ? value.slice(start + marker.length, end) : null;
  }
  function cleanTitle(value) {
    const raw = workbenchGoal(value) || String(value === undefined || value === null ? '' : value);
    const first = raw.split('\n').map((line) => line.trim()).find(Boolean) || '';
    const cleaned = first.replace(/^#+\s*/, '').replace(/\s+/g, ' ').trim();
    if (!cleaned) return '未命名会话';
    return cleaned.length > 84 ? cleaned.slice(0, 84) + '…' : cleaned;
  }
  function displayText(message) {
    const text = normalise(message && message.text);
    if (message && message.role === 'user') return workbenchGoal(text) || text;
    if (message && message.role === 'assistant') {
      const value = text.trim();
      if (value.startsWith('{')) {
        try {
          const result = JSON.parse(value);
          if (result && ['completed', 'needs_attention'].indexOf(result.status) >= 0 && typeof result.summary === 'string') {
            let output = result.summary;
            if (Array.isArray(result.completed_parts)) {
              const parts = result.completed_parts
                .filter((part) => part && typeof part.title === 'string' && typeof part.detail === 'string')
                .map((part) => part.title + '\n' + part.detail);
              if (parts.length) output += '\n\n' + parts.join('\n\n');
            }
            return output;
          }
        } catch (error) { /* keep raw text */ }
      }
    }
    return text;
  }
  function formatResult(value) {
    if (value === null || value === undefined) return '';
    if (typeof value === 'string') {
      const text = value.trim();
      if (text.startsWith('{')) {
        try {
          const parsed = JSON.parse(text);
          if (parsed && typeof parsed.summary === 'string') return parsed.summary;
        } catch (error) { /* keep raw */ }
      }
      return value;
    }
    if (typeof value === 'object') {
      if (typeof value.summary === 'string') return value.summary;
      try { return JSON.stringify(value, null, 2); } catch (error) { return String(value); }
    }
    return String(value);
  }

  function setLine(id, text, tone) {
    const node = $(id);
    if (!node) return;
    node.textContent = text || '';
    node.hidden = !text;
    node.classList.remove('error', 'warn', 'ok');
    if (tone) node.classList.add(tone);
  }

  function createSessionRecovery(storage, key, newId) {
    const drafts=new Map(),pending=new Map();let valid=true;
    try {
      const raw=storage.getItem(key);
      if(raw){
        const saved=JSON.parse(raw);
        if(saved.version!==1||!Array.isArray(saved.drafts)||!Array.isArray(saved.pending)||saved.drafts.length>40||saved.pending.length>40)throw Error('invalid state');
        for(const row of saved.drafts){if(!Array.isArray(row)||row.length!==2||typeof row[0]!=='string'||row[0].length>240||typeof row[1]!=='string'||row[1].length>20000)throw Error('invalid draft');drafts.set(row[0],row[1]);}
        for(const row of saved.pending){if(!Array.isArray(row)||row.length!==2||typeof row[0]!=='string'||row[0].length>41000||typeof row[1]!=='string'||row[1].length>100)throw Error('invalid receipt');pending.set(row[0],row[1]);}
      }
    }catch(error){valid=false;drafts.clear();pending.clear();}
    function persist(){if(!valid)return false;try{storage.setItem(key,JSON.stringify({version:1,drafts:[...drafts],pending:[...pending]}));return true;}catch(error){return false;}}
    function remember(target,text){
      if(typeof target!=='string'||target.length>240||typeof text!=='string'||text.length>20000)return false;
      if(text){if(!drafts.has(target)&&drafts.size>=40)return false;drafts.set(target,text);}else drafts.delete(target);
      return persist();
    }
    function signature(target,text){return JSON.stringify([target,text]);}
    return {
      remember,
      draft(target){return drafts.get(target)||'';},
      prepare(target,text){
        const sig=signature(target,text);
        if(!pending.has(sig)&&pending.size>=40)throw Error('有太多未确认回执，请先核对已有会话。');
        if(!remember(target,text))throw Error('无法保存会话草稿和操作编号，请检查浏览器本地存储；尚未发送。');
        if(!pending.has(sig))pending.set(sig,newId());
        if(!persist())throw Error('无法保存操作编号，尚未发送，请检查浏览器存储。');
        return pending.get(sig);
      },
      confirm(target,text,id){
        const sig=signature(target,text);if(pending.get(sig)!==id)return false;
        pending.delete(sig);if(drafts.get(target)===text)drafts.delete(target);return persist();
      }
    };
  }
  // end session recovery
  let recoveryStorage;try{recoveryStorage=localStorage;}catch(error){recoveryStorage={getItem(){throw error;},setItem(){throw error;}};}
  const sessionRecovery=createSessionRecovery(recoveryStorage,'sessionBot.recovery.v1.'+hashText(token)+'.'+hashText([...token].reverse().join(''))+'.'+hashText(sourceId),uid);

  /* ---------- drafts / attachments ---------- */

  function saveDraft() {
    if (!state.target) return;
    state.drafts.set(state.target.key, $('composerInput').value);
    sessionRecovery.remember(state.target.key,$('composerInput').value);
    state.fileDrafts.set(state.target.key, state.files);
  }
  function setTargetFiles(files) {
    state.files = files;
    if (state.target) state.fileDrafts.set(state.target.key, files);
    state.filesSig = '';
  }
  function restoreDraft() {
    const key = state.target ? state.target.key : '';
    $('composerInput').value = key ? (state.drafts.has(key)?state.drafts.get(key):sessionRecovery.draft(key)) : '';
    autoGrow();
  }
  function autoGrow() {
    const input = $('composerInput');
    if(simpleSingle&&document.documentElement.dataset.singleManualInput==='true')return;
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 160) + 'px';
  }

  const supportedImage = (file) =>
    /\.(png|jpe?g|webp)$/i.test(file.name) || /^image\/(png|jpeg|webp)$/i.test(file.type || '');
  const looksImage = (file) =>
    /^image\//i.test(file.type || '') || /\.(png|jpe?g|webp|heic|heif|gif|bmp|tiff?|avif|svg)$/i.test(file.name);

  function renderAttachments() {
    const tray = $('attachmentTray');
    if (!tray) return;
    const readOnlyDeepSeek = !!state.target && state.target.kind !== 'new' && state.target.partition === 'deepseek';
    const show = !!state.target && !readOnlyDeepSeek;
    const sig = JSON.stringify([state.target ? state.target.key : '', state.files.map((item) => [item.id, item.name, !!item.url]), state.phase]);
    if (sig === state.filesSig) {
      tray.hidden = !show || !state.files.length;
      return;
    }
    state.filesSig = sig;
    clear(tray);
    tray.hidden = !show || !state.files.length;
    if (tray.hidden) return;
    for (const item of state.files) {
      const card = el('div', 'file-card');
      if (item.url) {
        const image = el('img');
        image.src = item.url;
        image.alt = item.name;
        image.loading = 'lazy';
        card.append(image);
      } else {
        const ext = (item.name.split('.').pop() || 'FILE').toUpperCase().slice(0, 4);
        card.append(el('div', 'file-ext', ext));
      }
      card.append(el('div', 'file-name', item.name));
      card.append(el('div', 'file-size', sizeText(item.size)));
      const selected=el('span','partner-attachment-status','已选中 · 发送时交接');selected.dataset.state='done';card.append(selected);
      const remove = el('button', 'file-remove', '×');
      remove.type = 'button';
      remove.setAttribute('aria-label', '移除 ' + item.name);
      remove.disabled = state.phase !== 'idle';
      remove.onclick = () => {
        if (state.phase !== 'idle') return;
        if (item.url) URL.revokeObjectURL(item.url);
        setTargetFiles(state.files.filter((entry) => entry !== item));
        renderAttachments();
        updateComposer();
      };
      card.append(remove);
      tray.append(card);
    }
  }

  function addFiles(fileList) {
    if (!state.target || state.phase !== 'idle') return;
    const isNew = state.target.kind === 'new';
    const incoming = Array.from(fileList || []);
    if (!incoming.length) return;
    const errors = [];
    for (const file of incoming) {
      if (state.files.length >= MAX_FILES) { errors.push('最多添加 ' + MAX_FILES + ' 个附件'); break; }
      if (!file.size) { errors.push('文件为空：' + file.name); continue; }
      if (file.size > MAX_FILE) { errors.push('超过 100 MB：' + file.name); continue; }
      if (!isNew && !supportedImage(file)) {
        errors.push('历史会话续接仅支持 PNG / JPEG / WebP 图片：' + file.name);
        continue;
      }
      if (isNew && looksImage(file) && !supportedImage(file)) {
        errors.push('图片仅支持 PNG / JPEG / WebP，请先转换：' + file.name);
        continue;
      }
      state.files.push({
        id: uid(),
        file: file,
        name: file.name,
        size: file.size,
        uploaded: null,
        url: supportedImage(file) ? URL.createObjectURL(file) : null
      });
    }
    setTargetFiles(state.files);
    renderAttachments();
    updateComposer();
    if (errors.length) setLine('composerStatus', errors.slice(0, 3).join('；'), 'error');
  }

  /* ---------- connection / list ---------- */

  function mergeSessions(current, incoming) {
    const map = new Map(current.map((item) => [String(item.id), item]));
    for (const item of incoming) {
      if (item && item.id !== undefined) map.set(String(item.id), item);
    }
    return Array.from(map.values());
  }
  function normalizeTasks(value) {
    const list = Array.isArray(value) ? value : (value && Array.isArray(value.tasks) ? value.tasks : []);
    return list.filter((task) => task && task.id !== undefined && task.id !== null);
  }

  async function loadAgents() {
    try {
      const value = await request('/api/agents');
      const list = Array.isArray(value) ? value : (value && Array.isArray(value.agents) ? value.agents : []);
      const codex = list.find((item) => item && item.id === 'codex');
      const flash = list.find((item) => item && item.id === FLASH_AGENT);
      state.agentsAvailable.codex = codex ? codex.available === true : null;
      state.agentsAvailable[FLASH_AGENT] = flash ? flash.available === true : false;
      state.codexAvailable = state.agentsAvailable.codex;
      state.agentNames.codex = codex && codex.name ? String(codex.name) : 'Codex';
      state.agentNames[FLASH_AGENT] = flash && flash.name ? String(flash.name) : FLASH_NAME;
    } catch (error) {
      state.agentsAvailable.codex = null;
      state.agentsAvailable[FLASH_AGENT] = false;
      state.codexAvailable = null;
    }
    updateComposer();
    renderHeader();
    renderEmpty();
  }

  function viewFor(partition) {
    return state.views[partition] || null;
  }
  function activeView() {
    return state.views[state.partition] || state.views.codex;
  }
  function setViewStatus(view, text, tone) {
    if (!view) return;
    view.statusText = text || '';
    view.statusTone = tone || '';
    if (state.partition === view.id) setLine('listStatus', view.statusText, view.statusTone);
  }

  async function loadList(partition, reset) {
    const view = viewFor(partition);
    if (!view) return;
    if (state.phase !== 'idle') return;
    if (!reset && (view.busy || view.nextOffset === null)) return;
    const revision = ++view.revision;
    const query = view.query;
    const offset = reset ? 0 : (view.nextOffset || 0);
    view.busy = true;
    if (state.partition === partition) {
      updateInteraction();
      setLine('listStatus', partition === 'deepseek' ? '正在读取 DeepSeek 历史…' : '正在读取 Codex 会话列表…');
    }
    try {
      const path = partition === 'deepseek'
        ? '/api/bot/deepseek/sessions?q=' + encodeURIComponent(query) + '&offset=' + encodeURIComponent(offset)
        : '/api/bot/history/sessions?q=' + encodeURIComponent(query) + '&offset=' + encodeURIComponent(offset);
      const sessionsPromise = request(path);
      const tasksRevision = reset ? (state.tasksRevision += 1) : 0;
      const tasksPromise = reset ? request('/api/bot/tasks') : Promise.resolve(null);
      const results = await Promise.allSettled([sessionsPromise, tasksPromise]);
      if (revision !== view.revision) return;
      const sessionsResult = results[0];
      const tasksResult = results[1];
      if (sessionsResult.status === 'fulfilled') {
        const page = sessionsResult.value || {};
        const sessions = Array.isArray(page.sessions) ? page.sessions : [];
        view.sessions = reset ? sessions : mergeSessions(view.sessions, sessions);
        const next = page.next_offset;
        view.nextOffset = (next === undefined || next === null) ? null : next;
        view.warning = page.warning ? String(page.warning) : '';
        if (reset) view.loaded = true;
      }
      if (reset && tasksResult.status === 'fulfilled' && tasksResult.value !== null) {
        if (tasksRevision === state.tasksRevision) {
          state.tasks = normalizeTasks(tasksResult.value);
          rebuildList('codex');
          rebuildList('deepseek');
        }
      }
      const errors = [];
      if (sessionsResult.status === 'rejected') {
        errors.push((partition === 'deepseek' ? 'DeepSeek 历史' : 'Codex 会话列表') + '：' + errText(sessionsResult.reason));
      }
      if (reset && tasksResult.status === 'rejected') errors.push('任务：' + errText(tasksResult.reason));
      rebuildList(partition);
      if (errors.length) {
        setViewStatus(view, errors.join('；'), 'error');
      } else if (view.warning) {
        setViewStatus(view, view.warning, 'warn');
      } else {
        const noun = partition === 'deepseek' ? 'DeepSeek 记录' : 'Codex 会话';
        setViewStatus(view, query ? '找到 ' + view.list.length + ' 个' + noun : '已列出 ' + view.list.length + ' 个' + noun, '');
      }
    } catch (error) {
      if (revision !== view.revision) return;
      setViewStatus(view, (partition === 'deepseek' ? '读取 DeepSeek 历史失败：' : '读取 Codex 会话列表失败：') + errText(error), 'error');
    } finally {
      if (revision === view.revision) {
        view.busy = false;
        if (state.partition === partition) {
          updateInteraction();
          renderList();
          setLine('listStatus', view.statusText, view.statusTone);
        }
        publishHostHistory();
      }
    }
  }

  function rebuildList(partition) {
    const view = viewFor(partition);
    if (!view) return;
    const query = view.query.toLowerCase();
    const tasks = state.tasks.filter((task) => task && task.id !== undefined && partitionOfTask(task) === partition);
    const seenNative = new Map();
    for (const task of tasks) {
      const native = partition === 'codex'
        ? (task.remote_session ? String(task.remote_session) : '')
        : (task.provider_session ? String(task.provider_session) : '');
      if (!native) continue;
      const previous = seenNative.get(native);
      if (!previous || Number(task.updated || task.created || 0) > Number(previous.updated || previous.created || 0)) {
        seenNative.set(native, task);
      }
    }
    const items = [];
    const includedNative = new Set();
    for (const task of tasks) {
      const native = partition === 'codex'
        ? (task.remote_session ? String(task.remote_session) : '')
        : (task.provider_session ? String(task.provider_session) : '');
      if (native && seenNative.get(native) !== task) continue;
      const title = cleanTitle(task.title || task.goal || '');
      if (query && !title.toLowerCase().includes(query)) continue;
      items.push({
        kind: 'task',
        id: String(task.id),
        key: 'task:' + String(task.id),
        title: title,
        updated: Number(task.updated || task.created || 0),
        partition: partition,
        task: task
      });
      if (native) includedNative.add(native);
    }
    for (const session of view.sessions) {
      if (!session || session.id === undefined || session.id === null) continue;
      const id = String(session.id);
      if (partition === 'codex' && includedNative.has(id)) continue;
      if (partition === 'deepseek' && session.session_id !== undefined && session.session_id !== null && includedNative.has(String(session.session_id))) continue;
      const title = cleanTitle(session.title || '');
      if (query && !title.toLowerCase().includes(query)) continue;
      items.push({
        kind: partition === 'deepseek' ? 'deepseek' : 'thread',
        id: id,
        key: (partition === 'deepseek' ? 'deepseek:' : 'thread:') + id,
        title: title,
        updated: Number(session.updated || 0),
        partition: partition,
        session: session
      });
    }
    items.sort((left, right) => (right.updated || 0) - (left.updated || 0));
    view.list = items;
    view.sig = '';
    if (state.partition === partition) renderList();
  }
  function rebuildAllLists() {
    rebuildList('codex');
    rebuildList('deepseek');
  }

  function renderList() {
    const list = $('conversationList');
    if (!list) return;
    const view = activeView();
    const sig = JSON.stringify([
      state.partition,
      view.list.map((item) => [item.key, item.title, item.updated, item.kind, item.task ? item.task.status : '', item.task ? item.task.agent : '', item.kind === 'deepseek' && item.session ? (item.session.status || '') : '']),
      state.target ? state.target.key : '',
      view.nextOffset
    ]);
    if (state.listDomPartition !== state.partition) view.sig = '';
    if (sig === view.sig) { updateInteraction(); return; }
    const samePartitionDom = state.listDomPartition === state.partition;
    view.sig = sig;
    state.listDomPartition = state.partition;
    const previousTop = samePartitionDom ? list.scrollTop : 0;
    const activeChanged = view.lastActiveKey !== (state.target ? state.target.key : '');
    view.lastActiveKey = state.target ? state.target.key : '';
    clear(list);
    if (!view.list.length) {
      const empty = view.query
        ? '没有找到匹配的' + (state.partition === 'deepseek' ? ' DeepSeek 记录。' : ' Codex 会话。')
        : (state.partition === 'deepseek'
          ? 'DeepSeek 分区还没有记录，点“新会话”创建 Flash 任务。'
          : 'Codex 分区还没有会话，点“新会话”开始。');
      list.append(el('div', 'list-empty', empty));
    } else {
      for (const item of view.list) {
        const button = el('button', 'conv-item');
        button.type = 'button';
        button.dataset.targetKey = item.key;
        if (item.kind === 'task') button.dataset.taskId = item.id;
        else if (item.kind === 'deepseek') button.dataset.sessionId = item.id;
        else button.dataset.threadId = item.id;
        if (state.target && state.target.key === item.key) button.setAttribute('aria-current', 'true');
        const title = el('div', 'conv-title', item.title);
        const meta = el('div', 'conv-meta');
        const status = item.kind === 'task' ? item.task.status : (item.kind === 'deepseek' ? (item.session.status || 'unconfirmed') : '');
        const dot = el('span', 'conv-dot ' + dotClass(status));
        meta.append(dot);
        if (item.updated) meta.append(el('span', '', stampText(item.updated)));
        if (item.kind === 'task') {
          if (isFlashTask(item.task)) meta.append(el('span', 'conv-agent', FLASH_NAME));
          meta.append(el('span', '', labelFor(TASK_LABELS, item.task.status)));
        } else if (item.kind === 'deepseek') {
          meta.append(el('span', 'conv-agent', 'Harness 历史'));
          meta.append(el('span', '', labelFor(TASK_LABELS, status)));
        } else {
          meta.append(el('span', '', '历史会话'));
        }
        button.append(title, meta);
        button.onclick = () => selectItem(item);
        list.append(button);
      }
    }
    $('loadMore').hidden = view.nextOffset === null;
    list.scrollTop = previousTop;
    if (activeChanged) {
      const active = list.querySelector('[aria-current="true"]');
      if (active && typeof active.scrollIntoView === 'function') {
        active.scrollIntoView({ block: 'nearest' });
      }
    }
    updateInteraction();
  }

  function updateInteraction() {
    const busy = state.phase !== 'idle';
    const view = activeView();
    const newButton = $('newConversation');
    if (newButton) newButton.disabled = busy;
    const codexTab = $('partitionCodex');
    const deepseekTab = $('partitionDeepSeek');
    if (codexTab) codexTab.disabled = busy;
    if (deepseekTab) deepseekTab.disabled = busy;
    for (const id of ['sessionCodex','sessionDeepSeek','menuButton','singleModelChoice']) { const button=$(id);if(button)button.disabled=busy; }
    document.querySelectorAll('.conv-item').forEach((button) => { button.disabled = busy; });
    const more = $('loadMore');
    if (more) more.disabled = busy || view.busy;
    const older = $('loadOlder');
    if (older) older.disabled = busy || state.readBusy;
    publishHostHistory();
  }

  let historyHostOrigin = '';
  let historyHostSignature = '';

  function publishHostHistory(force = false) {
    if (!historyHostOrigin) return;
    const groups = Object.fromEntries(['codex', 'deepseek'].map(model => {
      const view = viewFor(model);
      return [model, {
        loading: view.busy,
        status: view.statusText,
        more: view.nextOffset !== null,
        rows: view.list.map(({key, title, updated}) => ({key, title, updated})),
      }];
    }));
    const data = {
      type: 'workstation-single-history',
      model: state.partition,
      busy: state.phase !== 'idle',
      active: state.target?.key || '',
      groups,
    };
    const signature = JSON.stringify(data);
    if (!force && signature === historyHostSignature) return;
    historyHostSignature = signature;
    parent.postMessage(data, historyHostOrigin);
  }

  function connectHistoryHost() {
    const query = new URLSearchParams(location.search);
    if (!simpleSingle || window === parent || query.get('desktop_embed') !== '1' || query.get('host_history') !== '1') return;
    window.addEventListener('message', event => {
      const command = event.data;
      if (event.source !== parent || !/^http:\/\/127\.0\.0\.1:\d{1,5}$/.test(event.origin) || command?.type !== 'workstation-single-history-action') return;
      if (command.action === 'connect') {
        historyHostOrigin = event.origin;
        document.documentElement.dataset.workstationHistoryHost = 'true';
        closeDrawer();
        publishHostHistory(true);
        for (const model of ['codex', 'deepseek']) {
          const view = viewFor(model);
          if (!view.loaded && !view.busy) loadList(model, true);
        }
        return;
      }
      if (historyHostOrigin !== event.origin || state.phase !== 'idle') return;
      if (command.action === 'new') newConversation();
      if (command.action === 'model' && ['codex','deepseek'].includes(command.value)) switchPartition(command.value);
      if (command.action === 'open' && ['codex','deepseek'].includes(command.value?.model) && typeof command.value.key === 'string') {
        const item = viewFor(command.value.model).list.find(entry => entry.key === command.value.key);
        if (item && item.key !== state.target?.key) selectItem(item);
      }
      if (command.action === 'search' && typeof command.value === 'string' && command.value.length <= 120) {
        for (const model of ['codex', 'deepseek']) searchHistory(model, command.value);
      }
      if (command.action === 'more' && ['codex','deepseek'].includes(command.value)) loadList(command.value, false);
    });
  }

  function searchHistory(partition, query) {
    const view = viewFor(partition);
    view.query = query;
    view.nextOffset = null;
    view.sessions = [];
    view.sig = '';
    view.loaded = false;
    rebuildList(partition);
    loadList(partition, true);
  }

  function syncPartitionUI() {
    const view = activeView();
    const partition = PARTITIONS[state.partition];
    const modelChoice=$('singleModelChoice');if(modelChoice){modelChoice.value=state.partition;modelChoice.disabled=state.phase!=='idle';}
    for (const [id, partitionId] of [['sessionCodex','codex'],['sessionDeepSeek','deepseek']]) { const button=$(id);button.setAttribute('aria-pressed',String(state.partition===partitionId));button.disabled=state.phase!=='idle'; }
    $('sessionModelHint').textContent=state.partition==='deepseek'?'逐条检查 · 可新建':'历史与续聊';
    const codexTab = $('partitionCodex');
    const deepseekTab = $('partitionDeepSeek');
    if (codexTab) {
      codexTab.setAttribute('aria-selected', state.partition === 'codex' ? 'true' : 'false');
      codexTab.classList.toggle('active', state.partition === 'codex');
    }
    if (deepseekTab) {
      deepseekTab.setAttribute('aria-selected', state.partition === 'deepseek' ? 'true' : 'false');
      deepseekTab.classList.toggle('active', state.partition === 'deepseek');
    }
    const search = $('searchInput');
    if (search) {
      if (state.searchPartition !== state.partition) {
        search.value = view.query;
        state.searchPartition = state.partition;
      }
      search.placeholder = '搜索 ' + partition.label + ' 历史';
      search.setAttribute('aria-label', '搜索 ' + partition.label + ' 历史');
    }
    const conversationList = $('conversationList');
    if (conversationList) conversationList.setAttribute('aria-label', partition.label + ' 历史会话');
    const newButton = $('newConversation');
    if (newButton) newButton.textContent = simpleSingle?'开启会话':state.partition === 'deepseek' ? '＋ 新 Flash 任务' : '＋ 新会话';
    const emptyNew = $('emptyNew');
    if (emptyNew) emptyNew.textContent = state.partition === 'deepseek' ? '新建 Flash 任务' : '新建 Codex 会话';
    const emptyTitle = $('emptyTitle');
    if (emptyTitle) emptyTitle.textContent = '今天，一起完成什么？';
    const emptyLead = $('emptyLead');
    if (emptyLead) {
      emptyLead.textContent = state.partition === 'deepseek'
        ? '读取DeepSeek历史；支持续聊的会话会显示可继续，也可新建任务。'
        : '查看 Codex 消息、任务进度和结果，或开始一个新的 Codex 会话。';
    }
    setLine('listStatus', view.busy
      ? (state.partition === 'deepseek' ? '正在读取 DeepSeek 历史…' : '正在读取 Codex 会话列表…')
      : view.statusText, view.busy ? '' : view.statusTone);
    $('loadMore').hidden = view.nextOffset === null;
  }

  /* ---------- targets / conversation ---------- */

  function currentThreadId() {
    const target = state.target;
    if (!target) return null;
    if (target.kind === 'deepseek') return null;
    if (target.partition === 'deepseek' || isFlashConversation()) return null;
    if (target.threadId) return String(target.threadId);
    const conversation = state.conversation;
    if (conversation && conversation.thread_id && !isFlashConversation()) return String(conversation.thread_id);
    if (conversation && conversation.task && conversation.task.remote_session && !isFlashTask(conversation.task)) return String(conversation.task.remote_session);
    return null;
  }

  function resetConversationState() {
    state.viewRevision += 1;
    state.readBusy = false;
    state.pollQueued = false;
    state.loading = false;
    state.messages = new Map();
    state.nextBefore = null;
    state.lastEmptyCursor = null;
    state.messagesDomSig = null;
    state.historySig = '';
    state.historyObserved = null;
    state.historyHint = '';
    state.historyScanLimited = false;
    state.historyError = '';
    state.assistantTexts = [];
    state.resultTokens = new Set();
    state.progressSig = '';
    state.jobsSig = '';
    state.jobs = [];
    state.canReply = false;
    state.cancellingTask = '';
    state.taskCancelError = '';
    state.scrollPending = false;
  }

  function switchPartition(partition) {
    if (state.phase !== 'idle') return;
    const next = partition === 'deepseek' ? 'deepseek' : 'codex';
    if (state.partition === next) return;
    saveDraft();
    if (state.target) state.fileDrafts.set(state.target.key, state.files);
    state.partition = next;
    state.selectedAgent = defaultAgentForPartition(next);
    if (state.target && state.target.partition !== next) {
      state.target = null;
      state.conversation = null;
      state.files = [];
      state.filesSig = '';
      resetConversationState();
      $('composerInput').value = '';
      autoGrow();
    }
    syncPartitionUI();
    renderAll();
    const view = viewFor(next);
    if (!view.loaded && !view.busy) loadList(next, true);
  }

  function openTarget(target, options) {
    const opts = options || {};
    if (!opts.skipDraft) saveDraft();
    if (state.target) state.fileDrafts.set(state.target.key, state.files);
    const partition = target.partition || (target.kind === 'deepseek' ? 'deepseek' : 'codex');
    target.partition = partition;
    state.partition = partition;
    if (target.kind === 'new') {
      target.agent = normalizeAgent(target.agent || defaultAgentForPartition(partition));
      state.selectedAgent = target.agent;
    } else {
      state.selectedAgent = defaultAgentForPartition(partition);
    }
    state.target = target;
    state.files = state.fileDrafts.get(target.key) || [];
    state.filesSig = '';
    state.conversation = opts.conversation || null;
    resetConversationState();
    state.loading = target.kind !== 'new';
    setLine('composerStatus', '');
    setLine('jobsError', '');
    restoreDraft();
    syncPartitionUI();
    closeDrawer();
    renderAll();
    autoGrow();
    if (target.kind !== 'new') loadConversation({ initial: true });
    else window.setTimeout(() => {
      try {
        $('conversationView').scrollTop = 0;
        $('composerInput').focus();
      } catch (error) {}
    }, 30);
  }

  function newConversation() {
    if (state.phase !== 'idle') return;
    const partition = state.partition;
    if (state.target && state.target.kind === 'new' && state.target.partition === partition) {
      closeDrawer();
      $('composerInput').focus();
      return;
    }
    saveDraft();
    const agent = defaultAgentForPartition(partition);
    state.selectedAgent = agent;
    openTarget({ kind: 'new', key: 'new:' + partition, partition: partition, agent: agent }, { skipDraft: true });
  }

  function selectItem(item) {
    if (state.phase !== 'idle') return;
    const partition = item.partition || (item.kind === 'deepseek' ? 'deepseek' : 'codex');
    let target;
    if (item.kind === 'task') {
      const flash = isFlashTask(item.task);
      target = {
        kind: 'task',
        key: 'task:' + item.id,
        taskId: item.id,
        agent: item.task.agent || '',
        threadId: !flash && item.task.remote_session ? String(item.task.remote_session) : null,
        partition: partition,
        title: item.title
      };
    } else if (item.kind === 'deepseek') {
      target = {
        kind: 'deepseek',
        key: 'deepseek:' + item.id,
        sessionId: String(item.id),
        harnessSessionId: item.session && item.session.session_id ? String(item.session.session_id) : '',
        threadId: null,
        taskId: null,
        partition: 'deepseek',
        title: item.title
      };
    } else {
      target = {
        kind: 'thread',
        key: 'thread:' + item.id,
        threadId: item.id,
        taskId: null,
        partition: 'codex',
        title: item.title
      };
    }
    if (state.target && state.target.key === target.key) { closeDrawer(); return; }
    let provisional;
    if (item.kind === 'task') {
      const flash = isFlashTask(item.task) || partition === 'deepseek';
      provisional = {
        task: item.task,
        provider: flash ? FLASH_AGENT : 'codex',
        thread_id: target.threadId,
        title: item.title,
        status: item.task.status,
        status_hint: '',
        history: null,
        jobs: [],
        can_reply: false,
        reply_hint: flash ? FLASH_REPLY_HINT : ''
      };
    } else if (item.kind === 'deepseek') {
      provisional = {
        task: null,
        provider: DEEPSEEK_PROVIDER,
        session_id: String(item.id),
        thread_id: null,
        title: item.title,
        status: item.session && item.session.status ? item.session.status : 'unconfirmed',
        status_hint: '',
        history: null,
        jobs: [],
        can_reply: false,
        reply_hint: DEEPSEEK_REPLY_HINT
      };
    } else {
      provisional = { task: null, thread_id: target.threadId, title: item.title, status: '', status_hint: '', history: null, jobs: [], can_reply: false };
    }
    openTarget(target, { conversation: provisional });
  }

  function messageKey(message) {
    if (!message) return '';
    if (message.offset !== undefined && message.offset !== null) return 'o:' + String(message.offset);
    if (message.id !== undefined && message.id !== null) return 'i:' + String(message.id);
    return '';
  }
  function messageOrderValue(message) {
    if (!message) return -1;
    if (message.offset !== undefined && message.offset !== null) return Number(message.offset) || 0;
    return Number(message.id) || 0;
  }

  function applyHistory(history, opts) {
    if (!history) return;
    const target = state.target;
    const nativeDeepSeek = target.kind === 'deepseek';
    if (nativeDeepSeek) {
      if (history.id && target.sessionId && String(history.id) !== String(target.sessionId)) {
        state.historyError = '返回的 DeepSeek 历史与所选会话不一致，未显示该页。';
        return;
      }
    } else if (history.id && target.threadId && String(history.id) !== String(target.threadId)) {
      state.historyError = '返回的历史会话与所选不一致，未显示该页。';
      return;
    }
    if (!nativeDeepSeek && !target.threadId && history.id) target.threadId = String(history.id);
    const messages = Array.isArray(history.messages) ? history.messages : [];
    const nextBefore = history.next_before === undefined ? null : history.next_before;
    const lastLoaded = Array.from(state.messages.values()).reduce((max, message) => Math.max(max, messageOrderValue(message)), -1);
    const pageBeyond = messages.length
      ? messages.every((message) => messageOrderValue(message) > lastLoaded)
      : nextBefore !== null && Number(nextBefore) > lastLoaded && String(nextBefore) !== String(state.lastEmptyCursor);
    const resetWindow = !opts.initial && !opts.older && pageBeyond;
    if (resetWindow) state.messages = new Map();
    if (!opts.older) state.lastEmptyCursor = messages.length ? null : nextBefore;
    for (const message of messages) {
      const key = messageKey(message);
      if (!key) continue;
      state.messages.set(key, message);
    }
    if (opts.initial || opts.older || resetWindow) state.nextBefore = nextBefore;
    state.historyObserved = history.observed_at === undefined ? null : history.observed_at;
    state.historyHint = history.status_hint || '';
    state.historyScanLimited = !!history.scan_limited;
  }

  function deepSeekCapability(data) {
    if(typeof data.resume_supported!=='boolean')return {supported:false,send:false,label:'需更新',hint:'电脑接收后台仍是旧版，请重开远程接收服务后刷新；只刷新手机页面不会更新后台。'};
    return {supported:data.resume_supported,send:data.can_reply===true,label:data.resume_supported?(data.can_reply===true?'可继续':'处理中'):'只读',hint:data.reply_hint||'请核对当前会话状态。'};
  }

  function applyConversation(data, opts) {
    if (!data) throw new Error('电脑返回了空响应');
    const target = state.target;
    if (!target) return;

    if (target.kind === 'deepseek') {
      if (data.provider && data.provider !== DEEPSEEK_PROVIDER) {
        state.historyError = '返回的记录不是 DeepSeek Harness 历史，已忽略。';
        renderAll(opts);
        return;
      }
      if (data.session_id !== undefined && data.session_id !== null && String(data.session_id) !== String(target.sessionId)) {
        state.historyError = '返回的 DeepSeek 会话与所选不一致，已忽略这次记录。';
        renderAll(opts);
        return;
      }
      const history = data.history && typeof data.history === 'object' ? data.history : null;
      const capability=deepSeekCapability(data);
      state.conversation = {
        provider: DEEPSEEK_PROVIDER,
        session_id: String(target.sessionId),
        thread_id: null,
        task: null,
        title: data.title || target.title || '',
        status: data.status || (history && history.status) || 'unconfirmed',
        status_hint: data.status_hint || (history && history.status_hint) || '',
        history: history,
        jobs: Array.isArray(data.jobs)?data.jobs:[],
        can_reply: capability.send,
        resume_supported: capability.supported,
        resume_label: capability.label,
        reply_hint: capability.hint
      };
      state.jobs = state.conversation.jobs;
      state.canReply = capability.send;
      state.loading = false;
      target.threadId = null;
      if (data.title) target.title = cleanTitle(data.title);
      if (history) {
        state.historyError = '';
        applyHistory(history, opts);
      } else if (data.history_error) {
        state.historyError = String(data.history_error);
      } else {
        state.historyError = '返回的 DeepSeek 历史格式不完整，暂未显示消息。';
      }
      renderAll(opts);
      return;
    }

    if (target.kind === 'thread' && data.thread_id && String(data.thread_id) !== String(target.threadId)) {
      state.historyError = '返回的会话与所选不一致，已忽略这次记录。';
      renderAll(opts);
      return;
    }
    if (target.kind === 'task' && data.task && data.task.id !== undefined && data.task.id !== null && String(data.task.id) !== String(target.taskId)) {
      state.historyError = '返回的任务与所选任务不一致，已忽略这次记录。';
      renderAll(opts);
      return;
    }
    if (target.kind === 'task' && target.threadId && data.thread_id && String(data.thread_id) !== String(target.threadId)) {
      state.historyError = '返回的会话与任务记录不一致，已忽略这次记录。';
      renderAll(opts);
      return;
    }
    const previous = state.conversation || {};
    let task = data.task
      ? Object.assign({}, previous.task || {}, data.task)
      : (previous.task || null);
    const flash = target.partition === 'deepseek' || target.agent === FLASH_AGENT || data.provider === FLASH_AGENT
      || previous.provider === FLASH_AGENT || isFlashTask(task);
    if (flash && task && task.agent !== FLASH_AGENT) task = Object.assign({}, task, { agent: FLASH_AGENT });
    const threadId = flash ? null : (data.thread_id || (task && task.remote_session) || target.threadId || null);
    state.conversation = Object.assign({}, previous, data, { task: task, thread_id: threadId });
    if (flash) {
      state.conversation.provider = FLASH_AGENT;
      state.conversation.reply_hint = data.reply_hint || previous.reply_hint || FLASH_REPLY_HINT;
      if (data.status_hint === undefined) state.conversation.status_hint = (task && task.status_hint) || '';
    }
    state.jobs = flash ? [] : (Array.isArray(data.jobs) ? data.jobs : (previous.jobs || []));
    state.conversation.jobs = state.jobs;
    state.canReply = !flash && data.can_reply === true;
    state.loading = false;
    if (flash) target.agent = FLASH_AGENT;
    if (threadId) target.threadId = String(threadId);
    if (data.title) target.title = cleanTitle(data.title);
    else if (!target.title && task) target.title = cleanTitle(task.title || '');
    if (flash) {
      state.historyError = '';
      state.historyObserved = null;
      state.historyHint = '';
      state.historyScanLimited = false;
      state.nextBefore = null;
      state.lastEmptyCursor = null;
      state.messages = new Map();
      state.conversation.history = null;
    } else if (data.history) {
      state.historyError = '';
      applyHistory(data.history, opts);
      state.conversation.history = data.history;
    } else if (data.history_error) {
      state.historyError = String(data.history_error);
    } else {
      state.historyError = '';
    }
    if (data.task && data.task.id !== undefined && data.task.id !== null) {
      const latest = Object.assign({}, task);
      if (flash) latest.agent = FLASH_AGENT;
      else if (!latest.remote_session && threadId) latest.remote_session = String(threadId);
      const index = state.tasks.findIndex((item) => item && String(item.id) === String(latest.id));
      if (index >= 0) {
        const merged = Object.assign({}, state.tasks[index], latest);
        if (stableStringify(state.tasks[index]) !== stableStringify(merged)) {
          state.tasks = state.tasks.slice();
          state.tasks[index] = merged;
          rebuildAllLists();
        }
      } else {
        state.tasks = [latest].concat(state.tasks);
        rebuildAllLists();
      }
    }
    renderAll(opts);
  }

  async function loadConversation(options) {
    const opts = options || {};
    const target = state.target;
    if (!target || target.kind === 'new') return;
    if (state.readBusy) {
      if (!opts.older) state.pollQueued = true;
      return;
    }
    const before = opts.older ? state.nextBefore : null;
    if (opts.older && (before === null || before === undefined)) return;
    const taskId = target.kind === 'task' ? target.taskId : null;
    const threadId = target.kind === 'thread' ? target.threadId : null;
    const sessionId = target.kind === 'deepseek' ? target.sessionId : null;
    if (!taskId && !threadId && !sessionId) return;
    const revision = state.viewRevision;
    const key = target.key;
    state.readBusy = true;
    if (opts.initial) state.loading = true;
    updateInteraction();
    try {
      const suffix = (before !== null && before !== undefined) ? '&before=' + encodeURIComponent(before) : '';
      let path;
      if (target.kind === 'deepseek') {
        path = '/api/bot/deepseek/conversation?source_id=' + encodeURIComponent(sourceId)
          + '&session_id=' + encodeURIComponent(sessionId) + suffix;
      } else {
        const parameter = taskId
          ? 'task_id=' + encodeURIComponent(taskId)
          : 'thread_id=' + encodeURIComponent(threadId);
        path = '/api/bot/conversation?source_id=' + encodeURIComponent(sourceId) + '&' + parameter + suffix;
      }
      const data = await request(path);
      if (revision !== state.viewRevision || !state.target || state.target.key !== key) return;
      applyConversation(data, { initial: !!opts.initial, older: !!opts.older });
    } catch (error) {
      if (revision !== state.viewRevision || !state.target || state.target.key !== key) return;
      state.loading = false;
      state.historyError = errText(error) + '。已保留上次显示内容。';
      renderAll();
    } finally {
      if (revision === state.viewRevision) {
        state.readBusy = false;
        state.loading = false;
        updateInteraction();
        if (state.pollQueued) {
          state.pollQueued = false;
          if (!document.hidden) window.setTimeout(() => { loadConversation({}); }, 0);
        }
      }
    }
  }

  /* ---------- rendering ---------- */

  function renderHeader() {
    const title = $('conversationTitle');
    const meta = $('conversationMeta');
    const dot = $('headerDot');
    const target = state.target;
    if (dot) dot.hidden = true;
    if (!target) {
      title.textContent = PARTITIONS[state.partition].label + ' 会话';
      meta.textContent = '选择一个 ' + PARTITIONS[state.partition].label + ' 会话，或新建会话';
      return;
    }
    if (target.kind === 'new') {
      const flash = state.selectedAgent === FLASH_AGENT;
      title.textContent = flash ? '新 Flash 任务' : '新 Codex 会话';
      const ready = state.connected === null ? '正在连接电脑…' : '发送后' + (flash ? '创建独立任务' : '开始新会话');
      meta.textContent = state.connected === false
        ? '连接中断'
        : (flash ? FLASH_NAME + ' · ' + ready + (state.partition === 'codex' ? ' · 成功后切到 DeepSeek 分区' : '') : 'Codex · ' + ready);
      return;
    }
    title.textContent = target.title || '会话';
    const conversation = state.conversation || {};
    const status = conversation.status || (conversation.task && conversation.task.status) || '';
    let text = status ? labelFor(TASK_LABELS, status) : (state.loading ? '读取中…' : '历史会话');
    if (target.kind === 'deepseek') text = DEEPSEEK_NAME + ' 历史 · ' + text;
    else if (isFlashConversation()) text = FLASH_NAME + ' · ' + text;
    else if (target.partition === 'codex') text = 'Codex · ' + text;
    if (state.connected === false) text = '离线 · ' + text;
    else if ((isFlashConversation() || target.kind === 'deepseek') && state.historyError) text = '上次状态 · ' + text;
    meta.textContent = text;
    if (dot) {
      const tone = toneFor(status);
      dot.hidden = false;
      dot.className = 'status-dot ' + (tone === 'ok' ? 'ok' : tone === 'warn' ? 'warn' : tone === 'bad' ? 'bad' : 'muted');
    }
  }

  function renderEmpty() {
    const target = state.target;
    $('emptyState').hidden = !!target;
    $('conversationView').hidden = !target;
    $('composer').hidden = !target;
    $('newHint').hidden = !target || target.kind !== 'new';
    if (!target) {
      const partition = PARTITIONS[state.partition];
      let hint = state.partition === 'deepseek'
        ? 'DeepSeek历史会逐条检查，区分可继续与只读。'
        : 'Codex 分区显示 Codex 任务与历史会话。';
      if (state.authError) hint = '链接已失效，请从电脑重新打开二维码链接。';
      else if (state.connected === false) hint = '电脑未连接，请检查 Wi-Fi 和电脑是否保持运行。';
      else if (state.connected === null) hint = '正在连接电脑…';
      else if (state.agentsAvailable.codex === false && state.agentsAvailable[FLASH_AGENT] !== true) hint = '电脑未找到可用的 Agent，仍可查看历史记录。';
      hint += ' ' + partition.label + ' 与另一分区的列表、搜索和分页互不影响。';
      $('emptyHint').textContent = hint;
    }
  }

  function renderStatus() {
    const panel = $('statusPanel');
    const target = state.target;
    if (!target || target.kind === 'new') {
      panel.hidden = true;
      clear(panel);
      return;
    }
    panel.hidden = false;
    clear(panel);
    const conversation = state.conversation;
    if (!conversation || (state.loading && !conversation.task && target.kind !== 'deepseek')) {
      panel.append(el('p', 'status-hint', '正在读取记录…'));
      return;
    }
    const status = conversation.status || (conversation.task && conversation.task.status) || '';
    const nativeDeepSeek = target.kind === 'deepseek';
    const deepSeek = isDeepSeekConversation();
    const line = el('div', 'status-line');
    line.append(el('span', 'chip ' + toneFor(status), status ? labelFor(TASK_LABELS, status) : '历史会话'));
    if (nativeDeepSeek) line.append(el('span', 'chip info', DEEPSEEK_NAME + ' 历史'));
    else if (deepSeek) line.append(el('span', 'chip info', FLASH_NAME));
    if (conversation.status_hint) line.append(el('span', 'status-hint', String(conversation.status_hint).slice(0, 140)));
    panel.append(line);

    const jobs = Array.isArray(conversation.jobs) ? conversation.jobs : [];
    const pending = jobs.filter((job) => job && (job.status === 'queued' || job.status === 'waiting'));
    if (pending.length) {
      const first = pending[0];
      const seconds = Number(first.waiting_seconds);
      let text = pending.length + ' 条后续指令尚未送达 · ' + (first.waiting_reason || '等待当前轮结束');
      if (isFinite(seconds)) text += ' · 已等待 ' + seconds + ' 秒';
      panel.append(el('div', 'wait-summary', text));
    }

    if(conversation.task?.agent==='codex-deepseek-code'){
      panel.append(el('div','notice',conversation.reply_hint||'代码项目进度与成果在此查看。'));
    } else if (nativeDeepSeek) {
      panel.append(el('div', 'notice', conversation.reply_hint || DEEPSEEK_REPLY_HINT));
    } else if (deepSeek) {
      panel.append(el('div', 'notice', conversation.reply_hint || FLASH_REPLY_HINT));
      if (state.taskCancelError) panel.append(el('div', 'error-box', state.taskCancelError));
    } else if (!currentThreadId()) {
      panel.append(el('div', 'notice', '正在建立会话，稍后可以继续发送。'));
    } else if (state.canReply === false) {
      panel.append(el('div', 'notice', '当前轮尚未结束，结束后可继续发送。'));
    }

    if (state.historyObserved) {
      panel.append(el('p', 'stamp', '更新于 ' + stampText(state.historyObserved) + (state.connected === false ? ' · 上次状态' : '')));
    } else if (state.connected === false) {
      panel.append(el('p', 'stamp', '上次状态 · 连接中断'));
    }
  }

  function claimResult(value) {
    const text = normalise(formatResult(value));
    if (!text) return false;
    if (state.resultTokens.has(text)) return false;
    if (state.assistantTexts.some((candidate) => candidate === text)) return false;
    state.resultTokens.add(text);
    return true;
  }

  function attachmentHref(taskId, name) {
    return api('/input/' + encodeURIComponent(taskId) + '/' + encodeURIComponent(name));
  }
  function replyInputHref(jobId, name) {
    return api('/api/bot/reply-input/' + encodeURIComponent(jobId) + '/' + encodeURIComponent(name) + '?source_id=' + encodeURIComponent(sourceId));
  }
  function artifactHref(taskId, file) {
    const path = String((file && file.path) || '').split('/').filter(Boolean).map(encodeURIComponent).join('/');
    return api('/artifact/' + encodeURIComponent(taskId) + '/' + path);
  }
  function fileViewerHref(taskId, path) {
    let href = '/file-viewer?task_id=' + encodeURIComponent(taskId);
    if (path) href += '&path=' + encodeURIComponent(String(path));
    return api(href);
  }
  function displayFileName(name) {
    return String(name || '').replace(/^[a-f0-9]{12}-/i, '');
  }

  function supportsPdfPreview(file) {
    if (!file || !file.path) return false;
    const pathMatch = String(file.path).match(/\.([a-z0-9]+)$/i);
    const nameMatch = String(file.name || '').match(/\.([a-z0-9]+)$/i);
    const match = pathMatch || nameMatch;
    return !!match && PDF_PREVIEW_EXTS.has(match[1].toLowerCase());
  }

  function previewViewerHref(receipt) {
    if (!receipt || typeof receipt !== 'object') return '';
    const id = String(receipt.id || '');
    if (!/^[a-f0-9]{64}$/i.test(id)) return '';
    if (!receipt.viewer_url) return '';
    let url;
    try {
      url = new URL(String(receipt.viewer_url), location.origin);
    } catch (error) {
      return '';
    }
    if (url.origin !== location.origin) return '';
    if (url.pathname !== '/preview-viewer') return '';
    const viewerId = String(url.searchParams.get('preview_id') || '');
    if (viewerId.toLowerCase() !== id.toLowerCase()) return '';
    url.searchParams.set('token', token);
    url.hash = '';
    return url.pathname + url.search;
  }

  function setPreviewNote(note, text, isError) {
    if (!note) return;
    clear(note);
    note.hidden = !text;
    note.classList.toggle('error', !!isError);
    if (text) note.textContent = text;
  }

  function setPreviewLink(note, href) {
    if (!note) return;
    clear(note);
    note.hidden = false;
    note.classList.remove('error');
    note.append('已生成预览，请点击打开：');
    const link = el('a', '', '打开 PDF 预览');
    link.href = href;
    link.target = '_blank';
    link.rel = 'noopener';
    note.append(link);
  }

  async function openPdfPreview(task, file, button, note) {
    if (!button || button.disabled) return;
    button.disabled = true;
    let popup = null;
    try {
      popup = window.open('about:blank', '_blank');
    } catch (error) {
      popup = null;
    }
    setPreviewNote(note, '正在准备 PDF 预览…', false);
    try {
      if (!task || task.id === undefined || task.id === null || !file || !file.path) {
        throw new Error('缺少任务或文件信息，无法预览');
      }
      const receipt = await request('/api/bot/preview', postJson({ task_id: task.id, path: file.path }));
      const href = previewViewerHref(receipt);
      if (!href) throw new Error('预览返回的地址无效');
      let opened = false;
      if (popup && !popup.closed) {
        try {
          popup.location.href = new URL(href, location.href).href;
          opened = true;
        } catch (error) {
          opened = false;
        }
      }
      if (opened) {
        setPreviewNote(note, new URLSearchParams(location.search).get('desktop_embed')==='1'?'预览已在当前工作站打开。':'预览已在新窗口打开。', false);
      } else {
        if (popup && !popup.closed) {
          try { popup.close(); } catch (error) { /* ignore */ }
        }
        setPreviewLink(note, href);
      }
    } catch (error) {
      if (popup && !popup.closed) {
        try { popup.close(); } catch (closeError) { /* ignore */ }
      }
      setPreviewNote(note, '预览失败：' + errText(error), true);
    } finally {
      if (button.isConnected) button.disabled = false;
    }
  }

  function renderProgress() {
    const panel = $('progressPanel');
    if (panel) {
      panel.hidden = true;
      clear(panel);
    }
    state.progressSig = '';
    return;
  }

  function orderedMessages() {
    return Array.from(state.messages.values()).sort((left, right) => messageOrderValue(left) - messageOrderValue(right));
  }
  function messageSignature(messages) {
    return messages.map((message) => [
      messageKey(message),
      message.role,
      hashText(String(message.text || '')),
      hashText(JSON.stringify(message.images || [])),
      message.time || '',
      message.truncated ? '1' : '0'
    ].join('~')).join('|');
  }
  function buildAssistantTexts(messages) {
    const texts = [];
    for (const message of messages) {
      if (!message || message.role !== 'assistant') continue;
      const raw = normalise(message.text);
      if (raw) texts.push(raw);
      const shown = normalise(shownMessageText(message));
      if (shown && shown !== raw) texts.push(shown);
    }
    return texts;
  }

  function taskGoalText(task) {
    const raw = normalise(task && task.goal);
    if (!raw) return '';
    const goal = workbenchGoal(raw);
    return goal === null ? raw : goal;
  }
  function taskAttachments(task) {
    if (!task || !Array.isArray(task.attachments)) return [];
    return task.attachments.filter((name) => typeof name === 'string' && name);
  }
  function resultTextCandidates(value) {
    const texts = [];
    const formatted = normalise(formatResult(value));
    if (formatted) texts.push(formatted);
    if (typeof value === 'string') {
      const raw = normalise(value);
      if (raw) texts.push(raw);
      const shown = normalise(displayText({ role: 'assistant', text: value }));
      if (shown) texts.push(shown);
    } else if (value && typeof value === 'object') {
      try {
        const raw = normalise(JSON.stringify(value));
        if (raw) {
          texts.push(raw);
          const shown = normalise(displayText({ role: 'assistant', text: raw }));
          if (shown) texts.push(shown);
        }
      } catch (error) { /* keep formatted summary */ }
    }
    return texts;
  }

  function renderTaskAttachments(taskId, names) {
    if (taskId === undefined || taskId === null || !names.length) return null;
    const list = el('div', 'attachment-list bubble-attachments');
    for (const name of names) {
      if (!name) continue;
      const item = el('div', 'attachment-item');
      const href = attachmentHref(taskId, name);
      const label = displayFileName(name);
      if (/\.(png|jpe?g|webp)$/i.test(String(name))) {
        const image = el('img');
        image.src = href;
        image.alt = label;
        image.loading = 'lazy';
        item.append(image);
      }
      const link = el('a', '', label);
      link.href = href;
      link.target = '_blank';
      link.rel = 'noopener';
      item.append(link);
      list.append(item);
    }
    return list.firstChild ? list : null;
  }

  function shownMessageText(message) {
    if (state.target && state.target.kind === 'deepseek') return normalise(message && message.text);
    return displayText(message);
  }

  function renderMessage(message, opts) {
    const options = opts || {};
    const assistant = message.role === 'assistant';
    const article = el('article', 'msg ' + (assistant ? 'assistant' : 'user'));
    article.dataset.messageId = message.id !== undefined && message.id !== null ? String(message.id) : '';
    if (message.offset !== undefined && message.offset !== null) article.dataset.messageOffset = String(message.offset);
    article.dataset.role = assistant ? 'assistant' : 'user';
    article.setAttribute('aria-label', assistant ? 'Agent 回复' : '我的指令');
    const stack = el('div', 'msg-stack');
    const head = el('div', 'msg-head');
    const avatar=el('span','partner-avatar');avatar.dataset.person=assistant?'assistant':'user';avatar.setAttribute('aria-hidden','true');article.append(avatar);
    head.append(el('span', 'msg-who', assistant ? 'Agent 回复' : '我的指令'));
    if (assistant) head.append(el('span', 'msg-model', replyAgentName()));
    if (message.time) head.append(el('span', 'msg-time', stampText(message.time)));
    const bubble = el('div', 'msg-bubble');
    const text = String(message.text || '');
    const environment = message.role === 'user' && /^<environment_context>[\s\S]*<\/environment_context>\s*$/.test(text.trim());
    if (environment) {
      const details = el('details');
      details.append(el('summary', '', '会话环境信息'));
      details.append(el('div', 'msg-text', shownMessageText(message)));
      bubble.append(details);
    } else {
      bubble.append(el('div', 'msg-text', shownMessageText(message)));
      if (message.role === 'user' && !(state.target && state.target.kind === 'deepseek') && workbenchGoal(text) !== null) {
        const details = el('details');
        details.append(el('summary', '', '查看完整提交内容'));
        details.append(el('div', 'msg-raw', text));
        bubble.append(details);
      }
    }
    const attachments = renderTaskAttachments(options.taskId, options.taskAttachments || []);
    if (attachments) bubble.append(attachments);
    if (assistant && Array.isArray(message.images) && !isFlashConversation()) {
      const thread = state.conversation && state.conversation.thread_id;
      const list = el('div', 'attachment-list bubble-attachments');
      for (const image of message.images) {
        if (!thread || !/^\d+$/.test(String(message.id)) || !Number.isInteger(image.index) || image.index < 0 || image.index >= 100) continue;
        const href = api('/api/bot/generated-image?thread_id=' + encodeURIComponent(thread) + '&offset=' + message.id + '&index=' + image.index);
        const item = el('div', 'attachment-item');
        const link = el('a', '', '查看原图');
        link.href = href; link.target = '_blank'; link.rel = 'noopener';
        const img = el('img'); img.src = href; img.alt = '生成的图片'; img.loading = 'lazy';
        img.onerror = () => { img.hidden = true; link.textContent = '图片加载失败，点此重试'; };
        const preview = el('a'); preview.href = href; preview.target = '_blank'; preview.rel = 'noopener';
        preview.append(img); item.append(preview, link); list.append(item);
      }
      if (list.firstChild) bubble.append(list);
    }
    if (message.truncated) bubble.append(el('p', 'truncated', '此条文字较长，当前预览已截断。'));
    stack.append(head, bubble);
    article.append(stack);
    return article;
  }

  function renderTaskGoalBubble(item) {
    const task = item.task;
    const article = el('article', 'msg user task-goal');
    article.dataset.role = 'user';
    const avatar=el('span','partner-avatar');avatar.dataset.person='user';avatar.setAttribute('aria-hidden','true');article.append(avatar);
    article.dataset.targetKey = state.target ? state.target.key : '';
    article.setAttribute('aria-label', '我的指令');
    const stack = el('div', 'msg-stack');
    const head = el('div', 'msg-head');
    head.append(el('span', 'msg-who', '我的指令'));
    if (task.created) head.append(el('span', 'msg-time', stampText(task.created)));
    const bubble = el('div', 'msg-bubble');
    if (item.goal) bubble.append(el('div', 'msg-text', item.goal));
    const raw = normalise(task.goal);
    if (item.goal && raw && raw !== item.goal) {
      const details = el('details');
      details.append(el('summary', '', '查看完整提交内容'));
      details.append(el('div', 'msg-raw', raw));
      bubble.append(details);
    }
    const attachments = renderTaskAttachments(task.id, item.attachments || []);
    if (attachments) bubble.append(attachments);
    stack.append(head, bubble);
    article.append(stack);
    return article;
  }

  function nativeSessionForTask(task) {
    if (!isFlashTask(task) || !task.provider_session) return null;
    return viewFor('deepseek').sessions.find(session => session.session_id === task.provider_session) || null;
  }

  function renderTaskStatusBubble(item) {
    const task = item.task;
    const status = task.status || '';
    const completed = status === 'completed';
    const conversation = state.conversation || {};
    const followup = !isFlashTask(task) && ['completed', 'failed', 'cancelled', 'needs_attention'].includes(status)
      && (conversation.status !== status || (Array.isArray(conversation.jobs) && conversation.jobs.some(job => job.status !== 'cancelled')));
    const kind = followup
      ? (completed ? '初始任务结果' : '初始任务进度')
      : (completed ? '任务结果' : (['failed', 'cancelled', 'needs_attention', 'interrupted'].includes(status) ? '任务状态' : '任务进度'));
    const article = el('article', 'msg assistant task-status' + (completed ? ' task-complete' : '') + (followup ? ' task-historic' : ''));
    article.dataset.role = 'assistant';
    const avatar=el('span','partner-avatar');avatar.dataset.person='assistant';avatar.setAttribute('aria-hidden','true');article.append(avatar);
    article.dataset.taskId = task.id !== undefined && task.id !== null ? String(task.id) : '';
    article.dataset.status = status;
    article.setAttribute('aria-label', kind);
    const stack = el('div', 'msg-stack');
    const head = el('div', 'msg-head');
    head.append(el('span', 'msg-who', '任务记录'));
    head.append(el('span', 'msg-model', taskAgentName(task)));
    if (task.updated) head.append(el('span', 'msg-time', stampText(task.updated)));
    const bubble = el('div', 'msg-bubble');

    const top = el('div', 'task-status-top');
    top.append(el('span', 'task-current-label', kind));
    top.append(el('span', 'chip ' + toneFor(status), labelFor(TASK_LABELS, status)));
    if (followup) top.append(el('span', 'task-followup-note', '历史记录'));
    bubble.append(top);

    const hint = followup ? '这是初始任务记录；最新状态以上方会话状态和后续指令为准。' : (task.status_hint || conversation.status_hint || '');
    if (hint) bubble.append(el('div', 'task-status-hint', String(hint)));

    const parts = (Array.isArray(task.completed_parts) ? task.completed_parts : [])
      .filter((part) => part && (part.title || part.detail));
    if (parts.length) {
      const latest = parts[parts.length - 1];
      const latestLine = el('div', 'task-stage-latest');
      latestLine.append(el('span', 'task-stage-name', '最新进度 · ' + (latest.title || '阶段')));
      if (latest.time) latestLine.append(el('span', 'task-stage-time', stampText(latest.time)));
      bubble.append(latestLine);

      const history = el('details', 'fold progress-history');
      history.append(el('summary', '', '全部阶段（' + parts.length + '）'));
      const inner = el('div');
      for (const part of parts) {
        const block = el('div', 'task-part');
        block.append(el('div', 'task-part-title', part.title || '阶段'));
        if (part.detail) block.append(el('div', 'task-part-detail', part.detail));
        if (part.time) block.append(el('div', 'task-part-time', stampText(part.time)));
        inner.append(block);
      }
      history.append(inner);
      bubble.append(history);
    } else if (status === 'queued' || status === 'pending' || status === 'unconfirmed') {
      bubble.append(el('p', 'task-note', '尚未开始，暂无阶段记录。'));
    } else if (status === 'running' || status === 'active') {
      bubble.append(el('p', 'task-note', '执行中，暂无阶段记录。'));
    } else if (status === 'completed') {
      bubble.append(el('p', 'task-note', '任务已完成，没有返回阶段记录。'));
    } else {
      bubble.append(el('p', 'task-note', '没有返回阶段记录。'));
    }

    const result = task.result;
    const hasResult = result !== undefined && result !== null && result !== '';
    if (hasResult && !item.resultSuppressed) {
      const section = el('div', 'task-detail-section task-result-section');
      const details = el('details', 'fold task-result');
      if (item.openResult) details.open = true;
      const summary = el('summary');
      summary.append(el('span', 'task-result-label', '结果正文'));
      if (!item.openResult) summary.append(el('span', 'task-result-hint', '展开查看'));
      details.append(summary);
      details.append(el('div', 'result-box', formatResult(result)));
      section.append(details);
      bubble.append(section);
    } else if (hasResult && item.resultSuppressed) {
      bubble.append(el('p', 'task-note', '结果已显示在 Agent 回复中。'));
    }

    const isWebProject=task.agent==='codex-deepseek-code'&&(task.project_kind||'web')==='web';
    if(isWebProject&&!['queued','running'].includes(task.status)&&(task.web_preview_ready===true||task.web_screenshot)){
      const row=el('div','task-detail-section');row.append(el('h3','','网页成品'));
      const note=el('p','task-note','在当前窗口远程浏览，电脑需保持在线。');
      const open=el('button','small-btn','打开网页'),capture=el('button','small-btn','生成截图');open.type=capture.type='button';
      open.onclick=async()=>{open.disabled=true;try{const receipt=await request('/api/web-product?id='+encodeURIComponent(task.id));window.openWebProductPreview(receipt.url);}catch(error){note.textContent=errText(error);}finally{open.disabled=false;}};
      capture.onclick=async()=>{capture.disabled=true;note.textContent='正在电脑生成截图，请稍候…';try{const response=await fetch(api('/api/web-product/screenshot'),postJson({id:task.id}));const result=await response.json();if(!response.ok)throw Error(result.error||'截图未生成');await loadConversation({});}catch(error){note.textContent=errText(error);}finally{capture.disabled=false;}};
      if(task.web_preview_ready===true)row.append(open,capture,note);
      if(task.web_screenshot){const image=el('img');image.src=api('/api/web-product/screenshot?id='+encodeURIComponent(task.id)+'&v='+encodeURIComponent(task.updated||''));image.alt='网页成品截图';image.style.cssText='display:block;width:100%;max-height:400px;object-fit:contain;margin-top:12px;border-radius:10px';image.loading='lazy';const download=el('a','small-btn','下载截图');download.href=image.src;download.download='网页截图.png';row.append(image,download);}
      bubble.append(row);
    }
    const artifacts = Array.isArray(task.artifacts) ? task.artifacts : [];
    if (artifacts.length) {
      const section = el(isWebProject ? 'details' : 'div', isWebProject ? 'task-detail-section fold task-source-files' : 'task-detail-section');
      if(isWebProject)section.append(el('summary','','源码与说明（'+artifacts.length+' 个文件）'));
      const headingRow = el('div');
      headingRow.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;';
      if(!isWebProject)headingRow.append(el('h3', '', '成果文件'));
      if (task.id !== undefined && task.id !== null) {
        const viewAll = el('a', 'small-btn artifact-view', '查看文件');
        viewAll.href = fileViewerHref(task.id);
        viewAll.target = '_blank';
        viewAll.rel = 'noopener noreferrer';
        viewAll.setAttribute('aria-label', '在新标签页只读查看全部成果文件');
        headingRow.append(viewAll);
      }
      section.append(headingRow);
      for (const file of artifacts) {
        if (!file) continue;
        const row = el('div', 'artifact-row');
        const link = el('a', 'artifact', (file.name || '下载') + (file.size ? ' · ' + sizeText(file.size) : ''));
        link.href = artifactHref(task.id, file);
        link.target = '_blank';
        link.rel = 'noopener';
        const downloadPptx=isMobile()&&/\.pptx$/i.test(String(file.path||file.name||''));
        if(downloadPptx){link.textContent='下载PPTX · '+(file.name||'演示文稿');link.download=file.name||'演示文稿.pptx';}
        row.append(link);
        if (!downloadPptx && file.path && task.id !== undefined && task.id !== null) {
          const view = el('a', 'small-btn artifact-view', '查看');
          view.href = fileViewerHref(task.id, file.path);
          view.target = '_blank';
          view.rel = 'noopener noreferrer';
          view.setAttribute('aria-label', '只读查看 ' + (file.name || file.path));
          row.append(document.createTextNode(' '), view);
        }
        if (supportsPdfPreview(file) && task.id !== undefined && task.id !== null) {
          const preview = el('button', 'small-btn preview-btn', 'PDF预览');
          preview.type = 'button';
          const note = el('div', 'artifact-preview-note');
          note.hidden = true;
          preview.addEventListener('click', () => openPdfPreview(task, file, preview, note));
          row.append(preview, note);
        }
        section.append(row);
      }
      bubble.append(section);
    }

    if (task.error) bubble.append(el('div', 'error-box', task.error));
    if (state.taskCancelError) bubble.append(el('div', 'error-box', state.taskCancelError));

    if ((isFlashTask(task)||task.agent==='codex-deepseek-code') && (status === 'queued' || status === 'running')) {
      const row = el('div', 'task-stop-row');
      const stop = el('button', 'small-btn stop-btn', state.cancellingTask === String(task.id) ? '正在停止…' : '停止任务');
      stop.id = task.agent==='codex-deepseek-code'?'cancelCodeTask':'cancelFlashTask';
      stop.type = 'button';
      stop.disabled = !!state.cancellingTask;
      stop.addEventListener('click', () => cancelFlashTask(task.id));
      row.append(stop);
      bubble.append(row);
    }

    const nativeSession = nativeSessionForTask(task);
    if (nativeSession) {
      const row = el('div', 'task-stop-row');
      const open = el('button', 'small-btn', '查看本机会话记录');
      open.type = 'button'; open.id = 'viewNativeHistory';
      open.addEventListener('click', () => selectItem({kind:'deepseek',id:nativeSession.id,title:cleanTitle(nativeSession.title),partition:'deepseek',session:nativeSession}));
      row.append(open); bubble.append(row);
    }

    const details = el('details', 'fold task-details');
    details.append(el('summary', '', '任务详情（ID / 路径）'));
    const fields = el('dl');
    const rows = [
      ['Agent', taskAgentName(task)],
      ['方式', task.mode === 'review' ? '只读审查' : '新任务'],
      ['任务号', task.number],
      ['创建时间', task.created ? stampText(task.created) : ''],
      ['原始状态', task.status || ''],
      ['任务 ID', task.id],
      ['会话 ID', !isFlashTask(task) ? (task.remote_session || currentThreadId() || '') : ''],
      ['Harness 会话', isFlashTask(task) ? (task.provider_session || (state.target && state.target.harnessSessionId) || '') : ''],
      ['执行位置', isFlashTask(task) ? '电脑上的 DeepSeek Flash；关闭此页面不会中断任务' : '电脑上的 Agent；关闭此页面不会中断任务']
    ];
    for (const row of rows) {
      if (row[1] === undefined || row[1] === null || row[1] === '') continue;
      const line = el('div', 'raw-row');
      line.append(el('dt', '', row[0]));
      line.append(el('dd', '', row[1]));
      fields.append(line);
    }
    details.append(fields);
    bubble.append(details);

    stack.append(head, bubble);
    article.append(stack);
    return article;
  }

  function buildChatItems(messages) {
    const task = state.conversation && state.conversation.task;
    if (!task) return messages.map((message) => ({ type: 'message', message: message }));
    const items = [];
    const goal = taskGoalText(task) || normalise(task.title);
    const attachments = taskAttachments(task);
    const userTexts = [];
    for (const message of messages) {
      if (!message || message.role !== 'user') continue;
      userTexts.push(normalise(message.text));
      userTexts.push(normalise(displayText(message)));
    }
    let attachIndex = -1;
    if (goal) {
      attachIndex = messages.findIndex((message) => message && message.role === 'user'
        && (normalise(message.text) === goal || normalise(displayText(message)) === goal));
    } else {
      attachIndex = messages.findIndex((message) => message && message.role === 'user');
    }
    if (goal && attachIndex < 0) {
      items.push({ type: 'task-goal', task: task, goal: goal, attachments: attachments });
    } else if (!goal && attachIndex < 0 && attachments.length) {
      items.push({ type: 'task-goal', task: task, goal: '', attachments: attachments });
    }
    for (let index = 0; index < messages.length; index += 1) {
      const message = messages[index];
      const extra = index === attachIndex ? attachments : [];
      items.push({ type: 'message', message: message, taskAttachments: extra, taskId: task.id });
    }
    const assistantTexts = buildAssistantTexts(messages);
    const candidates = (task.result !== undefined && task.result !== null && task.result !== '')
      ? resultTextCandidates(task.result)
      : [];
    const resultSuppressed = candidates.some((candidate) => assistantTexts.some((text) => text === candidate));
    const hasResult = task.result !== undefined && task.result !== null && task.result !== '';
    items.push({ type: 'task-status', task: task, resultSuppressed: resultSuppressed, openResult: hasResult && !assistantTexts.length });
    return items;
  }

  function renderMessages(messages, opts) {
    const view = $('conversationView');
    const box = $('messageList');
    const target = state.target;
    if (!target || target.kind === 'new') {
      box.hidden = true;
      $('loadOlder').hidden = true;
      return;
    }
    box.hidden = false;
    const task = state.conversation && state.conversation.task;
    const nearBottom = view.scrollHeight - view.scrollTop - view.clientHeight < 80;
    const previousHeight = view.scrollHeight;
    const previousTop = view.scrollTop;
    const sig = [
      target.key,
      target.kind,
      state.historySig,
      hashText(JSON.stringify(task || null)),
      (nativeSessionForTask(task) || {}).id || '',
      state.cancellingTask,
      hashText(state.taskCancelError || ''),
      hashText((state.conversation && state.conversation.status_hint) || ''),
      state.loading ? 'loading' : 'idle'
    ].join('|');
    if (state.messagesDomSig !== sig) {
      state.messagesDomSig = sig;
      const previousIds=new Set([...box.querySelectorAll('.msg')].map(n=>n.dataset.messageId||n.dataset.taskId||n.dataset.targetKey).filter(Boolean));
      const animate=simpleSingle&&box.dataset.motionTarget===target.key&&!(opts?.initial||opts?.older);
      box.dataset.motionTarget=target.key;
      const items = buildChatItems(messages);
      const disclosures = rememberDisclosures(box);
      clear(box);
      if (!items.length) {
        box.append(el('p', 'empty-line', state.loading ? '正在读取记录…' : '暂时没有可展示的文字记录。'));
      } else {
        for (const item of items) {
          if (item.type === 'task-goal') box.append(renderTaskGoalBubble(item));
          else if (item.type === 'task-status') box.append(renderTaskStatusBubble(item));
          else {const message=renderMessage(item.message, { taskAttachments: item.taskAttachments, taskId: item.taskId });
            if(animate&&message.dataset.messageId&&!previousIds.has(message.dataset.messageId))message.classList.add('single-message-enter');
            box.append(message);
          }
        }
      }
      restoreDisclosures(box, disclosures);
      if (opts && opts.older) {
        const delta = view.scrollHeight - previousHeight;
        view.scrollTop = previousTop + Math.max(0, delta);
      }
    }
    $('loadOlder').hidden = state.nextBefore === null;
    $('loadOlder').disabled = state.readBusy || state.phase !== 'idle';
    if ((opts && opts.initial) || (!opts || !opts.older) && nearBottom) state.scrollPending = true;
  }

  function updateHistoryStatus() {
    const target = state.target;
    const box = $('historyStatus');
    const wasExpanded = !!box.querySelector('.sync-details[open]');
    if (!target || target.kind === 'new') {
      setLine('historyStatus', '');
      return;
    }
    if (state.historyError) {
      setLine('historyStatus', state.historyError, 'error');
      return;
    }
    if (isFlashConversation()) {
      setLine('historyStatus', '');
      return;
    }
    clear(box);
    box.hidden = false;
    box.classList.remove('error');
    box.classList.toggle('warn', state.historyScanLimited);
    if (state.loading) {
      box.append(el('span', 'history-summary', '正在同步…'));
      return;
    }
    const count = state.messages.size;
    const summary = count
      ? '已显示 ' + count + ' 条消息'
      : (state.nextBefore !== null ? '此段没有消息' : '暂无文字记录');
    box.append(el('span', 'history-summary', summary));
    if (state.historyScanLimited) box.append(el('span', 'history-warn', '仅显示部分记录'));
    if (!state.historyHint && !state.historyScanLimited && state.nextBefore === null) return;
    const details = el('details', 'sync-details');
    details.open = wasExpanded;
    details.append(el('summary', '', '同步详情'));
    const lines = [];
    if (state.historyScanLimited) lines.push('仅扫描了部分本地记录，已显示的内容可能不完整。');
    if (state.nextBefore !== null) lines.push('还有更早的记录，可使用“加载更早记录”继续。');
    if (state.historyHint) lines.push(String(state.historyHint));
    for (const line of lines) details.append(el('div', 'sync-line', line));
    box.append(details);
  }

  function renderJobs() {
    const panel = $('jobsPanel');
    const target = state.target;
    const jobs = (state.conversation && Array.isArray(state.conversation.jobs)) ? state.conversation.jobs : [];
    if (!target || target.kind === 'new' || !jobs.length) {
      panel.hidden = true;
      clear($('jobsList'));
      state.jobsSig = '';
      return;
    }
    panel.hidden = false;
    const sig = hashText(JSON.stringify(jobs)) + '|' + state.historySig + '|' + Array.from(state.cancelling).sort().join(',');
    if (sig === state.jobsSig) return;
    state.jobsSig = sig;
    $('jobsCount').textContent = String(jobs.length);
    const box = $('jobsList');
    const disclosures = rememberDisclosures(box);
    clear(box);
    for (const job of jobs) box.append(renderJob(job));
    restoreDisclosures(box, disclosures);
  }

  function renderJob(job) {
    const status = String(job.status || '');
    const completed = status === 'completed';
    const card = el('div', 'job' + (completed ? ' job-complete' : ''));
    card.dataset.jobId = String(job.id);
    card.dataset.status = status;
    const head = el('div', 'job-head');
    head.append(el('span', 'job-kind', '后续指令'));
    head.append(el('span', 'chip ' + toneFor(status), labelFor(JOB_LABELS, status)));
    const stamp = job.created || job.updated;
    if (stamp) head.append(el('span', 'job-time', stampText(stamp)));
    card.append(head);

    if (status === 'queued' || status === 'waiting') {
      const seconds = Number(job.waiting_seconds);
      let wait = job.waiting_reason || '等待当前轮结束';
      if (isFinite(seconds)) wait += ' · 已等待 ' + seconds + ' 秒';
      wait += '（尚未送达）';
      card.append(el('div', 'job-wait', wait));
    } else if (status === 'sending') {
      card.append(el('div', 'job-wait sending', '正在续接原会话；回复完成前，状态以电脑返回为准。'));
    } else if (status === 'needs_attention') {
      card.append(el('div', 'job-wait attention', '此条后续指令需要处理；请查看错误信息或电脑端提示。'));
    } else if (status === 'failed' && !job.error) {
      card.append(el('div', 'job-error', '本次发送未完成，状态为发送失败。'));
    }

    if (status === 'queued' || status === 'waiting') {
      const cancel = el('button', 'small-btn cancel-job-btn', '取消待发送');
      cancel.type = 'button';
      cancel.disabled = state.cancelling.has(String(job.id));
      cancel.onclick = () => cancelJob(job);
      card.append(cancel);
    }

    const instruction = el('div', 'job-instruction');
    instruction.append(el('div', 'job-field-label', '我的指令'));
    if (job.text) instruction.append(el('div', 'job-text', job.text));
    const attachments = Array.isArray(job.attachments) ? job.attachments : [];
    if (attachments.length) {
      const list = el('div', 'attachment-list');
      for (const name of attachments) {
        if (!name) continue;
        const item = el('div', 'attachment-item');
        const href = replyInputHref(job.id, name);
        const label = displayFileName(name);
        if (/\.(png|jpe?g|webp)$/i.test(String(name))) {
          const image = el('img');
          image.src = href;
          image.alt = label;
          image.loading = 'lazy';
          item.append(image);
        }
        const link = el('a', '', label);
        link.href = href;
        link.target = '_blank';
        link.rel = 'noopener';
        item.append(link);
        list.append(item);
      }
      if (list.firstChild) instruction.append(list);
    }

    let resultBlock = null;
    if (job.result !== undefined && job.result !== null && job.result !== '' && claimResult(job.result)) {
      resultBlock = el('div', 'job-result');
      resultBlock.append(el('div', 'job-result-label', 'Agent 回复结果'));
      resultBlock.append(el('div', 'result-box', formatResult(job.result)));
    }

    if (completed) {
      const fold = el('details', 'job-fold');
      fold.append(el('summary', '', resultBlock ? '我的指令与回复结果（已完成）' : '我的指令（已完成）'));
      fold.append(instruction);
      if (resultBlock) fold.append(resultBlock);
      card.append(fold);
    } else {
      card.append(instruction);
      if (resultBlock) card.append(resultBlock);
    }

    if (job.error) card.append(el('div', 'job-error', job.error));
    const meta = [];
    if (job.status) meta.push(['原始状态', job.status]);
    if (job.created) meta.push(['创建', stampText(job.created)]);
    if (job.updated) meta.push(['更新', stampText(job.updated)]);
    if (job.attempts !== undefined && job.attempts !== null) meta.push(['尝试次数', job.attempts]);
    if (job.started_at) meta.push(['开始处理', stampText(job.started_at)]);
    if (job.last_attempt_at) meta.push(['最近尝试', stampText(job.last_attempt_at)]);
    if (job.next_attempt_at) meta.push(['下次尝试', stampText(job.next_attempt_at)]);
    if (job.finished_at) meta.push(['结束', stampText(job.finished_at)]);
    if (meta.length) {
      const details = el('details', 'fold job-details');
      details.append(el('summary', '', '时间与状态详情'));
      const list = el('dl');
      for (const row of meta) {
        const line = el('div', 'raw-row');
        line.append(el('dt', '', row[0]));
        line.append(el('dd', '', row[1]));
        list.append(line);
      }
      details.append(list);
      card.append(details);
    }
    return card;
  }

  function updateComposer() {
    const target = state.target;
    const composer = $('composer');
    if (!composer) return;
    const coding=state.conversation?.task?.agent==='codex-deepseek-code';
    for(const id of ['composerInput','sendButton','attachButton'])$(id).hidden=coding;
    if(coding){for(const id of ['newSelects','modeSelect','agentSelect'])if($(id))$(id).hidden=true;composer.hidden=false;$('sendButton').disabled=true;$('fileInput').disabled=true;$('sessionModelHint').textContent='项目进度';setLine('composerStatus','');setLine('composerNotice','项目进度、停止和成果都在上方；首版不向某一模型单独续发。');return;}
    const nativeResume = isDeepSeekNative() && state.conversation?.resume_supported === true;
    const deepSeekReadOnly = !!target && target.kind !== 'new' && target.partition === 'deepseek' && !nativeResume;
    composer.hidden = !target || deepSeekReadOnly;
    renderAttachments();
    if (!target) return;
    if (deepSeekReadOnly) {
      $('sessionModelHint').textContent=state.conversation?.resume_label||'只读';
      $('sendButton').disabled = true;
      $('sendButton').title = DEEPSEEK_REPLY_HINT;
      $('attachButton').disabled = true;
      $('fileInput').disabled = true;
      setLine('composerNotice', '');
      setLine('composerStatus', '');
      return;
    }

    const isNew = target.kind === 'new';
    const flashHistory = !isNew && isFlashConversation() && !nativeResume;
    const selectedAgent = normalizeAgent(state.selectedAgent);
    const selectedFlash = selectedAgent === FLASH_AGENT;
    const modeSelect = $('modeSelect');
    const agentSelect = $('agentSelect');
    const newSelects = $('newSelects');
    if (newSelects) newSelects.hidden = !isNew;
    if (modeSelect) modeSelect.hidden = !isNew;
    if (agentSelect) agentSelect.hidden = !isNew;

    if (isNew) {
      if (agentSelect) {
        agentSelect.value = selectedAgent;
        agentSelect.title = '可用仅表示本机运行器存在，不保证登录或额度。';
        const flashOption = agentSelect.querySelector('option[value="' + FLASH_AGENT + '"]');
        const flashName = agentName(FLASH_AGENT);
        if (flashOption) {
          flashOption.textContent = flashName;
          flashOption.disabled = state.agentsAvailable[FLASH_AGENT] !== true;
          flashOption.title = state.agentsAvailable[FLASH_AGENT] === true
            ? '仅表示本机运行器存在，不保证登录或额度'
            : '本机未找到 DeepSeek Flash 运行器';
        }
      }
      if (modeSelect) {
        modeSelect.value = selectedFlash ? 'task' : modeSelect.value;
        const reviewOption = modeSelect.querySelector('option[value="review"]');
        if (reviewOption) reviewOption.disabled = selectedFlash;
        modeSelect.title = selectedFlash ? 'Flash 首版仅支持普通新任务' : '';
      }
    }

    const hintTitle = $('newHintTitle');
    const hintText = $('newHintText');
    const hintTip = $('newHintTip');
    if (hintTitle) hintTitle.textContent = selectedFlash && isNew ? '新 Flash 任务' : '新 Codex 会话';
    if (hintText) hintText.textContent = selectedFlash && isNew ? NEW_HINT_FLASH_TEXT : NEW_HINT_TEXT;
    if (hintTip) hintTip.textContent = selectedFlash && isNew ? NEW_HINT_FLASH_TIP : NEW_HINT_TIP;

    $('attachButton').hidden = nativeResume;
    const attachLabel = isNew ? '添加图片或文件' : '添加图片';
    const attachText = $('attachButton').querySelector('.attach-label');
    if (attachText) attachText.textContent = isNew ? '附件' : '图片';
    $('attachButton').title = attachLabel;
    $('attachButton').setAttribute('aria-label', attachLabel);
    if (isNew) $('fileInput').removeAttribute('accept');
    else $('fileInput').setAttribute('accept', 'image/png,image/jpeg,image/webp');
    $('composerInput').placeholder = isNew
      ? (selectedFlash ? '描述 Flash 任务，可附图片或文件…' : '描述目标，可附图片或文件…')
      : (flashHistory ? 'Flash 首版不支持在此续聊' : '输入后续指令，可附图片…');
    $('composerInput').readOnly = state.phase !== 'idle' || flashHistory;

    const text = $('composerInput').value;
    const busy = state.phase !== 'idle';
    const connecting = state.connected === null;
    const offline = state.connected === false;
    const threadId = nativeResume ? target.sessionId : currentThreadId();
    let block = '';
    let reason = '';
    let canSend = false;

    if (busy) {
      block = state.phase === 'uploading' ? '正在上传附件…' : (state.phase === 'creating' ? '正在开始任务…' : '正在发送…');
      reason = block;
    } else if (connecting) {
      block = '正在连接电脑…';
      reason = block;
    } else if (offline) {
      block = state.authError ? '链接已失效，请从电脑重新打开。' : '连接中断，已暂停发送。恢复后会自动刷新。';
      reason = block;
    } else if (isNew) {
      const mode = selectedFlash ? 'task' : (modeSelect && modeSelect.value === 'review' ? 'review' : 'task');
      if (!agentAvailable(selectedAgent)) {
        block = selectedFlash
          ? (state.agentsAvailable[FLASH_AGENT] === false
            ? '本机未找到 DeepSeek Flash 运行器，暂不可用。'
            : 'DeepSeek Flash 当前不可用：未读取到本机运行器。')
          : '电脑未找到可用的 Agent。';
        reason = block;
      } else if (mode === 'review' && !state.files.length) {
        block = '只读审查需要至少一个附件。';
        reason = block;
      } else if (!text.trim() && !state.files.length) {
        reason = '输入目标，或添加图片／文件。';
      } else if (!text.trim() && mode !== 'review' && !state.files.every((item) => supportedImage(item.file))) {
        block = '请填写任务说明；只有图片可以不带文字说明。';
        reason = block;
      } else {
        canSend = true;
      }
    } else if (flashHistory) {
      block = FLASH_REPLY_HINT;
      reason = block;
    } else if (!threadId) {
      block = '正在建立会话，稍后可继续发送。';
      reason = block;
    } else if (state.loading) {
      block = '正在读取会话…';
      reason = block;
    } else if (!state.canReply) {
      block = '当前轮尚未结束，结束后可继续发送。';
      reason = block;
    } else if (!text.trim() && !state.files.length) {
      reason = '输入文字或添加图片后发送。';
    } else {
      canSend = true;
    }

    $('sendButton').disabled = !canSend;
    $('sendButton').textContent = '发送';
    $('sendButton').title = reason;
    const canAttach = isNew || !!threadId;
    $('attachButton').disabled = busy || offline || connecting || !canAttach;
    if (modeSelect) modeSelect.disabled = busy;
    if (agentSelect) agentSelect.disabled = busy;
    $('fileInput').disabled = busy || !canAttach;
    let notice = block;
    let tone = block ? 'warn' : '';
    if (!notice && isNew && selectedFlash && state.agentsAvailable[FLASH_AGENT] === false) {
      notice = 'DeepSeek Flash 暂不可用：本机未找到运行器。';
      tone = 'warn';
    } else if (!notice && isNew && selectedFlash) {
      notice = 'Flash 首版仅普通任务；' + FLASH_IMAGE_NOTE
        + (state.partition === 'codex' ? ' 发送成功后切到 DeepSeek 分区。' : '');
      tone = '';
    }
    if(nativeResume){notice=state.conversation.reply_hint||'继续原会话，会使用原工作目录及模型额度；本版仅支持文字。';tone='';$('composerInput').placeholder='继续这条DeepSeek会话…';$('sendButton').textContent='继续会话';$('sessionModelHint').textContent=state.canReply?'可继续':'处理中';}
    else if(isDeepSeekNative())$('sessionModelHint').textContent=state.conversation?.resume_label||'只读';
    setLine('composerNotice', notice, tone);
  }

  function renderAll(options) {
    const opts = options || {};
    const messages = orderedMessages();
    state.assistantTexts = buildAssistantTexts(messages);
    state.historySig = messageSignature(messages);
    state.resultTokens = new Set();
    renderHeader();
    renderEmpty();
    renderStatus();
    renderProgress();
    renderMessages(messages, opts);
    updateHistoryStatus();
    renderJobs();
    renderList();
    updateComposer();
    updateOpenCodexButton();
    if (state.scrollPending) {
      state.scrollPending = false;
      const view = $('conversationView');
      view.scrollTop = view.scrollHeight;
    }
  }

  /* ---------- actions ---------- */

  function setPhase(phase) {
    state.phase = phase;
    updateInteraction();
    updateComposer();
  }

  async function sendNew() {
    if (state.phase !== 'idle') return;
    if (state.connected !== true) { setLine('composerStatus', '电脑尚未连接，请稍后重试。', 'error'); return; }
    const input = $('composerInput');
    const text = input.value;
    const agent = normalizeAgent(state.selectedAgent);
    const mode = agent === FLASH_AGENT ? 'task' : ($('modeSelect').value === 'review' ? 'review' : 'task');
    const files = state.files.slice();
    const newTargetKey = state.target ? state.target.key : ('new:' + state.partition);
    if (!text.trim() && !files.length) { setLine('composerStatus', '请输入目标，或添加图片／文件。', 'error'); return; }
    if (mode === 'review' && !files.length) { setLine('composerStatus', '只读审查需要至少一个附件。', 'error'); return; }
    if (!text.trim() && mode !== 'review' && !files.every((item) => supportedImage(item.file))) {
      setLine('composerStatus', '请填写任务说明；只有图片可以不带文字说明。', 'error');
      return;
    }
    if (!agentAvailable(agent)) {
      setLine('composerStatus', agent === FLASH_AGENT
        ? '本机未找到 DeepSeek Flash 运行器，暂不可用。'
        : '电脑未找到可用的 Agent。', 'error');
      return;
    }

    let pendingRefresh = '';
    setPhase('uploading');
    setLine('composerStatus', '');
    try {
      for (let index = 0; index < files.length; index += 1) {
        const item = files[index];
        if (item.uploaded) continue;
        setLine('composerStatus', '正在上传附件 ' + (index + 1) + ' / ' + files.length + '：' + item.name);
        item.uploaded = await uploadFile(item);
      }
      const key = JSON.stringify(['new', agent, mode, text, files.map((item) => item.id)]);
      if (!state.pendingRequests.has(key)) state.pendingRequests.set(key, uid());
      const requestId = state.pendingRequests.get(key);
      setPhase('creating');
      setLine('composerStatus', agent === FLASH_AGENT ? '正在创建独立 Flash 任务…' : '正在创建独立任务…');
      const task = await request('/api/bot/tasks', postJson({
        text: text,
        attachments: files.map((item) => item.uploaded && item.uploaded.name).filter(Boolean),
        mode: mode,
        agent: agent,
        request_id: requestId
      }));
      if (!task || task.id === undefined || task.id === null) throw new Error('任务已提交，但返回格式不完整');
      if ((agent === FLASH_AGENT && task.agent !== FLASH_AGENT) || (task.agent && task.agent !== agent)) {
        throw new Error('返回任务的模型与本次选择不一致，未切换会话；请先核对任务队列，勿重复发送。');
      }
      state.pendingRequests.delete(key);

      if (input.value === text) {
        input.value = '';
        state.drafts.delete(newTargetKey);sessionRecovery.remember(newTargetKey,'');
      }
      const uploadedNames = files.map((item) => item.uploaded && item.uploaded.name).filter(Boolean);
      for (const item of files) if (item.url) URL.revokeObjectURL(item.url);
      setTargetFiles([]);
      autoGrow();
      renderAttachments();

      const createdAgent = task.agent === FLASH_AGENT || (!task.agent && agent === FLASH_AGENT) ? FLASH_AGENT : 'codex';
      const createdPartition = createdAgent === FLASH_AGENT ? 'deepseek' : 'codex';
      const createdTask = Object.assign({}, task, { agent: createdAgent });
      if (!normalise(createdTask.goal)) createdTask.goal = text;
      if (!Array.isArray(createdTask.attachments) || !createdTask.attachments.length) createdTask.attachments = uploadedNames;
      if (createdAgent === FLASH_AGENT) createdTask.remote_session = '';
      state.tasks = [createdTask].concat(state.tasks.filter((item) => String(item.id) !== String(task.id)));
      if (state.partition !== createdPartition) {
        state.partition = createdPartition;
        state.selectedAgent = defaultAgentForPartition(createdPartition);
      }
      rebuildAllLists();
      syncPartitionUI();
      const createdView = viewFor(createdPartition);
      if (!createdView.loaded) pendingRefresh = createdPartition;

      const target = {
        kind: 'task',
        key: 'task:' + String(task.id),
        taskId: String(task.id),
        agent: createdAgent,
        threadId: createdAgent === FLASH_AGENT ? null : (createdTask.remote_session ? String(createdTask.remote_session) : null),
        partition: createdPartition,
        title: cleanTitle(createdTask.title || text)
      };
      const provisional = {
        task: createdTask,
        provider: createdAgent === FLASH_AGENT ? FLASH_AGENT : 'codex',
        thread_id: target.threadId,
        title: target.title,
        status: createdTask.status || 'queued',
        status_hint: createdAgent === FLASH_AGENT ? 'Flash 任务已入队，等待本机运行器执行…' : '任务已入队，等待建立会话…',
        history: null,
        jobs: [],
        can_reply: false,
        reply_hint: createdAgent === FLASH_AGENT ? FLASH_REPLY_HINT : ''
      };
      openTarget(target, { skipDraft: true, conversation: provisional });
      setLine('composerStatus', createdAgent === FLASH_AGENT ? FLASH_REPLY_HINT : '任务已创建，正在建立会话…', createdAgent === FLASH_AGENT ? 'warn' : 'ok');
    } catch (error) {
      if (state.phase === 'uploading') {
        setLine('composerStatus', '上传失败：' + errText(error) + '。内容已保留，可重试。', 'error');
      } else {
        setLine('composerStatus', '提交失败或未确认：' + errText(error) + '。内容已保留，可重试；同一内容会复用请求编号，避免重复执行。', 'error');
      }
    } finally {
      setPhase('idle');
      if (pendingRefresh) loadList(pendingRefresh, true);
    }
  }

  async function sendDeepSeekReply() {
    if(state.phase!=='idle'||state.connected!==true||!state.canReply||!state.conversation?.resume_supported)return;
    const input=$('composerInput'),text=input.value,sessionId=state.target.sessionId,targetKey=state.target.key;
    if(!text.trim())return;
    let requestId;
    try{requestId=sessionRecovery.prepare(targetKey,text);}catch(error){setLine('composerStatus',errText(error),'error');return;}
    setPhase('replying');
    try{
      const result=await request('/api/bot/deepseek/reply',postJson({source_id:sourceId,session_id:sessionId,text,request_id:requestId}));
      if(input.value===text&&state.target?.key===targetKey){input.value='';state.drafts.delete(targetKey);sessionRecovery.remember(targetKey,'');}
      sessionRecovery.confirm(targetKey,text,requestId);
      await loadConversation({});
      setLine('composerStatus',result.text||'续聊已提交，请等待结果。','ok');
    }catch(error){setLine('composerStatus','未确认送达，原文已保留。请先刷新核对，不要重复提交。','error');}
    finally{setPhase('idle');}
  }

  async function sendReply() {
    if (state.phase !== 'idle') return;
    if (isDeepSeekNative()) { await sendDeepSeekReply();return; }
    if (isFlashConversation()) {
      setLine('composerStatus', FLASH_REPLY_HINT, 'warn');
      return;
    }
    if (state.connected !== true) { setLine('composerStatus', '电脑尚未连接，请稍后重试。', 'error'); return; }
    const threadId = currentThreadId();
    if (!threadId) {
      setLine('composerStatus', '正在建立会话，稍后可继续发送。', 'error');
      return;
    }
    if (!state.canReply) {
      setLine('composerStatus', '当前轮尚未结束，结束后可继续发送。', 'error');
      return;
    }
    const input = $('composerInput');
    const targetKey = state.target ? state.target.key : '';
    const text = input.value;
    const files = state.files.slice();
    if (!text.trim() && !files.length) {
      setLine('composerStatus', '请输入文字或添加图片。', 'error');
      return;
    }

    const key = JSON.stringify(['reply', threadId, text, files.map((item) => item.id)]);
    if (!state.pendingRequests.has(key)) state.pendingRequests.set(key, uid());
    const requestId = state.pendingRequests.get(key);
    setPhase('replying');
    setLine('composerStatus', '');
    try {
      for (let index = 0; index < files.length; index += 1) {
        const item = files[index];
        if (item.uploaded) continue;
        setLine('composerStatus', '正在上传图片 ' + (index + 1) + ' / ' + files.length + '：' + item.name);
        item.uploaded = await uploadFile(item);
      }
      const attachments = files.map((item) => item.uploaded && item.uploaded.name).filter(Boolean);
      setLine('composerStatus', '正在发送…');
      const result = await request('/api/bot/history/reply', postJson({
        source_id: sourceId,
        thread_id: threadId,
        text: text,
        attachments: attachments,
        request_id: requestId
      }));
      if (!result || result.kind !== 'reply' || !result.job || result.job.id === undefined) {
        throw new Error('回复回执格式不正确');
      }
      if (result.job.thread_id !== undefined && result.job.thread_id !== null && String(result.job.thread_id) !== String(threadId)) {
        throw new Error('返回的目标会话不匹配，指令未清空');
      }
      state.pendingRequests.delete(key);
      if (input.value === text) {
        input.value = '';
        state.drafts.delete(targetKey);sessionRecovery.remember(targetKey,'');
        autoGrow();
      }
      const sentIds = new Set(files.map((item) => item.id));
      if (state.target && state.target.key === targetKey) {
        setTargetFiles(state.files.filter((item) => !sentIds.has(item.id)));
        renderAttachments();
      } else {
        const remaining = (state.fileDrafts.get(targetKey) || []).filter((item) => !sentIds.has(item.id));
        state.fileDrafts.set(targetKey, remaining);
      }
      for (const item of files) if (item.url) URL.revokeObjectURL(item.url);
      if (state.conversation) {
        const jobs = Array.isArray(state.conversation.jobs) ? state.conversation.jobs.slice() : [];
        const index = jobs.findIndex((job) => String(job.id) === String(result.job.id));
        if (index >= 0) jobs[index] = result.job;
        else jobs.unshift(result.job);
        state.conversation.jobs = jobs;
        state.jobs = jobs;
        state.jobsSig = '';
        renderJobs();
        renderStatus();
      }
      setLine('composerStatus', result.text || '已加入队列，尚未送达。', 'ok');
    } catch (error) {
      setLine('composerStatus', '提交失败或未确认：' + errText(error) + '。文字和图片已保留，可重试；同一内容会复用请求编号，避免重复执行。', 'error');
    } finally {
      setPhase('idle');
    }
  }

  async function cancelJob(job) {
    const id = String(job && job.id !== undefined ? job.id : '');
    if (!id || state.cancelling.has(id)) return;
    const targetKey = state.target ? state.target.key : '';
    const revision = state.viewRevision;
    state.cancelling.add(id);
    state.jobsSig = '';
    renderJobs();
    setLine('jobsError', '');
    try {
      const data = await request((isDeepSeekNative()?'/api/bot/deepseek/replies/':'/api/bot/replies/') + encodeURIComponent(id) + '/cancel', postJson({ source_id: sourceId }));
      if (!state.target || state.target.key !== targetKey || revision !== state.viewRevision) return;
      if (data && data.job) {
        const jobs = (state.conversation && Array.isArray(state.conversation.jobs)) ? state.conversation.jobs : [];
        const index = jobs.findIndex((entry) => String(entry.id) === id);
        if (index >= 0) jobs[index] = data.job;
        if (state.conversation) state.conversation.jobs = jobs;
        state.jobs = jobs;
      } else {
        await loadConversation({});
      }
      setLine('composerStatus', '已取消待发送消息。', 'ok');
      renderStatus();
    } catch (error) {
      if (state.target && state.target.key === targetKey && revision === state.viewRevision) {
        setLine('jobsError', '取消失败：' + errText(error), 'error');
      }
    } finally {
      state.cancelling.delete(id);
      if (state.target && state.target.key === targetKey && revision === state.viewRevision) {
        state.jobsSig = '';
        renderJobs();
      }
    }
  }

  async function cancelFlashTask(taskId) {
    const id = String(taskId === undefined || taskId === null ? '' : taskId);
    const target = state.target;
    if (!id || !target || target.kind !== 'task' || String(target.taskId) !== id || state.cancellingTask) return;
    const conversationTask = state.conversation && state.conversation.task;
    if ((!isFlashConversation()&&conversationTask?.agent!=='codex-deepseek-code') || !conversationTask || String(conversationTask.id) !== id) return;
    if (conversationTask.status !== 'queued' && conversationTask.status !== 'running') return;
    const targetKey = target.key;
    const revision = state.viewRevision;
    state.cancellingTask = id;
    state.taskCancelError = '';
    state.progressSig = '';
    state.messagesDomSig = null;
    renderAll();
    try {
      await request('/api/tasks/' + encodeURIComponent(id) + '/cancel', postJson({}));
      if (!state.target || state.target.key !== targetKey || revision !== state.viewRevision) return;
      state.progressSig = '';
      await loadConversation({});
    } catch (error) {
      if (state.target && state.target.key === targetKey && revision === state.viewRevision) {
        state.taskCancelError = '停止失败：' + errText(error) + '。不会自动重试。';
        state.messagesDomSig = null;
        renderAll();
      }
    } finally {
      if (state.target && state.target.key === targetKey && revision === state.viewRevision) {
        state.cancellingTask = '';
        state.progressSig = '';
        state.messagesDomSig = null;
        renderAll();
      } else {
        state.cancellingTask = '';
      }
    }
  }

  /* ---------- menu / pair ---------- */

  function setMenuStatus(text, errorTone) {
    const node = $('menuStatus');
    if (!node) return;
    node.textContent = text || '';
    node.hidden = !text;
    node.classList.toggle('error', !!errorTone);
  }

  function desktopOpenTitle() {
    if (state.target && state.target.title) return cleanTitle(state.target.title);
    if (state.conversation && state.conversation.title) return cleanTitle(state.conversation.title);
    return '当前会话';
  }

  function updateOpenCodexButton() {
    const button = $('menuOpenCodex');
    if (!button) return;
    const open = state.desktopOpen;
    const nativeDeepSeek = isDeepSeekNative();
    const flash = isFlashConversation();
    const note = $('menuOpenCodexNote');
    if (note) note.textContent = nativeDeepSeek ? MENU_OPEN_DEEPSEEK_NOTE : (flash ? MENU_OPEN_FLASH_NOTE : MENU_OPEN_CODEX_NOTE);
    let reason = '';
    if (nativeDeepSeek) reason = '本机 Harness 历史只读，不支持在电脑 Codex 中打开。';
    else if (flash) reason = 'Flash 任务在本工作台查看；不支持在电脑 Codex 中打开。';
    else if (open.posting) reason = '正在提交打开请求…';
    else if (open.unresolved && (open.polling || open.timer)) reason = '正在等待电脑确认上次请求…';
    else if (open.unresolved) reason = '上次请求尚未确认；重新打开菜单可继续查询。';
    else if (state.connected === null) reason = '正在连接电脑…';
    else if (state.connected !== true) reason = '电脑未连接，暂时不能打开。';
    else if (state.phase !== 'idle') reason = '正在提交图片或消息，完成后再试。';
    else if (!currentThreadId()) reason = '当前会话还没有建立，暂时不能打开。';
    button.disabled = !!reason;
    button.title = reason || '在电脑 Codex 中打开当前会话';
  }

  function renderDesktopOpenStatus() {
    const open = state.desktopOpen;
    if (!open.message) return false;
    const prefix = open.title ? '「' + open.title + '」 ' : '';
    const failure = open.pollError || open.status === 'failed' || open.status === 'cancelled' || open.status === 'expired';
    setMenuStatus(prefix + open.message, failure);
    return true;
  }

  function finishDesktopOpen(status, message, errorTone) {
    const open = state.desktopOpen;
    open.posting = false;
    open.polling = false;
    open.unresolved = false;
    open.status = String(status || '');
    open.message = message || DESKTOP_OPEN_FALLBACK[open.status] || '';
    open.pollError = !!errorTone;
    if (open.timer) {
      window.clearTimeout(open.timer);
      open.timer = null;
    }
    if (open.expiryTimer) {
      window.clearTimeout(open.expiryTimer);
      open.expiryTimer = null;
    }
    renderDesktopOpenStatus();
    updateOpenCodexButton();
  }

  function applyDesktopOpenResult(result) {
    const open = state.desktopOpen;
    const status = String((result && result.status) || 'pending');
    const message = result && result.message ? String(result.message) : (DESKTOP_OPEN_FALLBACK[status] || DESKTOP_OPEN_FALLBACK.pending);
    open.posting = false;
    open.polling = false;
    open.pollError = false;
    open.status = status;
    open.message = message;
    if (isDesktopOpenTerminal(status)) {
      finishDesktopOpen(status, message, status === 'failed' || status === 'cancelled' || status === 'expired');
      return;
    }
    open.unresolved = true;
    if (!open.expiryTimer) {
      const requestId = open.requestId;
      open.expiryTimer = window.setTimeout(() => {
        open.expiryTimer = null;
        if (open.unresolved && open.requestId === requestId) {
          finishDesktopOpen('expired', '打开状态查询已到期，是否打开请以电脑为准；确认后可重新尝试。', true);
        }
      }, Math.max(0, open.deadline - Date.now()));
    }
    renderDesktopOpenStatus();
    updateOpenCodexButton();
  }

  function scheduleDesktopOpenPoll(delay) {
    const open = state.desktopOpen;
    if (!open.unresolved || !open.requestId || open.timer) return;
    const remaining = open.deadline - Date.now();
    if (remaining <= 0) {
      finishDesktopOpen('expired', DESKTOP_OPEN_FALLBACK.expired, true);
      return;
    }
    open.timer = window.setTimeout(pollDesktopOpen, Math.max(0, Math.min(delay, remaining)));
    updateOpenCodexButton();
  }

  async function pollDesktopOpen() {
    const open = state.desktopOpen;
    open.timer = null;
    if (!open.unresolved || !open.requestId) {
      open.polling = false;
      updateOpenCodexButton();
      return;
    }
    if (Date.now() >= open.deadline) {
      finishDesktopOpen('expired', DESKTOP_OPEN_FALLBACK.expired, true);
      return;
    }
    open.polling = true;
    const pollRequestId = open.requestId;
    updateOpenCodexButton();
    try {
      const data = await request('/api/bot/desktop-open/' + encodeURIComponent(pollRequestId));
      if (open.requestId !== pollRequestId) return;
      if (!open.unresolved) {
        open.polling = false;
        return;
      }
      applyDesktopOpenResult(data || {});
      if (open.unresolved) {
        const remaining = open.deadline - Date.now();
        if (remaining <= 0) finishDesktopOpen('expired', DESKTOP_OPEN_FALLBACK.expired, true);
        else scheduleDesktopOpenPoll(Math.min(1000, remaining));
      }
    } catch (error) {
      if (open.requestId !== pollRequestId) return;
      open.polling = false;
      if (!open.unresolved) return;
      if (Date.now() >= open.deadline) {
        finishDesktopOpen('expired', DESKTOP_OPEN_FALLBACK.expired, true);
        return;
      }
      open.pollError = true;
      open.message = '状态查询失败：' + errText(error) + '。可关闭后重新打开菜单继续查询。';
      renderDesktopOpenStatus();
      updateOpenCodexButton();
    }
  }

  function resumeDesktopOpenIfNeeded() {
    const open = state.desktopOpen;
    if (!open.unresolved || !open.requestId || open.polling || open.timer) return;
    if (Date.now() >= open.deadline) {
      finishDesktopOpen('expired', DESKTOP_OPEN_FALLBACK.expired, true);
      return;
    }
    if (open.pollError) {
      open.pollError = false;
      open.message = '正在重新查询打开状态…';
      renderDesktopOpenStatus();
    }
    scheduleDesktopOpenPoll(0);
  }

  async function requestDesktopOpen() {
    const open = state.desktopOpen;
    if (open.posting || open.unresolved) {
      updateOpenCodexButton();
      return;
    }
    if (isDeepSeekNative()) {
      setMenuStatus(DEEPSEEK_REPLY_HINT);
      updateOpenCodexButton();
      return;
    }
    if (isFlashConversation()) {
      setMenuStatus(MENU_OPEN_FLASH_NOTE);
      updateOpenCodexButton();
      return;
    }
    const threadId = currentThreadId();
    if (!threadId) {
      setMenuStatus('当前会话还没有建立，暂时不能打开。');
      updateOpenCodexButton();
      return;
    }
    if (state.connected !== true) {
      setMenuStatus('电脑未连接，暂时不能打开。', true);
      updateOpenCodexButton();
      return;
    }
    if (state.phase !== 'idle') {
      setMenuStatus('正在提交图片或消息，完成后再试。');
      updateOpenCodexButton();
      return;
    }
    const started = Date.now();
    open.posting = true;
    open.unresolved = true;
    open.polling = false;
    open.pollError = false;
    open.requestId = '';
    open.status = 'pending';
    open.threadId = String(threadId);
    open.title = desktopOpenTitle();
    open.message = '正在向电脑发送打开请求…';
    open.deadline = started + 20000;
    if (open.timer) {
      window.clearTimeout(open.timer);
      open.timer = null;
    }
    renderDesktopOpenStatus();
    updateOpenCodexButton();
    try {
      const result = await request('/api/bot/desktop-open', postJson({ thread_id: open.threadId }));
      if (!result || !result.request_id) {
        finishDesktopOpen('failed', '电脑返回的打开请求不完整，可重新尝试。', true);
        return;
      }
      open.requestId = String(result.request_id);
      const expires = parseStamp(result.expires_at);
      open.deadline = Math.min(started + 20000, expires ? expires.getTime() + 3000 : Infinity);
      applyDesktopOpenResult(result);
      if (open.unresolved) {
        const remaining = open.deadline - Date.now();
        if (remaining <= 0) finishDesktopOpen('expired', DESKTOP_OPEN_FALLBACK.expired, true);
        else scheduleDesktopOpenPoll(Math.min(1000, remaining));
      }
    } catch (error) {
      finishDesktopOpen('failed', '提交失败或未确认：' + errText(error) + '，可重新尝试。', true);
    }
  }

  async function refreshAll() {
    if (state.phase !== 'idle') {
      setMenuStatus('操作进行中，请稍后再刷新。');
      return;
    }
    setMenuStatus('正在刷新…');
    const tasks = [loadList(state.partition, true)];
    if (state.target && state.target.kind !== 'new') tasks.push(loadConversation({}));
    await Promise.allSettled(tasks);
    if (state.desktopOpen.unresolved) {
      renderDesktopOpenStatus();
    } else {
      setMenuStatus(state.connected === false ? '刷新失败，连接中断。' : '已刷新。', state.connected === false);
    }
  }
  function isTailnetHost(url) {
    try {
      const parts = new URL(url).hostname.split('.').map((part) => Number(part));
      return parts.length === 4 && parts[0] === 100 && parts[1] >= 64 && parts[1] <= 127;
    } catch (error) {
      return false;
    }
  }
  function networkOptionLabel(url, urls) {
    const tailnet = isTailnetHost(url);
    const kind = tailnet ? 'Tailscale 远程' : '同一 Wi-Fi';
    const same = urls.filter((entry) => isTailnetHost(entry) === tailnet);
    if (same.length <= 1) return kind;
    return kind + ' ' + (same.indexOf(url) + 1);
  }
  async function openPair() {
    const dialog = $('pairDialog');
    if (!dialog.open) dialog.showModal();
    $('pairStatus').classList.remove('error');
    $('pairStatus').textContent = '正在读取连接信息…';
    $('address').textContent = '';
    $('qr').hidden = true;
    clear($('network'));
    try {
      const info = await request('/api/info');
      const urls = Array.isArray(info && info.urls) ? info.urls : [];
      const select = $('network');
      urls.forEach((url, index) => {
        const option = el('option', '', networkOptionLabel(url, urls));
        option.value = String(index);
        select.append(option);
      });
      const show = () => {
        const index = Number(select.value || 0);
        if (!urls.length) {
          $('qr').hidden = true;
          $('address').textContent = '没有可用的连接地址，请检查电脑网络。';
          return;
        }
        $('qr').hidden = false;
        $('qr').src = api('/qr.svg?index=' + index + '&address=' + encodeURIComponent(urls[index]));
        $('address').textContent = urls[index] || '';
      };
      select.onchange = show;
      show();
      $('pairStatus').textContent = '';
    } catch (error) {
      $('pairStatus').textContent = errText(error);
      $('pairStatus').classList.add('error');
    }
  }

  /* ---------- diagnostics ---------- */

  function setDiagnosticsBusy(busy) {
    const run = $('runDiagnostics');
    if (run) {
      run.disabled = !!busy;
      run.textContent = busy ? '检查中…' : '重新检查';
    }
    const copy = $('copyDiagnostics');
    if (copy) copy.disabled = !!busy || !state.diagnostics.summary;
  }

  function resetDiagnosticsView(statusText, tone, listText, summaryText) {
    const d = state.diagnostics;
    const fixedSummary = typeof summaryText === 'string' ? summaryText : '';
    d.summary = fixedSummary;
    const summary = $('diagnosticsSummary');
    if (summary) summary.value = fixedSummary;
    const details = $('diagnosticsSummaryDetails');
    if (details) {
      details.open = false;
      details.hidden = !fixedSummary;
    }
    const box = $('diagnosticsChecks');
    if (box) {
      clear(box);
      if (listText) box.append(el('p', 'diag-empty', listText));
    }
    setLine('diagnosticsStatus', statusText || '', tone || '');
    const copy = $('copyDiagnostics');
    if (copy) copy.disabled = !fixedSummary;
  }

  function renderDiagnosticsChecks(checks) {
    const box = $('diagnosticsChecks');
    if (!box) return;
    clear(box);
    const list = Array.isArray(checks) ? checks : [];
    for (const check of list) {
      if (!check || typeof check !== 'object') continue;
      const status = String(check.status || '').toLowerCase();
      const key = Object.prototype.hasOwnProperty.call(DIAGNOSTICS_LABELS, status) ? status : 'unknown';
      const card = el('div', 'diag-check');
      const head = el('div', 'diag-check-head');
      head.append(el('span', 'chip ' + DIAGNOSTICS_TONES[key], DIAGNOSTICS_LABELS[key]));
      head.append(el('span', 'diag-check-label', check.label || '检查项'));
      card.append(head);
      const detail = normalise(check.detail);
      if (detail.trim()) card.append(el('p', 'diag-check-detail', detail));
      const action = normalise(check.action);
      if (action.trim()) card.append(el('div', 'diag-check-action', action));
      box.append(card);
    }
    if (!box.firstChild) box.append(el('p', 'diag-empty', '本次没有返回检查项。'));
  }

  function applyDiagnostics(data) {
    const payload = data && typeof data === 'object' ? data : {};
    const d = state.diagnostics;
    const summary = typeof payload.summary === 'string' ? normalise(payload.summary) : '';
    renderDiagnosticsChecks(payload.checks);
    d.summary = summary;
    const textarea = $('diagnosticsSummary');
    if (textarea) textarea.value = summary;
    const details = $('diagnosticsSummaryDetails');
    if (details) {
      details.open = false;
      details.hidden = !summary;
    }
    const copy = $('copyDiagnostics');
    if (copy) copy.disabled = !summary;
    const stamp = payload.checked_at === undefined || payload.checked_at === null ? '' : stampText(payload.checked_at);
    setLine('diagnosticsStatus', '检查完成' + (stamp ? ' · ' + stamp : '') + '。结果为电脑端本次观察，不代表手机网络状态。', 'ok');
  }

  async function runDiagnostics() {
    const dialog = $('diagnosticsDialog');
    const d = state.diagnostics;
    if (!dialog || !dialog.open || d.busy) return;
    const revision = ++d.revision;
    const threadId = currentThreadId();
    const targetKey = state.target ? state.target.key : '';
    d.busy = true;
    d.wantRun = false;
    resetDiagnosticsView('正在检查…不发送任务，不消耗模型额度。', '', '正在读取电脑端只读状态…');
    setDiagnosticsBusy(true);
    let path = '/api/bot/diagnostics?source_id=' + encodeURIComponent(sourceId);
    if (threadId) path += '&thread_id=' + encodeURIComponent(threadId);
    try {
      const data = await request(path);
      if (revision !== d.revision || !dialog.open) return;
      if ((state.target ? state.target.key : '') !== targetKey) {
        resetDiagnosticsView('会话已切换，本次检查结果已忽略，可重新检查。', 'warn', '本次结果未采用。');
        return;
      }
      if (!data || !Array.isArray(data.checks)) {
        resetDiagnosticsView('电脑返回的自检内容不完整，本次结果未采用。', 'warn', '未读取到可用的检查项。', DIAGNOSTICS_FAILURE_SUMMARY);
        return;
      }
      applyDiagnostics(data);
    } catch (error) {
      if (revision !== d.revision || !dialog.open) return;
      if ((state.target ? state.target.key : '') !== targetKey) {
        resetDiagnosticsView('会话已切换，本次检查结果已忽略，可重新检查。', 'warn', '本次结果未采用。');
        return;
      }
      if (state.authError) {
        resetDiagnosticsView('授权已失效，自检未能读取电脑状态。请从电脑重新配对并打开新链接，不要只当作网络离线。', 'error', '本次没有读取到电脑状态。', DIAGNOSTICS_FAILURE_SUMMARY);
      } else {
        resetDiagnosticsView('本次自检未能读取电脑状态。请按下方建议检查连接后重试。', 'error', '本次没有读取到电脑状态。', DIAGNOSTICS_FAILURE_SUMMARY);
      }
    } finally {
      d.busy = false;
      if (revision === d.revision) setDiagnosticsBusy(false);
      if (d.wantRun && dialog.open) {
        d.wantRun = false;
        runDiagnostics();
      }
    }
  }

  function openDiagnostics() {
    const dialog = $('diagnosticsDialog');
    if (!dialog || dialog.open) return;
    dialog.showModal();
    const d = state.diagnostics;
    if (d.busy) {
      resetDiagnosticsView('正在完成上一次检查，随后会自动重新检查…', '', '正在完成上一次检查…');
      setDiagnosticsBusy(true);
      d.wantRun = true;
      return;
    }
    runDiagnostics();
  }

  function closeDiagnostics() {
    const dialog = $('diagnosticsDialog');
    if (dialog && dialog.open) dialog.close();
  }

  function onDiagnosticsClosed() {
    const d = state.diagnostics;
    d.revision += 1;
    d.wantRun = false;
    if (!d.busy) setDiagnosticsBusy(false);
  }

  async function copyDiagnostics() {
    const d = state.diagnostics;
    const text = d.summary;
    const revision = d.revision;
    const stillCurrent = () => $('diagnosticsDialog').open && d.revision === revision && d.summary === text;
    if (!text) {
      setLine('diagnosticsStatus', '暂无可复制的摘要，请先完成检查。', 'warn');
      return;
    }
    try {
      if (!navigator.clipboard || typeof navigator.clipboard.writeText !== 'function') {
        throw new Error('clipboard unavailable');
      }
      await navigator.clipboard.writeText(text);
      if (!stillCurrent()) return;
      setLine('diagnosticsStatus', '已复制摘要。', 'ok');
    } catch (error) {
      if (!stillCurrent()) return;
      const details = $('diagnosticsSummaryDetails');
      if (details) details.open = true;
      const summary = $('diagnosticsSummary');
      if (summary) {
        summary.focus();
        try {
          summary.select();
          summary.setSelectionRange(0, summary.value.length);
        } catch (selectError) { /* selection is best effort */ }
      }
      setLine('diagnosticsStatus', '剪贴板不可用，请长按选择文字复制。', 'warn');
    }
  }

  /* ---------- codex usage / deepseek balance ---------- */

  function setUsageBusy(busy) {
    const button = $('refreshUsage');
    if (!button) return;
    button.disabled = !!busy;
    button.textContent = busy ? '查询中…' : '刷新额度';
  }

  function setBalanceBusy(busy) {
    const button = $('refreshBalance');
    if (!button) return;
    button.disabled = !!busy;
    button.textContent = busy ? '查询中…' : '刷新余额';
  }

  function usageEpochDate(value) {
    const number = typeof value === 'number' ? value : Number(value);
    if (!isFinite(number) || number <= 0) return null;
    const date = new Date(number * 1000);
    return isNaN(date.getTime()) ? null : date;
  }

  function usageTimeText(value) {
    const date = usageEpochDate(value);
    if (!date) return '';
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  function usagePercent(value) {
    if (value === null || value === undefined || value === '') return null;
    const number = Number(value);
    if (!isFinite(number) || number < 0 || number > 100) return null;
    return Math.round(number * 10) / 10;
  }

  function usagePercentText(value) {
    return (Math.round(value * 10) / 10) + '%';
  }

  function usageDurationText(value) {
    const number = Number(value);
    if (!isFinite(number) || number <= 0) return '';
    const total = Math.round(number);
    if (total < 60) return total + '分钟';
    if (total % 1440 === 0) return (total / 1440) + '天';
    if (total % 60 === 0) return (total / 60) + '小时';
    return Math.floor(total / 60) + '小时' + (total % 60) + '分钟';
  }

  function usageWindowTitle(minutes, index) {
    const duration = usageDurationText(minutes);
    return duration ? duration + '窗口' : '额度窗口' + (index + 1);
  }

  function usageMetaNode(payload) {
    const meta = el('div', 'usage-meta');
    const checked = usageTimeText(payload && payload.checked_at);
    meta.append(el('span', '', checked ? '查询时间：' + checked + '（本地时间）' : '查询时间：未提供'));
    meta.append(el('span', 'chip info usage-cache', payload && payload.cached ? '30秒缓存' : '未使用缓存'));
    return meta;
  }

  function resetUsageView(statusText, tone, listText) {
    setLine('usageStatus', statusText || '', tone || '');
    const box = $('usagePools');
    if (!box) return;
    clear(box);
    if (listText) box.append(el('p', 'usage-empty', listText));
  }

  function renderUsageWindow(windowData, index) {
    const data = windowData && typeof windowData === 'object' ? windowData : {};
    const card = el('div', 'usage-window');
    const used = usagePercent(data.used_percent);
    let remaining = usagePercent(data.remaining_percent);
    if (remaining === null && used !== null) remaining = Math.round((100 - used) * 10) / 10;

    const head = el('div', 'usage-window-head');
    head.append(el('span', 'usage-window-title', usageWindowTitle(data.window_minutes, index)));
    head.append(el('span', 'usage-remaining' + (remaining === null ? ' unknown' : ''), remaining === null ? '剩余未知' : '剩余' + usagePercentText(remaining)));
    card.append(head);

    if (remaining === null) {
      const unknown = el('div', 'usage-bar unknown');
      unknown.append(el('span', 'usage-bar-unknown', '比例未知'));
      card.append(unknown);
    } else {
      const bar = el('div', 'usage-bar');
      bar.setAttribute('role', 'img');
      bar.setAttribute('aria-label', '剩余' + usagePercentText(remaining));
      const fill = el('span', 'usage-bar-fill');
      fill.style.width = remaining + '%';
      bar.append(fill);
      card.append(bar);
    }

    if (used !== null) {
      card.append(el('p', 'usage-window-meta', '已用 ' + usagePercentText(used)));
    } else if (remaining !== null) {
      card.append(el('p', 'usage-window-meta', '已用 ' + usagePercentText(Math.round((100 - remaining) * 10) / 10)));
    } else {
      card.append(el('p', 'usage-window-meta', '已用比例未提供'));
    }

    const reset = usageEpochDate(data.resets_at);
    if (!reset) {
      card.append(el('p', 'usage-window-meta', '重置时间：未提供'));
    } else {
      card.append(el('p', 'usage-window-meta', '重置时间：' + usageTimeText(data.resets_at) + '（本地时间）'));
      if (reset.getTime() < Date.now()) {
        card.append(el('p', 'usage-window-note', '重置时间已过，等待刷新后查看最新额度。'));
      }
    }
    return card;
  }

  function renderUsagePools(payload) {
    const box = $('usagePools');
    if (!box) return;
    clear(box);
    box.append(usageMetaNode(payload));
    let rendered = 0;
    const pools = Array.isArray(payload.pools) ? payload.pools : [];
    for (const pool of pools) {
      if (!pool || typeof pool !== 'object' || Array.isArray(pool)) continue;
      const card = el('section', 'usage-pool');
      const label = typeof pool.label === 'string' ? normalise(pool.label).trim() : '';
      card.append(el('h3', 'usage-pool-label', label || 'Codex额度'));
      const windows = Array.isArray(pool.windows) ? pool.windows : [];
      if (!windows.length) {
        card.append(el('p', 'usage-empty', '该额度池没有返回额度窗口。'));
      } else {
        windows.forEach((item, index) => card.append(renderUsageWindow(item, index)));
      }
      rendered += 1;
      box.append(card);
    }
    if (!rendered) box.append(el('p', 'usage-empty', '电脑没有返回可显示的额度池。'));
  }

  function renderUsageUnavailable(payload) {
    setLine('usageStatus', USAGE_UNAVAILABLE_TEXT, 'warn');
    const box = $('usagePools');
    if (!box) return;
    clear(box);
    box.append(usageMetaNode(payload));
    box.append(el('p', 'usage-empty', '未显示任何额度数值，缺失比例保持未知。'));
  }

  function balanceCurrency(value) {
    if (typeof value !== 'string') return null;
    const code = value.trim().toUpperCase();
    return code === 'CNY' || code === 'USD' ? code : null;
  }

  function balanceAmount(value) {
    if (typeof value !== 'string') return null;
    const text = value.trim();
    if (!/^-?(?:0|[1-9]\d{0,14})(?:\.\d{1,12})?$/.test(text)) return null;
    return text;
  }

  function balanceMessage(payload) {
    if (!payload || typeof payload.message !== 'string') return '';
    return normalise(payload.message).trim().slice(0, 180);
  }

  function resetBalanceView(statusText, tone, listText) {
    setLine('balanceStatus', statusText || '', tone || '');
    const box = $('balancePools');
    if (!box) return;
    clear(box);
    if (listText) box.append(el('p', 'usage-empty', listText));
  }

  function renderBalanceUnavailable(payload, insufficient) {
    if (insufficient) {
      setLine('balanceStatus', 'DeepSeek 账户余额不足，模型调用不可用；本次余额查询未取得可显示数据。', 'warn');
    } else {
      const detail = balanceMessage(payload);
      setLine('balanceStatus', detail ? 'DeepSeek 余额当前不可用。' + detail : BALANCE_UNAVAILABLE_TEXT, 'warn');
    }
    const box = $('balancePools');
    if (!box) return;
    clear(box);
    box.append(usageMetaNode(payload));
    if (insufficient) box.append(el('p', 'usage-window-note', BALANCE_LOW_TEXT));
    box.append(el('p', 'usage-empty', '未显示任何余额数值，旧结果已清除。'));
  }

  function renderBalancePools(payload, insufficient) {
    const box = $('balancePools');
    if (!box) return;
    clear(box);
    box.append(usageMetaNode(payload));
    if (insufficient) box.append(el('p', 'usage-window-note', BALANCE_LOW_TEXT));
    let rendered = 0;
    const balances = Array.isArray(payload.balances) ? payload.balances : [];
    for (const item of balances) {
      if (!item || typeof item !== 'object' || Array.isArray(item)) continue;
      const currency = balanceCurrency(item.currency);
      if (!currency) continue;
      const total = balanceAmount(item.total);
      const granted = balanceAmount(item.granted);
      const toppedUp = balanceAmount(item.topped_up);
      const card = el('section', 'usage-pool');
      card.append(el('h3', 'usage-pool-label', currency + ' 余额'));
      const windowNode = el('div', 'usage-window');
      const head = el('div', 'usage-window-head');
      head.append(el('span', 'usage-window-title', '总余额'));
      head.append(el('span', 'usage-remaining' + (total === null ? ' unknown' : ''), total === null ? '总额未提供' : total + ' ' + currency));
      windowNode.append(head);
      const parts = [];
      if (granted !== null) parts.push('赠送 ' + granted + ' ' + currency);
      if (toppedUp !== null) parts.push('充值 ' + toppedUp + ' ' + currency);
      if (parts.length) windowNode.append(el('p', 'usage-window-meta', parts.join(' · ')));
      card.append(windowNode);
      box.append(card);
      rendered += 1;
    }
    if (!rendered) {
      box.append(el('p', 'usage-empty', insufficient ? '余额不足，电脑没有返回可显示的余额数值。' : '电脑没有返回可显示的余额数据，缺失字段未补零。'));
    }
  }

  async function runUsage() {
    const dialog = $('usageDialog');
    const u = state.usage;
    if (!dialog || !dialog.open || u.busy) return;
    if (u.provider !== 'codex') return;
    const revision = ++u.revision;
    u.busy = true;
    u.wantRun = false;
    resetUsageView('正在查询 Codex 额度…不发送任务，不消耗模型额度。', '', '正在读取电脑端额度，旧结果已清除…');
    setUsageBusy(true);
    try {
      const data = await request('/api/bot/usage');
      if (revision !== u.revision || !dialog.open || u.provider !== 'codex') return;
      if (!data || typeof data !== 'object' || Array.isArray(data)) {
        resetUsageView(USAGE_INCOMPLETE_TEXT, 'warn', '未显示额度数据，旧结果已清除。');
        return;
      }
      if (data.status === 'unavailable') {
        renderUsageUnavailable(data);
        return;
      }
      if (data.status !== 'available') {
        resetUsageView(USAGE_INCOMPLETE_TEXT, 'warn', '未显示额度数据，旧结果已清除。');
        return;
      }
      const usablePools = Array.isArray(data.pools) && data.pools.some((pool) => pool && typeof pool === 'object' && !Array.isArray(pool));
      if (!usablePools) {
        resetUsageView(USAGE_INCOMPLETE_TEXT, 'warn', '电脑没有返回可显示的额度池，旧结果已清除。');
        return;
      }
      setLine('usageStatus', '已读取 Codex 额度。剩余比例为主，重置时间已转换为手机本地时间。', 'ok');
      renderUsagePools(data);
    } catch (error) {
      if (revision !== u.revision || !dialog.open || u.provider !== 'codex') return;
      resetUsageView(state.authError ? USAGE_AUTH_TEXT : USAGE_FAILURE_TEXT, 'error', '未显示额度数据，旧结果已清除。');
    } finally {
      u.busy = false;
      if (revision === u.revision && u.provider === 'codex') setUsageBusy(false);
      if (u.wantRun && dialog.open && u.provider === 'codex') {
        u.wantRun = false;
        runUsage();
      }
    }
  }

  async function runBalance() {
    const dialog = $('usageDialog');
    const b = state.balance;
    if (!dialog || !dialog.open || b.busy) return;
    if (state.usage.provider !== 'deepseek') return;
    const revision = ++b.revision;
    b.busy = true;
    b.wantRun = false;
    resetBalanceView('正在查询 DeepSeek 余额…不提交模型任务。', '', '正在读取电脑端余额，旧结果已清除…');
    setBalanceBusy(true);
    try {
      const data = await request('/api/bot/deepseek/balance');
      if (revision !== b.revision || !dialog.open || state.usage.provider !== 'deepseek') return;
      if (!data || typeof data !== 'object' || Array.isArray(data)) {
        resetBalanceView(BALANCE_INCOMPLETE_TEXT, 'warn', '未显示余额数据，旧结果已清除。');
        return;
      }
      if (data.provider !== undefined && data.provider !== null && String(data.provider) !== 'deepseek') {
        resetBalanceView(BALANCE_INCOMPLETE_TEXT, 'warn', '未显示余额数据，旧结果已清除。');
        return;
      }
      const insufficient = data.is_available === false;
      if (data.status === 'unavailable') {
        renderBalanceUnavailable(data, insufficient);
        return;
      }
      if (data.status !== 'available') {
        if (insufficient) renderBalanceUnavailable(data, true);
        else resetBalanceView(BALANCE_INCOMPLETE_TEXT, 'warn', '未显示余额数据，旧结果已清除。');
        return;
      }
      const balances = Array.isArray(data.balances) ? data.balances : [];
      const usable = balances.some((item) => item && typeof item === 'object' && !Array.isArray(item) && balanceCurrency(item.currency));
      if (!usable && !insufficient) {
        resetBalanceView(BALANCE_INCOMPLETE_TEXT, 'warn', '电脑没有返回可显示的余额，旧结果已清除。');
        return;
      }
      if (insufficient) {
        setLine('balanceStatus', '已读取 DeepSeek 余额；当前账户余额不足，模型调用不可用。', 'warn');
      } else {
        setLine('balanceStatus', '已读取 DeepSeek 余额。这是当前 Harness 使用的官方 API Key 账户余额，不是 Codex 额度。', 'ok');
      }
      renderBalancePools(data, insufficient);
    } catch (error) {
      if (revision !== b.revision || !dialog.open || state.usage.provider !== 'deepseek') return;
      resetBalanceView(state.authError ? BALANCE_AUTH_TEXT : BALANCE_FAILURE_TEXT, 'error', '未显示余额数据，旧结果已清除。');
    } finally {
      b.busy = false;
      if (revision === b.revision && state.usage.provider === 'deepseek') setBalanceBusy(false);
      if (b.wantRun && dialog.open && state.usage.provider === 'deepseek') {
        b.wantRun = false;
        runBalance();
      }
    }
  }

  function syncUsageProviderUI() {
    const codex = state.usage.provider !== 'deepseek';
    const codexTab = $('usageTabCodex');
    const balanceTab = $('usageTabBalance');
    if (codexTab) {
      codexTab.setAttribute('aria-selected', codex ? 'true' : 'false');
      codexTab.classList.toggle('active', codex);
    }
    if (balanceTab) {
      balanceTab.setAttribute('aria-selected', codex ? 'false' : 'true');
      balanceTab.classList.toggle('active', !codex);
    }
    const codexPanel = $('usageCodexPanel');
    if (codexPanel) codexPanel.hidden = !codex;
    const balancePanel = $('usageBalancePanel');
    if (balancePanel) balancePanel.hidden = codex;
  }

  function setUsageProvider(provider, options) {
    const opts = options || {};
    const next = provider === 'deepseek' ? 'deepseek' : 'codex';
    const dialog = $('usageDialog');
    const changed = state.usage.provider !== next;
    state.usage.provider = next;
    if (changed) {
      if (next !== 'codex') state.usage.wantRun = false;
      if (next !== 'deepseek') state.balance.wantRun = false;
    }
    syncUsageProviderUI();
    if (!opts.run || !dialog || !dialog.open) return;
    if (next === 'codex') {
      const u = state.usage;
      if (u.busy) {
        resetUsageView('正在完成上一次查询，随后会自动刷新…', '', '正在完成上一次查询…');
        setUsageBusy(true);
        u.wantRun = true;
      } else {
        runUsage();
      }
      return;
    }
    const b = state.balance;
    if (b.busy) {
      resetBalanceView('正在完成上一次查询，随后会自动刷新…', '', '正在完成上一次查询…');
      setBalanceBusy(true);
      b.wantRun = true;
    } else {
      runBalance();
    }
  }

  function selectUsageProvider(provider) {
    const dialog = $('usageDialog');
    if (!dialog || !dialog.open) return;
    if (state.usage.provider === provider) return;
    setUsageProvider(provider, { run: true });
  }

  function openUsage() {
    const dialog = $('usageDialog');
    if (!dialog || dialog.open) return;
    state.usage.provider = 'codex';
    state.usage.wantRun = false;
    state.balance.wantRun = false;
    if (!state.balance.busy) setBalanceBusy(false);
    setUsageProvider('codex', { run: false });
    dialog.showModal();
    const u = state.usage;
    if (u.busy) {
      resetUsageView('正在完成上一次查询，随后会自动刷新…', '', '正在完成上一次查询…');
      setUsageBusy(true);
      u.wantRun = true;
      return;
    }
    runUsage();
  }

  function closeUsage() {
    const dialog = $('usageDialog');
    if (dialog && dialog.open) dialog.close();
  }

  function onUsageClosed() {
    const u = state.usage;
    const b = state.balance;
    u.revision += 1;
    u.wantRun = false;
    b.revision += 1;
    b.wantRun = false;
    if (!u.busy) setUsageBusy(false);
    if (!b.busy) setBalanceBusy(false);
  }

  /* ---------- drawer / helpers ---------- */

  function openDrawer() {
    $('sidebar').classList.add('open');
    $('drawerBackdrop').hidden = false;
    $('drawerButton').setAttribute('aria-expanded', 'true');
  }
  function closeDrawer() {
    $('sidebar').classList.remove('open');
    $('drawerBackdrop').hidden = true;
    $('drawerButton').setAttribute('aria-expanded', 'false');
  }

  async function probe() {
    if (state.probeBusy) return;
    state.probeBusy = true;
    try {
      await loadAgents();
      await request('/api/info');
      if (state.connected === true && state.phase === 'idle') loadList(state.partition, true);
    } catch (error) { /* connection state is updated by request */ }
    finally { state.probeBusy = false; }
  }

  function tick() {
    if (document.hidden) return;
    if (state.phase !== 'idle') return;
    if (!state.target || state.target.kind === 'new') {
      if (state.connected === false) probe();
      return;
    }
    if (state.pollBusy) return;
    state.pollBusy = true;
    loadConversation({}).finally(() => { state.pollBusy = false; });
  }

  /* ---------- code reference handoff ---------- */

  function codeReferenceTitle(task) {
    return cleanTitle(task && (task.title || task.goal) ? (task.title || task.goal) : '');
  }

  function codeReferenceRequirement(payload) {
    const value = normalise(payload && payload.instruction).trim();
    return value || CODE_REFERENCE_DEFAULT_INSTRUCTION;
  }

  function codeReferenceBody(payload, task) {
    return '请针对以下代码处理：\n' + codeReferenceRequirement(payload)
      + '\n\n引用文件：' + payload.path
      + '\n行号：L' + payload.start + '–L' + payload.end
      + '\n（来自任务：' + codeReferenceTitle(task) + '；引用为当时预览快照）'
      + '\n--- 引用片段开始 ---\n' + payload.text
      + '\n--- 引用片段结束 ---';
  }

  function codeReferenceSummary(payload, task) {
    return [
      '文件：' + payload.path + ' · 行号：L' + payload.start + '–L' + payload.end,
      '来源任务：' + codeReferenceTitle(task)
    ];
  }

  function codeReferenceNoticeNode() {
    let node = $('codeReferenceNotice');
    if (node) return node;
    node = el('section', 'notice');
    node.id = 'codeReferenceNotice';
    node.setAttribute('role', 'status');
    node.setAttribute('aria-live', 'polite');
    node.style.cssText = 'margin:8px 0;padding:10px 12px;border:1px solid rgba(34,35,52,.18);'
      + 'border-left:4px solid #3346d3;border-radius:10px;background:#f5f4ff;font-size:13px;'
      + 'line-height:1.55;overflow-wrap:anywhere;';
    const composer = $('composer');
    if (composer && composer.parentNode) composer.parentNode.insertBefore(node, composer);
    else document.body.insertBefore(node, document.body.firstChild);
    return node;
  }

  function showCodeReferenceNotice(options) {
    const opts = options || {};
    const node = codeReferenceNoticeNode();
    clear(node);
    node.hidden = false;
    const tone = opts.tone || 'info';
    node.style.borderLeftColor = tone === 'error' ? '#972b35' : (tone === 'warn' ? '#b18520' : '#3346d3');
    node.style.background = tone === 'error' ? '#fcebed' : (tone === 'warn' ? '#fbf3dc' : '#f5f4ff');
    const title = el('div', '', opts.title || '代码引用');
    title.style.cssText = 'font-weight:700;margin:0 0 2px';
    node.append(title);
    for (const line of (opts.lines || [])) {
      if (!line) continue;
      const paragraph = el('p', '', line);
      paragraph.style.cssText = 'margin:2px 0';
      node.append(paragraph);
    }
    if (opts.actions && opts.actions.length) {
      const row = el('div');
      row.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;margin-top:8px';
      for (const action of opts.actions) {
        if (!action || !action.label) continue;
        const button = el('button', 'btn secondary', action.label);
        button.type = 'button';
        if (action.id) button.id = action.id;
        button.style.cssText = 'min-height:36px;padding:0 10px';
        button.addEventListener('click', action.run);
        row.append(button);
      }
      if (row.childNodes.length) node.append(row);
    }
    return node;
  }

  function closeCodeReferenceNotice() {
    const node = $('codeReferenceNotice');
    if (node) {
      node.hidden = true;
      clear(node);
    }
    state.codeReference = null;
  }

  function codeReferenceActions(ref, includeOpen) {
    const actions = [];
    if (includeOpen) {
      actions.push({ id: 'codeReferenceOpenSource', label: '打开来源会话并填入', run: openCodeReferenceSource });
    }
    actions.push({ id: 'codeReferenceCopy', label: '复制引用', run: copyCodeReference });
    actions.push({ id: 'codeReferenceClose', label: '关闭', run: closeCodeReferenceNotice });
    return actions;
  }

  function codeReferenceFail(ref, text) {
    if (state.codeReference !== ref) return;
    ref.stage = 'unavailable';
    showCodeReferenceNotice({
      title: '代码引用无法使用',
      tone: 'error',
      lines: [text, '未写入任何草稿。'],
      actions: codeReferenceActions(ref, false)
    });
  }

  function codeReferenceValidationError(payload) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return '引用数据格式不正确。';
    if (payload.version !== 1) return '引用数据版本不受支持。';
    if (typeof payload.created !== 'number' || !isFinite(payload.created)) return '引用创建时间无效。';
    const now = Date.now();
    if (payload.created > now) return '引用创建时间在未来，已拒绝。';
    if (now - payload.created > CODE_REFERENCE_TTL) return '引用已过期（超过 10 分钟），请重新在文件预览中选择。';
    if (typeof payload.task_id !== 'string' || !CODE_REFERENCE_HEX.test(payload.task_id)) return '引用中的任务编号无效。';
    if (typeof payload.path !== 'string' || !payload.path) return '引用中的文件路径无效。';
    if (payload.path.charAt(0) === '/' || payload.path.charAt(0) === '\\') return '引用中的文件路径不能是绝对路径。';
    if (payload.path.indexOf('\\') >= 0) return '引用中的文件路径不能包含反斜杠。';
    if (payload.path.indexOf(':') >= 0) return '引用中的文件路径不能包含冒号。';
    if (/(?:^|\/)\.\.(?:\/|$)/.test(payload.path)) return '引用中的文件路径不能包含上级目录。';
    if (/[\u0000-\u001f\u007f]/.test(payload.path)) return '引用中的文件路径包含控制字符。';
    if (!Number.isInteger(payload.start) || !Number.isInteger(payload.end)) return '引用行号必须是整数。';
    if (payload.start < 1 || payload.start > 2000 || payload.end < 1 || payload.end > 2000) {
      return '引用行号必须在 1–2000 之间。';
    }
    if (payload.end < payload.start) return '引用结束行不能小于起始行。';
    if (payload.end - payload.start + 1 > 100) return '单次最多引用 100 行。';
    if (typeof payload.text !== 'string' || payload.text.length > 6000) return '引用片段无效或超过 6000 字符。';
    if (payload.text.split('\n').length !== payload.end - payload.start + 1) return '引用片段行数与行号范围不一致。';
    if (typeof payload.instruction !== 'string' || payload.instruction.length > 2000) return '引用中的处理要求无效或超过 2000 字符。';
    return '';
  }

  function stripCodeReferenceFromUrl() {
    try {
      const url = new URL(location.href);
      if (!url.searchParams.has('code_ref')) return;
      url.searchParams.delete('code_ref');
      history.replaceState(history.state, '', url.pathname + url.search + url.hash);
    } catch (error) { /* leave the URL intact if the browser refuses the rewrite */ }
  }

  function codeReferenceFallbackCopy(text) {
    const area = el('textarea');
    area.value = text;
    area.style.cssText = 'position:fixed;left:-9999px;top:0;width:1px;height:1px;opacity:0';
    area.setAttribute('readonly', 'readonly');
    document.body.append(area);
    let copied = false;
    try {
      area.select();
      copied = document.execCommand && document.execCommand('copy');
    } catch (error) {
      copied = false;
    } finally {
      area.remove();
    }
    return copied === true;
  }

  async function copyCodeReference() {
    const ref = state.codeReference;
    if (!ref || !ref.payload) return;
    const text = codeReferenceBody(ref.payload, ref.task);
    let copied = false;
    try {
      if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
        await navigator.clipboard.writeText(text);
        copied = true;
      }
    } catch (error) {
      copied = false;
    }
    if (!copied) copied = codeReferenceFallbackCopy(text);
    if (state.codeReference !== ref) return;
    if (!copied) {
      let dialog = $('codeReferenceManualCopy');
      if (!dialog) {
        dialog = el('dialog'); dialog.id = 'codeReferenceManualCopy';
        dialog.style.cssText = 'width:min(92vw,680px);max-height:85vh;padding:18px;border:1px solid var(--ink);border-radius:16px;background:var(--panel,#fffdf9);color:var(--ink);';
        const title = el('h2', '', '复制代码引用'); title.id = 'codeReferenceManualTitle';
        dialog.setAttribute('aria-labelledby', title.id);
        const note = el('p', '', '请长按下方文本选择“复制”，再手动粘贴到指令框。');
        const area = el('textarea'); area.id = 'codeReferenceManualText'; area.readOnly = true;
        area.setAttribute('aria-label', '可选择复制的代码引用');
        area.style.cssText = 'display:block;width:100%;height:38vh;font:16px/1.5 monospace;margin:12px 0;';
        const close = el('button', 'small-btn', '关闭'); close.type = 'button';
        close.addEventListener('click', () => dialog.close());
        dialog.append(title, note, area, close); document.body.append(dialog);
      }
      $('codeReferenceManualText').value = text;
      if (!dialog.open) dialog.showModal();
      $('codeReferenceManualText').focus(); $('codeReferenceManualText').select();
      return;
    }
    setLine('composerStatus', copied ? '引用已复制，可手动粘贴。' : '复制失败，请检查浏览器剪贴板权限后重试。', copied ? 'ok' : 'error');
  }

  function appendCodeReferenceToTarget(target, payload, task) {
    if (!target || !state.target || state.target.key !== target.key) return false;
    const input = $('composerInput');
    if (!input) return false;
    const reference = codeReferenceBody(payload, task);
    const existing = input.value;
    const next = existing ? existing + '\n\n' + reference : reference;
    input.value = next;
    state.drafts.set(target.key, next);
    autoGrow();
    updateInteraction();
    updateComposer();
    setLine('composerStatus', '引用已放入该会话的指令框，请检查后发送。', 'ok');
    return true;
  }

  function openCodeReferenceSource() {
    const ref = state.codeReference;
    if (!ref || !ref.target || !ref.payload) return;
    if (ref.stage === 'loading' || ref.stage === 'error' || ref.stage === 'nonresumable'
      || ref.stage === 'applied' || ref.stage === 'newtask') return;
    if (state.phase !== 'idle') {
      setLine('composerStatus', '当前操作进行中，请稍后再试。', 'warn');
      return;
    }
    try {
      openTarget(ref.target, { conversation: ref.conversation });
    } catch (error) {
      setLine('composerStatus', '打开来源会话失败：' + errText(error), 'error');
      return;
    }
    if (!appendCodeReferenceToTarget(ref.target, ref.payload, ref.task)) {
      setLine('composerStatus', '没有找到来源会话的指令框，引用未填入。', 'error');
      return;
    }
    ref.stage = 'applied';
    showCodeReferenceNotice({
      title: '代码引用已填入',
      tone: 'info',
      lines: ['引用已放入该会话的指令框，请检查后发送。'].concat(codeReferenceSummary(ref.payload, ref.task)),
      actions: codeReferenceActions(ref, false)
    });
  }

  function openCodeReferenceNewTask() {
    const ref = state.codeReference;
    if (!ref || !ref.payload || !ref.task) return;
    if (ref.stage === 'newtask' || ref.stage === 'applied') return;
    if (state.phase !== 'idle') {
      setLine('composerStatus', '当前操作进行中，请稍后再试。', 'warn');
      return;
    }
    const agent = ref.task.agent === FLASH_AGENT ? FLASH_AGENT : 'codex';
    const partition = agent === FLASH_AGENT ? 'deepseek' : 'codex';
    const target = { kind: 'new', key: 'new:' + partition, partition: partition, agent: agent };
    try {
      openTarget(target, {});
    } catch (error) {
      setLine('composerStatus', '新建任务草稿失败：' + errText(error), 'error');
      return;
    }
    if (!appendCodeReferenceToTarget(target, ref.payload, ref.task)) {
      setLine('composerStatus', '没有找到新任务的指令框，引用未填入。', 'error');
      return;
    }
    ref.stage = 'newtask';
    setLine('composerStatus', '引用已放入新任务草稿，尚未发送；请检查后发送。', 'ok');
    showCodeReferenceNotice({
      title: '代码引用已放入新任务',
      tone: 'info',
      lines: [
        '引用已放入新任务草稿，尚未发送。',
        '原任务不能续接，工作台没有自动创建或发送任务。'
      ].concat(codeReferenceSummary(ref.payload, ref.task)),
      actions: codeReferenceActions(ref, false)
    });
  }

  async function resolveCodeReference(payload, options) {
    const opts = options || {};
    const auto = opts.auto === true;
    const revision = typeof opts.revision === 'number' ? opts.revision : state.viewRevision;
    const ref = {
      payload: payload,
      task: null,
      conversation: null,
      target: null,
      stage: 'loading'
    };
    state.codeReference = ref;
    showCodeReferenceNotice({
      title: '代码引用',
      tone: 'info',
      lines: ['正在核对来源任务与是否可续接…'].concat(codeReferenceSummary(payload, null)),
      actions: [{ id: 'codeReferenceClose', label: '关闭', run: closeCodeReferenceNotice }]
    });

    let task = null;
    let data = null;
    try {
      const tasks = normalizeTasks(await request('/api/bot/tasks'));
      if (state.codeReference !== ref) return;
      task = tasks.find((item) => item && item.id !== undefined && item.id !== null
        && String(item.id).toLowerCase() === payload.task_id.toLowerCase()) || null;
      if (!task) {
        codeReferenceFail(ref, '未在任务记录中找到引用对应的来源任务。');
        return;
      }
      if (task.agent !== 'codex' && task.agent !== FLASH_AGENT) {
        codeReferenceFail(ref, '来源任务的模型不是 Codex 或 DeepSeek Flash，不能带到工作台。');
        return;
      }
      ref.task = task;
      data = await request('/api/bot/conversation?source_id=' + encodeURIComponent(sourceId)
        + '&task_id=' + encodeURIComponent(String(task.id)));
      if (state.codeReference !== ref) return;
      if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('对话记录格式不完整');
      if (!data.task || data.task.id === undefined || data.task.id === null
        || String(data.task.id).toLowerCase() !== payload.task_id.toLowerCase()) {
        codeReferenceFail(ref, '来源任务的对话记录与引用不一致，已停止处理。');
        return;
      }
    } catch (error) {
      if (state.codeReference !== ref) return;
      ref.stage = 'error';
      showCodeReferenceNotice({
        title: '代码引用读取失败',
        tone: 'error',
        lines: [
          '读取来源任务或对话失败：' + errText(error) + '。引用仍保留；不会自动新建任务或发送。'
        ].concat(codeReferenceSummary(payload, task)),
        actions: [
          {
            id: 'codeReferenceRetry',
            label: '重试',
            run: () => { resolveCodeReference(payload, { auto: true, revision: state.viewRevision }); }
          },
          { id: 'codeReferenceCopy', label: '复制引用', run: copyCodeReference },
          { id: 'codeReferenceClose', label: '关闭', run: closeCodeReferenceNotice }
        ]
      });
      return;
    }

    if (state.codeReference !== ref) return;
    const resumable = task.agent === 'codex'
      && data.can_reply === true
      && typeof data.thread_id === 'string' && data.thread_id
      && typeof task.remote_session === 'string' && task.remote_session
      && String(data.thread_id) === String(task.remote_session);
    const partition = task.agent === FLASH_AGENT ? 'deepseek' : 'codex';
    const title = codeReferenceTitle(task);
    ref.task = task;
    ref.conversation = data;
    ref.target = {
      kind: 'task',
      key: 'task:' + String(task.id),
      taskId: String(task.id),
      threadId: resumable ? String(data.thread_id) : (task.remote_session ? String(task.remote_session) : null),
      agent: task.agent,
      partition: partition,
      title: title
    };

    if (!resumable) {
      ref.stage = 'nonresumable';
      showCodeReferenceNotice({
        title: '原任务不能续接',
        tone: 'warn',
        lines: [
          task.agent === FLASH_AGENT
            ? '该 Flash 任务首版没有可续聊通道。'
            : '该 Codex 任务没有可续接的会话（缺少 remote_session，或当前不能回复、会话编号不一致）。',
          '引用仍保留在内存中，不会自动创建任务，也不会发送。',
          '只有点击“带到新任务”才会切换到原任务对应的分区并填入新任务草稿。'
        ].concat(codeReferenceSummary(payload, task)),
        actions: [
          { id: 'codeReferenceNewTask', label: '带到新任务', run: openCodeReferenceNewTask },
          { id: 'codeReferenceCopy', label: '复制引用', run: copyCodeReference },
          { id: 'codeReferenceClose', label: '关闭', run: closeCodeReferenceNotice }
        ]
      });
      return;
    }

    if (auto && (revision !== state.viewRevision || state.phase !== 'idle')) {
      ref.stage = 'switched';
      showCodeReferenceNotice({
        title: '代码引用仍保留',
        tone: 'warn',
        lines: [
          revision !== state.viewRevision
            ? '你已切换到其他会话；为避免覆盖当前草稿，引用没有自动填入。'
            : '当前正在处理其他操作；为避免覆盖草稿，引用没有自动填入。',
          '只有点击“打开来源会话并填入”才会切换并追加到来源会话的指令框。'
        ].concat(codeReferenceSummary(payload, task)),
        actions: codeReferenceActions(ref, true)
      });
      return;
    }

    ref.stage = 'resumable';
    openCodeReferenceSource();
  }

  async function receiveCodeReference() {
    let refId = '';
    try {
      refId = new URL(location.href).searchParams.get('code_ref') || '';
    } catch (error) {
      refId = '';
    }
    if (!refId) return;
    stripCodeReferenceFromUrl();
    if (!CODE_REFERENCE_HEX.test(refId)) {
      showCodeReferenceNotice({
        title: '代码引用无法使用',
        tone: 'error',
        lines: ['引用编号格式无效（需要 32 位十六进制编号）。', '未写入任何草稿。'],
        actions: [{ id: 'codeReferenceClose', label: '关闭', run: closeCodeReferenceNotice }]
      });
      return;
    }
    const key = CODE_REFERENCE_PREFIX + refId;
    let raw = null;
    try {
      raw = sessionStorage.getItem(key);
    } catch (error) {
      showCodeReferenceNotice({
        title: '代码引用无法使用',
        tone: 'error',
        lines: ['无法读取浏览器临时引用存储。', '未写入任何草稿；请返回文件预览重新引用，或复制引用后手动粘贴。'],
        actions: [{ id: 'codeReferenceClose', label: '关闭', run: closeCodeReferenceNotice }]
      });
      return;
    }
    let referenceConsumed = true;
    try {
      if (raw !== null) sessionStorage.removeItem(key);
    } catch (error) { referenceConsumed = false; }
    if (raw === null) {
      showCodeReferenceNotice({
        title: '代码引用无法使用',
        tone: 'error',
        lines: ['没有找到这次引用（可能已被使用、过期或临时存储被清理）。', '未写入任何草稿。'],
        actions: [{ id: 'codeReferenceClose', label: '关闭', run: closeCodeReferenceNotice }]
      });
      return;
    }
    let payload = null;
    try {
      payload = JSON.parse(raw);
    } catch (error) {
      showCodeReferenceNotice({
        title: '代码引用无法使用',
        tone: 'error',
        lines: ['引用数据已损坏，无法读取。', '未写入任何草稿。'],
        actions: [{ id: 'codeReferenceClose', label: '关闭', run: closeCodeReferenceNotice }]
      });
      return;
    }
    const reason = codeReferenceValidationError(payload);
    if (reason) {
      showCodeReferenceNotice({
        title: '代码引用无法使用',
        tone: 'error',
        lines: [reason, '未写入任何草稿。'],
        actions: [{ id: 'codeReferenceClose', label: '关闭', run: closeCodeReferenceNotice }]
      });
      return;
    }
    if (!referenceConsumed) {
      const ref = { payload: payload, task: null, stage: 'manual' };
      state.codeReference = ref;
      showCodeReferenceNotice({
        title: '引用需要手动复制', tone: 'warn',
        lines: ['浏览器无法清除临时引用记录，已停止自动填入，避免重复引用。', '未写入任何草稿，可复制引用后手动粘贴。'],
        actions: codeReferenceActions(ref, false)
      });
      return;
    }
    await resolveCodeReference(payload, { auto: true, revision: state.viewRevision });
  }

  function setupEvents() {
    if(simpleSingle){
      document.documentElement.dataset.singleSimple='true';document.documentElement.dataset.historyCollapsed='false';
      const label=el('label','single-model-choice','选择模型'),choice=el('select');choice.id='singleModelChoice';choice.setAttribute('aria-label','单模型选择');
      for(const [id,name] of [['codex','Codex'],['deepseek','DeepSeek']]){const option=el('option','',name);option.value=id;choice.append(option);}
      choice.value=state.partition;choice.onchange=()=>switchPartition(choice.value);label.append(choice);
      $('newConversation').before(label);
      const historyLabel=el('strong','single-history-label','历史会话');$('searchForm').before(historyLabel);
    }
    connectHistoryHost();
    $('newConversation').addEventListener('click', newConversation);
    $('emptyNew').addEventListener('click', newConversation);
    $('partitionCodex').addEventListener('click', () => switchPartition('codex'));
    $('partitionDeepSeek').addEventListener('click', () => switchPartition('deepseek'));
    $('emptyPick').addEventListener('click', () => {
      if (isMobile()) openDrawer();
      else { try { $('searchInput').focus(); } catch (error) {} }
    });
    $('searchForm').addEventListener('submit', (event) => {
      event.preventDefault();
      if (state.phase !== 'idle') {
        setLine('listStatus', '操作进行中，请稍后再搜索。', 'warn');
        return;
      }
      searchHistory(state.partition, $('searchInput').value.trim());
    });
    $('loadMore').addEventListener('click', () => loadList(state.partition, false));
    $('loadOlder').addEventListener('click', () => {
      if (state.readBusy) return;
      loadConversation({ older: true });
    });

    $('drawerButton').addEventListener('click', openDrawer);
    $('sidebarClose').addEventListener('click', closeDrawer);
    $('drawerBackdrop').addEventListener('click', closeDrawer);

    $('menuButton').addEventListener('click', refreshAll);
    $('sessionCodex').addEventListener('click', () => switchPartition('codex'));
    $('sessionDeepSeek').addEventListener('click', () => switchPartition('deepseek'));
    $('closePair').addEventListener('click', () => $('pairDialog').close());
    $('closeDiagnostics').addEventListener('click', closeDiagnostics);
    $('runDiagnostics').addEventListener('click', runDiagnostics);
    $('copyDiagnostics').addEventListener('click', copyDiagnostics);
    $('diagnosticsDialog').addEventListener('close', onDiagnosticsClosed);
    $('closeUsage').addEventListener('click', closeUsage);
    $('refreshUsage').addEventListener('click', runUsage);
    $('refreshBalance').addEventListener('click', runBalance);
    $('usageTabCodex').addEventListener('click', () => selectUsageProvider('codex'));
    $('usageTabBalance').addEventListener('click', () => selectUsageProvider('deepseek'));
    $('usageDialog').addEventListener('close', onUsageClosed);

    $('composer').addEventListener('submit', (event) => {
      event.preventDefault();
      if (state.phase !== 'idle' || !state.target) return;
      if (state.target.kind === 'new') sendNew();
      else sendReply();
    });
    $('composerInput').addEventListener('input', () => {
      if (state.target) {state.drafts.set(state.target.key,$('composerInput').value);if(!sessionRecovery.remember(state.target.key,$('composerInput').value))setLine('composerStatus','当前文字仅保留在本页，浏览器存储不可用。请勿刷新。','warn');}
      autoGrow();
      updateComposer();
    });
    $('composerInput').addEventListener('keydown', (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && !event.isComposing) {
        event.preventDefault();
        $('composer').requestSubmit();
      }
    });
    $('attachButton').addEventListener('click', () => $('fileInput').click());
    $('fileInput').addEventListener('change', (event) => {
      addFiles(event.target.files);
      event.target.value = '';
    });
    $('modeSelect').addEventListener('change', () => {
      if (state.selectedAgent === FLASH_AGENT) $('modeSelect').value = 'task';
      updateComposer();
    });
    $('agentSelect').addEventListener('change', () => {
      if (state.phase !== 'idle') {
        $('agentSelect').value = state.selectedAgent;
        return;
      }
      state.selectedAgent = normalizeAgent($('agentSelect').value);
      if (state.selectedAgent === FLASH_AGENT) $('modeSelect').value = 'task';
      updateComposer();
      renderHeader();
    });

    let resumeAt = 0;
    function resumeConversation() {
      if (document.hidden || navigator.onLine === false || Date.now() - resumeAt < 1400) return;
      if (state.phase !== 'idle') return;
      resumeAt = Date.now();
      if (state.target && state.target.kind !== 'new') loadConversation({});
      if (state.connected === false) probe();
      loadList(state.partition, true);
    }
    window.WorkstationSingleResume = resumeConversation;
    document.addEventListener('visibilitychange', resumeConversation);
    window.addEventListener('online', resumeConversation);
    window.addEventListener('pageshow', event => { if (event.persisted) resumeConversation(); });
    window.addEventListener('resize', () => {
      if (!isMobile()) closeDrawer();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') closeDrawer();
    });
  }

  async function boot() {
    setupEvents();
    syncUsageProviderUI();
    if (!token) {
      state.authError = true;
      state.connected = false;
    }
    updateConnectionUI();
    updateOpenCodexButton();
    syncPartitionUI();
    renderAll();
    await Promise.allSettled([loadAgents(), loadList(state.partition, true)]);
    try {
      await receiveCodeReference();
    } catch (error) {
      showCodeReferenceNotice({
        title: '代码引用无法使用', tone: 'error',
        lines: ['读取引用时发生错误：' + errText(error) + '。', '请返回文件预览重试。'],
        actions: [{ id: 'codeReferenceClose', label: '关闭', run: closeCodeReferenceNotice }]
      });
    }
    setInterval(tick, 3000);
  }

  window.openWebProductPreview=function(value){
    const url=new URL(value,location.origin);if(url.origin!==location.origin||!/^\/web-product\/[a-f0-9]{48}\/index\.html$/.test(url.pathname))throw Error('无效网页预览。');
    const notify=open=>{try{if(parent!==window)parent.postMessage({type:'workstation-web-preview-state',open},location.origin);}catch{}};
    let dialog=$('webProductPreview');
    if(!dialog){
      const style=el('style');style.textContent='#webProductPreview{box-sizing:border-box;width:100%;height:100%;height:100dvh;max-width:none;max-height:none;inset:0;margin:0;padding:0;border:0;border-radius:0;background:var(--bg,#edf3f9);color:var(--ink,#24354c)}#webProductPreview[open]{display:flex;flex-direction:column}#webProductPreview .web-review-toolbar{display:flex;align-items:center;flex-wrap:wrap;gap:6px;padding:8px 10px;padding-top:max(8px,env(safe-area-inset-top));background:var(--panel,#f4f8fd);border-bottom:1px solid var(--line,#d4dfec);flex-shrink:0}#webProductPreview .web-review-toolbar strong{margin-right:auto;font-size:14px}#webProductPreview button{font-size:12px;padding:7px 10px;min-height:38px}#webProductPreview button[aria-pressed=true]{background:var(--accent-soft,#e6f0fe);color:var(--accent-strong,#2f6fcf)}#webProductPreview .web-review-canvas{flex:1;min-height:0;overflow:auto;overscroll-behavior:contain;display:flex;justify-content:center;background:#dfe7f0}#webProductPreview .web-review-stage{position:relative;flex-shrink:0;background:white}#webProductPreview iframe{display:block;border:0;position:absolute;top:0;left:0;transform-origin:top left;background:white}#webProductPreview .web-review-note{padding:4px 8px;padding-bottom:max(4px,env(safe-area-inset-bottom));font-size:10px;flex-shrink:0;text-align:center;background:var(--panel,#f4f8fd);color:var(--muted,#647a92)}@media(max-width:420px){#webProductPreview .web-review-toolbar strong{width:100%}}';document.head.append(style);
      dialog=el('dialog');dialog.id='webProductPreview';dialog.setAttribute('aria-label','网页成果审查');
      const toolbar=el('div','web-review-toolbar'),canvas=el('div','web-review-canvas'),stage=el('div','web-review-stage'),frame=el('iframe');
      frame.title='网页成品预览';frame.referrerPolicy='no-referrer';frame.setAttribute('sandbox','allow-scripts');
      toolbar.append(el('strong','','网页审查'));let width=0;const modes=[];
      const note=el('div','web-review-note','远程浏览 · 电脑需在线 · 宽度预览不等同真实设备测试');
      function layout(){if(!dialog.open)return;const available=Math.max(1,canvas.clientWidth),height=Math.max(1,canvas.clientHeight),viewport=width||available,scale=Math.min(1,available/viewport);stage.style.width=Math.round(viewport*scale)+'px';stage.style.height=height+'px';frame.style.width=viewport+'px';frame.style.height=Math.ceil(height/scale)+'px';frame.style.transform='scale('+scale+')';}
      for(const [label,value]of [['适应',0],['手机',390],['电脑',1280]]){const button=el('button','small-btn',label);button.type='button';button.setAttribute('aria-pressed',String(value===0));button.onclick=()=>{width=value;for(const [b,v]of modes)b.setAttribute('aria-pressed',String(v===width));layout();};modes.push([button,value]);toolbar.append(button);}
      const refresh=el('button','small-btn','刷新'),close=el('button','small-btn','返回成果');refresh.type=close.type='button';refresh.onclick=()=>{frame.src=frame.src;};close.onclick=()=>dialog.close();toolbar.append(refresh,close);
      stage.append(frame);canvas.append(stage);dialog.append(toolbar,canvas,note);document.body.append(dialog);
      new ResizeObserver(layout).observe(canvas);dialog.addEventListener('close',()=>{frame.src='about:blank';notify(false);});dialog.webReviewLayout=layout;
    }
    dialog.querySelector('iframe').src=url.href;if(!dialog.open)dialog.showModal();notify(true);requestAnimationFrame(()=>dialog.webReviewLayout());
  };

  // Own page action: open an existing, paired coding record without submitting a model turn.
  window.openWorkstationTask = async function(id) {
    if(state.phase!=='idle'||typeof id!=='string'||!/^[a-f0-9]{32}$/.test(id))return false;
    const tasks=normalizeTasks(await request('/api/bot/tasks'));
    const task=tasks.find(t=>t.id===id);if(!task||state.phase!=='idle')return false;
    const partition=partitionOfTask(task);if(!partition)return false;state.tasks=tasks;rebuildList(partition);switchPartition(partition);
    if(state.target?.key==='task:'+task.id){await loadConversation({});return true;}
    selectItem({kind:'task',id:task.id,partition,task,title:task.title||task.goal});return state.target?.key==='task:'+task.id;
  };

  window.openWorkstationCodeTask=async function(id){return window.openWorkstationTask(id);};

  // Same-origin mobile shell may prepare text; sending stays with the original UI.
  window.remoteWorkstationPrepareDraft = function (text) {
    try { if (parent === window || parent.location.origin !== location.origin || new URLSearchParams(location.search).get('desktop_embed') !== '1') return { accepted: false, reason: '请在原对话入口填写。' }; } catch (_) { return { accepted: false, reason: '对话来源不匹配。' }; }
    if (typeof text !== 'string' || !text.trim() || text.length > 20000) return { accepted: false, reason: '请填写有效的对话内容。' };
    if (state.phase !== 'idle') return { accepted: false, reason: '当前对话正在处理，原文已保留在助手输入框。' };
    if (state.target && state.target.kind !== 'new' && (state.target.partition === 'deepseek' || isFlashConversation())) return { accepted: false, reason: '当前历史对话只供查看，请先新建对话；原文仍保留在助手输入框。' };
    const input = $('composerInput');
    if (input.value.trim() || (!state.target && state.drafts.get('new:' + state.partition))) return { accepted: false, reason: '对话已有草稿，未覆盖；原文仍保留在助手输入框。' };
    if (!state.target) newConversation();
    if ($('composer').hidden || input.readOnly || input.value.trim()) return { accepted: false, reason: '对话已有草稿或暂不可输入，未覆盖；原文仍保留在助手输入框。' };
    input.value = text.trim();input.dispatchEvent(new Event('input', { bubbles: true }));input.focus();
    return { accepted: true, reason: '已带入普通对话，请在原会话里检查并发送。' };
  };

  boot();
})();
