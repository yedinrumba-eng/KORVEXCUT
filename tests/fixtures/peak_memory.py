"""Peak memory of a Python child process, for the tests that cap what a command may reserve.

`psutil` is not a dependency, so the numbers come from `GetProcessMemoryInfo` (Windows only, which
is where kcut runs first): the working set (pages touched) and the commit charge (what the process
asked the system to back, which is what a `bytes(1 << 30)` or a huge image buffer costs even before
it is touched). The child calls `mark()` after its imports; the figures are the growth from there.
"""

import json
import subprocess
import sys
from dataclasses import dataclass

import pytest

MB = 1024 * 1024
_WRAPPER = """
import ctypes, json, sys
from ctypes import wintypes

class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

def reading():
    info = PMC()
    info.cb = ctypes.sizeof(PMC)
    kernel, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(info), info.cb)
    return info

marks = []
def mark():
    marks.append(reading())

exec(compile(sys.argv[1], "<child>", "exec"), {"mark": mark, "__name__": "__main__"})
end = reading()
start = marks[0] if marks else end
print("@@MEM@@" + json.dumps({
    "ws_start": start.WorkingSetSize, "ws_peak": end.PeakWorkingSetSize,
    "commit_start": start.PagefileUsage, "commit_peak": end.PeakPagefileUsage,
}))
"""


@dataclass(frozen=True)
class Measured:
    """What the child printed, and how far its memory went after `mark()`."""

    returncode: int
    stdout: str
    stderr: str
    ws_peak_mb: float  # absolute peak working set of the process
    ws_growth_mb: float  # peak working set minus the working set at `mark()`
    commit_growth_mb: float  # peak commit charge minus the commit charge at `mark()`


def measure(code: str, timeout_s: float = 300) -> Measured:
    """Run `code` in a fresh `python -I -X utf8` and measure its peak memory (Windows only)."""
    if sys.platform != "win32":
        pytest.skip("la memoria pico se mide con la API de Windows (psutil no es dependencia)")
    done = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", _WRAPPER, code],
        capture_output=True,
        encoding="utf-8",
        timeout=timeout_s,
        check=False,
    )
    out, _, tail = done.stdout.rpartition("@@MEM@@")
    figures = json.loads(tail) if tail.strip() else {}
    if not figures:
        return Measured(done.returncode, done.stdout, done.stderr, 0.0, 1e9, 1e9)
    return Measured(
        done.returncode,
        out,
        done.stderr,
        figures["ws_peak"] / MB,
        (figures["ws_peak"] - figures["ws_start"]) / MB,
        (figures["commit_peak"] - figures["commit_start"]) / MB,
    )
