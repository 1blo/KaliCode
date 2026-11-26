"""Smoke test for the session-based server.

Exercises:
  - GET /health
  - GET / (UI shell routing)
  - GET static assets
  - REST: /api/sessions list / create / get / archive
  - WebSocket handshake with a WRONG token (must be rejected)
  - WebSocket handshake with the RIGHT token (must be accepted, new session)
  - hello selecting an existing session
  - new_session / switch_session / set_model / set_mode / rename / sessions
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


async def recv_until(ws, wanted: set[str], timeout: float = 15.0):
    """Read messages until one of `wanted` arrives (or timeout)."""
    deadline = asyncio.get_running_loop().time() + timeout
    seen = []
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"none of {wanted} arrived; saw {seen}")
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        msg = json.loads(raw)
        seen.append(msg.get("type"))
        if msg.get("type") in wanted:
            return msg


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
        check("a UI shell served", "Kali Code" in r.text and "app.js" in r.text)

        for asset in ("/manifest.json", "/app.js", "/icon.svg", "/sw.js",
                      "/icon-192.png", "/icon-512.png"):
            r = await c.get(base + asset)
            check(f"GET {asset} -> 200", r.status_code == 200, str(r.status_code))

        r = await c.get(base + "/../pyproject.toml")
        check("path traversal blocked", r.status_code in (404, 400), str(r.status_code))

        # REST session list
        r = await c.get(base + "/api/sessions")
        check("GET /api/sessions -> 200", r.status_code == 200, r.text[:200])
        check("sessions is a list", isinstance(r.json().get("sessions"), list))

        # REST session create
        r = await c.post(base + "/api/sessions", json={"title": "REST made"})
        check("POST /api/sessions -> 200", r.status_code == 200, r.text[:200])
        rest_sid = (r.json().get("session") or {}).get("id", "")
        check("created session has an id", bool(rest_sid))

        if rest_sid:
            r = await c.get(base + f"/api/sessions/{rest_sid}")
            check("GET /api/sessions/{id} -> 200", r.status_code == 200)
            check("session title round-trips",
                  (r.json().get("session") or {}).get("title") == "REST made")

            r = await c.post(base + f"/api/sessions/{rest_sid}/archive")
            check("POST archive -> 200", r.status_code == 200)
            check("archive ok", r.json().get("ok") is True)

            r = await c.get(base + f"/api/sessions/{rest_sid}")
            check("archived session flagged",
                  (r.json().get("session") or {}).get("archived") is True)

    # ---- WebSocket: bad token ------------------------------------------
    try:
        async with websockets.connect("ws://127.0.0.1:8765/ws") as ws:
            await ws.send(json.dumps({"type": "hello", "token": "wrong"}))
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            check("bad token rejected", msg.get("type") == "error"
                  and "unauthorized" in str(msg.get("message", "")).lower(),
                  str(msg))
    except Exception as e:
        check("bad token rejected (connection closed)", True, str(e))

    # ---- WebSocket: good token -----------------------------------------
    async with websockets.connect("ws://127.0.0.1:8765/ws") as ws:
        await ws.send(json.dumps({"type": "hello", "token": TOKEN}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        check("good token accepted", msg.get("type") == "ready", str(msg))
        sid1 = msg.get("session", "")
        check("ready carries a session id", bool(sid1), str(msg))
        check("ready carries the model", bool(msg.get("model")), str(msg))
        check("ready carries cwd", bool(msg.get("cwd")), str(msg))
        check("ready carries the session list", isinstance(msg.get("sessions"), list))

        await ws.send(json.dumps({"type": "ping"}))
        msg = await recv_until(ws, {"pong"})
        check("ping -> pong", msg.get("type") == "pong", str(msg))

        # new session
        await ws.send(json.dumps({"type": "new_session", "title": "Second"}))
        msg = await recv_until(ws, {"ready"})
        sid2 = msg.get("session", "")
        check("new_session returns a ready", msg.get("type") == "ready", str(msg))
        check("new_session has a different id", sid2 and sid2 != sid1,
              f"{sid1} vs {sid2}")

        # switch back
        await ws.send(json.dumps({"type": "switch_session", "session": sid1}))
        msg = await recv_until(ws, {"ready"})
        check("switch_session returns the target", msg.get("session") == sid1, str(msg))

        # set_model
        model = (msg.get("sessions") and "stepfun-ai/step-5-preview") or "stepfun-ai/step-5-preview"
        await ws.send(json.dumps({"type": "set_model", "model": model}))
        msg = await recv_until(ws, {"session_meta", "error"})
        check("set_model -> session_meta", msg.get("type") == "session_meta", str(msg))
        # The session object travels in "meta"; "session" holds the id.
        meta = msg.get("meta") or {}
        check("session_meta carries the session id",
              msg.get("session") == sid1, str(msg))
        check("model applied", meta.get("model") == model, str(msg))

        await ws.send(json.dumps({"type": "set_model", "model": "not-a-model"}))
        msg = await recv_until(ws, {"session_meta", "error"})
        check("unknown model rejected", msg.get("type") == "error", str(msg))

        # set_mode
        await ws.send(json.dumps({"type": "set_mode", "mode": "plan"}))
        msg = await recv_until(ws, {"session_meta", "error"})
        check("set_mode -> session_meta", msg.get("type") == "session_meta", str(msg))
        check("mode applied",
              (msg.get("meta") or {}).get("permissionMode") == "plan", str(msg))

        await ws.send(json.dumps({"type": "set_mode", "mode": "nonsense"}))
        msg = await recv_until(ws, {"session_meta", "error"})
        check("unknown mode rejected", msg.get("type") == "error", str(msg))

        # rename
        await ws.send(json.dumps({"type": "rename", "title": "Renamed"}))
        msg = await recv_until(ws, {"session_meta", "error"})
        check("rename -> session_meta", msg.get("type") == "session_meta", str(msg))
        check("title applied",
              (msg.get("meta") or {}).get("title") == "Renamed", str(msg))

        # sessions listing over ws
        await ws.send(json.dumps({"type": "sessions"}))
        msg = await recv_until(ws, {"sessions"})
        check("sessions message", msg.get("type") == "sessions", str(msg))
        check("session list non-empty", len(msg.get("sessions") or []) > 0)

        # reconnect with an existing session id
    async with websockets.connect("ws://127.0.0.1:8765/ws") as ws:
        await ws.send(json.dumps({"type": "hello", "token": TOKEN, "session": sid1}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        check("hello selects an existing session", msg.get("session") == sid1, str(msg))

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
