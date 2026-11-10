"""PC functional areas; navigation grouping is independent of execution rights."""
from copy import deepcopy

ZONES=(('work','工作区'),('leisure','休闲区'),('shared','公共设置'))
MODULES=(
    ('tasks','独立任务','work','native'),('collaboration','双模型高级协作','work','native'),
    ('artifacts','任务成果','work','native'),('materials','资料管理','work','adapter'),
    ('delivery','文件打包','work','adapter'),('agent','Agent 工作台','work','native'),
    ('games','游戏管理','leisure','adapter'),('wheel','游戏轮盘','leisure','adapter'),
    ('reading','书房与放松','leisure','native'),
    ('town','小镇与专注','leisure','embedded'),('focus','专注计时','leisure','embedded'),
    ('icons','图标换装台','shared','native'),('status','桌面状态卡片','shared','external'),
    ('settings','模型与外观设置','shared','native'),('diagnostics','维护自检','shared','native'))
AREA={m[0]:m[2] for m in MODULES}
# Compatibility only: the main UI routes town/focus to the embedded town frame.
EXTERNAL=frozenset(('town','focus','status'))

def catalog():
    return {'schema_version':1,'zones':[{'id':key,'name':name,'modules':[
        {'id':identifier,'name':label,'integration':kind,**({'route':'town'} if identifier in ('town','focus') else {'route':'icons'} if identifier=='icons' else {})} for identifier,label,area,kind in MODULES if area==key]}
        for key,name in ZONES], 'note':'功能分区，不搬迁数据或启用自动调度；外部模块保留独立窗口。'}

def validate_module(payload):
    if not isinstance(payload,dict) or set(payload)!={'id'} or payload.get('id') not in EXTERNAL:
        raise ValueError('只允许打开已登记的个人工具模块。')
    return payload['id']

def split_tools(data,zone):
    if zone not in dict(ZONES):raise ValueError('未知功能分区。')
    result=deepcopy(data);result['zone']=zone
    result['tools']=[t for t in result.get('tools',[]) if AREA.get(t.get('id'),'shared')==zone]
    if zone!='leisure':
        result.pop('games',None);result.pop('wheel',None)
    if zone!='work':
        result.pop('pack',None);result.pop('materials',None);result['jobs']=[]
    def recent_area(row):
        key=row.get('id','')
        if key.startswith(('game:','steam:')) or key=='wheel':return 'leisure'
        if key=='pack' or key.startswith(('materials:','material:')):return 'work'
        return AREA.get(key,'shared')
    result['recent']=[r for r in result.get('recent',[]) if recent_area(r)==zone]
    return result
