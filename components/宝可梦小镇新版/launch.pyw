from pathlib import Path
import subprocess,sys
base=Path(__file__).resolve().parent
python=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/pythonw.exe'
if not python.is_file():python=Path(sys.executable)
(base/'logs').mkdir(exist_ok=True)
with (base/'logs/startup-error.log').open('ab') as stream:
    subprocess.Popen([str(python),str(base/'app.py')],cwd=base,stdout=stream,stderr=stream)
