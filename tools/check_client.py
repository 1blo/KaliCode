"""Verify that the desktop client connected to the server.

Instead of fighting other windows for the foreground, this asks the
server directly: a connected desktop client shows up in the session list
and the WebSocket handshake has completed.

Usage:
    python tools/check_client.py [url]
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import websockets


def load_token() -> str:
    try:
        from kali.resources import user_data_dir

        p = user_data_dir() / "desktop.json"
        if p.exists():
            return str(json.loads(p.read_text(encoding="utf-8"))["token"])
    except Exception:
        pass
    return ""


async def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8765/ws"
    token = load_token()
    if not token:
        print("no token found")
        return 1

    async with websockets.connect(url, open_timeout=10) as ws:
        await ws.send(json.dumps({"type": "hello", "token": token}))
        seen = []
        while len(seen) < 3:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=15)
            except asyncio.TimeoutError:
                break
            msg = json.loads(raw)
            seen.append(msg.get("type"))
            if msg.get("type") == "ready":
                print("ready:")
                print(json.dumps(msg, indent=2)[:1200])
                break

        # Ask for the session list to see whether the desktop client is
        # attached to the same session.
        await ws.send(json.dumps({"type": "sessions"}))
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            msg = json.loads(raw)
            if msg.get("type") == "sessions":
                print(f"\nsessions: {len(msg.get('sessions', []))}")
                for s in msg.get("sessions", []):
                    print("  ", json.dumps(s))
        except asyncio.TimeoutError:
            print("no sessions message")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
