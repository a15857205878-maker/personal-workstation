"""Provider boundary: local Codex, local Harness, optional official text APIs."""
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit, quote

BASE = Path(__file__).resolve().parent
from codex_channel import CodexChannel, find_codex
from provider_client import ProviderClient, ProviderError, Cancelled
from credential_store import protect, unprotect, atomic_json, validate_url

LABELS = dict(text_claude='Claude',excel_gemini='Gemini（Excel）',animation_gemini='Gemini（小动画）',research_kimi='Kimi（搜索）',presentation_gemini='Gemini（PPTX）', image_gemini='Gemini（图片生成）', text_1='GPT-6.1 Terra', text_2='千问', presentation='Claude Sonnet 5.5',
              excel='Kimi', research_sources='Gemini', frontend='DeepSeek',
              backend_and_integration='GPT-6.1 Sol')


class Settings:
    def __init__(self, folder, encrypt=protect, decrypt=unprotect):
        self.path = Path(folder) / 'connections.json'
        self.encrypt, self.decrypt = encrypt, decrypt
        self.lock = threading.RLock()

    def _read(self):
        if not self.path.exists():
            return {}
        try:
            if self.path.stat().st_size > 32768:
                raise ValueError()
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (OSError, ValueError):
            raise ValueError('接入配置损坏，请检查 data/connections.json，原文件未覆盖。') from None

    def public(self):
        with self.lock:
            config = self._read()
            result = {provider: dict(base_url=config.get(provider, {}).get('base_url',
                                        'https://generativelanguage.googleapis.com/v1beta/openai' if provider == 'gemini' else ''),
                                   model=config.get(provider, {}).get('model', ''),
                                   has_key=bool(config.get(provider, {}).get('secret')))
                    for provider in ('qwen', 'gemini','claude','kimi')}
            result['gemini']['image_model']=config.get('gemini',{}).get('image_model','')
            return result

    def secret(self, provider):
        with self.lock:
            value = self._read().get(provider, {}).get('secret', '')
            return self.decrypt(value) if value else ''

    def save(self, p):
        provider = p.get('provider')
        if provider not in ('qwen','gemini','claude','kimi'):
            raise ValueError('请选择千问、Gemini、Claude或Kimi')
        base = validate_url(p.get('base_url', ''))
        parsed = urlsplit(base)
        host = parsed.hostname
        from .generation_channels import allowed_endpoint
        allowed_endpoint(provider,base)
        model = p.get('model', '')
        key = p.get('key', '')
        if not isinstance(model, str) or not re.fullmatch(r'[a-zA-Z0-9._/-]{1,200}', model):
            raise ValueError('请填写明确的 API 模型 ID（并非网页显示名称）')
        if not isinstance(key, str) or len(key) > 4096 or any(c.isspace() for c in key):
            raise ValueError('API Key 格式无效')
        image_model=p.get('image_model','')
        if not isinstance(image_model,str) or (image_model and not re.fullmatch(r'[a-zA-Z0-9._/-]{1,200}',image_model)):raise ValueError('图片模型ID无效')
        with self.lock:
            config = self._read()
            secret = self.encrypt(key) if key else config.get(provider, {}).get('secret', '')
            if not secret:
                raise ValueError('首次配置需要 API Key；客户端登录不会提供 API Key。')
            config[provider] = dict(base_url=base, model=model, secret=secret,**({'image_model':p.get('image_model',config.get(provider,{}).get('image_model',''))} if provider=='gemini' else {}))
            atomic_json(self.path, config)
        return self.public()


