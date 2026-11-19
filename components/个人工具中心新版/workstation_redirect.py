"""Retired standalone tool entries forward only to the existing workstation."""
from pathlib import Path
import os,subprocess,sys

def launch(base=None,spawn=None,executable=None):
    base=Path(base) if base is not None else Path(__file__).resolve().parent
    entry=base.parent/'Agent工作台/launch.pyw'
    if not entry.is_file():raise FileNotFoundError('个人工具中心独立入口已退役，请保留相邻个人工作站目录。')
    runtime=Path(executable) if executable is not None else Path(sys.executable)
    if executable is None and runtime.with_name('pythonw.exe').is_file():runtime=runtime.with_name('pythonw.exe')
    return (spawn or subprocess.Popen)([str(runtime),str(entry)],cwd=str(entry.parent),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
