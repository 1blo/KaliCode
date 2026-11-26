"""Kali Code desktop shell - a WebView2 window over the local server.

The Windows Claude app is a native PE executable, so the shell here is native
too: a small Win32 window hosting the WebView2 runtime (preinstalled on
Windows 10/11) pointed at the local Kali Code server.

Everything below is optional. If WebView2 is missing the shell falls back to
opening the server URL in the default browser, so the GUI still works.

Usage:
    KaliCode.exe --gui
"""
from __future__ import annotations

import ctypes
import json
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _free_port(preferred: int = 0) -> int:
    """Pick a free TCP port (preferred first, then anything free)."""
    candidates = [preferred] if preferred else []
    candidates += list(range(8765, 8800))
    for port in candidates:
        if not port:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for(url: str, timeout: float = 30.0) -> bool:
    """Poll until the server answers."""
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.25)
    return False


# --------------------------------------------------------------------------- #
# The window
# --------------------------------------------------------------------------- #
if sys.platform == "win32":
    try:
        import ctypes.wintypes as wintypes

        _user32 = ctypes.windll.user32
        _GWL_STYLE = -16
        _WS_OVERLAPPEDWINDOW = 0x00CF0000
        _WS_VISIBLE = 0x10000000
        _SW_SHOW = 5
        _SW_MAXIMIZE = 3
        _WM_DESTROY = 0x0002
        _WM_CLOSE = 0x0010
        _WM_SIZE = 0x0005
        _WM_MOVE = 0x0003
        _WM_GETMINMAXINFO = 0x0024
        _CS_HREDRAW = 0x0002
        _CS_VREDRAW = 0x0001
        _IDC_ARROW = 32512

        # WPARAM / LPARAM are pointer-sized on x64. Declaring them as plain
        # ints truncates the values and makes DefWindowProcW overflow.
        _LRESULT = ctypes.c_ssize_t
        _WPARAM = ctypes.c_size_t
        _LPARAM = ctypes.c_ssize_t

        # The user32 entry points need matching signatures too.
        _user32.DefWindowProcW.argtypes = [
            wintypes.HWND, ctypes.c_uint, _WPARAM, _LPARAM]
        _user32.DefWindowProcW.restype = _LRESULT
        _user32.CreateWindowExW.restype = wintypes.HWND
        _user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG), wintypes.HWND,
            ctypes.c_uint, ctypes.c_uint]
        _user32.GetMessageW.restype = ctypes.c_int
    except Exception:  # pragma: no cover
        _user32 = None
else:
    _user32 = None


