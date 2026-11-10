"""Dependency-free opened-file identity shared by library and preview hosts."""
import os
from pathlib import Path

def opened_path(stream,fallback):
    if os.name!='nt':
        fd=Path('/proc/self/fd')/str(stream.fileno())
        return fd.resolve() if fd.exists() else fallback.resolve()
    import ctypes,msvcrt
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    fn=kernel.GetFinalPathNameByHandleW
    fn.argtypes=[wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD];fn.restype=wintypes.DWORD
    buf=ctypes.create_unicode_buffer(32768)
    length=fn(msvcrt.get_osfhandle(stream.fileno()),buf,len(buf),0)
    if not length or length>=len(buf):raise OSError('无法核实文件位置')
    value=buf.value
    if value.startswith('\\\\?\\UNC\\'):value='\\\\'+value[8:]
    elif value.startswith('\\\\?\\'):value=value[4:]
    return Path(value)
