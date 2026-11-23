"""Task list tools - TaskCreate / TaskGet / TaskList / TaskUpdate.

Claude Code 2.1.x replaced the 1.x TodoWrite tool with this four-tool family,
sharing one task store on the agent (agent.tasks). The legacy TodoWrite tool is
kept at the bottom of this module for 1.x compatibility but is gated OFF by
default: it is only registered when KALI_CODE_ENABLE_TASKS=0, mirroring Claude
Code's CLAUDE_CODE_ENABLE_TASKS=0.
"""
from __future__ import annotations

import json

from .base import Tool, ToolResult, ToolContext, STR, _s

VALID_STATUSES = {"pending", "in_progress", "completed"}


# ---------------------------------------------------------------- store utils
def _store(ctx: ToolContext) -> list[dict]:
    return ctx.agent.tasks


def _next_id(tasks: list[dict]) -> str:
    return str(max((int(t["id"]) for t in tasks if str(t["id"]).isdigit()), default=0) + 1)


def _find(tasks: list[dict], task_id: str) -> dict | None:
    return next((t for t in tasks if str(t["id"]) == str(task_id)), None)


def _render_task(t: dict) -> str:
    deps = ""
    if t.get("blockedBy"):
        deps += f"  blockedBy: {', '.join(t['blockedBy'])}"
    if t.get("blocks"):
        deps += f"  blocks: {', '.join(t['blocks'])}"
    active = t.get("activeForm") or ""
    out = (f"#{t['id']} [{t['status']}] {t['subject']}{deps}")
    if t.get("description"):
        out += f"\n    {t['description']}"
    if active and t["status"] == "in_progress":
        out += f"\n    (active: {active})"
    return out


# ----------------------------------------------------------------- TaskCreate
class TaskCreate(Tool):
    name = "TaskCreate"
    description = """Use this tool to create a structured task list for your current coding session. This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user.
It also helps the user understand the progress of the task and overall progress of their requests.

### When to Use This Tool

Use this tool proactively in these scenarios:

- Complex multi-step tasks - When a task requires 3 or more distinct steps or actions
- Non-trivial and complex tasks - Tasks that require careful planning or multiple operations
- Plan mode - When using plan mode, create a task list to track the work
- User explicitly requests todo list - When the user directly asks you to use the todo list
- User provides multiple tasks - When users provide a list of things to be done (numbered or comma-separated)
- After receiving new instructions - Immediately capture user requirements as tasks
- When you start working on a task - Mark it as in_progress BEFORE beginning work
- After completing a task - Mark it as completed and add any new follow-up tasks discovered during implementation

### When NOT to Use This Tool

Skip using this tool when:
- There is only a single, straightforward task
- The task is trivial and tracking it provides no organizational benefit
- The task can be completed in less than 3 trivial steps
- The task is purely conversational or informational

NOTE that you should not use this tool if there is only one trivial task to do. In this case you are better off just doing the task directly.

### Task Fields

- **subject**: A brief, actionable title in imperative form (e.g., "Fix authentication bug in login flow")
- **description**: What needs to be done
- **activeForm** (optional): Present continuous form shown in the spinner when the task is in_progress (e.g., "Fixing authentication bug"). If omitted, the spinner shows the subject instead.

All tasks are created with status `pending`.

### Tips

- Create tasks with clear, specific subjects that describe the outcome
- After creating tasks, use TaskUpdate to set up dependencies (blocks/blockedBy) if needed
- Check TaskList first to avoid creating duplicate tasks"""
    schema = _s(
        {
            "subject": {**STR, "description": "A brief title for the task"},
            "description": {**STR, "description": "What needs to be done"},
            "activeForm": {**STR, "description": 'Present continuous form shown in spinner when in_progress (e.g., "Running tests")'},
            "metadata": {
                "description": "Arbitrary metadata to attach to the task",
                "type": "object",
                "propertyNames": {"type": "string"},
                "additionalProperties": {},
            },
        },
        required=["subject", "description"],
    )
    read_only = False

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        tasks = _store(ctx)
        # one or more tasks per call: the documented single-task form, plus an
        # undocumented batch form via a "tasks" array for convenience
        batch = args.get("tasks")
        items = batch if isinstance(batch, list) and batch else [args]
        created: list[dict] = []
        for item in items:
            task = {
                "id": _next_id(tasks),
                "subject": str(item.get("subject", "")),
                "description": str(item.get("description", "")),
                "activeForm": str(item.get("activeForm") or ""),
                "status": "pending",
                "owner": "",
                "metadata": dict(item.get("metadata") or {}),
                "blocks": [],
                "blockedBy": [],
            }
            tasks.append(task)
            created.append(task)
        lines = [f"Task {t['id']} created: {t['subject']}" for t in created]
        lines.append("All tasks start as pending. Use TaskUpdate to mark one in_progress before starting work.")
        return ToolResult("\n".join(lines))