class Adapters:
    def __init__(self, settings):
        self.settings = settings
        self.codex = find_codex()
        self.harness = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/DeepSeek Harness/DeepSeek Harness.exe'

    def capabilities(self):
        config = self.settings.public()
        result = {}
        for role, label in LABELS.items():
            mode, can_run, detail = 'manual', False, '客户端交接：打开后自行提交，完成后导入成果。'
            if role in ('text_1', 'backend_and_integration'):
                mode, can_run = 'codex_text', bool(self.codex)
                detail = ('本机 Codex 文字通道，使用现有登录；实际权限以调用结果为准。'
                          if can_run else '未找到本机 Codex 原生程序。')
                if role == 'backend_and_integration':
                    detail += '当前可讲解操作步骤和分析报错；实际操作及代码修改需要在 Codex 中交接。'
            elif role == 'frontend':
                mode, can_run = 'deepseek_harness', self.harness.is_file()
                detail = '本机 Harness 独立执行；执行目录为当前任务目录。' if can_run else '未安装 DeepSeek Harness。'
            elif role in ('presentation_gemini','excel_gemini','image_gemini','animation_gemini','text_claude','research_kimi'):
                provider='claude' if role=='text_claude' else 'kimi' if role=='research_kimi' else 'gemini'
                cfg=config.get(provider,{})
                model=cfg.get('image_model') if role=='image_gemini' else cfg.get('model')
                ready=bool(cfg.get('has_key') and model and cfg.get('base_url'))
                mode,can_run=('api' if ready else 'needs_config'),ready
                detail='官方API已配置；实际权限以调用结果为准。' if ready else '请在连接设置填写官方API、模型ID和密钥；不会自动改用其他模型。'
                if role=='image_gemini':detail+='图片模型与文字模型分别配置。'
                if role=='animation_gemini':detail+='生成离线CSS/SVG动画，在工作站隔离预览，不执行脚本。'
                if role=='research_kimi':detail+='先调用Kimi搜索再汇总，最多两次请求；搜索失败不会降级为无搜索回答。'
            elif role in ('text_2', 'research_sources'):
                provider = 'qwen' if role == 'text_2' else 'gemini'
                ready = bool(config[provider]['has_key'] and config[provider]['model'] and config[provider]['base_url'])
                mode, can_run = ('api' if ready else 'needs_config'), ready
                detail = ('已配置 API，实际权限以调用结果为准。' if ready
                          else '未配置官方 API；可打开客户端交接，或在设置中填写接口。')
                if role == 'research_sources' and ready:
                    detail += '使用原生 Google Search grounding；不支持该工具的模型会明确失败，不降级成无搜索回答。'
            result[role] = dict(label=label, mode=mode, can_run=can_run, detail=detail,
                                can_review=bool(can_run and mode in ('codex_text','api') and role in ('text_1','text_2','text_claude','backend_and_integration')))
        return result

    def run(self, role, prompt, cancel, on_chunk, folder):
        if role in ('presentation_gemini','excel_gemini','image_gemini','animation_gemini','text_claude','research_kimi'):
            from .generation_channels import GenerationChannels
            return GenerationChannels(self.settings).run(role,prompt,cancel,on_chunk,folder)
        if role in ('text_1', 'backend_and_integration'):
            channel = CodexChannel()
            model = 'gpt-6.1-terra' if role == 'text_1' else 'gpt-6.1-sol'
            if role == 'backend_and_integration':
                prompt = '当前通道只能讲解和分析，不能操作软件或修改代码。用户要求实际执行时明确告知需要在 Codex 客户端交接。\n' + prompt
            try:
                return channel.complete({'model': model}, '', [{'role': 'user', 'content': prompt}],
                                        5000, cancel, on_chunk, time.time() + 180)['content']
            finally:
                channel.interrupt()
        if role == 'frontend':
            return self._deepseek(prompt, cancel, on_chunk, folder)
        if role in ('text_2', 'research_sources'):
            provider = 'qwen' if role == 'text_2' else 'gemini'
            config = self.settings.public()[provider]
            key = self.settings.secret(provider)
            if not key or not config['model']:
                raise ValueError('请先配置该服务的 API')
            if provider == 'gemini':
                return self._gemini(config, key, prompt, cancel, on_chunk)
            channel = ProviderClient()
            try:
                answer = channel.complete({**config, 'kind': 'compatible'}, key,
                                          [{'role': 'user', 'content': prompt}], 5000,
                                          cancel, on_chunk, time.time() + 180)
                return answer['content'] + '\n\n接口返回模型：' + answer['model']
            finally:
                channel.interrupt()
        raise ValueError('该岗位当前使用客户端交接，请打开客户端并导入成果。')

    def _deepseek(self, prompt, cancel, on_chunk, folder):
        taskfile = folder / 'request.txt'
        taskfile.write_text('独立完成当前任务，不派生其他 Agent、不发布或发送第三方消息、不修改账号或安全设置。'
                            '只处理当前任务，改动限制在当前工作目录；如需要原项目文件则说明缺失。\n' + prompt,
                            encoding='utf-8')
        args = [sys.executable, str(BASE / 'integration/dispatch.py'), '--workspace', str(folder),
                '--task-file', str(taskfile), '--timeout', '300']
        with (folder / 'harness-launch.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen(args, stdout=log, stderr=log, cwd=folder,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            last = ''
            while process.poll() is None:
                if cancel.wait(.25):
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
                    else:
                        process.terminate()
                    raise Cancelled('本地跟踪已停止，远端状态需检查。')
                statefiles = list((folder / 'work/deepseek-collab/runs').glob('*/state.json'))
                if statefiles:
                    try:
                        value = json.loads(max(statefiles, key=lambda p: p.stat().st_mtime).read_text(encoding='utf-8'))
                        text = value.get('answer', '')
                        if text.startswith(last) and text != last:
                            on_chunk(text[len(last):])
                            last = text
                    except (OSError, ValueError):
                        pass
            runs = list((folder / 'work/deepseek-collab/runs').glob('*/result.json'))
            if process.returncode != 0 or not runs:
                raise ValueError('Harness 执行未完成，请检查登录、额度或任务目录中的 harness-launch.log。')
            result = json.loads(max(runs, key=lambda p: p.stat().st_mtime).read_text(encoding='utf-8'))
            if result.get('status') not in ('completed', 'success'):
                raise ValueError('Harness 未确认完成，请检查任务目录中的运行记录。')
            answerfile = max(runs, key=lambda p: p.stat().st_mtime).parent / 'answer.md'
            answer = answerfile.read_text(encoding='utf-8')
            if not last:
                on_chunk(answer)
            return answer

    def _gemini(self, config, key, prompt, cancel, on_chunk):
        # Use the native endpoint because compatible text completions do not imply web search.
        connection = http.client.HTTPSConnection('generativelanguage.googleapis.com', timeout=90)
        finished = threading.Event()
        def watch_cancel():
            while not finished.wait(.1):
                if cancel.is_set():
                    if connection.sock:
                        try:
                            connection.sock.shutdown(2)
                        except OSError:
                            pass
                    connection.close()
                    return
        threading.Thread(target=watch_cancel, daemon=True).start()
        try:
            payload = dict(contents=[dict(parts=[dict(text=prompt)])], tools=[dict(google_search={})])
            connection.request('POST', '/v1beta/models/' + quote(config['model'], safe='') + ':generateContent',
                               json.dumps(payload).encode(), {'x-goog-api-key': key, 'Content-Type': 'application/json'})
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError(f'Gemini 接口返回 HTTP {response.status}；请核对 Key、模型和搜索权限。')
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError('Gemini 响应超过 2 MB')
            value = json.loads(raw)
            candidate = value.get('candidates', [{}])[0]
            if candidate.get('finishReason') != 'STOP':
                raise ValueError('Gemini 未正常完成回答，未将其标记为成功。')
            text = '\n'.join(part.get('text', '') for part in candidate.get('content', {}).get('parts', [])
                             if not part.get('thought'))
            chunks = candidate.get('groundingMetadata', {}).get('groundingChunks', [])
            sources = [row['web'] for row in chunks if isinstance(row.get('web'), dict)
                       and row['web'].get('uri', '').startswith('https://')]
            text += '\n\n搜索来源：\n' + ('\n'.join(f"{s.get('title', '来源')}：{s['uri']}" for s in sources)
                                          if sources else '本次未返回搜索来源，不能视为已核实的资料。')
            if cancel.is_set():
                raise Cancelled('已停止')
            text = text.replace(key, '[已隐藏密钥]')
            on_chunk(text)
            return text
        except (OSError, ValueError, IndexError) as exc:
            if isinstance(exc, ValueError) and 'Gemini' in str(exc):
                raise
            raise ValueError('Gemini 调用失败，请检查网络、模型及搜索权限；未自动重试。') from None
        finally:
            finished.set()
            connection.close()
