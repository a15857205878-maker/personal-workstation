"""Fixed room-runner subprocess; no general shell endpoint."""
from pathlib import Path
import os,shutil,subprocess,tempfile,time

def powershell():
    found=shutil.which('pwsh')
    if found:return found
    for candidate in (Path('C:/Program Files/PowerShell/7/pwsh.exe'),Path(os.environ.get('ProgramFiles','C:/Program Files'))/'PowerShell/7/pwsh.exe'):
        if candidate.is_file():return str(candidate)
    raise ValueError('找不到 PowerShell 7，请先安装或加入 PATH')

class RoomRunner:
    def __init__(self,root,timeout=90,limit=256*1024):self.root=Path(root).resolve();self.timeout=timeout;self.limit=limit
    def __call__(self,arguments):
        script=(self.root/'bin/room.ps1').resolve()
        if not script.is_relative_to(self.root) or not script.is_file():raise ValueError('找不到可信的 bin/room.ps1')
        reason='';started=time.monotonic()
        with tempfile.TemporaryFile() as output:
            process=subprocess.Popen([powershell(),'-NoLogo','-NoProfile','-NonInteractive','-File',str(script),*arguments],cwd=str(self.root),stdout=output,stderr=subprocess.STDOUT,shell=False,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                while process.poll() is None:
                    if time.monotonic()-started>self.timeout:reason='命令超时，已停止';break
                    if os.fstat(output.fileno()).st_size>self.limit:reason='命令输出超过上限，已停止';break
                    time.sleep(.03)
            finally:
                if process.poll() is None:process.kill()
                process.wait(timeout=5)
            output.seek(0);raw=output.read(self.limit+1)
        if len(raw)>self.limit:reason=reason or '命令输出超过上限，已截断'
        text=raw[:self.limit].decode('utf-8-sig',errors='replace')
        if reason:text+='\n'+reason
        return dict(exit_code=process.returncode if not reason else -1,output=text,seconds=round(time.monotonic()-started,2))
