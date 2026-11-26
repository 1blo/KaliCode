"""Diagnostic: identify the WebView2 vtable slots safely.

The environment pointer from the callback is a valid COM interface, but
calling QueryInterface on it crashes. That suggests the SDK loader hands
back a *proxy* whose QueryInterface/AddRef/Release are the loader's own
thunks - and those thunks expect the loader's internal 0x48-byte layout,
not a plain vtable.

So instead of guessing, probe the methods directly and check the results:

  * `get_BrowserVersionString` returns a wide string - easy to verify.
  * `CreateCoreWebView2Controller` returns S_OK and fires a callback.

Every probe is guarded: an access violation kills the process, so each
candidate runs in a separate child process.
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


def pump(predicate, timeout=25):
    deadline = time.time() + timeout
    while not predicate() and time.time() < deadline:
        msg = ctypes.wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)
    return predicate()


def make_window(cls_name="KaliCodeProbe"):
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
    cls.lpszClassName = cls_name
    user32.RegisterClassW(ctypes.byref(cls))
    return user32.CreateWindowExW(
        0, cls_name, "Kali Code", ds._WS_OVERLAPPEDWINDOW,
        50, 50, 1200, 800, None, None,
        ctypes.windll.kernel32.GetModuleHandleW(None), None)


def create_environment():
    """Create the environment and return the raw pointer from the callback."""
    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx.restype = HRESULT
    ole32.CoInitializeEx.argtypes = [c_void_p, ctypes.c_uint]
    ole32.CoInitializeEx(None, 0x2)

    loader = wv2.WebView2Loader()
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
    hr = loader.create(None, None, None, c_void_p(ctypes.addressof(handler)))
    if hr != 0:
        raise RuntimeError(f"loader hr={hex(hr & 0xFFFFFFFF)}")
    if not pump(lambda: "hr" in holder):
        raise RuntimeError("timeout")
    if holder["hr"] != 0:
        raise RuntimeError(f"env hr={hex(holder['hr'])}")
    return wv2._as_ptr(holder["env"]), keep


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "version"

    env, keep = create_environment()
    print("env:", hex(wv2._addr(env)))

    if mode == "version":
        # get_BrowserVersionString(LPWSTR*) - try several indices.
        for i in range(3, 12):
            try:
                fn = wv2._method(env, i, HRESULT, [ctypes.POINTER(c_wchar_p)])
                out = c_wchar_p()
                h = fn(wv2._addr(env), ctypes.byref(out))
                print(f"  [{i}] hr={hex(h & 0xFFFFFFFF)} out={out.value!r}")
                if h == 0 and out.value:
                    print(f"  >>> get_BrowserVersionString is slot {i}")
                    break
            except Exception as e:
                print(f"  [{i}] EXC {type(e).__name__}: {e}")
                break

    elif mode.startswith("ctrl"):
        index = int(mode[4:])
        hwnd = make_window()
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
        try:
            fn = wv2._method(env, index, HRESULT, [c_void_p, c_void_p])
            h = fn(wv2._addr(env), c_void_p(hwnd),
                   c_void_p(ctypes.addressof(ctrl_handler)))
            print(f"  [{index}] hr={hex(h & 0xFFFFFFFF)}")
            if h == 0:
                pump(lambda: "hr" in ctrl_holder)
                print("  callback hr:",
                      hex(ctrl_holder.get("hr", 0) & 0xFFFFFFFF),
                      "ctrl:",
                      hex(wv2._addr(wv2._as_ptr(ctrl_holder.get("ctrl"))) or 0))
        except Exception as e:
            print(f"  [{index}] EXC {type(e).__name__}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