# -------------------------------------------------------------------- TaskGet
class TaskGet(Tool):
    name = "TaskGet"
    description = """Use this tool to retrieve a task by its ID from the task list.

### When to Use This Tool

- When you need the full description and context before starting work on a task
- To understand task dependencies (what it blocks, what blocks it)
- After being assigned a task, to get complete requirements

### Output

Returns full task details:
- **subject**: Task title
- **description**: Detailed requirements and context
- **status**: 'pending', 'in_progress', or 'completed'
- **blocks**: Tasks waiting on this one to complete
- **blockedBy**: Tasks that must complete before this one can start

### Tips

- After fetching a task, verify its blockedBy list is empty before beginning work.
- Use TaskList to see all tasks in summary form."""
    schema = _s(
        {"taskId": {**STR, "description": "The ID of the task to retrieve"}},
        required=["taskId"],
    )
    read_only = True

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        task = _find(_store(ctx), str(args.get("taskId", "")))
        if task is None:
            return ToolResult(f"Task not found: {args.get('taskId')}", error=True)
        return ToolResult(json.dumps(task, ensure_ascii=False, indent=2))


# ------------------------------------------------------------------- TaskList
class TaskList(Tool):
    name = "TaskList"
    description = """Use this tool to list all tasks in the task list.

### When to Use This Tool

- To see what tasks are available to work on (status: 'pending', no owner, not blocked)
- To check overall progress on the project
- To find tasks that are blocked and need dependencies resolved
- After completing a task, to check for newly unblocked work or claim the next available task
- **Prefer working on tasks in ID order** (lowest ID first) when multiple tasks are available, as earlier tasks often set up context for later ones

### Output

Returns a summary of each task:
- **id**: Task identifier (use with TaskGet, TaskUpdate)
- **subject**: Brief description of the task
- **status**: 'pending', 'in_progress', or 'completed'
- **owner**: Agent ID if assigned, empty if available
- **blockedBy**: List of open task IDs that must be resolved first (tasks with blockedBy cannot be claimed until dependencies resolve)

Use TaskGet with a specific task ID to view full details including description and comments."""
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    read_only = True

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        tasks = _store(ctx)
        if not tasks:
            return ToolResult("No tasks in the task list.")
        return ToolResult("\n".join(_render_task(t) for t in tasks))


