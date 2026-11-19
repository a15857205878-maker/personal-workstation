"""Display diagnostics and explicit retry targets; never dispatches requests."""
import re

def diagnose(error):
    detail=str(error or '本次未收到完整结果')[:2000]
    detail=re.sub(r'https?://[^\s<>]+','[接口地址]',detail,flags=re.I)
    detail=re.sub(r'(?i)\b(?:sk-|Bearer\s+)[\w.-]+','[已隐藏凭证]',detail)
    detail=re.sub(r'(?i)(?:api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+','[已隐藏凭证]',detail)
    detail=re.sub(r'(?i)\b[A-Z]:[\\/][^\r\n<>"|]+|\\\\[^\r\n<>"|]+','[本机路径]',detail)
    detail=re.sub(r'/(?:Users|home|tmp|var|mnt|etc)/[^\s<>]+','[本机路径]',detail)
    raw=str(error or '').lower()
    rules=[('auth',r'401|403|unauthor|forbidden|api.?key|密钥|未登录|登录|认证','模型连接需要检查','在电脑的模型连接中检查登录或密钥，再重试。'),
           ('quota',r'429|rate.?limit|quota|余额|额度|限流|频率','额度不足或请求过于频繁','稍后重试，或检查该模型的额度。'),
           ('timeout',r'timeout|timed out|超时|等待时间|秒上限|分钟上限','等待模型回复超时','检查连接后可单独重试；上次请求可能已经计费。'),
           ('connection',r'connect|network|502|503|504|网络|连接|离线','暂时无法连接模型','检查网络和模型服务，再重试这一项。'),
           ('format',r'格式|json|完整|finish|截断|字符|svg|文件|协议','回复不完整或格式不符合要求','可单独重试；若反复出现，调整需求或检查模型能力。')]
    for code,pattern,title,hint in rules:
        if re.search(pattern,raw):return dict(code=code,title=title,hint=hint,detail=detail)
    return dict(code='failed',title='这次回复未完成',hint='查看详情，检查该模型后可单独重试。',detail=detail)

def failure_targets(session,turn):
    result=[]
    def add(item,label,error):
        attempts=[t for t in session['turns'] if t.get('retry_of')==dict(turn_id=turn['id'],item=item)]
        retryable=turn['state']=='failed' and not attempts
        reason='此项已有单独重试记录，请查看后续回复。' if attempts else '中断结果未确认，请先核对原记录。' if turn['state']!='failed' else ''
        result.append(dict(item=item,label=label,**diagnose(error),retryable=retryable,blocked_reason=reason))
    run=turn.get('run') or {}
    if turn['kind'] in ('chat','discuss'):
        for row in run.get('messages',[]):
            if row.get('state')=='failed' and row.get('seat') in session['roles']:
                add('message:'+row['id'],session['roles'][row['seat']]['name'],row.get('error') or run.get('error') or turn.get('error'))
    for i,job in enumerate(turn.get('jobs',[])):
        jr=job.get('run') or {}
        if (jr.get('status') or job['state'])=='failed':add('job:'+str(i),job['title'],jr.get('error') or job.get('error') or turn.get('error'))
    if not result and turn.get('state') in ('failed','interrupted'):
        error=str(turn.get('error') or '')
        if turn.get('drafted') and turn['state']=='failed' and not turn.get('jobs') and error.startswith(('协商方案未通过校验：','协商方案格式、能力或剩余预算','DeepSeek 的 JSON 模式返回空白')):
            detail='这条旧记录没有保存具体校验原因。拟分工阶段已停止。' if error.startswith('协商方案格式、能力或剩余预算') else diagnose(error)['detail']
            return [dict(item='',label='本轮',code='plan_rejected',title='未能生成可确认的分工',
                         hint='可把原需求放回输入框，再请龙娘拟分工，或用「交办任务」手动指定。',
                         detail=detail,retryable=False,blocked_reason='子任务尚未开始。重新拟分工会另计一次调用。')]
        # Startup/crash uncertainty is visible, but has no safe single-item replay.
        d=dict(item='',label='本轮',**diagnose(turn.get('error')),retryable=False,blocked_reason='请先核对执行记录；未确认的请求不会自动重发。')
        if turn['kind']=='execute' and not turn.get('jobs') and run.get('status')=='failed':
            add('work','结果',run.get('error') or turn.get('error'))
        else:result.append(d)
    return result


def retry_history(turns,origin):
    by_id={t['id']:i for i,t in enumerate(turns)};seen=set();identifier=origin['turn_id']
    while True:
        if identifier in seen or identifier not in by_id:raise ValueError('重试来源不完整，请先核对原记录')
        seen.add(identifier);index=by_id[identifier];source=turns[index]
        if not source.get('retry_of'):return turns[:index+1]
        identifier=source['retry_of']['turn_id']
