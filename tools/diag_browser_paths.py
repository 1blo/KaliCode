"""Diagnostic: try every candidate browser folder until one works."""
from __future__ import annotations

import ctypes
import os
import sys
from ctypes import HRESULT, c_void_p, c_wchar_p

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kali.webview2 as wv2

loader = wv2.WebView2Loader()

candidates = [
    None,
    r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application\158.0.4370.33",
    r"C:\Program Files (x86)\Microsoft\EdgeCore\158.0.4370.33",
    r"C:\Program Files (x86)\Microsoft\EdgeCore\Optimized",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\158.0.4370.33",
]

for folder in candidates:
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
            c_wchar_p(folder) if folder else None,
            None,
            None,
            c_void_p(ctypes.addressof(handler)),
        )
    except Exception as e:
        print(f"{folder}: EXC {e}")
        continue
    if hr != 0:
        print(f"{folder}: loader hr={hex(hr & 0xFFFFFFFF)}")
        continue

    import time
    deadline = time.time() + 20
    while "hr" not in holder and time.time() < deadline:
        msg = ctypes.wintypes.MSG()
        while ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)

    code = holder.get("hr")
    name = {0: "S_OK",
            0x800401F0: "CLASS_E_CLASSNOTAVAILABLE",
            0x8007007E: "ERROR_MOD_NOT_FOUND",
            0x80070005: "E_ACCESSDENIED"}.get(code, hex(code) if code is not None else "timeout")
    print(f"{folder}: callback hr={name}, env={holder.get('env')}")
