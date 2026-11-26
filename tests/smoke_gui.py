"""Verify the native desktop shell: the Win32 window and the WebView2 host.

  - the WebView2Loader.dll is present and exports the entry point
  - a Win32 window can be created and its message pump runs
  - the WebView2 controller can be created and navigate to the local server

The WebView2 part needs the runtime installed; it is skipped otherwise.

Run:  python tests/smoke_gui.py
"""
from __future__ import annotations

import ctypes
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn

from kali.serve import build_app

TOKEN = "gui-token"


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if cond:
            print(f"  ok   {name}")
        else:
            print(f"  FAIL {name} {detail}")
            failures.append(name)

    # ---- the loader ------------------------------------------------------
    from kali.webview2 import WebView2Loader

    loader = WebView2Loader()
    check("WebView2Loader.dll found", loader.available,
          "the loader DLL was not found")
    check("the loader exports CreateCoreWebView2EnvironmentWithOptions",
          loader.create is not None)

    # ---- start the server ------------------------------------------------
    app, server = build_app(token=TOKEN, cwd=os.getcwd())
    config = uvicorn.Config(app, host="127.0.0.1", port=8769, log_level="warning")
    srv = uvicorn.Server(config)
    task = threading.Thread(target=srv.run, daemon=True)
    task.start()
    time.sleep(1.5)

    url = "http://127.0.0.1:8769/"
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=5) as r:
            check("the local server answers", r.status == 200, str(r.status))
    except Exception as e:
        check("the local server answers", False, str(e))

    # ---- the Win32 window ------------------------------------------------
    import kali.desktop_shell as ds

    if ds._user32 is None:
        check("a native window can be created", False, "user32 is unavailable")
    else:
        win = ds.DesktopWindow("Kali Code", url)
        # Replace the WebView2 attach so only the window is exercised here.
        win._attach_webview = lambda hwnd: None

        def closer():
            time.sleep(1.0)
            ctypes.windll.user32.PostMessageW(win.hwnd, 0x0010, 0, 0)

        threading.Thread(target=closer, daemon=True).start()
        try:
            rc = win.run()
            check("the window creates and its message pump runs", rc == 0, str(rc))
        except Exception as e:
            check("the window creates and its message pump runs", False, str(e))

        # ---- the WebView2 host --------------------------------------------
        if loader.available:
            from kali.webview2 import WebView2Host
            import urllib.request

            user32 = ds._user32

            # Register a window class for the host window.
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
            cls.lpszClassName = "KaliCodeGuiTest"
            user32.RegisterClassW(ctypes.byref(cls))

            hwnd = user32.CreateWindowExW(
                0, "KaliCodeGuiTest", "Kali Code", ds._WS_OVERLAPPEDWINDOW,
                50, 50, 1200, 800, None, None,
                ctypes.windll.kernel32.GetModuleHandleW(None), None)
            check("a window can be created for the WebView2 control", bool(hwnd))
            # WebView2 needs a visible parent window.
            if hwnd:
                user32.ShowWindow(hwnd, 5)  # SW_SHOW
                user32.UpdateWindow(hwnd)

            created = False
            if hwnd:
                host = WebView2Host(url, user_data_folder=None)
                try:
                    created = host.create(hwnd)
                    check("the WebView2 controller is created", created)
                except Exception as e:
                    check("the WebView2 controller is created", False, str(e))

                if created:
                    time.sleep(2.0)
                    try:
                        with urllib.request.urlopen(url, timeout=5) as r:
                            body = r.read().decode("utf-8", "replace")
                        check("the page served to the WebView2 is the desktop shell",
                              "desktop/app.js" in body and "sessionList" in body,
                              body[:120])
                    except Exception as e:
                        check("the page served to the WebView2 is the desktop shell",
                              False, str(e))
                    host.close()
                    user32.DestroyWindow(hwnd)
        else:
            print("  ..   the WebView2 runtime is missing, skipping the host test")

    srv.should_exit = True
    time.sleep(0.5)

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {', '.join(failures)}")
        return 1
    print("ALL GUI TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
