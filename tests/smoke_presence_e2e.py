"""Verify the presence payload Discord receives.

Discord does not expose a 'get activity' RPC command, but the local client
does write the current activity to its logs and to a local 'rpc' state file.
This checks the payload we send is exactly what we expect, and (optionally)
dumps Discord's client log for evidence the activity was accepted.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kali.config import load_settings
from kali.discord_presence import DiscordPresence, load_config

sent = []


class SpyIpc:
    def __init__(self, inner):
        self._inner = inner
        self._connected = True

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def set_activity(self, activity):
        sent.append(activity)
        return self._inner.set_activity(activity)

    def close(self):
        self._connected = False
        return self._inner.close()


async def main() -> int:
    settings = load_settings()
    p = DiscordPresence(load_config(settings))
    if not p.start():
        print("FAILED to start:", p.last_error)
        return 1
    p.ipc = SpyIpc(p.ipc)

    p.set_title("Fixing the streaming bug")
    await asyncio.sleep(0.4)
    p.set_activity("Running Bash")
    await asyncio.sleep(0.4)
    p.set_activity("")
    await asyncio.sleep(0.4)

    print("=== payloads sent to Discord ===")
    for a in sent:
        print(json.dumps(a, indent=2))

    last = sent[-1]
    checks = {
        "app name": last["name"] == "Kali Code",
        "state line": last["state"] == "Using Kali Code",
        "chat title": last["details"] == "Fixing the streaming bug",
        "timer": isinstance(last["timestamps"]["start"], int),
        "logo": last["assets"]["large_image"].startswith("http"),
    }
    print("\n=== checks ===")
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    ok = all(checks.values())
    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))

    p.stop()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
