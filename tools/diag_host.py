"""Diagnostic: the WebView2 host, using the verified vtable layout.

The vtable layout comes from the WebView2 IDL:

    ICoreWebView2Environment
        3 CreateCoreWebView2Controller
        4 CreateWebResourceResponse
        5 GetBrowserVersionString

    ICoreWebView2Controller
        3 GetIsVisible
        4 PutIsVisible
        5 GetBounds
        6 PutBounds
        7 GetZoomFactor
        8 PutZoomFactor
        9 AddZoomFactorChanged
        10 RemoveZoomFactorChanged
        11 SetBoundsAndZoomFactor
        12 MoveFocus
        ...
        24 Close
        25 GetCoreWebView2

    ICoreWebView2
        3 GetSettings
        4 GetSource
        5 Navigate

The reference implementation (sffxzzp/go-webview2) creates the controller
from inside the environment completion callback, which is what WebView2
requires: the environment must be used from the thread that created it.
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
cls.lpszClassName = "KaliCodeHost"
user32.RegisterClassW(ctypes.byref(cls))

hwnd = user32.CreateWindowExW(
    0, "KaliCodeHost", "Kali Code", ds._WS_OVERLAPPEDWINDOW,
    50, 50, 1200, 800, None, None,
    ctypes.windll.kernel32.GetModuleHandleW(None), None)
user32.ShowWindow(hwnd, 5)  # SW_SHOW
user32.UpdateWindow(hwnd)
print("hwnd:", hwnd, "visible:",
      user32.IsWindowVisible(hwnd))


def pump(predicate, timeout=25):
    deadline = time.time() + timeout
    while not predicate() and time.time() < deadline:
        msg = ctypes.wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)
    return predicate()


def dump(name, ptr, count=10):
    if not ptr:
        print(f"{name}: NULL")
        return
    addr = wv2._addr(ptr)
    try:
        raw = ctypes.string_at(addr, 48)
        print(f"{name} @ {hex(addr)} raw:",
              " ".join(raw[i:i + 8].hex() for i in range(0, 48, 8)))
    except Exception as e:
        print(f"{name} @ {hex(addr)}: unreadable ({e})")
        return
    for off in (0, 8):
        try:
            vptr = int.from_bytes(raw[off:off + 8], 'little')
            vtbl = ctypes.cast(vptr, ctypes.POINTER(ctypes.POINTER(c_void_p))).contents
            slots = [hex(vtbl[i] or 0) for i in range(min(count, 8))]
            print(f"   vtable at obj+{off} = {hex(vptr)}: {slots}")
        except Exception:
            pass
    try:
        vtbl = ctypes.cast(addr, ctypes.POINTER(ctypes.POINTER(c_void_p))).contents
        print(f"   vtable at obj+0 = {hex(vtbl[0] or 0)}")
        for i in range(count):
            print(f"   [{i:2}] {hex(vtbl[i] or 0)}")
    except Exception as e:
        print("   direct vtable read failed:", e)


state = {"env": None, "ctrl": None, "webview": None, "settings": None}
env_holder = {}
ctrl_holder = {}


def on_ctrl(error_code, ctrl, _h=ctrl_holder):
    _h["hr"] = int(error_code) & 0xFFFFFFFF
    _h["ctrl"] = ctrl
    print("   [ctrl callback] hr:", hex(int(error_code) & 0xFFFFFFFF),
          "ctrl:", hex(ctrl or 0))
    if ctrl:
        addr = ctrl
        try:
            raw = ctypes.string_at(addr, 48)
            print("   [ctrl callback] raw:",
                  " ".join(raw[i:i + 8].hex() for i in range(0, 48, 8)))
        except Exception as e:
            print("   [ctrl callback] raw read failed:", e)

        # The runtime invalidates the pointer when the callback returns, so
        # keep a reference alive - the same thing the reference
        # implementations do.
        try:
            addref = wv2._method(wv2._as_ptr(ctrl), 1, ctypes.c_ulong, [])
            n = addref(addr)
            print("   [ctrl callback] AddRef ->", n)
        except Exception as e:
            print("   [ctrl callback] AddRef EXC:", type(e).__name__, e)
    return 0


ctrl_handler, ctrl_keep = wv2._make_handler(
    wv2._CTRL_INVOKE,
    wv2.IID_COREWEBVIEW2_CREATE_CONTROLLER_COMPLETED_HANDLER,
    on_ctrl,
)


def on_env(error_code, env, _h=env_holder):
    _h["hr"] = int(error_code) & 0xFFFFFFFF
    _h["env"] = env
    print("   [env callback] hr:", hex(int(error_code) & 0xFFFFFFFF),
          "env:", hex(env or 0))

    if not env or int(error_code) != 0:
        return 0

    state["env"] = wv2._as_ptr(env)

    # The reference implementation AddRefs the environment before using it.
    try:
        addref = wv2._method(state["env"], 1, ctypes.c_ulong, [])
        n = addref(wv2._addr(state["env"]))
        print("   [env callback] AddRef ->", n)
    except Exception as e:
        print("   [env callback] AddRef EXC:", type(e).__name__, e)

    if os.environ.get("WV2_CREATE_IN_CALLBACK") == "1":
        # Create the controller right here - the environment must be used
        # from the thread that created it.
        try:
            create = wv2._method(state["env"], 3, HRESULT, [c_void_p, c_void_p])
            hr = create(wv2._addr(state["env"]), c_void_p(hwnd),
                        c_void_p(ctypes.addressof(ctrl_handler)))
            print("   [env callback] create controller hr:", hex(hr & 0xFFFFFFFF))
        except Exception as e:
            print("   [env callback] create controller EXC:", type(e).__name__, e)
    else:
        print("   [env callback] deferring controller creation to the main thread")
    return 0


env_handler, env_keep = wv2._make_handler(
    wv2._ENV_INVOKE,
    wv2.IID_COREWEBVIEW2_CREATE_ENVIRONMENT_COMPLETED_HANDLER,
    on_env,
)

import tempfile
ud = os.path.join(tempfile.gettempdir(), "kali-wv2-ud")
os.makedirs(ud, exist_ok=True)
print("user data folder:", ud)

loader = wv2.WebView2Loader()
hr = loader.create(None, c_wchar_p(ud), None,
                   c_void_p(ctypes.addressof(env_handler)))
print("loader hr:", hex(hr & 0xFFFFFFFF))
pump(lambda: "hr" in env_holder)
print("env callback hr:", hex(env_holder.get("hr", 0) & 0xFFFFFFFF))

dump("ICoreWebView2Environment", state["env"])

# ---- create the controller from the main thread ---------------------------
if state["env"] and os.environ.get("WV2_CREATE_IN_CALLBACK") != "1":
    try:
        create = wv2._method(state["env"], 3, HRESULT, [c_void_p, c_void_p])
        hr = create(wv2._addr(state["env"]), c_void_p(hwnd),
                    c_void_p(ctypes.addressof(ctrl_handler)))
        print("main-thread create controller hr:", hex(hr & 0xFFFFFFFF))
        pump(lambda: "hr" in ctrl_holder)
    except Exception as e:
        print("main-thread create controller EXC:", type(e).__name__, e)

if ctrl_holder:
    pump(lambda: "hr" in ctrl_holder)
    print("controller callback hr:",
          hex(ctrl_holder.get("hr", 0) & 0xFFFFFFFF))
    state["ctrl"] = wv2._as_ptr(ctrl_holder.get("ctrl"))

dump("ICoreWebView2Controller", state["ctrl"], 30) if False else None
try:
    caddr = wv2._addr(state["ctrl"])
    craw = ctypes.string_at(caddr, 16)
    print("controller raw qwords:",
          [hex(int.from_bytes(craw[i:i + 8], 'little')) for i in (0, 8)])
except Exception as e:
    print("controller raw read failed:", e)
# ---- get the webview (controller slot 25) ---------------------------------
if state["ctrl"]:
    try:
        get_wv = wv2._method(state["ctrl"], 25, HRESULT,
                             [ctypes.POINTER(c_void_p)])
        out = c_void_p()
        h = get_wv(wv2._addr(state["ctrl"]), ctypes.byref(out))
        print("GetCoreWebView2 hr:", hex(h & 0xFFFFFFFF),
              "ptr:", hex(out.value or 0))
        state["webview"] = out
    except Exception as e:
        print("GetCoreWebView2 EXC:", type(e).__name__, e)

dump("ICoreWebView2", state["webview"], 8)

# ---- settings (webview slot 3) --------------------------------------------
if state["webview"]:
    try:
        get_set = wv2._method(state["webview"], 3, HRESULT,
                              [ctypes.POINTER(c_void_p)])
        out = c_void_p()
        h = get_set(wv2._addr(state["webview"]), ctypes.byref(out))
        print("GetSettings hr:", hex(h & 0xFFFFFFFF),
              "ptr:", hex(out.value or 0))
        state["settings"] = out
    except Exception as e:
        print("GetSettings EXC:", type(e).__name__, e)

dump("ICoreWebView2Settings", state["settings"], 8)

# ---- navigate (webview slot 5) --------------------------------------------
if state["webview"]:
    try:
        nav = wv2._method(state["webview"], 5, HRESULT, [c_wchar_p])
        h = nav(wv2._addr(state["webview"]), c_wchar_p("http://127.0.0.1:1/"))
        print("Navigate hr:", hex(h & 0xFFFFFFFF))
    except Exception as e:
        print("Navigate EXC:", type(e).__name__, e)

user32.DestroyWindow(hwnd)
print("done")
