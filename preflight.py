"""Read-only checks. Does not start a model, pair a phone or write user data."""
from pathlib import Path
import importlib.util
import os
import sys

ROOT=Path(__file__).resolve().parent
def check():
    errors=[]
    if sys.platform!='win32':errors.append('原生桌面仅支持 Windows；需要 Windows + WebView2。')
    for name in ('webview','clr','PIL','pypdf','reportlab','qrcode','tzdata'):
        if importlib.util.find_spec(name) is None:errors.append(f'缺少 Python 依赖 {name}；执行 python -m pip install -r requirements-lock.txt')
    for name in ('Agent工作台','宝可梦小镇新版','个人工具中心新版'):
        for rel in ('frontend/dist/index.html','frontend/dist/assets/app.js','frontend/dist/assets/app.css'):
            path=ROOT/'components'/name/rel
            if not path.is_file() or not path.stat().st_size:errors.append(f'缺少构建文件 components/{name}/{rel}；执行 build.ps1')
    for rel in ('components/远程服务/app/transfer.py','components/Agent工作台/persona_catalog.json','components/Agent工作台/examples/collab/bin/room.ps1'):
        if not (ROOT/rel).is_file():errors.append(f'缺少业务模块 {rel}；重新解压完整源码包。')
    return errors
def main():
    errors=check()
    for error in errors:print(error)
    if errors:return 2
    print('启动依赖和生产构建已具备。桌宠、DeepSeek Harness、Codex CLI、Tailscale为按功能配置的可选程序。')
    if not os.environ.get('AGENT_PET_ROOT'):print('未配置 AGENT_PET_ROOT：桌宠及小屋连接将显示未连接；工作站与小镇可独立使用。')
    return 0
if __name__=='__main__':raise SystemExit(main())
