"""Diagnostic: trace the HTTP and WebSocket traffic of the desktop client.

Starts a Kali Code server on a free port with request logging turned on,
opens a WebView2 window at it and reports which requests the page made.

Usage:
    python tools/diag_traffic.py
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import kali.desktop_shell as ds
from kali.serve import build_app, resolve_token

user32 = ds._user32

hits: list[str] = []


class LoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        hits.append(f"-> {scope['method']} {scope['path']}")

        async def _send(message):
            if message["type"] == "http.response.start":
                hits.append(f"   {scope['method']} {scope['path']} -> "
                            f"{message['status']}")
            await send(message)

        await self.app(scope, receive, _send)


def main() -> int:
    import uvicorn

    port = ds._free_port()
    url = f"http://127.0.0.1:{port}/"
    token = resolve_token()

    app, server = build_app(token=token, cwd=os.getcwd())
    app = LoggingMiddleware(app)

    config = uvicorn.Config(app, host="127.0.0.1", port=port,
                            log_level="warning")
    srv = uvicorn.Server(config)
    threading.Thread(target=srv.run, daemon=True).start()

    if not ds._wait_for(url, timeout=30):
        print("server did not start")
        return 1
    print("server up:", url)

    page = url if os.environ.get("NO_FRAGMENT") == "1" else f"{url}#token={token}"
    import tempfile
    if os.environ.get("SHARED_PROFILE") == "1":
        from kali.resources import user_data_dir

        ud = str(user_data_dir() / "webview")
    else:
        ud = tempfile.mkdtemp(prefix="kali-diag-ud-")
    print("user data folder:", ud)

    from kali.webview2 import WebView2Host

    host = WebView2Host(page, user_data_folder=ud)
    win = ds.DesktopWindow("Kali Code", page)
    win._attach_webview = lambda hwnd: (host.create(hwnd),
                                         host.set_bounds(0, 0, 1900, 1000))
    threading.Thread(target=win.run, daemon=True).start()
    for _ in range(30):
        time.sleep(1)
        if any("/desktop/app.js" in h for h in hits):
            break
    time.sleep(3)

    print("\n=== HTTP requests ===")
    for h in hits:
        print(" ", h)
    if not hits:
        print("  (none - the page never loaded!)")

    print("\n=== the page HTML (first 900 chars) ===")
    import urllib.request

    with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
        print("  content-type:", r.headers.get("Content-Type"))
        print(r.read().decode("utf-8", "replace")[:900])

    print("\n=== health ===")
    import urllib.request

    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health",
                                timeout=5) as r:
        print(" ", r.read().decode())

    srv.should_exit = True
    return 0


if __name__ == "__main__":
    sys.exit(main())
