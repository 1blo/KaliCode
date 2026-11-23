"""Tool registry - the exact Claude Code 2.1.x built-in set (+ deferred MCP tools)."""
from __future__ import annotations

import os

from .base import Tool, ToolResult, ToolContext
from .shell import Bash, TaskStop
from .files import Read, Write, Edit, NotebookEdit
from .search import Glob, Grep
from .web import WebFetch, WebSearch
from .todo import TaskCreate, TaskGet, TaskList, TaskUpdate, TodoWrite
from .task import Agent, BUILTIN_AGENTS
from .user import AskUserQuestion
from .plan import EnterPlanMode, ExitPlanMode
from .skill_tool import Skill
from .toolsearch import ToolSearch


def default_tools() -> dict[str, Tool]:
    """The built-in toolset, matching Claude Code 2.1.x order and naming.

    TodoWrite is disabled by default (Claude Code 2.1.x behavior); it is only
    registered when KALI_CODE_ENABLE_TASKS=0, mirroring Claude Code's
    CLAUDE_CODE_ENABLE_TASKS=0.
    """
    tools: list[Tool] = [
        Bash(), TaskStop(),
        Read(), Edit(), Write(),
        Glob(), Grep(),
        NotebookEdit(),
        WebFetch(), WebSearch(),
        TaskCreate(), TaskGet(), TaskList(), TaskUpdate(),
        Agent(),
        AskUserQuestion(),
        EnterPlanMode(), ExitPlanMode(),
        Skill(),
        ToolSearch(),
    ]
    if os.environ.get("KALI_CODE_ENABLE_TASKS") == "0":
        tools.append(TodoWrite())
    return {t.name: t for t in tools}


# Names Claude Code treats specially
PLAN_BLOCKED_TOOLS = {"Edit", "Write", "NotebookEdit", "Bash"}  # Bash filtered per-command in plan mode

SAFE_READONLY = {"Read", "Glob", "Grep", "TaskList", "TaskGet", "AskUserQuestion", "EnterPlanMode"}

__all__ = [
    "Tool", "ToolResult", "ToolContext", "default_tools", "BUILTIN_AGENTS",
    "PLAN_BLOCKED_TOOLS", "SAFE_READONLY",
    "Bash", "TaskStop", "Read", "Edit", "Write", "Glob", "Grep",
    "NotebookEdit", "WebFetch", "WebSearch", "TaskCreate", "TaskGet",
    "TaskList", "TaskUpdate", "TodoWrite", "Agent",
    "AskUserQuestion", "EnterPlanMode", "ExitPlanMode", "Skill", "ToolSearch",
]
