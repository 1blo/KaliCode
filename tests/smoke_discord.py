"""Test the Discord presence end-to-end with the real settings."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kali.config import load_settings
from kali.discord_presence import DiscordPresence, load_config


async def main() -> int:
    settings = load_settings()
    cfg = load_config(settings)
    print("config:", cfg)

    p = DiscordPresence(cfg)
    ok = p.start()
    print("start ->", ok, "| error:", p.last_error or "(none)")
    if not ok:
        return 1

    p.set_title("Fixing the streaming bug")
    await asyncio.sleep(0.5)
    print("activity:", p.build_activity())

    p.set_activity("Running Bash")
    await asyncio.sleep(0.5)
    print("activity (busy):", p.build_activity())

    p.set_activity("")
    await asyncio.sleep(2)
    print("final:", p.build_activity())
    p.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
