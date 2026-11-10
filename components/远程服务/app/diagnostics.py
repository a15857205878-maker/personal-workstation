"""Read-only diagnostics assembled exclusively from fixed labels and counts."""
from datetime import datetime, timezone
import time
from adapters import agents


def diagnostic_report(network, agent_list, task_list, jobs, uptime):
    checks = []

    def add(identifier, label, status, detail, action=''):
        checks.append(dict(id=identifier,label=label,status=status,detail=detail,action=action))

    add('receiver','电脑接收器','ok','本次自检请求已到达电脑。','切换网络后如有短暂中断，稍候再重新检查。')
    remote_state = (network or {}).get('remote_access',{}).get('state')
    remote_details = {
        'connected':('ok','电脑的 Tailscale 已连接。'),
        'not_installed':('warn','电脑未安装 Tailscale，同一局域网仍可使用。'),
        'needs_login':('warn','电脑的 Tailscale 等待登录或网络批准。'),
        'needs_approval':('warn','电脑等待 Tailscale 网络管理员批准。'),
        'offline':('warn','电脑的 Tailscale 未连接，同一局域网仍可使用。'),
        'starting':('info','电脑的 Tailscale 正在建立连接。'),
        'unavailable':('unknown','暂时无法读取电脑的 Tailscale 状态。'),
    }
    status, detail = remote_details.get(remote_state,('unknown','暂时无法确认电脑的远程网络状态。'))
    add('remote','Tailscale（电脑端）',status,detail,'这里只检查电脑；手机端也需保持 Tailscale 连接，并使用已配对的远程入口。')
    if agent_list is None:
        add('agent','Codex 执行程序','unknown','暂时无法检查执行程序。','可在电脑确认 Codex 能否正常使用。')
    elif any(agent.get('id')=='codex' and agent.get('available') for agent in agent_list):
        add('agent','Codex 执行程序','ok','已找到执行程序；未检查登录状态或额度。','自检不会调用模型。任务失败时请查看对应会话的错误提示。')
    else:
        add('agent','Codex 执行程序','warn','电脑未找到 Codex 执行程序。','请在电脑完成安装和登录后重新检查。')
    if task_list is None:
        add('tasks','电脑新任务队列','unknown','暂时无法读取任务状态。','请稍后重试，不要重复发布原任务。')
    else:
        queued=sum(task.get('status')=='queued' for task in task_list)
        running=sum(task.get('status')=='running' for task in task_list)
        add('tasks','电脑新任务队列','info' if queued or running else 'ok',f'排队 {queued} 项，执行中 {running} 项。','这是工作台创建的新任务计数，不代表桌面全部会话状态。')
    label='本网页续发指令（当前范围最近20条）'
    if jobs is None:
        add('replies',label,'unknown','暂时无法读取指令队列。','请稍后重试，发送结果以原会话队列为准。')
    else:
        recent=jobs[:20]
        pending=sum(job.get('status') in ('queued','waiting') for job in recent)
        sending=sum(job.get('status')=='sending' for job in recent)
        busy=any(job.get('status') in ('queued','waiting') and (job.get('observed_status')=='native_writer_busy' or job.get('blocked_by')=='native_writer_busy') for job in recent)
        detail=f'最近 {len(recent)} 条中，尚未送达 {pending} 条，处理中 {sending} 条。'
        if busy:
            detail+=' 最近一次执行尝试发现原会话被占用，队列将按原规则等待重试。'
        add('replies',label,'warn' if pending else ('info' if sending else 'ok'),detail,
            '需要后台执行时，请退出占用该会话的 Codex 桌面，保持接收器运行；不要重复发送。' if busy else '仅统计当前网页来源；选择会话时仅看该会话，未选择时看该网页全部会话。')
    checked_at=time.time()
    stamp=datetime.fromtimestamp(checked_at,timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    summary='工作台连接自检\n检查时间：'+stamp+'\n'+'\n'.join(check['label']+'：'+check['detail']+(' 建议：'+check['action'] if check['action'] else '') for check in checks)
    return dict(version=1,checked_at=checked_at,uptime_seconds=max(0,int(uptime)),checks=checks,summary=summary)


def server_diagnostics(server, source, thread_id=None):
    def read(probe):
        try:
            return probe()
        except Exception:
            # Never copy exception strings, filesystem paths or raw logs.
            return None
    return diagnostic_report(
        read(server.refresh_network), read(agents), read(server.tasks.list),
        read(lambda:server.bot.replies.list('web',source,thread_id)),
        time.monotonic()-server.started_at)
