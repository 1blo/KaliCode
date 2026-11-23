"""Skill - invokes a loaded skill (Claude Code's progressive-disclosure system)."""
from __future__ import annotations

from .base import Tool, ToolResult, ToolContext, STR, _s


class Skill(Tool):
    name = "Skill"
    # Verbatim from the Sonnet 4.6 CLI leak (spec section 2.1).
    description = """Invoke a skill.

A skill is a packaged set of instructions the user or project has set up for a particular kind of task (deploy steps, a review checklist, a repo-specific workflow). Available skills appear in a system-reminder listing with one-line descriptions. When the task at hand is one a listed skill covers, call this tool first - the skill's instructions load into the turn for you to follow in place of your default approach; some skills instead run in a subagent and return the finished result. A skill that runs in the background returns only the agent's name - its result arrives later as a task notification, so don't wait on it or invoke it again in the meantime. Users may also ask for one by name (`/<name>`, or "slash command"); that's a request to invoke it.

- `skill`: exact name from the listing, no leading slash. Plugin skills use `plugin:skill`. Directory-scoped skills are listed with a path prefix (`apps/web:deploy`); when both scoped and unscoped variants of a name exist, pick the one whose directory contains the files you're working on (most specific wins; unscoped otherwise).
- `args`: optional arguments to pass through.

Only names from the listing (or that the user typed explicitly) are valid. Built-in CLI commands (`/help`, `/clear`, ...) aren't skills. If a `<command-name>` block is already present this turn, the skill is loaded - follow it directly rather than calling again."""
    schema = _s(
        {
            "skill": {**STR, "description": "The name of a skill from the available-skills list. Do not guess names."},
            "args": {**STR, "description": "Optional arguments for the skill"},
        },
        required=["skill"],
    )

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        name = args.get("skill", "")
        skill = ctx.agent.skills.get(name)
        if skill is None:
            available = ", ".join(sorted(ctx.agent.skills)) or "(none)"
            return ToolResult(f"Unknown skill: {name}. Available: {available}", error=True)
        content = ctx.agent.skills.render(name, args.get("args"))
        ctx.agent.loaded_skills.add(name)
        return ToolResult(content, system=f"Skill '{name}' loaded. Follow its instructions for this task.")
