"""Smoke test for the mobile companion server.

Starts the Starlette app on an ephemeral port, then exercises:
  - GET /health
  - GET / (PWA shell)
  - GET /manifest.json, /app.js, /icon.svg
  - WebSocket handshake with a WRONG token (must be rejected)
  - WebSocket handshake with the RIGHT token (must be accepted)
  - ping / pong

Does NOT call the model - the turn path is covered by the live smoke tests.

Run:  python tests/smoke_serve.py
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

TOKEN = "test-token-abc123"


async def main() -> int:
    import websockets

    app, server = build_app(token=TOKEN, cwd=os.getcwd())
    config = uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="warning")
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

    base = "http://127.0.0.1:8765"

    # ---- REST -----------------------------------------------------------
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(base + "/health")
        check("GET /health -> 200", r.status_code == 200, r.text[:200])
        try:
            body = r.json()
            check("health has ok=true", body.get("ok") is True)
            check("health names the service", body.get("service") == "kali-code")
        except Exception as e:
            check("health is json", False, str(e))

        r = await c.get(base + "/")
        check("GET / -> 200", r.status_code == 200)
        check("PWA shell served", "Kali Code" in r.text and "app.js" in r.text)

        for asset in ("/manifest.json", "/app.js", "/icon.svg", "/sw.js",
                      "/icon-192.png", "/icon-512.png"):
            r = await c.get(base + asset)
            check(f"GET {asset} -> 200", r.status_code == 200, str(r.status_code))

        r = await c.get(base + "/../pyproject.toml")
        check("path traversal blocked", r.status_code in (404, 400), str(r.status_code))

    # ---- WebSocket: bad token ------------------------------------------
    try:
        async with websockets.connect("ws://127.0.0.1:8765/ws") as ws:
            await ws.send(json.dumps({"type": "auth", "token": "wrong"}))
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            check("bad token rejected", msg.get("type") == "error"
                  and "unauthorized" in str(msg.get("message", "")).lower(),
                  str(msg))
    except Exception as e:
        check("bad token rejected (connection closed)", True, str(e))

    # ---- WebSocket: good token -----------------------------------------
    async with websockets.connect("ws://127.0.0.1:8765/ws") as ws:
        await ws.send(json.dumps({"type": "auth", "token": TOKEN}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        check("good token accepted", msg.get("type") == "ready", str(msg))
        check("ready carries a session id", bool(msg.get("session")), str(msg))
        check("ready carries the model", bool(msg.get("model")), str(msg))

        await ws.send(json.dumps({"type": "ping"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        check("ping -> pong", msg.get("type") == "pong", str(msg))

        await ws.send(json.dumps({"type": "reset"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        check("reset returns a new session", msg.get("type") == "ready", str(msg))

    srv.should_exit = True
    await task

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {', '.join(failures)}")
        return 1
    print("ALL SERVE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
