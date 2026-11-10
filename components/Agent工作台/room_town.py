"""Local desktop room boundary; original TownAdapter owns all state."""
ALLOWED=frozenset(('bootstrap','focus_state','town_action','focus_start','focus_pause','focus_resume','focus_end'))
def call_room_town(bridge,request):
    if not isinstance(request,dict) or set(request)!={'action','payload'}:raise ValueError('小镇请求无效')
    if not isinstance(request['action'],str) or request['action'] not in ALLOWED or not isinstance(request['payload'],dict):raise ValueError('不支持的小镇操作')
    if request['action']=='town_action' and request['payload'].get('action')=='set_partner':raise ValueError('伙伴选择已移除')
    result=bridge.call('workstation_town_call',request)
    if not isinstance(result,dict) or result.get('ok') is not True:raise ValueError(result.get('error','小镇请求未确认') if isinstance(result,dict) else '小镇请求未确认')
    return result['data']