def _webview2_available() -> bool:
    """Is the WebView2 runtime installed?"""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        for hive, path in (
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
            (winreg.HKEY_CURRENT_USER,
             r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        ):
            try:
                with winreg.OpenKey(hive, path) as k:
                    ver, _ = winreg.QueryValueEx(k, "pv")
                    if ver:
                        return True
            except OSError:
                continue
    except Exception:
        pass
    # A last check: the runtime's loader DLL.
    for p in (
        Path(os.environ.get("SYSTEMROOT", "C:/Windows")) /
        "System32" / "msedgewebview2.exe",
    ):
        if p.exists():
            return True
    return False


class DesktopWindow:
    """A native Win32 window hosting the WebView2 control.

    Uses the WebView2 COM API directly through ctypes so the build has no
    extra dependency. When anything goes wrong the caller falls back to the
    system browser.
    """

    def __init__(self, title: str, url: str, width: int = 1440, height: int = 900):
        self.title = title
        self.url = url
        self.width = width
        self.height = height
        self.hwnd = None
        self._controller = None
        self._ok = False

    # ------------------------------------------------------------- run
    def run(self) -> int:
        if _user32 is None:
            return self._fallback()
        try:
            return self._run_win32()
        except Exception as e:
            print(f"[gui] native window failed: {e}")
            return self._fallback()

    def _fallback(self) -> int:
        print(f"[gui] opening {self.url} in the default browser")
        webbrowser.open(self.url)
        # Keep the server alive while the browser tab is open.
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            return 0

    # ---------------------------------------------------------- win32
    def _run_win32(self) -> int:
        """Create the window and pump messages until it closes."""
        user32 = _user32

        WNDCLASS = type("WNDCLASS", (ctypes.Structure,), {
            "_fields_": [
                ("style", ctypes.c_uint),
                ("lpfnWndProc", ctypes.WINFUNCTYPE(
                    _LRESULT, wintypes.HWND, ctypes.c_uint,
                    _WPARAM, _LPARAM)),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ],
        })

        hinstance = ctypes.windll.kernel32.GetModuleHandleW(None)

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == _WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            if msg == _WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            if msg == _WM_SIZE:
                # Keep the WebView2 control filling the client area.
                self._sync_bounds(hwnd)
                return 0
            if msg == _WM_MOVE:
                # Tell the runtime the parent window moved.
                self._notify_moved()
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc = ctypes.WINFUNCTYPE(
            _LRESULT, wintypes.HWND, ctypes.c_uint,
            _WPARAM, _LPARAM)(wndproc)

        cls = WNDCLASS()
        cls.style = _CS_HREDRAW | _CS_VREDRAW
        cls.lpfnWndProc = self._wndproc
        cls.hInstance = hinstance
        cls.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(_IDC_ARROW))
        cls.hbrBackground = ctypes.c_void_p(16)  # COLOR_BTNFACE+1
        cls.lpszClassName = "KaliCodeDesktop"

        if not user32.RegisterClassW(ctypes.byref(cls)):
            err = ctypes.get_last_error()
            if err not in (0, 1410):  # already registered is fine
                raise OSError(f"RegisterClassW failed: {err}")

        style = _WS_OVERLAPPEDWINDOW
        hwnd = user32.CreateWindowExW(
            0, "KaliCodeDesktop", self.title, style,
            100, 100, self.width, self.height,
            None, None, hinstance, None)
        if not hwnd:
            raise OSError("CreateWindowExW failed")
        self.hwnd = hwnd

        user32.ShowWindow(hwnd, _SW_MAXIMIZE)
        user32.UpdateWindow(hwnd)

        # Attach the WebView2 control to the window's client area.
        self._attach_webview(hwnd)

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        return 0

    # ------------------------------------------------------- webview2
    def _attach_webview(self, hwnd) -> None:
        """Create the WebView2 environment and controller."""
        from .webview2 import WebView2Host

        user_data = None
        try:
            from .resources import user_data_dir

            user_data = str(user_data_dir() / "webview")
        except Exception:
            user_data = None

        host = WebView2Host(self.url, user_data_folder=user_data)
        if not host.create(hwnd):
            raise RuntimeError("WebView2 could not be created")
        self._host = host
        self._user_data = user_data

        # The controller starts with a zero-sized bounds, so nothing would
        # be visible until it is told how large it should be.
        self._sync_bounds(hwnd)

    # ----------------------------------------------------------- recovery
    def reset_profile(self) -> bool:
        """Wipe the WebView2 profile and reload the page.

        The profile caches the UI shell. If the server was restarted with
        a different token, the cached shell can fail to connect and the
        page stays blank. Clearing the profile fixes that.
        """
        user_data = getattr(self, "_user_data", None)
        if not user_data:
            return False
        try:
            host = getattr(self, "_host", None)
            if host is not None:
                host.close()
        except Exception:
            pass
        try:
            import shutil

            shutil.rmtree(user_data, ignore_errors=True)
        except Exception:
            return False

        # Recreate the control with a fresh profile.
        try:
            self._attach_webview(self.hwnd)
        except Exception:
            return False
        return True

    # ----------------------------------------------------------- bounds
    def _client_size(self, hwnd) -> tuple[int, int]:
        """The client area size of the parent window, in pixels."""
        user32 = _user32
        rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return (self.width, self.height)
        return (rect.right - rect.left, rect.bottom - rect.top)

    def _sync_bounds(self, hwnd) -> None:
        """Make the WebView2 control fill the parent window's client area."""
        host = getattr(self, "_host", None)
        if host is None:
            return
        width, height = self._client_size(hwnd)
        if width <= 0 or height <= 0:
            return
        try:
            host.set_bounds(0, 0, width, height)
        except Exception:
            pass

    def _notify_moved(self) -> None:
        """Tell WebView2 the parent window changed position."""
        host = getattr(self, "_host", None)
        if host is None:
            return
        try:
            host.notify_parent_moved()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def run_gui(cwd: str | None = None, port: int = 0, token: str | None = None,
            model: str | None = None, permission_mode: str | None = None,
            open_browser: bool = False) -> int:
    """Launch the local server and show the desktop window."""
    from .serve import build_app, resolve_token

    chosen = port or _free_port()
    url = f"http://127.0.0.1:{chosen}/"
    server_token = token or resolve_token()

    import uvicorn

    app, server = build_app(token=server_token, cwd=cwd or os.getcwd(),
                             model=model, permission_mode=permission_mode)
    config = uvicorn.Config(app, host="127.0.0.1", port=chosen,
                            log_level="warning")
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()

    print(f"Kali Code desktop -> {url}")
    print(f"Access token: {server_token}")

    # A packaged build has no console attached, so the details are also
    # written to a file. The phone client reads it to pair automatically.
    try:
        from .resources import user_data_dir

        info = user_data_dir() / "desktop.json"
        info.parent.mkdir(parents=True, exist_ok=True)
        info.write_text(
            json.dumps({"url": url, "token": server_token,
                        "port": chosen}, indent=2),
            encoding="utf-8")
    except Exception:
        pass

    if not _wait_for(url, timeout=30):
        print("[gui] the server did not come up in time")
        return 1

    if open_browser:
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            srv.should_exit = True
            return 0

    # The desktop shell hosts the server itself, so the access token is
    # handed to the page in the URL fragment. There is nothing to type.
    page_url = f"{url}#token={server_token}"

    win = DesktopWindow("Kali Code", page_url)

    # Watchdog: if the page never connects, the cached shell in the
    # WebView2 profile is stale. Wipe it and reload once.
    def _watchdog():
        deadline = time.time() + 20
        while time.time() < deadline:
            time.sleep(1.0)
            try:
                if server.connected_clients() > 0:
                    return
            except Exception:
                pass
        try:
            print("[gui] the UI did not connect - resetting the WebView2 profile")
            win.reset_profile()
        except Exception:
            pass

    threading.Thread(target=_watchdog, daemon=True).start()

    try:
        return win.run()
    finally:
        srv.should_exit = True


if __name__ == "__main__":
    sys.exit(run_gui())
