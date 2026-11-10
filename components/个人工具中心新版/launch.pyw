"""Stable no-console desktop entry, using the validated bundled runtime."""
from pathlib import Path
import subprocess,sys
base=Path(__file__).resolve().parent
runtime=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/pythonw.exe'
if not runtime.is_file():runtime=Path(sys.executable)
logs=base/'logs';logs.mkdir(exist_ok=True)
with (logs/'startup-error.log').open('ab') as err:
    subprocess.Popen([str(runtime),str(base/'app.py')],cwd=base,stdout=err,stderr=err)
