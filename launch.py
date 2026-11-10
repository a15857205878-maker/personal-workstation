from pathlib import Path
import runpy
import sys
from preflight import main

if __name__=='__main__':
    status=main()
    if status:raise SystemExit(status)
    if '--check' not in sys.argv:
        target=Path(__file__).resolve().parent/'components/Agent工作台/app.py'
        sys.path.insert(0,str(target.parent))
        runpy.run_path(str(target),run_name='__main__')
