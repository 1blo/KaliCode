"""Hooks - Claude Code-compatible lifecycle hooks driven from settings.json.

Events: PreToolUse, PostToolUse, UserPromptSubmit, Notification, Stop,
SubagentStop, SessionStart, SessionEnd, PreCompact.
Config shape:
  "hooks": {"PreToolUse": [{"matcher": "Bash|Edit", "hooks": [{"type": "command", "command": "..."}]}]}
Hook stdin JSON mirrors Claude Code's shape. Exit code 2 => blocking error (stderr fed to model);
JSON output {"decision": "block"|"approve", "reason": ...} respected.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

EVENTS = [
    "PreToolUse", "PostToolUse", "UserPromptSubmit", "Notification", "Stop",
    "SubagentStop", "SessionStart", "SessionEnd", "PreCompact",
]


class HookEngine:
    def __init__(self, settings: dict):
        cfg = settings.get("hooks") or {}
        self.rules: dict[str, list[dict]] = {
            ev: list(cfg.get(ev) or []) for ev in EVENTS
        }

    @property
    def has_hooks(self) -> bool:
        return any(self.rules.values())

    async def emit(self, event: str, payload: dict) -> dict | None:
        """Run matching hooks; return a combined decision dict or None."""
        results: list[dict] = []
        for rule in self.rules.get(event, []):
            matcher = rule.get("matcher")
            if matcher and not _matches(matcher, payload):
                continue
            for hook in rule.get("hooks", []):
                if hook.get("type") != "command":
                    continue
                res = await self._run_command(hook["command"], event, payload)
                if res is not None:
                    results.append(res)
        if not results:
            return None
        combined: dict = {}
        for r in results:
            if r.get("decision") == "block" or r.get("permissionDecision") == "deny":
                combined["decision"] = "block"
                combined["reason"] = r.get("reason") or "blocked by hook"
            elif r.get("decision") == "approve" or r.get("permissionDecision") == "allow":
                combined.setdefault("decision", "approve")
                combined["reason"] = r.get("reason", "")
            elif r.get("continue") is False:
                combined["stop"] = True
                combined["stopReason"] = r.get("stopReason", "hook requested stop")
        return combined or None

    async def _run_command(self, command: str, event: str, payload: dict) -> dict | None:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "KALI_EVENT": event},
            )
            try:
                out, err = await asyncio.wait_for(
                    proc.communicate(json.dumps(payload).encode()), timeout=60
                )
            except asyncio.TimeoutError:
                proc.kill()
                return None
        except OSError:
            return None

        if proc.returncode == 2:
            return {"decision": "block", "reason": err.decode("utf-8", "replace")[:2000]}
        if proc.returncode != 0:
            return None
        stdout = out.decode("utf-8", "replace").strip()
        if not stdout:
            return None
        try:
            parsed = json.loads(stdout)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None


def _matches(matcher: str, payload: dict) -> bool:
    target = payload.get("tool_name", "")
    if matcher in ("*", ""):
        return True
    return any(fnmatch(target, pat.strip()) for pat in matcher.split("|"))
