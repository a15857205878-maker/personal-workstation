"""Isolated tool-center adapter. No model engine or desktop pet is started."""
from pathlib import Path
import contextlib
import json
import sys
import os

OUTPUT=sys.stdout
def emit(value):
    OUTPUT.write(json.dumps(value,ensure_ascii=False)+'\n');OUTPUT.flush()

class DialogWindow:
    def create_file_dialog(self,kind,**options):
        emit({'event':'dialog','kind':kind,'options':options})
        reply=json.loads(sys.stdin.readline())
        return reply.get('selection')

def main():
    from workstation_core import TOOL_ACTIONS
    from workstation_zones import validate_module
    tool_root=Path(__file__).resolve().parent.parent/'个人工具中心新版'
    sys.path.insert(0,str(tool_root/'vendor'))
    sys.path.insert(0,str(tool_root))
    # Load the center backend only inside this process: its legacy absolute
    # imports must never pollute the workbench's module registry.
    with contextlib.redirect_stdout(sys.stderr):
        from backend import Bridge
        test_root=os.environ.get('PC_WORKSTATION_TEST_ROOT')
        bridge=Bridge(Path(test_root)/'个人工具中心新版',Path(test_root)) if test_root else Bridge(tool_root)
    bridge._window=DialogWindow()
    if test_root:
        sys.path.insert(0,str(Path(__file__).resolve().parent/'tests'))
        from icon_studio_fixture import make_api
        bridge._icon_studio_api=make_api(Path(test_root)/'个人工具中心')
    try:
        for line in sys.stdin:
            try:
                request=json.loads(line);action=request.get('action')
                if action=='__close__':break
                if action=='open_module':
                    validate_module(request.get('payload',{}))
                    action='launch_tool'
                elif action not in TOOL_ACTIONS:raise ValueError('不支持的工具操作')
                with contextlib.redirect_stdout(sys.stderr):result=bridge.call(action,request.get('payload',{}))
                emit(result)
            except Exception:
                emit({'ok':False,'error':'工具操作未完成，请检查所选内容或稍后重试。'})
    finally:
        bridge._shutdown()

if __name__=='__main__':main()
