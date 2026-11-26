"""Verify the mobile permission-prompt path.

This is the regression test for the deadlock: the agent parks on a permission
prompt while the server's receive loop must stay free to read the phone's
reply. The test asks the agent to run a harmless command, expects a
`permission` frame, approves it from the "phone", and checks the turn
completes.

Run:  python tests/smoke_serve_permission.py
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

TOKEN = "perm-token"


async def main() -> int:
    from kali.config import resolve_api_key

    if not resolve_api_key():
        print("SKIP - no API key configured")
        return 0

    app, server = build_app(token=TOKEN, cwd=os.getcwd())
    config = uvicorn.Config(app, host="127.0.0.1", port=8767, log_level="warning")
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

    saw_permission = False
    saw_done = False
    perm_name = ""
    final_text = ""
    saw_tool_start = False

    try:
        async with websockets.connect("ws://127.0.0.1:8767/ws") as ws:
            await ws.send(json.dumps({"type": "hello", "token": TOKEN}))
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
            check("connected", msg.get("type") == "ready", str(msg))

            # Ask for something that definitely needs a Bash permission.
            await ws.send(json.dumps({
                "type": "prompt",
                "text": "Run the shell command `echo KALI_PERM_OK` using the Bash tool, "
                        "then tell me what it printed.",
            }))

            deadline = asyncio.get_running_loop().time() + 240
            while asyncio.get_running_loop().time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                m = json.loads(raw)
                t = m.get("type")

                if t == "permission":
                    saw_permission = True
                    perm_name = m.get("name", "")
                    check("permission frame names the tool", bool(perm_name), str(m))
                    check("permission frame carries the command",
                          bool(m.get("summary")), str(m))
                    # Approve from the phone.
                    await ws.send(json.dumps({"type": "reply", "id": m.get("id"),
                                              "answer": "allow"}))
                elif t == "tool_start":
                    saw_tool_start = True
                elif t == "tool_result":
                    check("tool ran after approval", True)
                elif t == "done":
                    saw_done = True
                    final_text = m.get("text", "")
                    break
                elif t == "error":
                    print(f"  ..   server error: {m.get('message')}")
                    break

            check("a permission prompt was raised", saw_permission,
                  "the agent did not ask for permission")
            check("the tool was announced", saw_tool_start)
            check("the turn completed (no deadlock)", saw_done)
            check("the reply mentions the output",
                  "KALI_PERM_OK" in final_text, repr(final_text[:300]))
    finally:
        srv.should_exit = True
        await task

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {', '.join(failures)}")
        return 1
    print("ALL PERMISSION TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
