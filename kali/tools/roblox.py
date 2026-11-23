"""Roblox publishing tools - build a Rojo project and publish it via Open Cloud.

These are opt-in: they are only registered when Roblox credentials are present
(or when KALI_ENABLE_ROBLOX=1), so a normal install behaves exactly as before.
"""
from __future__ import annotations

import os

from .base import Tool, ToolResult, ToolContext, _s, STR, BOOL


class RobloxPublish(Tool):
    name = "RobloxPublish"
    description = (
        "Build the current Rojo project and publish it to Roblox via the Open Cloud "
        "Place Publishing API. Uses `rojo build` to produce a .rbxl place file, then "
        "uploads it to the configured universe/place. Requires ROBLOX_API_KEY, "
        "ROBLOX_UNIVERSE_ID and ROBLOX_PLACE_ID to be set. Returns the new version "
        "number on success."
    )
    schema = _s(
        {
            "commit": {
                "type": "boolean",
                "description": "Commit and push any pending changes before building. Default true.",
            },
            "message": {
                "type": "string",
                "description": "Commit message to use when committing changes.",
            },
            "saved_only": {
                "type": "boolean",
                "description": "Save the version without publishing it to players. Default false.",
            },
        },
    )
    read_only = False

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        from .. import roblox

        if args.get("commit", True):
            msg = str(args.get("message") or "Kali Code: update")
            ok, out = roblox.git_sync(message=msg)
            if not ok:
                return ToolResult(
                    f"git sync failed before build:\n{out[:2000]}", error=True)

        result = await roblox.publish(unpublished=bool(args.get("saved_only", False)))
        if not result.ok:
            text = result.message
            if result.detail:
                text += "\n\n" + result.detail
            return ToolResult(text, error=True)

        link = roblox.game_link(result.universe_id)
        text = result.message
        if result.version:
            text += f"\nVersion: {result.version}"
        if link:
            text += f"\nGame: {link}"
        if result.detail:
            text += "\n" + result.detail
        return ToolResult(text)


class RobloxStatus(Tool):
    name = "RobloxStatus"
    description = (
        "Show the Roblox publishing configuration and whether the required tools and "
        "credentials are available. Read-only; does not contact Roblox."
    )
    schema = _s({})
    read_only = True

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        from .. import roblox

        key, universe, place = roblox.get_credentials()
        rojo = roblox.rojo_binary()
        proj = roblox.find_rojo_project()

        lines = ["Roblox publish configuration:"]
        lines.append(f"  API key:      {'set' if key else 'MISSING (ROBLOX_API_KEY)'}")
        lines.append(f"  Universe ID:  {universe if universe else 'MISSING (ROBLOX_UNIVERSE_ID)'}")
        lines.append(f"  Place ID:     {place if place else 'MISSING (ROBLOX_PLACE_ID)'}")
        lines.append(f"  Rojo binary:  {rojo or 'MISSING (install rojo)'}")
        lines.append(f"  Project dir:  {roblox.project_dir()}")
        lines.append(f"  Rojo project: {proj or 'MISSING (no default.project.json found)'}")

        if universe:
            lines.append(f"  Game link:    https://www.roblox.com/games/{universe}/")

        ready = bool(key and universe and place and rojo and proj)
        lines.append("")
        lines.append("Ready to publish." if ready
                     else "Not ready - fix the MISSING items above first.")
        return ToolResult("\n".join(lines))


def roblox_tools() -> list[Tool]:
    """Return the Roblox tools if they should be enabled."""
    from .. import roblox

    forced = os.environ.get("KALI_ENABLE_ROBLOX") == "1"
    if forced:
        return [RobloxPublish(), RobloxStatus()]
    if os.environ.get("KALI_ENABLE_ROBLOX") == "0":
        return []
    # Auto-enable when the environment is configured.
    if roblox.is_configured():
        return [RobloxPublish(), RobloxStatus()]
    return []
