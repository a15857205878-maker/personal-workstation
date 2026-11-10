"""Public focus metadata; no task text and no independent timer."""
import time

def focus_summary(value=None,known=False):
    v=value if isinstance(value,dict) else {}
    remaining=v.get('remaining');duration=v.get('duration')
    valid=type(remaining) is int and 0<=remaining<=86400 and type(duration) is int and 0<=duration<=1440
    kind=('running' if v.get('running') is True else 'paused') if known and valid and v.get('active') is True else 'idle' if valid and v.get('active') is False else 'unknown'
    return {'kind':kind,'remaining':remaining if valid else None,'duration':duration if valid else None,'observed_at':time.time()}
