"""A Windows job contains only this newly launched process and its descendants."""
import ctypes
from ctypes import wintypes
import os
import signal
import threading


class OwnedProcessGroup:
    def __init__(self,process):
        self.process=process;self.handle=None;self.lock=threading.Lock()
        if os.name!='nt':return
        size=ctypes.c_size_t
        class Basic(ctypes.Structure):
            _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),('flags',wintypes.DWORD),
                      ('min_working',size),('max_working',size),('active_limit',wintypes.DWORD),
                      ('affinity',size),('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_=[(name,ctypes.c_ulonglong) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
        class Limits(ctypes.Structure):
            _fields_=[('basic',Basic),('io',IO),('process_memory',size),('job_memory',size),('peak_process',size),('peak_job',size)]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True);self.kernel=kernel
        kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR];kernel.CreateJobObjectW.restype=wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD];kernel.SetInformationJobObject.restype=wintypes.BOOL
        kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE];kernel.AssignProcessToJobObject.restype=wintypes.BOOL
        kernel.TerminateJobObject.argtypes=[wintypes.HANDLE,wintypes.UINT];kernel.TerminateJobObject.restype=wintypes.BOOL
        kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
        handle=kernel.CreateJobObjectW(None,None)
        if not handle:raise ctypes.WinError(ctypes.get_last_error())
        limits=Limits();limits.basic.flags=0x2000  # KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(handle,9,ctypes.byref(limits),ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(handle,int(process._handle)):
            error=ctypes.get_last_error();kernel.CloseHandle(handle);raise ctypes.WinError(error)
        self.handle=handle

    def terminate(self):
        with self.lock:
            if os.name=='nt':
                if self.handle and not self.kernel.TerminateJobObject(self.handle,1):
                    raise ctypes.WinError(ctypes.get_last_error())
            else:
                try:os.killpg(self.process.pid,signal.SIGTERM)
                except ProcessLookupError:pass

    def close(self):
        with self.lock:
            if self.handle:
                self.kernel.CloseHandle(self.handle);self.handle=None
