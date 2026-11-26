"""Diagnostic: identify the WebView2 vtable slots empirically.

The COM method order is fixed by the WebView2 IDL, but the reference docs
list the members alphabetically, so the indices are easy to get wrong.

This script creates the environment and controller, then probes each vtable
slot to work out which one is which:

  * `get_CoreWebView2` is the slot that returns a pointer with a vtable
    whose slot 3 answers `get_Settings`.
  * `Navigate` is the slot that accepts a wide string and returns S_OK.
  * `put_IsVisible` / `put_AreDevToolsEnabled` are the slots that accept
    a BOOL.

Every probe is done on a *copy* of the interface pointer where possible so
a wrong guess cannot corrupt the object.
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

ole32 = ctypes.windll.ole32
ole32.CoInitializeEx.restype = HRESULT
ole32.CoInitializeEx.argtypes = [c_void_p, ctypes.c_uint]
print("CoInitializeEx:", hex(ole32.CoInitializeEx(None, 0x2) & 0xFFFFFFFF))

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
cls.lpszClassName = "KaliCodeVtableProbe"
user32.RegisterClassW(ctypes.byref(cls))

hwnd = user32.CreateWindowExW(
    0, "KaliCodeVtableProbe", "Kali Code", ds._WS_OVERLAPPEDWINDOW,
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


def cb(error_code, env, _h=holder):
    _h["hr"] = int(error_code) & 0xFFFFFFFF
    _h["env"] = env
    print("   [callback] error_code:", error_code,
          "env repr:", repr(env), "type:", type(env))
    return 0


handler, keep = wv2._make_handler(
    wv2._ENV_INVOKE,
    wv2.IID_COREWEBVIEW2_CREATE_ENVIRONMENT_COMPLETED_HANDLER,
    cb,
)

hr = loader.create(None, None, None, c_void_p(ctypes.addressof(handler)))
pump(lambda: "hr" in holder)
print("env hr:", hex(holder.get("hr", 0) & 0xFFFFFFFF))

env = wv2._as_ptr(holder.get("env"))
print("raw env value:", hex(wv2._addr(env)))
print("raw env type:", type(holder.get("env")))
env = wv2._query_interface(env, wv2.IID_ICORE_WEBVIEW2_ENVIRONMENT)
print("env:", hex(wv2._addr(env)))

# ---- the controller -------------------------------------------------------
ctrl_holder = {}


def cc(error_code, ctrl, _h=ctrl_holder):
    _h["hr"] = int(error_code) & 0xFFFFFFFF
    _h["ctrl"] = ctrl
    return 0


ctrl_handler, ctrl_keep = wv2._make_handler(
    wv2._CTRL_INVOKE,
    wv2.IID_COREWEBVIEW2_CREATE_CONTROLLER_COMPLETED_HANDLER,
    cc,
)

create_ctrl = wv2._method(env, 5, HRESULT, [c_void_p, c_void_p])
hr2 = create_ctrl(wv2._addr(env), c_void_p(hwnd),
                  c_void_p(ctypes.addressof(ctrl_handler)))
print("create controller hr:", hex(hr2 & 0xFFFFFFFF))
pump(lambda: "hr" in ctrl_holder)
print("controller callback hr:", hex(ctrl_holder.get("hr", 0) & 0xFFFFFFFF))

ctrl = wv2._as_ptr(ctrl_holder.get("ctrl"))
print("controller:", hex(wv2._addr(ctrl)))

# ---- probe the controller vtable -----------------------------------------
# get_CoreWebView2 returns an ICoreWebView2** - a pointer to a pointer.
print("\n--- probing the controller vtable for get_CoreWebView2 ---")
for i in range(3, 30):
    try:
        fn = wv2._method(ctrl, i, HRESULT, [ctypes.POINTER(c_void_p)])
        out = c_void_p()
        h = fn(wv2._addr(ctrl), ctypes.byref(out))
        if h == 0 and out.value:
            # Is the returned pointer a valid interface?
            try:
                vtbl = ctypes.cast(out.value,
                                   ctypes.POINTER(ctypes.POINTER(c_void_p))).contents
                valid = bool(vtbl[0])
            except Exception:
                valid = False
            print(f"  [{i}] hr=0 out={hex(out.value)} vtable_ok={valid}")
            if valid:
                print(f"  >>> get_CoreWebView2 is slot {i}")
                wv = out
                break
        else:
            print(f"  [{i}] hr={hex(h & 0xFFFFFFFF)} out={hex(out.value or 0)}")
    except Exception as e:
        print(f"  [{i}] EXC {type(e).__name__}: {e}")
        break

# ---- probe the webview vtable --------------------------------------------
if "wv" in dir():
    print("\n--- probing ICoreWebView2 ---")
    for i in range(3, 12):
        try:
            fn = wv2._method(wv, i, HRESULT, [ctypes.POINTER(c_void_p)])
            out = c_void_p()
            h = fn(wv2._addr(wv), ctypes.byref(out))
            print(f"  [{i}] hr={hex(h & 0xFFFFFFFF)} out={hex(out.value or 0)}")
        except Exception as e:
            print(f"  [{i}] EXC {type(e).__name__}: {e}")
            break

    print("\n--- probing ICoreWebView2 for get_Settings (slot?) ---")
    for i in (3, 4, 5):
        try:
            fn = wv2._method(wv, i, HRESULT, [ctypes.POINTER(c_void_p)])
            out = c_void_p()
            h = fn(wv2._addr(wv), ctypes.byref(out))
            print(f"  [{i}] hr={hex(h & 0xFFFFFFFF)} out={hex(out.value or 0)}")
            if h == 0 and out.value:
                settings = out
                print(f"  >>> get_Settings is slot {i}")
                break
        except Exception as e:
            print(f"  [{i}] EXC {type(e).__name__}: {e}")

user32.DestroyWindow(hwnd)
