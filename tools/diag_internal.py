"""Diagnostic: call the loader's internal entry point directly.

`CreateWebViewEnvironmentWithOptionsInternal` is the entry point the
official loader uses internally:

    HRESULT CreateWebViewEnvironmentWithOptionsInternal(
        int apiVersion,            // 1
        int runtimeType,           // 0 = installed, 1 = redistributable
        PCWSTR userDataFolder,
        ICoreWebView2EnvironmentOptions* options,
        ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler* handler)
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import HRESULT, c_void_p, c_wchar_p

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kali.webview2 as wv2

RUNTIME = r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application\158.0.4370.33"

loader = wv2.WebView2Loader()
dll = loader.dll
print("loader:", loader.dll)

internal = dll.CreateWebViewEnvironmentWithOptionsInternal
internal.restype = HRESULT
internal.argtypes = [
    ctypes.c_int,    # apiVersion
    ctypes.c_int,    # runtimeType
    c_wchar_p,       # userDataFolder
    c_void_p,        # options
    c_void_p,        # handler
]


def attempt(runtime_type: int, folder: str | None, label: str):
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
        hr = internal(
            1,
            runtime_type,
            c_wchar_p(folder) if folder else None,
            None,
            c_void_p(ctypes.addressof(handler)),
        )
    except Exception as e:
        print(f"{label}: EXC {e}")
        return None

    if hr != 0:
        print(f"{label}: hr={hex(hr & 0xFFFFFFFF)}")
        return None

    deadline = time.time() + 20
    while "hr" not in holder and time.time() < deadline:
        msg = ctypes.wintypes.MSG()
        while ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)

    code = holder.get("hr")
    env = holder.get("env")
    print(f"{label}: callback hr={hex(code) if code is not None else 'timeout'}, "
          f"env={'yes' if env else 'no'}")
    return env


attempt(0, None, "installed, no folder")
attempt(1, RUNTIME, "redistributable, runtime folder")
attempt(1, RUNTIME + r"\EBWebView\x64", "redistributable, EBWebView/x64")
attempt(0, RUNTIME, "installed, runtime folder")
