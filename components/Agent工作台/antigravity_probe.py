"""Read-only installation discovery; never executes binaries or reads credentials."""
from pathlib import Path
import shutil


def snapshot(home=None, path_lookup=None):
    home = Path.home() if home is None else Path(home)
    lookup = shutil.which if path_lookup is None else path_lookup
    local = home / 'AppData' / 'Local'
    desktop = local / 'Programs' / 'antigravity' / 'Antigravity.exe'
    found = lookup('agy.exe')
    candidates = ([Path(found)] if found else []) + [
        local / 'agy' / 'bin' / 'agy.exe',
        local / 'Programs' / 'antigravity' / 'bin' / 'agy.exe',
        home / '.local' / 'bin' / 'agy.exe',
        home / '.antigravity' / 'bin' / 'agy.exe',
    ]
    cli = next((p for p in candidates if p.name.lower() == 'agy.exe' and p.is_file()), None)
    installed = desktop.is_file()
    state = 'cli_found_unverified' if cli else 'desktop_only' if installed else 'missing'
    messages = {
        'cli_found_unverified': '已找到 CLI；登录、模型目录和生成能力尚未验证，暂未加入群聊。',
        'desktop_only': '已安装桌面版，尚未找到官方 agy.exe CLI；暂未加入群聊。',
        'missing': '尚未找到 Antigravity 桌面版或官方 agy.exe CLI。',
    }
    return dict(state=state, desktop_installed=installed, cli_found=bool(cli),
                can_generate=False, message=messages[state])
