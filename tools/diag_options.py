"""Diagnostic: create the ICoreWebView2EnvironmentOptions object.

The runtime's `CreateWebViewEnvironmentWithOptionsInternal` dereferences
the options pointer (`*(short *)param_3`), so it cannot be NULL when the
runtime computes the user data folder.

The options class is registered by the runtime:

    CLSID {2FDE08A8-1E9A-4766-8C05-95A9CEB9D1C5}
    IID   {2FDE08A8-1E9A-4766-8C05-95A9CEB9D1C5}
"""
from __future__ import annotations

import ctypes
import os
import sys
from ctypes import HRESULT, c_void_p, c_wchar_p

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kali.webview2 as wv2

RUNTIME = r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application\158.0.4370.33"
SERVER = os.path.join(RUNTIME, "EBWebView", "x64", "EmbeddedBrowserWebView.dll")

CLSID_OPTIONS = wv2.GUID.parse("c680f941-d1f5-400d-b4fc-69408414e77c")
IID_OPTIONS = wv2.GUID.parse("c680f941-d1f5-400d-b4fc-69408414e77c")

ole32 = ctypes.windll.ole32

# COM must be initialised on this thread before any CoCreateInstance.
COINIT_APARTMENTTHREADED = 0x2
COINIT_MULTITHREADED = 0x0
ole32.CoInitializeEx.restype = HRESULT
ole32.CoInitializeEx.argtypes = [c_void_p, ctypes.c_uint]
hr_init = ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
print("CoInitializeEx hr:", hex(hr_init & 0xFFFFFFFF))

ole32.CoCreateInstance.restype = HRESULT
ole32.CoCreateInstance.argtypes = [
    ctypes.POINTER(wv2.GUID), c_void_p, ctypes.c_uint, ctypes.POINTER(wv2.GUID),
    ctypes.POINTER(c_void_p),
]

out = c_void_p()
hr = ole32.CoCreateInstance(
    ctypes.byref(CLSID_OPTIONS), None, 1, ctypes.byref(IID_OPTIONS),
    ctypes.byref(out),
)
print("CoCreateInstance hr:", hex(hr & 0xFFFFFFFF), "ptr:", hex(out.value or 0))
if hr != 0:
    sys.exit(1)

# ICoreWebView2EnvironmentOptions::put_AdditionalBrowserArguments
# vtable: IUnknown(3) + get_AdditionalBrowserArguments(4) + put_(5)
# The SDK header order is:
#   3 get_AdditionalBrowserArguments
#   4 get_AllowChromiumCompiler
#   ...
# Real order (WebView2EnvironmentOptions.h):
#   3 put_AdditionalBrowserArguments
#   4 get_AdditionalBrowserArguments
#   5 put_AllowChromiumCompiler
#   6 get_AllowChromiumCompiler
try:
    put_args = _method = wv2._method(out, 3, HRESULT, [c_wchar_p])
    put_args(wv2._addr(out), c_wchar_p("--disable-features=msEdgeSidebarV2"))
    print("put_AdditionalBrowserArguments ok")
except Exception as e:
    print("put args failed:", e)

# Now try the internal creation with the options object.
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


struct = CallbackStruct()
struct.lpVtbl = handler.lpVtbl
struct.apiVersion = 1
struct.handler = c_void_p(ctypes.addressof(handler))
struct.flag = 1
keep["struct"] = struct

dll = ctypes.WinDLL(SERVER)
internal = dll.CreateWebViewEnvironmentWithOptionsInternal
internal.restype = HRESULT
internal.argtypes = [ctypes.c_uint, ctypes.c_uint, c_void_p, c_wchar_p, c_void_p]

import time
import tempfile
ud = os.path.join(tempfile.gettempdir(), "kali-wv2-ud")

hr = internal(1, 1, c_void_p(out.value), c_wchar_p(ud),
              c_void_p(ctypes.addressof(struct)))
print("internal hr:", hex(hr & 0xFFFFFFFF))

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
