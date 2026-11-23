"""Permissions - Claude Code's rule model: modes, allow/ask/deny lists, interactive prompts.

Rule syntax (same as Claude Code):
  "Bash"                  -> any Bash command
  "Bash(npm run *)"       -> commands starting with `npm run `
  "Edit(docs/**)"         -> edits inside docs/
  "Read(~/.zshrc)"        -> specific file
  "WebFetch(domain:api.github.com)" -> that domain
  "mcp__github"           -> whole MCP server; "mcp__github__create_issue" -> one tool
Modes: default | acceptEdits | plan | bypassPermissions ("dangerously skip")
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Decision:
    behavior: str  # "allow" | "deny" | "ask"
    reason: str = ""
    updated_input: dict | None = None


def _rule_parts(rule: str) -> tuple[str, str | None]:
    rule = rule.strip()
    m = re.match(r"^([A-Za-z_][\w]*|mcp__[\w.-]+(?:__[\w.-]+)?)\s*\((.*)\)\s*$", rule)
    if m:
        return m.group(1), m.group(2)
    return rule, None


def _match_content(rule_content: str, actual: str) -> bool:
    """Prefix-with-wildcard matching like Bash(npm run *)."""
    rule_content = rule_content.strip()
    actual = actual.strip()
    if rule_content == "*":
        return True
    if "*" in rule_content or "?" in rule_content:
        if fnmatch.fnmatch(actual, rule_content):
            return True
        # "git status *" should also match the bare command "git status".
        # The trailing wildcard implies "the prefix and anything after it".
        prefix = rule_content.rstrip("*").rstrip("?").rstrip()
        if prefix and actual == prefix:
            return True
        if prefix and actual.startswith(prefix + " "):
            return True
        return False
    return actual == rule_content or actual.startswith(rule_content)


class PermissionManager:
    def __init__(self, settings: dict, mode: str = "default", cli_allow: list[str] | None = None,
                 cli_deny: list[str] | None = None):
        perms = settings.get("permissions") or {}
        self.allow: list[str] = list(perms.get("allow") or []) + list(cli_allow or [])
        self.ask: list[str] = list(perms.get("ask") or [])
        self.deny: list[str] = list(perms.get("deny") or []) + list(cli_deny or [])
        self.mode = mode
        # persisted "don't ask again" additions land here
        self.session_allow: list[str] = []
        # When True every tool call is auto-approved (set by /alwaysallow).
        self.allow_all: bool = False

    # ------------------------------------------------------------------ core
    def check(self, tool_name: str, args: dict, tool_meta: "object" = None) -> Decision:
        """Decide allow/deny/ask for a tool call."""
        if self.allow_all:
            return Decision("allow", "always allow is enabled")
        if self.mode == "bypassPermissions":
            return Decision("allow")

        for rule in self.deny:
            if self._matches(rule, tool_name, args):
                return Decision("deny", f"denied by settings deny rule: {rule}")

        for rule in [*self.session_allow, *self.allow]:
            if self._matches(rule, tool_name, args):
                return Decision("allow", f"allowed by rule: {rule}")

        if self.mode == "acceptEdits" and tool_meta is not None and getattr(tool_meta, "is_edit", False):
            return Decision("allow", "acceptEdits mode")

        if tool_meta is not None and getattr(tool_meta, "read_only", False):
            return Decision("allow", "read-only tool")

        if self.mode == "plan":
            if tool_name in {"Edit", "Write", "NotebookEdit"}:
                return Decision("deny", "plan mode: editing is not allowed until the plan is approved")
            if tool_name == "Bash":
                cmd = str(args.get("command", "")).strip()
                if _is_safe_plan_command(cmd):
                    return Decision("allow", "plan mode: read-only command")
                return Decision("deny", "plan mode: only read-only commands are allowed before plan approval")

        if tool_name in {"TaskCreate", "TaskGet", "TaskList", "TaskUpdate", "TaskStop",
                         "ExitPlanMode", "EnterPlanMode", "AskUserQuestion", "Agent",
                         "Skill", "ToolSearch", "Read", "Glob", "Grep", "TodoWrite"}:
            return Decision("allow")

        return Decision("ask")

    def _matches(self, rule: str, tool_name: str, args: dict) -> bool:
        base, content = _rule_parts(rule)
        if base != tool_name:
            return False
        if content is None:
            return True
        if tool_name == "Bash":
            return _match_content(content, str(args.get("command", "")))
        if tool_name in ("Edit", "Write", "Read", "NotebookEdit"):
            return _match_path_rule(content, str(args.get("file_path") or args.get("notebook_path") or ""))
        if tool_name == "WebFetch":
            if content.startswith("domain:"):
                domain = content[len("domain:"):].strip()
                url = str(args.get("url", ""))
                return domain in url
        if tool_name == "WebSearch":
            return True
        return True

    # -------------------------------------------------------------- persist
    def remember_allow(self, tool_name: str, args: dict, scope: str = "user") -> None:
        """Persist a 'Yes, don't ask again' choice into the user settings."""
        rule = _rule_for(tool_name, args)
        if not rule or rule in self.allow or rule in self.session_allow:
            return
        self.session_allow.append(rule)
        _update_user_settings({"permissions": {"allow": [rule]}}, append_allow=True)

    # ----------------------------------------------------------- /alwaysallow
    def always_allow(self, pattern: str = "", scope: str = "user") -> str:
        """Allow every command (no pattern) or a specific command pattern.

        With no pattern this enables a session-wide bypass equivalent to
        Claude Code's "always allow" on a catch-all rule. The bypass is
        persisted to the *user* settings so it applies to every project.

        With a pattern (e.g. "git status") a `Bash(pattern *)` rule is added
        so that matching commands never prompt again.

        Returns a human-readable confirmation line.
        """
        pattern = (pattern or "").strip()
        if not pattern:
            self.allow_all = True
            self.mode = "bypassPermissions"
            _update_user_settings({"permissionMode": "bypassPermissions"})
            return "Always allow enabled - every command is now auto-approved."

        # A pattern like "git status" becomes the rule "Bash(git status *)".
        rule = f"Bash({pattern} *)"
        if pattern.endswith("*"):
            rule = f"Bash({pattern})"
        if rule not in self.allow and rule not in self.session_allow:
            self.session_allow.append(rule)
            _update_user_settings({"permissions": {"allow": [rule]}}, append_allow=True)
        return f"Always allow enabled for: {pattern}"


