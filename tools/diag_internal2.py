"""Diagnostic: replicate the SDK loader's exact call into the runtime DLL.

Reverse-engineered contract (from the SDK loader's disassembly):

The SDK's `CreateCoreWebView2EnvironmentWithOptions` builds a 0x48-byte
callback object:

    +0x00  vtable pointer
    +0x08  (unused)
    +0x0c  apiVersion = 1
    +0x10  16 bytes of copied arguments
    +0x20  16 bytes of copied arguments
    +0x30  8 bytes  (the user data folder / options pointer)
    +0x38  the completion handler pointer
    +0x40  a flag = 1

It then calls the runtime DLL's export:

    HRESULT CreateWebViewEnvironmentWithOptionsInternal(
        uint32_t runtimeType,
        uint32_t apiVersion,
        void*    options,
        void*    userDataFolder,
        void*    callbackStruct);
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


class CallbackStruct(ctypes.Structure):
    """The loader's callback object - a COM object plus the handler."""

    _fields_ = [
        ("lpVtbl", ctypes.POINTER(c_void_p)),      # +0x00
        ("pad", ctypes.c_ulong),                    # +0x08
        ("apiVersion", ctypes.c_uint),              # +0x0c
        ("blob0", ctypes.c_ubyte * 16),             # +0x10
        ("blob1", ctypes.c_ubyte * 16),             # +0x20
        ("extra", c_void_p),                        # +0x30
        ("handler", c_void_p),                      # +0x38
        ("flag", ctypes.c_uint),                    # +0x40
    ]


def try_internal(runtime_type: int, api_version: int, folder: str | None,
                 user_data: str | None = None):
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
    struct.apiVersion = api_version
    struct.handler = c_void_p(ctypes.addressof(handler))
    struct.flag = 1
    keep["struct"] = struct

    dll = ctypes.WinDLL(SERVER)
    internal = dll.CreateWebViewEnvironmentWithOptionsInternal
    internal.restype = HRESULT
    internal.argtypes = [
        ctypes.c_uint,   # runtimeType
        ctypes.c_uint,   # apiVersion
        c_void_p,        # options
        c_wchar_p,       # userDataFolder
        c_void_p,        # callback struct
    ]

    try:
        hr = internal(
            runtime_type,
            api_version,
            None,
            c_wchar_p(user_data) if user_data else None,
            c_void_p(ctypes.addressof(struct)),
        )
    except Exception as e:
        print("EXC:", type(e).__name__, e)
        return None
    print("immediate hr:", hex(hr & 0xFFFFFFFF))
    if hr != 0:
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


import tempfile
ud = os.path.join(tempfile.gettempdir(), "kali-wv2-test")

for rt, folder, udir, label in (
    (1, RUNTIME, ud, "redistributable + runtime folder + user data"),
    (1, RUNTIME, None, "redistributable + runtime folder"),
    (1, None, None, "redistributable + no folder"),
    (0, None, None, "installed + no folder"),
):
    print(f"--- {label} ---")
    env = try_internal(rt, 1, folder, udir)
    if env:
        print("SUCCESS")
        break
