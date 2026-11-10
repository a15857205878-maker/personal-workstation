"""One read-only projection for a newly-created task or an existing chat."""
import sqlite3


TASK_HINTS={'queued':'电脑已接收，正在排队。','running':'电脑正在执行本次任务。',
            'completed':'任务已完成。','failed':'执行失败，请查看错误。',
            'needs_attention':'任务需要处理，请查看提示。','cancelled':'任务已停止。'}
JOB_HINTS={'queued':'指令已接收，尚未送达。','waiting':'等待会话释放占用。',
           'sending':'正在连接或执行原会话。','completed':'最近一次指令已完成。',
           'needs_attention':'指令需要处理，请核对提示。'}


def conversation_detail(tasks, reader, replies, source, task_id=None, thread_id=None, before=None):
    if not isinstance(source,str) or not 1<=len(source)<=120:
        raise ValueError('网页来源标识无效，请刷新后重试。')
    for value in (task_id,thread_id):
        if value is not None and (not isinstance(value,str) or not 1<=len(value)<=120):
            raise ValueError('会话标识无效。')
    if not task_id and not thread_id:raise ValueError('请先选择会话。')
    if before is not None and (type(before) is not int or before<0):raise ValueError('历史游标无效。')
    task=tasks.get(task_id) if task_id else next((t for t in tasks.list() if t.get('remote_session')==thread_id),None)
    if task and task.get('agent')=='codex-deepseek-code':
        if thread_id:raise ValueError('代码协作请按项目任务读取，不接管单独会话。')
        from web_product import WebProducts
        task=dict(task)
        try:
            WebProducts(tasks).entry_root(task_id or task['id']);task['web_preview_ready']=True
        except (ValueError,KeyError,OSError):task['web_preview_ready']=False
        stages={'queued':'等待开始','backend':'Codex 后端与接口','frontend':'DeepSeek 前端','integration':'Codex 联调测试','completed':'执行阶段完成'}
        if task.get('code_route')=='static':stages.update(integration='Codex 前端验收',completed='纯前端两阶段完成')
        return {'task':task,'provider':'codex-deepseek-code','thread_id':None,'title':task['title'],
                'status':task['status'],'status_hint':('纯前端 · ' if task.get('code_route')=='static' else '')+stages.get(task.get('code_stage'),'阶段待确认')+' · '+TASK_HINTS.get(task['status'],''),
                'history':None,'history_error':None,'jobs':[],'can_reply':False,
                'reply_hint':'这是共用代码项目，进度与文件在此查看；首版不把后续消息发到某一方历史会话。'}
    if task and task.get('agent')=='deepseek-flash':
        if thread_id:raise ValueError('Flash任务不使用Codex会话，请重新选择任务。')
        return {'task':task,'provider':'deepseek-flash','thread_id':None,'title':task['title'],
                'status':task['status'],'status_hint':TASK_HINTS.get(task['status'],'状态暂未确认。'),
                'history':None,'history_error':None,'jobs':[],'can_reply':False,
                'reply_hint':'Flash首版为独立任务通道；后续请新建Flash任务。'}
    if task:
        target=task.get('remote_session') or None
        if thread_id and target!=thread_id:raise ValueError('任务与会话编号不匹配，未读取其他会话。')
        thread_id=target
    history=None;history_error=None;metadata=None;can_reply=False
    title=task['title'] if task else '未命名会话'
    jobs=[]
    if thread_id:
        try:
            metadata=reader.get(thread_id)
        except KeyError:
            if task is None:raise
            history_error='会话记录尚未就绪，可继续查看任务进度。'
        except (OSError,ValueError,sqlite3.Error):
            history_error='暂时无法读取会话索引，任务与指令状态仍可查看。'
        if metadata:
            native_title=metadata.get('title') or '未命名会话'
            if not task or not native_title.startswith('这是用户从个人任务工作台提交的独立任务。'):
                title=native_title
            can_reply=replies is not None and (task is None or task.get('agent')=='codex')
            try:
                history=reader.history(thread_id,before=before)
            except (OSError,ValueError,KeyError,sqlite3.Error):
                history_error='暂时无法读取历史正文，任务与指令状态仍可查看；可稍后刷新或重新选择会话。'
        if replies is not None:jobs=replies.list('web',source,thread_id)
    status=task['status'] if task else (history or {}).get('status','unknown')
    hint=TASK_HINTS.get(status,'状态暂未确认。') if task else (history or {}).get('status_hint','状态暂未确认。')
    latest=next((j for j in jobs if j.get('status')!='cancelled'),None)
    sending=next((j for j in jobs if j.get('status')=='sending'),None)
    initial_active=task and task['status'] in ('queued','running')
    if not initial_active:
        if sending:
            status='running';hint=JOB_HINTS['sending']
        elif latest and latest.get('status') in ('queued','waiting','sending'):
            status='running' if latest['status']=='sending' else latest['status']
            hint=latest.get('waiting_reason') or JOB_HINTS[latest['status']]
        elif history and history.get('status') in ('running','unconfirmed'):
            status=history['status'];hint=history.get('status_hint','状态依据本地记录。')
        elif latest and latest.get('updated',0)>=(task or {}).get('updated',0):
            status=latest['status'];hint=JOB_HINTS.get(status,'请查看指令状态。')
    return {'task':task,'thread_id':thread_id,'title':title,'status':status,'status_hint':hint,
            'history':history,'history_error':history_error,'jobs':jobs,'can_reply':can_reply}
