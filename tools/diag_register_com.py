"""Diagnostic: register the WebView2 COM class under HKCU and retry.

The runtime's `EBWebView\\<arch>\\EmbeddedBrowserWebView.dll` is the COM
server for the WebView2 environment class:

    CLSID {60A417CA-F1AB-4307-801B-F96003F8938B}

The runtime normally registers it at install time. When that registration
is missing the loader fails with CLASS_E_CLASSNOTAVAILABLE (0x800401F0).

This registers it under HKCU (no elevation needed) and retries.
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
SERVER = os.path.join(RUNTIME, "EBWebView", "x64", "EmbeddedBrowserWebView.dll")
CLSID = "{60A417CA-F1AB-4307-801B-F96003F8938B}"


def register() -> None:
    import winreg

    path = rf"Software\Classes\CLSID\{CLSID}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "WebView2 Embedded Browser")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path + r"\InprocServer32") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, SERVER)
        winreg.SetValueEx(k, "ThreadingModel", 0, winreg.REG_SZ, "Both")
    print("registered under HKCU:", SERVER)


def try_once():
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
    dll = ctypes.WinDLL(SERVER)
    internal = dll.CreateWebViewEnvironmentWithOptionsInternal
    internal.restype = HRESULT
    internal.argtypes = [ctypes.c_int, ctypes.c_int, c_wchar_p, c_void_p, c_void_p]
    hr = internal(1, 1, c_wchar_p(RUNTIME), None,
                  c_void_p(ctypes.addressof(handler)))
    if hr != 0:
        print("immediate hr:", hex(hr & 0xFFFFFFFF))
        return None

    deadline = time.time() + 25
    while "hr" not in holder and time.time() < deadline:
        msg = ctypes.wintypes.MSG()
        while ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)

    code = holder.get("hr")
    env = holder.get("env")
    print("callback hr:", hex(code) if code is not None else "TIMEOUT",
          "env:", "YES" if env else "no")
    return env


print("--- before ---")
try_once()
print("--- registering ---")
register()
print("--- after ---")
env = try_once()
if env:
    print("SUCCESS")
