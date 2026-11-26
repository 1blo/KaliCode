"""Capture the Kali Code desktop window from the screen.

`PrintWindow` cannot capture a WebView2 surface - the browser renders in a
separate GPU-composited layer that the window does not own. Grabbing the
screen region the window occupies does capture it.

Usage:
    python tools/screenshot_screen.py [output.png]
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path


def find_window(title: str) -> int:
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value.strip() == title and user32.IsWindowVisible(hwnd):
                # Skip the WebView2 child windows.
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(cb, 0)
    if found:
        return found[0]

    # Fall back to a partial match.
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb2(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if title.lower() in buf.value.lower() and user32.IsWindowVisible(hwnd):
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(cb2, 0)
    return found[0] if found else 0


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "gui-screenshot.png")
    title = sys.argv[2] if len(sys.argv) > 2 else "Kali Code"

    hwnd = find_window(title)
    if not hwnd:
        print(f"no window titled '{title}' found")
        return 1

    user32 = ctypes.windll.user32
    user32.SetForegroundWindow(hwnd)
    user32.ShowWindow(hwnd, 9)   # SW_RESTORE
    time.sleep(0.4)
    user32.ShowWindow(hwnd, 3)   # SW_MAXIMIZE
    user32.BringWindowToTop(hwnd)
    user32.RedrawWindow(hwnd, None, None, 0x0001 | 0x0004 | 0x0080)
    ctypes.windll.user32.SetWindowPos(
        hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)  # HWND_TOPMOST
    time.sleep(1.5)

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    x, y = rect.left, rect.top
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    print(f"window {width}x{height} at {x},{y}")

    # Grab the screen region.
    gdi32 = ctypes.windll.gdi32
    screen_dc = user32.GetDC(0)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
    gdi32.SelectObject(mem_dc, bitmap)
    # SRCCOPY = 0x00CC0020
    gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, x, y, 0x00CC0020)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", ctypes.c_long),
            ("biHeight", ctypes.c_long),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", ctypes.c_long),
            ("biYPelsPerMeter", ctypes.c_long),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    header = BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.biWidth = width
    header.biHeight = -height          # top-down
    header.biPlanes = 1
    header.biBitCount = 32
    header.biCompression = 0

    buf = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem_dc, bitmap, 0, height, buf, ctypes.byref(header), 0)

    try:
        from PIL import Image
        img = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1)
        img.convert("RGB").save(out)
        print(f"wrote {out} ({out.stat().st_size} bytes)")
    except ImportError:
        bmp = out.with_suffix(".bmp")
        with open(bmp, "wb") as f:
            f.write(b"BM")
            f.write((14 + 40 + len(buf)).to_bytes(4, "little"))
            f.write((0).to_bytes(2, "little") + (0).to_bytes(2, "little"))
            f.write((54).to_bytes(4, "little"))
            f.write((40).to_bytes(4, "little"))
            f.write(width.to_bytes(4, "little") + height.to_bytes(4, "little"))
            f.write((1).to_bytes(2, "little") + (32).to_bytes(2, "little"))
            f.write((0).to_bytes(4, "little") + len(buf).to_bytes(4, "little"))
            f.write((0).to_bytes(4, "little") * 4)
            f.write(buf)
        print(f"wrote {bmp} (install Pillow for a PNG)")

    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(0, screen_dc)
    ctypes.windll.user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002)
    return 0


if __name__ == "__main__":
    sys.exit(main())
