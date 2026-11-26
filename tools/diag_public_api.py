"""Diagnostic: the SDK loader's public API with COM initialised.

Earlier attempts at `CreateCoreWebView2EnvironmentWithOptions` failed with
CLASS_E_CLASSNOTAVAILABLE, but COM was never initialised on the calling
thread. That is the classic cause of that error from inside a COM server.
"""
from __future__ import annotations

import ctypes
import os
import sys
import tempfile
import time
from ctypes import HRESULT, c_void_p, c_wchar_p

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kali.webview2 as wv2

ole32 = ctypes.windll.ole32
ole32.CoInitializeEx.restype = HRESULT
ole32.CoInitializeEx.argtypes = [c_void_p, ctypes.c_uint]

# COINIT_APARTMENTTHREADED = 0x2, COINIT_MULTITHREADED = 0x0
# The mode can only be chosen once per thread, so pick one.
hr = ole32.CoInitializeEx(None, 0x2)
print("CoInitializeEx(APARTMENTTHREADED) hr:", hex(hr & 0xFFFFFFFF))

loader = wv2.WebView2Loader()
print("loader:", loader.dll)
print("browser folder:", loader.browser_executable)

user32 = ctypes.windll.user32
ud = os.path.join(tempfile.gettempdir(), "kali-wv2-ud")
os.makedirs(ud, exist_ok=True)


def attempt(browser, label):
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
    try:
        hr = loader.create(
            c_wchar_p(browser) if browser else None,
            c_wchar_p(ud),
            None,
            c_void_p(ctypes.addressof(handler)),
        )
    except Exception as e:
        print(f"{label}: EXC {type(e).__name__} {e}")
        return None
    if hr != 0:
        print(f"{label}: immediate hr={hex(hr & 0xFFFFFFFF)}")
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
    print(f"{label}: callback hr={hex(code) if code is not None else 'TIMEOUT'}, "
          f"env={'YES' if env else 'no'}")
    return env


for browser, label in (
    (None, "auto-detect"),
    (loader.browser_executable, "explicit runtime folder"),
):
    env = attempt(browser, label)
    if env:
        print("SUCCESS")
        break
