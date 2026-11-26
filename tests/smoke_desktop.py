"""Smoke test for the desktop GUI assets and the session server.

Checks (no browser required):
  - the desktop UI files exist and the JS parses
  - the server routes the desktop shell to a desktop user-agent
  - the server routes a phone user-agent to the mobile shell
  - the static asset routes serve the desktop files
  - the new REST endpoints exist (files, file, side-chat, diff)

Run:  python tests/smoke_desktop.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import uvicorn

from kali.serve import build_app

TOKEN = "desktop-token"


async def main() -> int:
    import websockets

    app, server = build_app(token=TOKEN, cwd=os.getcwd())
    config = uvicorn.Config(app, host="127.0.0.1", port=8768, log_level="warning")
    srv = uvicorn.Server(config)
    task = asyncio.create_task(srv.serve())
    await asyncio.sleep(1.5)

    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if cond:
            print(f"  ok   {name}")
        else:
            print(f"  FAIL {name} {detail}")
            failures.append(name)

    base = "http://127.0.0.1:8768"

    # ---- assets on disk -----------------------------------------------
    from kali.resources import resource_dir

    base_dir = resource_dir()
    for name in ("index.html", "app.js", "style.css", "icon.svg"):
        p = base_dir / "desktop" / name
        check(f"desktop/{name} exists", p.exists(), str(p))

    # ---- the JS must parse --------------------------------------------
    import shutil
    node = shutil.which("node")
    if node:
        js = base_dir / "desktop" / "app.js"
        proc = __import__("subprocess").run(
            [node, "--check", str(js)], capture_output=True, text=True)
        check("desktop/app.js parses", proc.returncode == 0,
              (proc.stderr or "")[:400])

        js = base_dir / "mobile" / "app.js"
        proc = __import__("subprocess").run(
            [node, "--check", str(js)], capture_output=True, text=True)
        check("mobile/app.js parses", proc.returncode == 0,
              (proc.stderr or "")[:400])
    else:
        print("  ..   node not found, skipping the JS parse check")

    # ---- HTTP ----------------------------------------------------------
    async with httpx.AsyncClient(timeout=10) as c:
        desktop_ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                    "Chrome/131.0 Safari/537.36"}
        mobile_ua = {"User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
                                   "Chrome/131.0 Mobile Safari/537.36"}

        r = await c.get(base + "/", headers=desktop_ua)
        check("desktop user-agent -> desktop shell", r.status_code == 200
              and "desktop/app.js" in r.text, r.text[:200])

        r = await c.get(base + "/", headers=mobile_ua)
        check("mobile user-agent -> mobile shell", r.status_code == 200
              and "mobile/app.js" in r.text, r.text[:200])

        for asset in ("/desktop/app.js", "/desktop/style.css",
                      "/desktop/icon.svg", "/desktop/index.html"):
            r = await c.get(base + asset)
            check(f"GET {asset} -> 200", r.status_code == 200, str(r.status_code))

        r = await c.get(base + "/desktop/../../pyproject.toml")
        check("desktop path traversal blocked", r.status_code in (404, 400),
              str(r.status_code))

        # REST endpoints the UI calls.
        r = await c.get(base + "/api/files", params={"cwd": os.getcwd()})
        check("GET /api/files -> 200", r.status_code == 200, r.text[:200])
        check("/api/files returns entries", "entries" in r.json())

        r = await c.get(base + "/api/file", params={
            "cwd": os.getcwd(), "path": "pyproject.toml"})
        check("GET /api/file -> 200", r.status_code == 200, r.text[:200])
        check("/api/file returns content", "content" in r.json())

        r = await c.get(base + "/api/file", params={
            "cwd": os.getcwd(), "path": "../secret.txt"})
        check("/api/file blocks escapes", r.status_code in (403, 404),
              str(r.status_code))

        r = await c.post(base + "/api/side-chat", json={})
        check("POST /api/side-chat rejects an empty question",
              r.status_code == 400, str(r.status_code))

        r = await c.get(base + "/api/diff", params={"session": "nope"})
        check("GET /api/diff on an unknown session -> 404",
              r.status_code == 404, str(r.status_code))

    # ---- websocket: session switching over the wire ---------------------
    async with websockets.connect("ws://127.0.0.1:8768/ws") as ws:
        await ws.send(json.dumps({"type": "hello", "token": TOKEN}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        check("desktop client connects", msg.get("type") == "ready", str(msg))
        sid = msg.get("session", "")
        check("desktop client gets a session", bool(sid))

        # A second client sees the same session in the list.
        async with websockets.connect("ws://127.0.0.1:8768/ws") as ws2:
            await ws2.send(json.dumps({"type": "hello", "token": TOKEN,
                                       "session": sid}))
            msg2 = json.loads(await asyncio.wait_for(ws2.recv(), timeout=15))
            check("second client joins the same session",
                  msg2.get("session") == sid, str(msg2))
            check("session list includes it",
                  any(s.get("id") == sid for s in msg2.get("sessions") or []),
                  str(msg2.get("sessions")))

    srv.should_exit = True
    await task

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {', '.join(failures)}")
        return 1
    print("ALL DESKTOP TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
