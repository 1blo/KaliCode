"""Diagnostic: the loader's public API, with the COM apartment tuned.

The WebView2 environment creation succeeds through the SDK loader, and the
environment pointer it hands back is a normal COM interface. The next call
- `CreateCoreWebView2Controller` - reports RPC_E_WRONG_THREAD, which means
the environment lives in a different apartment than the caller.

This tries each apartment mode in a *separate process* so the choice is
clean, and reports which one works.
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import HRESULT, c_void_p, c_wchar_p

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kali.webview2 as wv2
import kali.desktop_shell as ds

user32 = ds._user32

MODE = int(sys.argv[1]) if len(sys.argv) > 1 else 0x2

ole32 = ctypes.windll.ole32
ole32.CoInitializeEx.restype = HRESULT
ole32.CoInitializeEx.argtypes = [c_void_p, ctypes.c_uint]
hr = ole32.CoInitializeEx(None, MODE)
print(f"CoInitializeEx(0x{MODE:x}) hr:", hex(hr & 0xFFFFFFFF))

WNDCLASS = type("WNDCLASS", (ctypes.Structure,), {
    "_fields_": [
        ("style", ctypes.c_uint),
        ("lpfnWndProc", ctypes.WINFUNCTYPE(
            ds._LRESULT, ctypes.wintypes.HWND, ctypes.c_uint,
            ds._WPARAM, ds._LPARAM)),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.wintypes.HINSTANCE),
        ("hIcon", ctypes.wintypes.HICON),
        ("hCursor", ctypes.wintypes.HANDLE),
        ("hbrBackground", ctypes.wintypes.HANDLE),
        ("lpszMenuName", ctypes.wintypes.LPCWSTR),
        ("lpszClassName", ctypes.wintypes.LPCWSTR),
    ],
})


def wndproc(hwnd, msg, wparam, lparam):
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


proc = ctypes.WINFUNCTYPE(
    ds._LRESULT, ctypes.wintypes.HWND, ctypes.c_uint,
    ds._WPARAM, ds._LPARAM)(wndproc)
cls = WNDCLASS()
cls.style = ds._CS_HREDRAW | ds._CS_VREDRAW
cls.lpfnWndProc = proc
cls.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)
cls.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))
cls.lpszClassName = "KaliCodeApt"
user32.RegisterClassW(ctypes.byref(cls))

hwnd = user32.CreateWindowExW(
    0, "KaliCodeApt", "Kali Code", ds._WS_OVERLAPPEDWINDOW,
    50, 50, 1200, 800, None, None,
    ctypes.windll.kernel32.GetModuleHandleW(None), None)
print("hwnd:", hwnd)


def pump(predicate, timeout=25):
    deadline = time.time() + timeout
    while not predicate() and time.time() < deadline:
        msg = ctypes.wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)
    return predicate()


# ---- the environment ------------------------------------------------------
loader = wv2.WebView2Loader()
holder = {}
ctrl_holder = {}
hwnd_ref = {}


def cc(error_code, ctrl, _h=ctrl_holder):
    _h["hr"] = int(error_code) & 0xFFFFFFFF
    _h["ctrl"] = ctrl
    _h["tid"] = ctypes.windll.kernel32.GetCurrentThreadId()
    print("   [ctrl callback] hr:",
          hex(int(error_code) & 0xFFFFFFFF),
          "thread:", _h["tid"])
    return 0


ctrl_handler, ctrl_keep = wv2._make_handler(
    wv2._CTRL_INVOKE,
    wv2.IID_COREWEBVIEW2_CREATE_CONTROLLER_COMPLETED_HANDLER,
    cc,
)


def cb(error_code, env, _h=holder):
    _h["hr"] = int(error_code) & 0xFFFFFFFF
    _h["env"] = env
    _h["tid"] = ctypes.windll.kernel32.GetCurrentThreadId()
    print("   [env callback] hr:", hex(int(error_code) & 0xFFFFFFFF),
          "thread:", _h["tid"],
          "env:", hex(env or 0))

    # Create the controller right here - the environment must be used from
    # the thread that created it.
    if env and error_code == 0:
        try:
            fn = wv2._method(wv2._as_ptr(env), 5, HRESULT,
                             [c_void_p, c_void_p])
            h = fn(wv2._addr(wv2._as_ptr(env)), c_void_p(hwnd_ref["hwnd"]),
                   c_void_p(ctypes.addressof(ctrl_handler)))
            print("   [env callback] create controller hr:",
                  hex(h & 0xFFFFFFFF))
        except Exception as e:
            print("   [env callback] create controller EXC:",
                  type(e).__name__, e)
    return 0


hwnd_ref["hwnd"] = hwnd

handler, keep = wv2._make_handler(
    wv2._ENV_INVOKE,
    wv2.IID_COREWEBVIEW2_CREATE_ENVIRONMENT_COMPLETED_HANDLER,
    cb,
)

print("main thread:", ctypes.windll.kernel32.GetCurrentThreadId())
hr = loader.create(None, None, None, c_void_p(ctypes.addressof(handler)))
print("loader hr:", hex(hr & 0xFFFFFFFF))
pump(lambda: "hr" in holder)
print("env callback hr:", hex(holder.get("hr", 0) & 0xFFFFFFFF),
      "thread:", holder.get("tid"))

if ctrl_holder:
    pump(lambda: "hr" in ctrl_holder)
    print("controller callback hr:",
          hex(ctrl_holder.get("hr", 0) & 0xFFFFFFFF),
          "ctrl:", hex(wv2._addr(
              wv2._as_ptr(ctrl_holder.get("ctrl"))) or 0))

env = wv2._as_ptr(holder.get("env"))
if env:
    addr = wv2._addr(env)
    print("env:", hex(addr))
    vtbl = ctypes.cast(addr, ctypes.POINTER(ctypes.POINTER(c_void_p))).contents
    for i in range(8):
        print(f"   vtbl[{i}] = {hex(vtbl[i] or 0)}")

user32.DestroyWindow(hwnd)
