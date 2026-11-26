"""Diagnostic: trace the WebView2 host step by step."""
from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import HRESULT, c_void_p, c_wchar_p, byref

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kali.webview2 as wv2

# ---- 1. the loader --------------------------------------------------------
loader = wv2.WebView2Loader()
print("loader available:", loader.available)
print("browser executable:", loader.browser_executable)

# ---- 2. a window ----------------------------------------------------------
import kali.desktop_shell as ds

user32 = ds._user32
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
cls.lpszClassName = "KaliCodeDiag"
user32.RegisterClassW(ctypes.byref(cls))

hwnd = user32.CreateWindowExW(
    0, "KaliCodeDiag", "Kali Code", ds._WS_OVERLAPPEDWINDOW,
    50, 50, 1200, 800, None, None,
    ctypes.windll.kernel32.GetModuleHandleW(None), None)
print("hwnd:", hwnd)

# ---- 3. the environment ---------------------------------------------------
host = wv2.WebView2Host("http://127.0.0.1:1/")
print("host loader available:", host._loader.available)

env_handler, env_keep = wv2._make_handler(
    wv2._ENV_INVOKE,
    wv2.IID_COREWEBVIEW2_CREATE_ENVIRONMENT_COMPLETED_HANDLER,
    host._on_env_ready,
)
host._keepalive.append((env_handler, env_keep))

handler_addr = ctypes.addressof(env_handler)
print("handler address:", hex(handler_addr))
print("handler vtbl:", hex(ctypes.cast(env_handler.lpVtbl, c_void_p).value))

hr = loader.create(
    loader.browser_executable,
    None,
    None,
    c_void_p(handler_addr),
)
print("create env hr:", hex(hr & 0xFFFFFFFF))

ok = host._wait_for(host._env_result, 20)
print("env callback fired:", ok, "hr:", hex(host._env_result["hr"] & 0xFFFFFFFF))
raw = host._env_result["env"]
print("raw env:", raw, type(raw))
print("addr(env):", hex(wv2._addr(raw)))

env = wv2._as_ptr(raw)
print("env as ptr:", hex(env.value))

# ---- 4. the vtable --------------------------------------------------------
vtbl = ctypes.cast(env.value, ctypes.POINTER(ctypes.POINTER(c_void_p))).contents
for i in range(8):
    print(f"  vtbl[{i}] = {hex(vtbl[i] or 0)}")

# ---- 5. create the controller --------------------------------------------
ctrl_handler, ctrl_keep = wv2._make_handler(
    wv2._CTRL_INVOKE,
    wv2.IID_COREWEBVIEW2_CREATE_CONTROLLER_COMPLETED_HANDLER,
    host._on_ctrl_ready,
)
host._keepalive.append((ctrl_handler, ctrl_keep))

for index in (4, 5):
    print(f"--- trying CreateCoreWebView2Controller at vtbl index {index} ---")
    try:
        create_ctrl = wv2._method(env, index, HRESULT, [c_void_p, c_void_p])
        hr2 = create_ctrl(wv2._addr(env), c_void_p(hwnd),
                          c_void_p(ctypes.addressof(ctrl_handler)))
        print("   hr:", hex(hr2 & 0xFFFFFFFF))
        if hr2 == 0:
            ok2 = host._wait_for(host._ctrl_result, 20)
            print("   ctrl callback:", ok2,
                  hex(host._ctrl_result["hr"] & 0xFFFFFFFF))
            break
    except Exception as e:
        print("   EXC:", type(e).__name__, e)

user32.DestroyWindow(hwnd)
