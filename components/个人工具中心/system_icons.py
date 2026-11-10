"""Desktop namespace icons, with per-user overrides and exact value backups."""
from copy import deepcopy
import ctypes
import threading
from playful_store import load_json, save_json

SYSTEM_ICONS = {
    'computer': ('此电脑', '{20D04FE0-3AEA-1069-A2D8-08002B30309D}'),
    'recycle': ('回收站', '{645FF040-5081-101B-9F08-00AA002F954E}'),
    'control': ('控制面板', '{5399E694-6CE5-4D6C-8FCE-1D8870FDCBA0}'),
}


def system_key(path):
    key = str(path).removeprefix('system:')
    if str(path) != 'system:' + key or key not in SYSTEM_ICONS:
        raise ValueError('不支持的系统图标')
    return key


def value_names(key):
    return ('', 'empty', 'full') if key == 'recycle' else ('',)


def validate_values(key, values):
    if not isinstance(values, dict) or set(values) != set(value_names(key)):
        raise ValueError('系统图标备份格式错误，原记录保留')
    for value in values.values():
        if value is not None and (not isinstance(value, list) or len(value) != 2
                or not isinstance(value[0], str) or value[1] not in (1, 2)):
            raise ValueError('系统图标值格式错误')


def validate_records(data):
    if not isinstance(data, dict) or not isinstance(data.get('records'), dict):
        raise ValueError('系统图标记录格式错误')
    for key, record in data['records'].items():
        system_key('system:' + key)
        if not isinstance(record, dict) or record.get('state') not in ('pending','applied','restored'):
            raise ValueError('系统图标记录格式错误')
        for field in ('original', 'prior', 'applied'):
            validate_values(key, record.get(field))


class SystemIconBackend:
    def __init__(self, shortcuts):
        self.shortcuts = shortcuts

    def registry_path(self, key):
        system_key('system:' + key)
        return r'Software\Microsoft\Windows\CurrentVersion\Explorer\CLSID' + '\\' + SYSTEM_ICONS[key][1] + r'\DefaultIcon'

    @staticmethod
    def query(hive, path, name):
        import winreg
        try:
            with winreg.OpenKey(hive, path) as handle:
                value, kind = winreg.QueryValueEx(handle, name)
                if kind not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) or not isinstance(value, str):
                    raise ValueError('系统图标注册表值不是字符串')
                return [value, kind]
        except FileNotFoundError:
            return None

    def read(self, key):
        import winreg
        path = self.registry_path(key)
        values = {name: self.query(winreg.HKEY_CURRENT_USER, path, name) for name in value_names(key)}
        effective = values['']
        if effective is None:
            effective = self.query(winreg.HKEY_CLASSES_ROOT, 'CLSID\\' + SYSTEM_ICONS[key][1] + '\\DefaultIcon', '')
        return dict(values=values, icon=effective[0] if effective else '')

    def scan(self):
        ids = self.shortcuts.request(dict(action='system_ids'))
        result = []
        for key, (name, guid) in SYSTEM_ICONS.items():
            if guid not in ids: continue
            state = self.read(key)
            result.append(dict(path='system:' + key, name=name, kind='system',
                               shell_path='::' + guid, icon=state['icon'], system_state=state))
        return result

    def write(self, key, values):
        import winreg
        validate_values(key, values)
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self.registry_path(key), 0,
                                winreg.KEY_SET_VALUE) as handle:
            for name, value in values.items():
                if value is None:
                    try: winreg.DeleteValue(handle, name)
                    except FileNotFoundError: pass
                else: winreg.SetValueEx(handle, name, 0, value[1], value[0])
        # Deliver an association-change notification without restarting Explorer.
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)


class SystemIconService:
    def __init__(self, shortcuts, backend=None):
        self.shortcuts = shortcuts
        self.backend = backend or SystemIconBackend(shortcuts.backend)
        self.path = shortcuts.root / 'system_records.json'
        self.lock = threading.RLock()

    def records(self):
        return load_json(self.path, {'records': {}}, validate_records)

    def save(self, data):
        save_json(self.path, data, {'records': {}}, validate_records)

    def write_verified(self, key, values):
        self.backend.write(key, values)
        if self.backend.read(key)['values'] != values:
            raise OSError('系统图标保存后核对失败，原设置备份已保留')

    def apply(self, path, icon, expected):
        key = system_key(path)
        with self.lock:
            current = self.backend.read(key)
            if current != expected.get('system_state'):
                raise ValueError('系统图标已变化，请刷新后重新选择')
            data = self.records()
            old = deepcopy(data['records'].get(key))
            source = self.shortcuts._asset(icon)
            applied = {name: [source, 1] for name in value_names(key)}
            original = old['original'] if old and old['state'] != 'restored' else current['values']
            record = dict(original=deepcopy(original), prior=deepcopy(current['values']),
                          applied=applied, state='pending')
            data['records'][key] = record
            self.save(data)
            try:
                if self.backend.read(key) != current:
                    raise ValueError('系统图标在操作期间发生变化')
                self.write_verified(key, applied)
                record['state'] = 'applied'
                self.save(data)
            except Exception:
                # Restore only fields which still contain either our new value or the prior one.
                now = self.backend.read(key)['values']
                if all(now[n] in (applied[n], current['values'][n]) for n in value_names(key)):
                    try:
                        self.write_verified(key, current['values'])
                        data['records'][key] = old or dict(record, state='restored')
                        self.save(data)
                    except Exception: pass  # The pending backup remains available for recovery.
                raise
            return dict(path=path, status='applied')

    def restore(self, path):
        key = system_key(path)
        with self.lock:
            data = self.records()
            record = data['records'].get(key)
            if not record: raise ValueError('此系统图标没有本换装台的记录')
            if record['state'] == 'restored': return dict(path=path, status='already_restored')
            now = self.backend.read(key)['values']
            allowed = [record['applied'], record['original']]
            if record['state'] == 'pending': allowed.append(record['prior'])
            if not all(any(now[n] == candidate[n] for candidate in allowed) for n in value_names(key)):
                raise ValueError('冲突：系统图标已被其他操作更改，未覆盖')
            self.write_verified(key, record['original'])
            record['state'] = 'restored'
            self.save(data)
            return dict(path=path, status='restored')

    def restore_all(self):
        results = []
        for key, record in self.records()['records'].items():
            if record['state'] == 'restored': continue
            path = 'system:' + key
            try: results.append(self.restore(path))
            except Exception as exc: results.append(dict(path=path, status='failed', message=str(exc)))
        return results
