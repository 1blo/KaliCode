"""List the visible top-level windows with their owning process."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

user32 = ctypes.windll.user32
rows = []


@ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
def cb(hwnd, _lp):
    n = user32.GetWindowTextLengthW(hwnd)
    if n and user32.IsWindowVisible(hwnd):
        b = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, b, n + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        rows.append((hwnd, pid.value, b.value))
    return True


user32.EnumWindows(cb, 0)
for hwnd, pid, title in rows:
    print(hex(hwnd), pid, repr(title))
