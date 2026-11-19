"""Quick input only creates drafts / requests reviewed transfer; never submits models."""
import threading,uuid
class QuickCommands:
    def __init__(self,bridge,dispatch):self.bridge=bridge;self.dispatch=dispatch;self.cache={};self.lock=threading.Lock()
    def submit(self,p):
        if not self.lock.acquire(blocking=False):raise ValueError('正在交接，请稍候。')
        try:
            nonce=p.get('request_id','')
            if not isinstance(nonce,str) or len(nonce)>80 or not nonce:raise ValueError('请求编号无效。')
            if nonce in self.cache:
                event=self.cache[nonce];self.dispatch(event);return dict(delivered=True,kind=event['kind'],id=event.get('id'))
            text=p.get('text','')
            if not isinstance(text,str) or not text.strip() or len(text)>8000:raise ValueError('请输入1–8000字符的具体要求。')
            if p.get('mode')=='work':
                bundle=self.bridge.attachments.bundle(p.get('attachments',[]));text=text.strip()+('\n\n'+bundle['text'] if bundle['text'] else '')
                if len(text)>8000:raise ValueError('高级协作需求与附件文字合计超过8000字符，请精简资料后交接。')
                event=dict(kind='advanced',text=text)
            elif p.get('mode')=='tasks':raise ValueError('独立任务已停用，请将需求送入搭档。')
            else:raise ValueError('请选择搭档需求交接。')
            event['request_id']=nonce
            self.cache[nonce]=event
            if len(self.cache)>32:self.cache.pop(next(iter(self.cache)))
            try:self.dispatch(event)
            except Exception:raise ValueError('草稿已保留，但大窗口尚未接收；请点击重试或打开大窗口查看，不会执行模型。') from None
            return dict(delivered=True,kind=event['kind'],id=event.get('id'))
        finally:self.lock.release()
