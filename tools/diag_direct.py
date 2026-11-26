"""Diagnostic: call the runtime's CreateWebViewEnvironmentWithOptionsInternal.

The SDK's WebView2Loader.dll is a shim: it locates the runtime's
`EBWebView\\<arch>\\EmbeddedBrowserWebView.dll` and calls the
`CreateWebViewEnvironmentWithOptionsInternal` export inside it.

Signature (from the loader's disassembly and the Go port):

    HRESULT CreateWebViewEnvironmentWithOptionsInternal(
        int      unknown,          // 1
        int      runtimeType,      // 0 = installed, 1 = redistributable
        PCWSTR   userDataFolder,
        void*    options,          // ICoreWebView2EnvironmentOptions*
        void*    handler);         // the completion handler (a COM object)

The handler is a plain COM object with a four-slot vtable:
QueryInterface | AddRef | Release | Invoke.

This bypasses the loader's internal proxy, so the object the callback
receives is the genuine ICoreWebView2Environment.
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

RUNTIMES = [
    r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application\158.0.4370.33",
    r"C:\Program Files (x86)\Microsoft\EdgeCore\158.0.4370.33",
]


def pump(predicate, timeout=25):
    deadline = time.time() + timeout
    while not predicate() and time.time() < deadline:
        msg = ctypes.wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)
    return predicate()


# ---- a window -------------------------------------------------------------
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
cls.lpszClassName = "KaliCodeDirect"
user32.RegisterClassW(ctypes.byref(cls))

hwnd = user32.CreateWindowExW(
    0, "KaliCodeDirect", "Kali Code", ds._WS_OVERLAPPEDWINDOW,
    50, 50, 1200, 800, None, None,
    ctypes.windll.kernel32.GetModuleHandleW(None), None)
print("hwnd:", hwnd)

import tempfile
ud = os.path.join(tempfile.gettempdir(), "kali-wv2-direct")
os.makedirs(ud, exist_ok=True)

for runtime in RUNTIMES:
    server = os.path.join(runtime, "EBWebView", "x64",
                           "EmbeddedBrowserWebView.dll")
    if not os.path.exists(server):
        print("skip (no server):", runtime)
        continue

    print("\n---", runtime)

    holder = {}

    # A raw ctypes callback so every argument can be inspected.
    def _raw_invoke(this, a1, a2):
        print("   [raw] this:", hex(this or 0))
        print("   [raw] a1:", hex(a1 & 0xFFFFFFFF),
              hex(a1 & 0xFFFFFFFF),
              "a2:", hex(a2 or 0))
        holder["this"] = this
        holder["a1"] = a1
        holder["a2"] = a2
        return 0

    _RAW = ctypes.WINFUNCTYPE(HRESULT, c_void_p, ctypes.c_int64, c_void_p)
    raw_fn = _RAW(_raw_invoke)

    # Build the handler vtable by hand so the raw callback is used.
    iid = wv2.IID_COREWEBVIEW2_CREATE_ENVIRONMENT_COMPLETED_HANDLER

    def _qi(this, iid_ptr, out):
        try:
            want = ctypes.cast(iid_ptr, ctypes.POINTER(wv2.GUID)).contents
            if want == iid or want == wv2.IID_IUNKNOWN:
                out[0] = this
                return 0
        except Exception:
            pass
        return -2147467262

    qi_fn = wv2._QUERY_INTERFACE_PROTO(_qi)

    vtbl = (ctypes.c_void_p * 4)()
    vtbl[0] = ctypes.cast(qi_fn, ctypes.c_void_p)
    vtbl[1] = ctypes.cast(wv2._addref_fn, ctypes.c_void_p)
    vtbl[2] = ctypes.cast(wv2._release_fn, ctypes.c_void_p)
    vtbl[3] = ctypes.cast(raw_fn, ctypes.c_void_p)

    class _Obj(ctypes.Structure):
        _fields_ = [("lpVtbl", ctypes.POINTER(ctypes.c_void_p))]

    obj = _Obj()
    obj.lpVtbl = ctypes.cast(vtbl, ctypes.POINTER(ctypes.c_void_p))
    keep = {"fn": raw_fn, "vtbl": vtbl, "obj": obj, "qi": qi_fn}

    handler = obj

    dll = ctypes.WinDLL(server)
    internal = dll.CreateWebViewEnvironmentWithOptionsInternal
    internal.restype = HRESULT
    internal.argtypes = [
        ctypes.c_int,    # unknown
        ctypes.c_int,    # runtimeType
        c_wchar_p,       # userDataFolder
        c_void_p,        # options
        c_void_p,        # handler
    ]

    try:
        hr = internal(
            1,
            1 if "EdgeCore" not in runtime else 1,
            c_wchar_p(ud),
            None,
            c_void_p(ctypes.addressof(handler)),
        )
    except Exception as e:
        print("   EXC:", type(e).__name__, e)
        continue

    print("   immediate hr:", hex(hr & 0xFFFFFFFF))
    if hr != 0:
        continue

    pump(lambda: "a2" in holder)
    print("   raw a1:", hex(holder.get("a1", 0) & 0xFFFFFFFF),
          "raw a2:", hex(holder.get("a2", 0) or 0))
    env = holder.get("a2")
    code = 0
    print("   callback hr:", hex(code) if code is not None else "TIMEOUT",
          "env:", hex(env or 0))

    if not env:
        continue

    # ---- is it a real interface? -----------------------------------------
    ptr = wv2._as_ptr(env)
    addr = wv2._addr(ptr)
    print("   raw address:", hex(addr))
    try:
        raw = ctypes.string_at(addr, 48)
        print("   48 bytes:", raw.hex(' '))
        for i in range(6):
            q = int.from_bytes(raw[i*8:i*8+8], 'little')
            print(f"      qword[{i}] = {hex(q)}")
    except Exception as e:
        print("   raw read failed:", type(e).__name__, e)

    # Try the vtable at offset +8 (the object carries an EH cookie first).
    for vtbl_off in (8, 0):
        try:
            vptr = int.from_bytes(raw[vtbl_off:vtbl_off+8], 'little')
            vt = ctypes.string_at(vptr, 48)
            slots = [int.from_bytes(vt[i*8:i*8+8], 'little')
                     for i in range(6)]
            print(f"   vtable at obj+{vtbl_off} = {hex(vptr)}:",
                  [hex(s) for s in slots])
        except Exception as e:
            print(f"   vtable at obj+{vtbl_off} unreadable:",
                  type(e).__name__, e)

    try:
        qi = wv2._query_interface(ptr, wv2.IID_ICORE_WEBVIEW2_ENVIRONMENT)
        print("   QueryInterface ok ->", hex(wv2._addr(qi)))
        ptr = qi
    except Exception as e:
        print("   QueryInterface failed:", e)

    # ---- create the controller -------------------------------------------
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

    for index in (5, 4):
        try:
            fn = wv2._method(ptr, index, HRESULT, [c_void_p, c_void_p])
            h = fn(wv2._addr(ptr), c_void_p(hwnd),
                   c_void_p(ctypes.addressof(ctrl_handler)))
            print(f"   create controller [{index}] hr:",
                  hex(h & 0xFFFFFFFF))
            if h == 0:
                pump(lambda: "hr" in ctrl_holder)
                print("   controller callback hr:",
                      hex(ctrl_holder.get("hr", 0) & 0xFFFFFFFF))
                if ctrl_holder.get("ctrl"):
                    break
        except Exception as e:
            print(f"   create controller [{index}] EXC:",
                  type(e).__name__, e)
            break

    if ctrl_holder.get("ctrl"):
        print("   SUCCESS")
        break

user32.DestroyWindow(hwnd)