# ----------------------------------------------------------------- TaskUpdate
class TaskUpdate(Tool):
    name = "TaskUpdate"
    description = """Use this tool to update a task in the task list.

### When to Use This Tool

**Mark tasks as resolved:**
- When you have completed the work described in a task
- When a task is no longer needed or has been superseded
- IMPORTANT: Always mark your assigned tasks as resolved when you finish them
- After resolving, call TaskList to find your next task
- ONLY mark a task as completed when you have FULLY accomplished it
- If you encounter errors, blockers, or cannot finish, keep the task as in_progress
- When blocked, create a new task describing what needs to be resolved
- Never mark a task as completed if:
  - Tests are failing
  - Implementation is partial
  - You encountered unresolved errors
  - You couldn't find necessary files or dependencies

**Delete tasks:**
- When a task is no longer relevant or was created in error
- Setting status to `deleted` permanently removes the task

**Update task details:**
- When requirements change or become clearer
- When establishing dependencies between tasks

### Fields You Can Update

- **status**: The task status (see Status Workflow below)
- **subject**: Change the task title (imperative form, e.g., "Run tests")
- **description**: Change the task description
- **activeForm**: Present continuous form shown in spinner when in_progress (e.g., "Running tests")
- **owner**: Change the task owner (agent name)
- **metadata**: Merge metadata keys into the task (set a key to null to delete it)
- **addBlocks**: Mark tasks that cannot start until this one completes
- **addBlockedBy**: Mark tasks that must complete before this one can start

### Status Workflow

Status progresses: `pending` -> `in_progress` -> `completed`

Use `deleted` to permanently remove a task.

### Staleness

Make sure to read a task's latest state using `TaskGet` before updating it."""
    schema = _s(
        {
            "taskId": {**STR, "description": "The ID of the task to update"},
            "subject": {**STR, "description": "New subject for the task"},
            "description": {**STR, "description": "New description for the task"},
            "activeForm": {**STR, "description": 'Present continuous form shown in spinner when in_progress (e.g., "Running tests")'},
            "status": {
                "description": "New status for the task",
                "anyOf": [
                    {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                    {"type": "string", "const": "deleted"},
                ],
            },
            "addBlocks": {"description": "Task IDs that this task blocks", "type": "array", "items": {"type": "string"}},
            "addBlockedBy": {"description": "Task IDs that block this task", "type": "array", "items": {"type": "string"}},
            "owner": {**STR, "description": "New owner for the task"},
            "metadata": {
                "description": "Metadata keys to merge into the task. Set a key to null to delete it.",
                "type": "object",
                "propertyNames": {"type": "string"},
                "additionalProperties": {},
            },
        },
        required=["taskId"],
    )

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        tasks = _store(ctx)
        task = _find(tasks, str(args.get("taskId", "")))
        if task is None:
            return ToolResult(f"Task not found: {args.get('taskId')}", error=True)

        if "subject" in args:
            task["subject"] = str(args["subject"])
        if "description" in args:
            task["description"] = str(args["description"])
        if "activeForm" in args:
            task["activeForm"] = str(args["activeForm"] or "")
        if "owner" in args:
            task["owner"] = str(args["owner"] or "")
        if isinstance(args.get("metadata"), dict):
            meta = task.setdefault("metadata", {})
            for k, v in args["metadata"].items():
                if v is None:
                    meta.pop(k, None)
                else:
                    meta[k] = v

        for key in ("addBlocks", "addBlockedBy"):
            ids = args.get(key)
            if isinstance(ids, list):
                field = "blocks" if key == "addBlocks" else "blockedBy"
                for tid in ids:
                    tid = str(tid)
                    if _find(tasks, tid) is None:
                        return ToolResult(f"Unknown task id in {key}: {tid}", error=True)
                    if tid != str(task["id"]) and tid not in task[field]:
                        task[field].append(tid)

        status = args.get("status")
        if status is not None:
            status = str(status)
            if status == "deleted":
                tasks.remove(task)
                for other in tasks:
                    other["blocks"] = [i for i in other["blocks"] if i != str(task["id"])]
                    other["blockedBy"] = [i for i in other["blockedBy"] if i != str(task["id"])]
                return ToolResult(f"Task {task['id']} deleted.")
            if status not in VALID_STATUSES:
                return ToolResult(f"Invalid status: {status!r}", error=True)
            if status == "in_progress":
                others = [t for t in tasks if t["status"] == "in_progress" and t["id"] != task["id"]]
                if others:
                    other = others[0]
                    return ToolResult(
                        f"Cannot set task {task['id']} to in_progress: task #{other['id']} "
                        f"('{other['subject']}') is already in_progress. Exactly ONE task may be "
                        f"in_progress at a time - mark the current one completed (or pending) first, then retry.",
                        error=True,
                    )
            task["status"] = status

        return ToolResult(f"Updated task {task['id']} [{task['status']}] {task['subject']}")


# ---------------------------------------------------------------- legacy 1.x
class TodoWrite(Tool):
    """1.x-era TodoWrite, kept for compatibility; disabled by default (only
    registered when KALI_CODE_ENABLE_TASKS=0). Writes into the shared task
    store so the /tasks panel and TaskList stay consistent."""

    name = "TodoWrite"
    description = """Use this tool to create and manage a structured task list for the current session. It helps you track progress and gives the user visibility.

When to use: complex multi-step tasks (>3 distinct steps), the user provides multiple tasks, or after accepting a plan.
When NOT: single trivial task, pure conversation Q&A, simple one-liner questions.

Rules:
- Mark tasks completed IMMEDIATELY after finishing (no batching, no marking done prematurely).
- Exactly ONE task in_progress at a time; complete it before starting the next.
- Only mark completed when truly done - if you hit errors/blockers, keep it in_progress and add a new task describing the blocker.
- Remove tasks no longer relevant; rewrite the list if scope changes."""
    schema = _s(
        {
            "todos": {
                "type": "array",
                "description": "The full updated todo list",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "Imperative task description"},
                        "status": {"type": "string", "enum": sorted(VALID_STATUSES), "description": "pending | in_progress | completed"},
                        "activeForm": {"type": "string", "description": "Present-continuous form shown while in_progress"},
                    },
                    "required": ["content", "status"],
                },
            }
        },
        required=["todos"],
    )

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        todos = args.get("todos") or []
        for t in todos:
            if t.get("status") not in VALID_STATUSES:
                return ToolResult(f"Invalid status: {t.get('status')!r}", error=True)
        in_prog = [t for t in todos if t.get("status") == "in_progress"]
        if len(in_prog) > 1:
            return ToolResult("Error: only one task may be in_progress at a time", error=True)
        # rebuild the shared task store from the legacy flat list
        tasks = _store(ctx)
        tasks.clear()
        for i, t in enumerate(todos, 1):
            tasks.append({
                "id": str(i),
                "subject": str(t.get("content", "")),
                "description": "",
                "activeForm": str(t.get("activeForm") or t.get("active_form") or ""),
                "status": str(t.get("status", "pending")),
                "owner": "",
                "metadata": {},
                "blocks": [],
                "blockedBy": [],
            })
        done = sum(1 for t in todos if t.get("status") == "completed")
        return ToolResult(f"Todo list updated: {done}/{len(todos)} completed")
