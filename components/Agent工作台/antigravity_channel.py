"""Bounded text-only Antigravity CLI transport; credentials stay with the client."""
from pathlib import Path
import json,os,re,shutil,subprocess,tempfile,threading,time
from provider_client import ProviderError,Cancelled

SETTINGS={'permissions':{'allow':[],'ask':[],'deny':[x+'(*)' for x in ('read_file','write_file','command','read_url','execute_url','mcp')]},'statusLine':{'enabled':False},'title':{'enabled':False}}

def find_agy():
    candidates=[Path.home()/'AppData/Local/agy/bin/agy.exe',shutil.which('agy.exe')]
    return next((str(Path(p).resolve()) for p in candidates if p and Path(p).name.lower()=='agy.exe' and Path(p).is_file()),None)

def command(executable,args):
    return [executable,'--disable-slash-commands','--settings',json.dumps(SETTINGS,separators=(',',':')),*args]

def check_customizations(home=None):
    # Lifecycle hooks/MCP startup are outside model tool permissions.
    # Do not read or alter the user's configurations; refuse inherited execution.
    base=(Path.home() if home is None else Path(home))/'.gemini/config'
    try:
        configured=any((base/name).exists() and (base/name).stat().st_size>0 for name in ('hooks.json','mcp_config.json'))
        plugins=base/'plugins'
        configured=configured or (plugins.exists() and any(plugins.iterdir()))
    except OSError:configured=True
    if configured:raise ProviderError('检测到 Antigravity 全局扩展配置；当前文字通道暂不启动，避免继承钩子或 MCP。原配置未修改。')

class AntigravityChannel:
    def __init__(self,finder=find_agy,command_factory=command):
        self.finder=finder;self.factory=command_factory;self.lock=threading.Lock();self.process=None
    @staticmethod
    def _kill(p):
        if p.poll() is not None:return
        if os.name=='nt':
            subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        if p.poll() is None:p.kill()
        try:p.wait(timeout=3)
        except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)
    def interrupt(self):
        with self.lock:p=self.process
        if p:self._kill(p)
    def _run(self,args,content,cancel,deadline):
        if cancel.is_set():raise Cancelled('已停止')
        if time.time()>=deadline:raise ProviderError('Antigravity 调用超时，已停止')
        executable=self.finder()
        if not executable:raise ProviderError('尚未找到 Antigravity CLI，请先安装官方 agy.exe')
        check_customizations()
        with tempfile.TemporaryDirectory(prefix='workstation-agy-') as directory:
            root=Path(directory)
            with (root/'stdout').open('w+b') as out,(root/'stderr').open('w+b') as err:
                p=subprocess.Popen(self.factory(executable,args),cwd=root,stdin=subprocess.PIPE,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                with self.lock:self.process=p
                writer=None
                try:
                    if cancel.is_set():raise Cancelled('已停止')
                    if time.time()>=deadline:raise ProviderError('Antigravity 调用超时，已停止')
                    payload=(json.dumps({'event':'user','message':{'content':content}},ensure_ascii=False)+'\n').encode('utf-8') if content is not None else b''
                    # Writing in a worker keeps cancellation responsive even during startup.
                    def feed():
                        try:
                            if not cancel.is_set() and time.time()<deadline:p.stdin.write(payload)
                            p.stdin.close()
                        except (OSError,ValueError):pass
                    writer=threading.Thread(target=feed,daemon=True);writer.start()
                    while p.poll() is None:
                        if cancel.is_set():raise Cancelled('已停止')
                        if time.time()>=deadline:raise ProviderError('Antigravity 调用超时，已停止')
                        if any((root/n).stat().st_size>2*1024*1024 for n in ('stdout','stderr')):raise ProviderError('Antigravity 输出过大，已停止')
                        time.sleep(.05)
                    if cancel.is_set():raise Cancelled('已停止')
                    out.seek(0);err.seek(0);raw=out.read(2*1024*1024+1);errors=err.read(2*1024*1024+1)
                    if len(raw)>2*1024*1024 or len(errors)>2*1024*1024:raise ProviderError('Antigravity 输出过大，已停止')
                    if p.returncode:
                        if any(s in errors.lower() for s in (b'authentication required',b'not authenticated',b'login required')):raise ProviderError('Antigravity 需要本人在 CLI 中登录，登录后再试')
                        raise ProviderError('Antigravity CLI 未完成请求，请检查登录、模型权限或客户端版本')
                    return raw.decode('utf-8')
                finally:
                    self._kill(p)
                    if writer:writer.join(timeout=1)
                    with self.lock:
                        if self.process is p:self.process=None
    def models(self,profile=None,key=''):
        raw=self._run(['models'],None,threading.Event(),time.time()+30)
        return [line.split()[0] for line in raw.splitlines() if re.fullmatch(r'[a-z0-9][a-z0-9._-]{1,150}',line.split()[0] if line.split() else '')][:100]
    def discover(self):
        if not self.finder():return dict(state='not_installed',models=[],message='请先安装官方 Antigravity CLI',generation_verified=False)
        models=self.models()
        if not models:raise ProviderError('CLI 未返回可用模型，请先完成本人登录')
        return dict(state='catalog',models=[{'id':x} for x in models],message='已读取 Antigravity 模型目录；尚未验证生成。选择模型后保存配置。',generation_verified=False)
    def complete(self,profile,key,messages,max_tokens,cancel,on_chunk,deadline):
        model=profile['model']
        if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{1,150}',model):raise ProviderError('Antigravity 模型 ID 无效')
        content='你是文字协作成员。仅根据以下消息回复，不使用工具、命令、文件或网页。目标回复不超过'+str(max_tokens)+' token。\n'+json.dumps(messages,ensure_ascii=False)
        if len(content)>100000:raise ProviderError('Antigravity 上下文过大')
        raw=self._run(['--input-format','stream-json','--output-format','stream-json','--disable-slash-commands','--mode','plan','--model',model,'--print-timeout',str(max(1,int(deadline-time.time())))+'s'],content,cancel,deadline)
        result=None
        try:
            for line in raw.splitlines():
                event=json.loads(line)
                if not isinstance(event,dict):raise ValueError()
                if event.get('event')=='step_update' and event.get('step_update',{}).get('step_type')=='tool':raise ProviderError('Antigravity 尝试调用群聊不支持的工具，未交付回复')
                if event.get('event')=='result':
                    if result is not None:raise ValueError()
                    result=event['result']
            if not isinstance(result,dict) or result.get('status')!='SUCCESS':raise ValueError()
            text=result['response']
            if not isinstance(text,str) or not text.strip() or len(text)>65536:raise ValueError()
        except (ValueError,KeyError,TypeError,AttributeError) as exc:
            if isinstance(exc,ProviderError):raise
            raise ProviderError('Antigravity 未返回完整有效回复') from None
        if cancel.is_set():raise Cancelled('已停止')
        usage=result.get('usage') or {};public_usage=None
        if not isinstance(usage,dict):usage={}
        if all(type(usage.get(k)) is int and 0<=usage[k]<=10**9 for k in ('input_tokens','output_tokens')):
            public_usage=dict(prompt_tokens=usage['input_tokens'],completion_tokens=usage['output_tokens'])
        on_chunk(text)
        return dict(content=text,model=model,finish_reason='stop',usage=public_usage)
