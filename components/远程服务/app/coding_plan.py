"""Cheap deterministic routing for new projects; never calls a model."""
import re

STATIC_STAGES=('frontend','integration')
FULLSTACK_STAGES=('backend','frontend','integration')

def coding_route(task):
    if task.get('project_kind','web')=='local-tool':return 'fullstack'
    goal=task.get('goal','')
    if not isinstance(goal,str):raise ValueError('项目目标无效。')
    text=re.sub(r'https?://\S+','',goal,flags=re.I)
    # Remove only the named negative requirements, not later positive requests.
    negative=r'(?:不需要|不需|无需|不要|不用|不做|不使用|不接入|不添加|不含|不涉及|不加|没有|无须|无)'
    feature=r'(?:后端(?:接口|服务)?|服务端(?:数据库|接口|API|服务)?|服务器(?:数据库|接口)?|登录(?:注册|功能|认证|验证)?|注册(?:功能)?|数据库|身份认证|权限管理|后台管理|支付|联网|外部依赖|纯前端|纯静态|前端|静态)'
    text=re.sub(negative+r'\s*'+feature+r'(?:\s*(?:、|/|以及|和|或|与|及)\s*(?:'+negative+r'\s*)?'+feature+r')*','',text,flags=re.I)
    text=re.sub(r'(?:登录|注册)(?:页面|界面|表单|页)','',text)
    # Browser-local storage does not require a service or a server database.
    text=re.sub(r'浏览器(?:的)?(?:本地)?数据库(?:\s*(?:IndexedDB|localStorage))?|(?:IndexedDB|localStorage)(?:\s*(?:本地)?数据库)?','',text,flags=re.I)
    positive=text
    server=bool(re.search(r'后端|服务端|数据库|身份认证|权限管理|后台管理|登录|注册|支付|跨设备(?:同步|共享)|多人(?:共享|同步)|(?:接入|调用|提供|实现|开发|编写|对接|使用|需要).{0,8}(?:API|接口)',positive,re.I))
    static=bool(re.search(r'纯前端|纯静态|只(?:做|要|用|需).{0,4}(?:前端|静态)',positive))
    if static and server:raise ValueError('纯前端与服务端需求冲突，请明确是否需要后端、数据库或真实登录。')
    return 'fullstack' if server else 'static'

def stages_for(route):
    if route not in ('static','fullstack'):raise ValueError('未知代码协作路线。')
    return STATIC_STAGES if route=='static' else FULLSTACK_STAGES
