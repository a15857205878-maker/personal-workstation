"""Bounded two/three member center helpers; old lab remains two-member by default."""
def member_keys(payload,allow_third=True):
    keys=[('A','primary_id'),('B','reviewer_id')]
    if payload.get('third_id'):
        if not allow_third:raise ValueError('此入口仅支持两名成员')
        keys.append(('C','third_id'))
    return keys

def validate_target(target,roles,rounds=1):
    if (not isinstance(target,str) or not 1<=len(target)<=len(roles)
        or len(set(target))!=len(target) or any(s not in roles for s in target)
        or type(rounds) is not int or rounds not in (1,2,4,6)
        or (rounds>1 and len(target)<2)):
        raise ValueError('回应成员、顺序或轮数无效')
    return target
