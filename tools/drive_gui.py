"""Fill in the access token in the Kali Code window and capture the UI.

The desktop app shows a token gate on first run. This script finds the
window, focuses the token field, types the token from the server's stdout,
presses Enter and then screenshots the result.

Usage:
    python tools/drive_gui.py [token]
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.windll.user32
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.FindWindowExW.argtypes = [
    wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = wintypes.HWND
user32.SendMessageW.restype = ctypes.c_ssize_t


def find_window(title: str) -> int:
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lp):
        n = user32.GetWindowTextLengthW(hwnd)
        if n and user32.IsWindowVisible(hwnd):
            b = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, b, n + 1)
            if b.value.strip() == title:
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else 0


def server_token() -> str:
    """The access token of the running server.

    The token is printed on stdout when the server starts. A frozen build
    redirects it to a file; a source run prints it to the terminal.
    """
    # A packaged build writes the connection details to a file.
    try:
        from kali.resources import user_data_dir

        p = user_data_dir() / "desktop.json"
        if p.exists():
            import json

            token = str(json.loads(p.read_text(encoding="utf-8"))["token"])
            if token:
                return token
    except Exception:
        pass

    candidates = [
        Path.home() / "AppData/Local/Temp/kali-gui-out.txt",
        Path.home() / "AppData/Local/Temp/kali-exe-out.txt",
    ]
    for out in candidates:
        try:
            for line in out.read_text(encoding="utf-8",
                                      errors="replace").splitlines():
                if line.startswith("Access token:"):
                    return line.split(":", 1)[1].strip()
        except OSError:
            continue
    return ""


def main() -> int:
    hwnd = find_window("Kali Code")
    if not hwnd:
        print("no Kali Code window")
        return 1

    token = server_token()
    if not token:
        print("no access token found")
        return 1
    print("token:", token[:6] + "...")

    # The WebView2 renders in a separate process, so there is no HWND to
    # type into. Drive it through the keyboard instead: focus the window,
    # click the token field by tabbing from the page, then type.
    user32.SetForegroundWindow(hwnd)
    user32.ShowWindow(hwnd, 3)
    time.sleep(1.0)

    # Click in the middle of the token field. The lock box is centred, and
    # the field sits just above the Connect button.
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    cx = (rect.left + rect.right) // 2
    cy = (rect.top + rect.bottom) // 2
    # The token input is roughly 90px above the button, which is 50px
    # below the vertical centre of the lock box.
    field_y = cy - 40
    user32.SetCursorPos(cx, field_y)
    user32.mouse_event(0x0002, 0, 0, 0, 0)   # LEFTDOWN
    user32.mouse_event(0x0004, 0, 0, 0, 0)   # LEFTUP
    time.sleep(0.4)

    for ch in token:
        user32.keybd_event(0, 0, 0, 0)  # placeholder to keep timing
        break

    # Use clipboard paste for speed and reliability.
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_bool
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]

    data = token + "\0"
    size = len(data) * ctypes.sizeof(ctypes.c_wchar)
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
    ptr = kernel32.GlobalLock(handle)
    ctypes.memmove(ptr, ctypes.create_unicode_buffer(token), size)
    kernel32.GlobalUnlock(handle)

    user32.OpenClipboard(hwnd)
    user32.EmptyClipboard()
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData(CF_UNICODETEXT, ctypes.c_void_p(handle))
    user32.CloseClipboard()

    user32.keybd_event(0x11, 0, 0, 0)  # CTRL down
    user32.keybd_event(0x56, 0, 0, 0)  # V down
    user32.keybd_event(0x56, 0, 2, 0)  # V up
    user32.keybd_event(0x11, 0, 2, 0)  # CTRL up
    time.sleep(0.5)

    user32.keybd_event(0x0D, 0, 0, 0)  # ENTER down
    user32.keybd_event(0x0D, 0, 2, 0)  # ENTER up
    time.sleep(2.5)

    shot = Path.home() / "AppData/Local/Temp/kali-gui-connected.png"
    subprocess.run([sys.executable,
                    str(Path(__file__).with_name("screenshot_screen.py")),
                    str(shot), "Kali Code"], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
