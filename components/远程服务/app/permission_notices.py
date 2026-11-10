"""Explicit permission-blocker notices, not an authorization or isolation layer."""
import re
import json

PERMISSION_MARKER='[需要你处理：权限]'
PERMISSION_INSTRUCTIONS=(
    '\n\n权限处理约定：若下一步超出用户已授权的范围、需要额外目录/网络/管理员授权，'
    '或执行器明确拒绝权限，请暂停相关操作。不要通过关闭沙箱、更换工具或自行提权规避拒绝。'
    '只汇报已完成部分，并说明拟进行的操作、受限原因、最小所需授权和用户可在电脑端手动完成的步骤。'
    '本工作台当前不能在手机直接批准系统权限；不要声称已获得授权。'
    '需要用户处理权限时，最终摘要以'+PERMISSION_MARKER+'开头；结构化结果必须使用needs_attention，不能标记completed。'
    '不需要额外权限的正常任务直接继续。')


def permission_error(value):
    if not isinstance(value,str):return False
    return bool(re.search(r'permission denied|access (?:is )?denied|operation not permitted|\bEACCES\b|\bEPERM\b|'
                         r'winerror\s*5\b|requires? (?:user )?approval|approval (?:required|denied)|'
                         r'权限不足|访问被拒绝|拒绝访问|需要(?:管理员|额外|用户)授权',value[:6000],re.I))


def permission_notice(summary=''):
    summary=summary.strip().removeprefix(PERMISSION_MARKER).strip() if isinstance(summary,str) else ''
    return ('需要你处理：权限\n'+(summary[:2000]+'\n' if summary else '执行器报告权限被拒绝或需要额外授权。\n')+
            '请在电脑端核对拟操作内容，按最小范围授权，或手动完成受限步骤后再发送后续指令。'
            '本次不会自动提权或重新发送任务。')


def reply_blocker(result):
    if not isinstance(result,str):return None
    text=result.strip()
    if text.startswith(PERMISSION_MARKER):return permission_notice(text)
    fenced=re.fullmatch(r'```(?:json)?\s*([\s\S]*?)\s*```',text)
    if fenced:text=fenced[1]
    try:value=json.loads(text)
    except ValueError:return None
    if not isinstance(value,dict) or value.get('status') not in ('completed','needs_attention'):return None
    summary=value.get('summary')
    if not isinstance(summary,str) or not summary.strip():return None
    if summary.lstrip().startswith(PERMISSION_MARKER):return permission_notice(summary)
    return summary[:2000] if value['status']=='needs_attention' else None
