"""End-to-end test of the mobile companion with a REAL model call.

Starts the server, connects over WebSocket, sends a prompt, and waits for the
agent to answer. Verifies the full protocol path: text streaming, tool events,
and the `done` frame.

Run:  python tests/smoke_serve_e2e.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn
import websockets

from kali.serve import build_app

TOKEN = "e2e-token"


async def main() -> int:
    from kali.config import resolve_api_key

    if not resolve_api_key():
        print("SKIP - no API key configured")
        return 0

    app, server = build_app(token=TOKEN, cwd=os.getcwd())
    config = uvicorn.Config(app, host="127.0.0.1", port=8766, log_level="warning")
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

    saw_text = False
    saw_done = False
    final_text = ""
    tool_names: list[str] = []

    try:
        async with websockets.connect("ws://127.0.0.1:8766/ws") as ws:
            await ws.send(json.dumps({"type": "hello", "token": TOKEN}))
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
            check("connected", msg.get("type") == "ready", str(msg))

            await ws.send(json.dumps({"type": "prompt",
                                      "text": "Reply with exactly: MOBILE_OK"}))

            # Poll with a short timeout rather than one long wait: cancelling a
            # pending recv() can corrupt the websockets connection state.
            deadline = asyncio.get_running_loop().time() + 180
            while asyncio.get_running_loop().time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                m = json.loads(raw)
                t = m.get("type")
                if t == "text":
                    saw_text = True
                elif t == "tool_start":
                    tool_names.append(m.get("name", ""))
                elif t == "tool_denied":
                    tool_names.append("denied:" + m.get("name", ""))
                elif t == "permission":
                    # The phone must be able to unblock the turn - this is the
                    # path that used to deadlock.
                    tool_names.append("permission:" + m.get("name", ""))
                    await ws.send(json.dumps({"type": "reply", "id": m.get("id"),
                                              "answer": "allow"}))
                elif t == "question":
                    await ws.send(json.dumps({"type": "answer", "id": m.get("id"),
                                              "value": "test"}))
                elif t == "plan":
                    await ws.send(json.dumps({"type": "reply", "id": m.get("id"),
                                              "answer": "approve"}))
                elif t == "done":
                    saw_done = True
                    final_text = m.get("text", "")
                    break
                elif t == "error":
                    print(f"  ..   server error: {m.get('message')}")
                    break

            check("received a text delta", saw_text)
            check("received the done frame", saw_done)
            check("reply contains the expected token", "MOBILE_OK" in final_text,
                  repr(final_text[:200]))
            if tool_names:
                print(f"  ..   tools used: {', '.join(tool_names)}")
    finally:
        srv.should_exit = True
        await task

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {', '.join(failures)}")
        return 1
    print("ALL SERVE E2E TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
