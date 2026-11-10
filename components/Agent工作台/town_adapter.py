"""Lazy local town service, isolated imports and the original save conflict checks."""
from pathlib import Path
import ast
import hashlib
import json
import sys
import threading
import types

SOURCE = Path(__file__).resolve().parent.parent / '宝可梦小镇新版'
ACTIONS = frozenset(('bootstrap', 'focus_state', 'town_action', 'focus_start',
                     'focus_pause', 'focus_resume', 'focus_end', 'set_mode', 'settings_save'))
FIELDS = {'bootstrap': set(), 'focus_state': set(), 'town_action': {'action', 'args'},
          'focus_start': {'task', 'minutes'}, 'focus_pause': set(), 'focus_resume': set(),
          'focus_end': set(), 'set_mode': {'mode'}, 'settings_save': {'theme', 'motion'}}
MODULES = ('town_state', 'town_collectibles', 'town_map', 'town_rules', 'town_focus', 'town_store', 'town_backend')
_IMPORT_LOCK = threading.Lock()


def load_backend(source=SOURCE):
    """Load trusted sibling source under unique names; never alter sys.path/old imports."""
    source = Path(source).resolve()
    package = '_workstation_town_' + hashlib.sha256(str(source).encode()).hexdigest()[:16]
    with _IMPORT_LOCK:
        backend_name = package + '.town_backend'
        if backend_name in sys.modules:
            return sys.modules[backend_name]
        container = types.ModuleType(package)
        container.__path__ = [str(source)]
        sys.modules[package] = container
        try:
            for name in MODULES:
                file = source / (name + '.py')
                tree = ast.parse(file.read_text(encoding='utf-8-sig'), filename=str(file))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module in MODULES:
                        node.module = package + '.' + node.module
                module = types.ModuleType(package + '.' + name)
                module.__file__ = str(file)
                module.__package__ = package
                sys.modules[module.__name__] = module
                exec(compile(tree, str(file), 'exec'), module.__dict__)
            return sys.modules[backend_name]
        except Exception:
            for name in (package, *(package + '.' + name for name in MODULES)):
                sys.modules.pop(name, None)
            raise


class TownAdapter:
    def __init__(self, base=SOURCE, source=SOURCE, clock=None):
        self._base = Path(base)
        self._source = Path(source)
        self._clock = clock
        self._bridge = None
        self._lock = threading.RLock()
        self._closed = False

    def room_layout(self):
        """Read scenery ownership without starting a clock or creating a save."""
        path=self._base/'data/town.json'
        if not path.exists():return {'inventory':{},'layout_note':'尚无小镇存档，可从原小镇开始布置。'}
        try:
            if path.stat().st_size>4*1024*1024:raise ValueError('oversize')
            data=json.loads(path.read_text(encoding='utf-8-sig'))
            load_backend(self._source).validate_town(data)
            return {'inventory':dict(data['inventory']),'layout_note':'房间家具沿用原小镇已拥有的物品。'}
        except (OSError,ValueError,TypeError,KeyError):
            return {'inventory':{},'layout_note':'小镇布置暂不可读，原存档已保留。'}

    def call(self, action, payload=None):
        if not isinstance(action, str) or action not in ACTIONS:
            raise ValueError('不支持的小镇操作')
        if payload is None:
            payload = {}
        if not isinstance(payload, dict) or set(payload) - FIELDS[action]:
            raise ValueError('小镇参数无效；不接受文件路径')
        try:
            size = len(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        except (TypeError, ValueError):
            raise ValueError('小镇参数无效') from None
        if size > 8192:
            raise ValueError('小镇参数过大')
        # town_action arguments are domain values, never file-system capabilities.
        args = payload.get('args', {})
        if action == 'town_action' and (not isinstance(args, dict) or
                set(args) - {'kind', 'item_id', 'area', 'x', 'y', 'partner', 'task'}):
            raise ValueError('小镇操作参数无效；不接受文件路径')
        with self._lock:
            if self._closed:
                raise ValueError('小镇服务正在退出')
            if self._bridge is None:
                bridge_type = load_backend(self._source).Bridge
                options = {} if self._clock is None else {'clock': self._clock}
                self._bridge = bridge_type(self._base, **options)
            result = self._bridge.call(action, payload)
            if not result.get('ok'):
                raise ValueError(result.get('error') or '小镇操作未完成')
            return result['data']

    def focus_summary(self):
        from focus_summary import focus_summary
        with self._lock:
            if self._closed:return focus_summary()
            if self._bridge is not None:
                result=self._bridge.call('focus_state',{})
                data=result.get('data') if isinstance(result,dict) else None
                return focus_summary(data.get('focus') if isinstance(data,dict) else None,known=isinstance(result,dict) and result.get('ok') is True)
            path=self._base/'data/town.json'
            if not path.exists():return focus_summary(dict(active=False,remaining=0,duration=0),known=True)
            try:
                if path.stat().st_size>4*1024*1024:raise ValueError('oversize')
                data=json.loads(path.read_text(encoding='utf-8-sig'));load_backend(self._source).validate_town(data)
                return focus_summary(data.get('focus'),known=False)
            except (OSError,ValueError,TypeError,KeyError):return focus_summary()

    def close(self):
        with self._lock:
            if self._closed:
                return
            # Only pause the instance created by this adapter. A failed save keeps
            # close retryable and propagates to the native closing guard.
            if self._bridge is not None:
                self._bridge._pause_for_close()
            self._closed = True