def _update_user_settings(patch: dict, append_allow: bool = False) -> None:
    """Read-modify-write ONLY the user settings file (~/.kali/settings.json).

    This deliberately avoids `config.save_settings(load_settings())`, which
    would write the *merged* settings (user + project) into a single file
    and pollute the user config with project-scoped values.

    `patch` is a shallow-merged dict of top-level keys. When
    `append_allow` is set, `patch["permissions"]["allow"]` entries are
    appended to the existing allow list instead of replacing it.
    """
    import json

    from .config import USER_DIR

    path = USER_DIR / "settings.json"
    current: dict = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8")) or {}
        except Exception:
            current = {}
    if not isinstance(current, dict):
        current = {}

    for key, value in patch.items():
        if append_allow and key == "permissions":
            perms = current.get("permissions")
            if not isinstance(perms, dict):
                perms = {}
            allow = list(perms.get("allow") or [])
            for rule in (value or {}).get("allow") or []:
                if rule not in allow:
                    allow.append(rule)
            perms["allow"] = allow
            current["permissions"] = perms
        else:
            current[key] = value

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")


def _rule_for(tool_name: str, args: dict) -> str | None:
    if tool_name == "Bash":
        cmd = str(args.get("command", "")).strip()
        # Save the head of the command as the rule (like Claude Code's prefix rules)
        head = re.split(r"\s*&&\s*|\s*;\s*|\s*\|\s*", cmd)[0].strip()
        parts = head.split(" ")
        prefix = " ".join(parts[:2]) if len(parts) > 1 else head
        return f"Bash({prefix} *)"
    if tool_name in ("Edit", "Write", "Read", "NotebookEdit"):
        p = str(args.get("file_path") or args.get("notebook_path") or "")
        return f"{tool_name}({p})" if p else None
    if tool_name in ("WebFetch", "WebSearch", "Agent"):
        return tool_name
    return tool_name


def _match_path_rule(rule: str, path: str) -> bool:
    rule = rule.replace("~", str(Path.home()))
    p = str(Path(path).expanduser().resolve()) if path else ""
    if "**" in rule or "*" in rule:
        base = rule.split("**")[0].rstrip("/\\")
        return p.startswith(str(Path(base).resolve())) if base else fnmatch.fnmatch(p, rule)
    try:
        return Path(p) == Path(rule).expanduser().resolve()
    except Exception:
        return p == rule


SAFE_PLAN_BASH = re.compile(
    r"^\s*(ls|dir|pwd|cat|type|head|tail|rg|findstr|git (status|log|diff|show|branch|rev-parse)|"
    r"gh (pr view|issue view|repo view)|echo|which|where|node --version|python --version|uv .*|--version)\b",
    re.I,
)


def _is_safe_plan_command(cmd: str) -> bool:
    return bool(SAFE_PLAN_BASH.match(cmd))
