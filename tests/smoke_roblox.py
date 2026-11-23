"""Smoke test for the Roblox publishing pipeline.

Builds a tiny Rojo project (no network), verifies:
  - the project is discovered
  - `rojo build` produces a place file   (skipped if rojo is not installed)
  - credentials are resolved from env/settings
  - the publish endpoint is constructed correctly and rejects a bad key
    with the expected status code (uses the real API, but with a garbage key,
    so it can only ever fail with 401 - it never publishes anything)

Run:  python tests/smoke_roblox.py
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kali import roblox

PROJECT_JSON = {
    "name": "SmokeTestGame",
    "tree": {
        "$className": "DataModel",
        "ServerScriptService": {
            "$className": "ServerScriptService",
            "Main": {"$path": "src/server"},
        },
        "ReplicatedStorage": {
            "$className": "ReplicatedStorage",
            "Shared": {"$path": "src/shared"},
        },
    },
}

SERVER_LUA = """--!strict
local Players = game:GetService("Players")

local function onPlayerAdded(player: Player)
    print("joined:", player.Name)
end

Players.PlayerAdded:Connect(onPlayerAdded)
"""

SHARED_LUA = """--!strict
local Config = {
    speed = 16,
}

return Config
"""


def make_project(root: Path) -> Path:
    (root / "src" / "server").mkdir(parents=True, exist_ok=True)
    (root / "src" / "shared").mkdir(parents=True, exist_ok=True)
    (root / "default.project.json").write_text(json.dumps(PROJECT_JSON, indent=2), "utf-8")
    (root / "src" / "server" / "Main.server.lua").write_text(SERVER_LUA, "utf-8")
    (root / "src" / "shared" / "Config.lua").write_text(SHARED_LUA, "utf-8")
    return root


async def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if cond:
            print(f"  ok   {name}")
        else:
            print(f"  FAIL {name} {detail}")
            failures.append(name)

    tmp = Path(tempfile.mkdtemp(prefix="kali-roblox-"))
    try:
        proj = make_project(tmp / "game")

        # ---- project discovery ------------------------------------------
        found = roblox.find_rojo_project(tmp)
        check("finds the Rojo project", found is not None and found.name == "game",
              str(found))

        # ---- credentials ------------------------------------------------
        os.environ["ROBLOX_API_KEY"] = "test-key-not-real"
        os.environ["ROBLOX_UNIVERSE_ID"] = "123456"
        os.environ["ROBLOX_PLACE_ID"] = "789012"
        key, universe, place = roblox.get_credentials()
        check("resolves the API key", key == "test-key-not-real", key)
        check("resolves the universe id", universe == 123456, str(universe))
        check("resolves the place id", place == 789012, str(place))
        check("is_configured() is true", roblox.is_configured())

        # ---- build (needs rojo) ------------------------------------------
        rojo = roblox.rojo_binary()
        if not rojo:
            print("  skip rojo build - rojo is not installed")
            print("       install: https://github.com/rojo-rbx/rojo/releases")
        else:
            print(f"  ..   rojo: {rojo}")
            os.environ["ROBLOX_PROJECT_DIR"] = str(proj)
            try:
                out = await roblox.build_place(project=proj, binary=True)
                check("rojo build produced a .rbxl", out.exists() and out.suffix == ".rbxl",
                      str(out))
                check("built file is non-empty", out.exists() and out.stat().st_size > 0,
                      str(out.stat().st_size if out.exists() else 0))
            except roblox.RobloxError as e:
                check("rojo build succeeded", False, str(e)[:400])

        # ---- publish against a bogus key (must be 401, never a publish) --
        bogus_file = proj / "fake.rbxl"
        bogus_file.write_bytes(b"\x00" * 16)
        res = await roblox.publish_place(
            bogus_file, 123456, 789012, "definitely-not-a-real-key")
        check("bogus key is rejected", not res.ok, res.message)
        check("rejection mentions the status code", "401" in res.message or "403" in res.message,
              res.message[:200])
        check("rejection includes a hint", bool(res.detail), res.detail[:200])

        # ---- missing place file is a clean error, not a crash -----------
        res = await roblox.publish_place(
            proj / "does-not-exist.rbxl", 123456, 789012, "k")
        check("missing place file is handled", not res.ok and "not found" in res.message.lower(),
              res.message)

        # ---- missing credential handling --------------------------------
        # publish() reports the first missing credential; check each one.
        os.environ["ROBLOX_API_KEY"] = ""
        os.environ["ROBLOX_UNIVERSE_ID"] = "123456"
        os.environ["ROBLOX_PLACE_ID"] = "789012"
        res = await roblox.publish()
        check("missing API key is reported",
              not res.ok and "API_KEY" in res.message.upper(), res.message)

        os.environ["ROBLOX_API_KEY"] = "test-key-not-real"
        os.environ["ROBLOX_UNIVERSE_ID"] = ""
        os.environ["ROBLOX_PLACE_ID"] = "789012"
        res = await roblox.publish()
        check("missing universe id is reported",
              not res.ok and "UNIVERSE" in res.message.upper(), res.message)

        os.environ["ROBLOX_UNIVERSE_ID"] = "123456"
        os.environ["ROBLOX_PLACE_ID"] = ""
        res = await roblox.publish()
        check("missing place id is reported",
              not res.ok and "PLACE" in res.message.upper(), res.message)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        for k in ("ROBLOX_API_KEY", "ROBLOX_UNIVERSE_ID", "ROBLOX_PLACE_ID",
                  "ROBLOX_PROJECT_DIR"):
            os.environ.pop(k, None)

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {', '.join(failures)}")
        return 1
    print("ALL ROBLOX TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
