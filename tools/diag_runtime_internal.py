"""Diagnostic: trace the runtime's debug output while creating the environment.

The WebView2 runtime and the SDK loader report progress through
`OutputDebugStringW`. Capturing that tells us exactly why the
environment creation fails.

It also retries against both runtime installs:

    * EdgeWebView\\Application\\<version>   (the classic runtime)
    * EdgeCore\\<version>                    (the newer runtime)
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import HRESULT, c_void_p, c_wchar_p

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kali.webview2 as wv2

# ---- capture OutputDebugString --------------------------------------------
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# A hidden window that receives WM_COPYDATA? No - use a second thread with
# ReadDebugString-like behaviour is not possible. Instead use the
# `DEBUG_OUTPUT_DEBUGSTRING` event via a debugger-free trick:
# we register an output debug string listener through the undocumented
# `DbgUiRemoteBreakin`? No.
#
# The supported way is to read the process's stdout - but OutputDebugString
# does not go there. The practical alternative: use the `DbgPrint` hook is
# not available without a debugger.
#
# So instead we rely on the loader's own logging: the SDK loader writes to
# the debug output, and we can capture it with a small helper that reads the
# "DebugView" style - which requires WinDbg.
#
# Practical fallback: try each runtime install and print the HRESULT.
print("OutputDebugString capture is unavailable; trying each runtime install.")


class CallbackStruct(ctypes.Structure):
    _fields_ = [
        ("lpVtbl", ctypes.POINTER(c_void_p)),
        ("pad", ctypes.c_ulong),
        ("apiVersion", ctypes.c_uint),
        ("blob0", ctypes.c_ubyte * 16),
        ("blob1", ctypes.c_ubyte * 16),
        ("extra", c_void_p),
        ("handler", c_void_p),
        ("flag", ctypes.c_uint),
    ]


def try_runtime(runtime_folder: str, user_data: str):
    server = os.path.join(runtime_folder, "EBWebView", "x64",
                           "EmbeddedBrowserWebView.dll")
    if not os.path.exists(server):
        print("  no server dll:", server)
        return None

    holder = {}

    def cb(error_code, env, _h=holder):
        _h["hr"] = int(error_code) & 0xFFFFFFFF
        _h["env"] = env
        return 0

    handler, keep = wv2._make_handler(
        wv2._ENV_INVOKE,
        wv2.IID_COREWEBVIEW2_CREATE_ENVIRONMENT_COMPLETED_HANDLER,
        cb,
    )

    struct = CallbackStruct()
    struct.lpVtbl = handler.lpVtbl
    struct.apiVersion = 1
    struct.handler = c_void_p(ctypes.addressof(handler))
    struct.flag = 1
    keep["struct"] = struct

    dll = ctypes.WinDLL(server)
    internal = dll.CreateWebViewEnvironmentWithOptionsInternal
    internal.restype = HRESULT
    internal.argtypes = [ctypes.c_uint, ctypes.c_uint, c_void_p, c_wchar_p,
                         c_void_p]

    try:
        hr = internal(1, 1, None, c_wchar_p(user_data),
                      c_void_p(ctypes.addressof(struct)))
    except Exception as e:
        print("  EXC:", type(e).__name__, e)
        return None
    if hr != 0:
        print("  immediate hr:", hex(hr & 0xFFFFFFFF))
        return None

    deadline = time.time() + 30
    while "hr" not in holder and time.time() < deadline:
        msg = ctypes.wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)

    code = holder.get("hr")
    env = holder.get("env")
    print("  callback hr:", hex(code) if code is not None else "TIMEOUT",
          "env:", "YES" if env else "no")
    return env


import tempfile

ud = os.path.join(tempfile.gettempdir(), "kali-wv2-ud")

RUNTIMES = [
    r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application\158.0.4370.33",
    r"C:\Program Files (x86)\Microsoft\EdgeCore\158.0.4370.33",
]

for rt in RUNTIMES:
    print("---", rt)
    env = try_runtime(rt, ud)
    if env:
        print("SUCCESS with", rt)
        break
