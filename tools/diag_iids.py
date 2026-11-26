"""Diagnostic: discover the IIDs the WebView2 runtime asks for.

Our handler's QueryInterface is where the runtime tells us which
interface it expects. Instead of hard-coding a guessed IID, this logs
every IID the runtime asks about and answers "yes" for all of them, so
the creation succeeds and we can learn the real values.
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
ole32.CoInitializeEx(None, 0x2)

seen: list[str] = []


def make_probe_handler(invoke_proto, label):
    """A handler whose QueryInterface accepts (and logs) every IID."""

    def _qi(this, iid_ptr, out):
        try:
            want = ctypes.cast(iid_ptr, ctypes.POINTER(wv2.GUID)).contents
            seen.append(f"{label}: {want}")
            print(f"   [QI {label}] asked for {want}")
            out[0] = this
            return 0
        except Exception as e:
            print(f"   [QI {label}] error: {e}")
            return -2147467262

    qi_fn = wv2._QUERY_INTERFACE_PROTO(_qi)

    def _invoke(this, error_code, obj):
        print(f"   [Invoke {label}] hr:", hex(int(error_code) & 0xFFFFFFFF),
              "obj:", hex(obj or 0))
        return 0

    fn = invoke_proto(_invoke)

    vtbl = (ctypes.c_void_p * 4)()
    vtbl[0] = ctypes.cast(qi_fn, ctypes.c_void_p)
    vtbl[1] = ctypes.cast(wv2._addref_fn, ctypes.c_void_p)
    vtbl[2] = ctypes.cast(wv2._release_fn, ctypes.c_void_p)
    vtbl[3] = ctypes.cast(fn, ctypes.c_void_p)

    class _Obj(ctypes.Structure):
        _fields_ = [
            ("lpVtbl", ctypes.POINTER(c_void_p)),
            ("refcount", ctypes.c_long),
            ("callback", ctypes.c_void_p),
        ]

    obj = _Obj()
    obj.lpVtbl = ctypes.cast(vtbl, ctypes.POINTER(c_void_p))
    obj.refcount = 1
    obj.callback = ctypes.cast(fn, ctypes.c_void_p)
    keep = {"fn": fn, "qi": qi_fn, "vtbl": vtbl, "obj": obj}
    return obj, keep


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
cls.lpszClassName = "KaliCodeIID"
user32.RegisterClassW(ctypes.byref(cls))

hwnd = user32.CreateWindowExW(
    0, "KaliCodeIID", "Kali Code", ds._WS_OVERLAPPEDWINDOW,
    50, 50, 1200, 800, None, None,
    ctypes.windll.kernel32.GetModuleHandleW(None), None)


def pump(predicate, timeout=20):
    deadline = time.time() + timeout
    while not predicate() and time.time() < deadline:
        msg = ctypes.wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)
    return predicate()


ctrl_handler, ctrl_keep = make_probe_handler(wv2._CTRL_INVOKE, "ctrl")

state = {}


def on_env(error_code, env, _h=state):
    _h["hr"] = int(error_code) & 0xFFFFFFFF
    _h["env"] = env
    if not env or int(error_code) != 0:
        return 0
    ptr = wv2._as_ptr(env)
    try:
        create = wv2._method(ptr, 3, HRESULT, [c_void_p, c_void_p])
        hr = create(wv2._addr(ptr), c_void_p(hwnd),
                    c_void_p(ctypes.addressof(ctrl_handler)))
        print("   create controller hr:", hex(hr & 0xFFFFFFFF))
    except Exception as e:
        print("   create controller EXC:", type(e).__name__, e)
    return 0


env_handler, env_keep = make_probe_handler(wv2._ENV_INVOKE, "env")

loader = wv2.WebView2Loader()
hr = loader.create(None, None, None, c_void_p(ctypes.addressof(env_handler)))
print("loader hr:", hex(hr & 0xFFFFFFFF))
pump(lambda: "hr" in state)
print("env hr:", hex(state.get("hr", 0) & 0xFFFFFFFF))
pump(lambda: any("ctrl" in s for s in seen), timeout=5)

print("\n=== IIDs the runtime asked for ===")
for s in seen:
    print(" ", s)

user32.DestroyWindow(hwnd)
