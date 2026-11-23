"""EnterPlanMode / ExitPlanMode - Claude Code 2.1.x symmetric plan-mode pair.

exit_plan_mode (1.x) became ExitPlanMode and gained the EnterPlanMode twin.
ExitPlanMode no longer takes the plan text as a required parameter; only the
deprecated `allowedPrompts` param remains in its schema.
"""
from __future__ import annotations

from .base import Tool, ToolResult, ToolContext, _s


class EnterPlanMode(Tool):
    name = "EnterPlanMode"
    description = """Use this tool proactively when you're about to start a non-trivial implementation task. Getting user sign-off on your approach before writing code prevents wasted effort and ensures alignment. This tool transitions you into plan mode where you can explore the codebase and design an implementation approach for user approval.

### When to Use This Tool

**Prefer using EnterPlanMode** for implementation tasks unless they're simple. Use it when ANY of these conditions apply:

1. **New Feature Implementation**: Adding meaningful new functionality
   - Example: "Add a logout button" - where should it go? What should happen on click?
   - Example: "Add form validation" - what rules? What error messages?

2. **Multiple Valid Approaches**: The task can be solved in several different ways
   - Example: "Add caching to the API" - could use Redis, in-memory, file-based, etc.
   - Example: "Improve performance" - many optimization strategies possible

3. **Code Modifications**: Changes that affect existing behavior or structure
   - Example: "Refactor this component" - what exactly should change?
   - Example: "Improve error handling" - what's the current flow? What are the failure modes?

4. **Architectural Decisions**: The task requires choosing between patterns or technologies
   - Example: "Add real-time updates" - WebSockets vs SSE vs polling
   - Example: "Implement state management" - Redux vs Context vs custom solution

5. **Multi-File Changes**: The task will likely touch more than 2-3 files
   - Example: "Refactor the authentication system"
   - Example: "Add a new API endpoint with tests"

6. **Unclear Requirements**: You need to explore before understanding the full scope
   - Example: "Make the app faster" - need to profile and identify bottlenecks
   - Example: "Fix the bug in checkout" - need to investigate root cause

7. **User Preferences Matter**: The implementation could reasonably go multiple ways
   - If you would use AskUserQuestion to clarify the approach, use EnterPlanMode instead
   - Plan mode lets you explore first, then present options with context

### When NOT to Use This Tool

Only skip EnterPlanMode for simple tasks:
- Single-line or few-line fixes (typos, obvious bugs, small tweaks)
- Adding a single function with clear requirements
- Tasks where the user has given very specific, detailed instructions
- Pure research/exploration tasks (use the Agent tool instead)

### What Happens in Plan Mode

In plan mode, you'll:
1. Thoroughly explore the codebase using `find`/Glob, `grep`/Grep, and Read
2. Understand existing patterns and architecture
3. Design an implementation approach
4. Present your plan to the user for approval
5. Use AskUserQuestion if you need to clarify approaches
6. Exit plan mode with ExitPlanMode when ready to implement

### Important Notes

- This tool REQUIRES user approval - they must consent to entering plan mode
- If unsure whether to use it, err on the side of planning - it's better to get alignment upfront than to redo work
- Users appreciate being consulted before significant changes are made to their codebase"""
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    read_only = True

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        if ctx.agent.permission_mode == "plan":
            return ToolResult(
                "Already in plan mode. Research the codebase and design your implementation "
                "approach, then call ExitPlanMode when the plan is ready for approval."
            )
        ctx.agent.permission_mode = "plan"
        return ToolResult(
            "Plan mode entered. Research the codebase (Read, Glob, Grep and read-only Bash "
            "commands), understand the existing patterns, and design an implementation approach. "
            "Do not write or edit any files while in plan mode. When the plan is ready, call "
            "ExitPlanMode to present it for user approval."
        )


class ExitPlanMode(Tool):
    name = "ExitPlanMode"
    description = """Use this tool when you are in plan mode and have finished writing your plan to the plan file and are ready for user approval.

### How This Tool Works
- You should have already written your plan to the plan file specified in the plan mode system message
- This tool does NOT take the plan content as a parameter - it will read the plan from the file you wrote
- This tool simply signals that you're done planning and ready for the user to review and approve
- The user will see the contents of your plan file when they review it

### When to Use This Tool
IMPORTANT: Only use this tool when the task requires planning the implementation steps of a task that requires writing code. For research tasks where you're gathering information, searching files, reading files or in general trying to understand the codebase - do NOT use this tool.

### Before Using This Tool
Ensure your plan is complete and unambiguous:
- If you have unresolved questions about requirements or approach, use AskUserQuestion first (in earlier phases)
- Once your plan is finalized, use THIS tool to request approval

**Important:** Do NOT use AskUserQuestion to ask "Is this plan okay?" or "Should I proceed?" - that's exactly what THIS tool does. ExitPlanMode inherently requests user approval of your plan.

### Examples

1. Initial task: "Search for and understand the implementation of vim mode in the codebase" - Do not use the exit plan mode tool because you are not planning the implementation steps of a task.
2. Initial task: "Help me implement yank mode for vim" - Use the exit plan mode tool after you have finished planning the implementation steps of the task.
3. Initial task: "Add a new feature to handle user authentication" - If unsure about auth method (OAuth, JWT, etc.), use AskUserQuestion first, then use exit plan mode tool after clarifying the approach."""
    # Verbatim schema (note the deprecated legacy param; no required plan param).
    schema = {
        "type": "object",
        "properties": {
            "allowedPrompts": {
                "description": "Deprecated: no longer used.",
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tool": {"description": "The tool this prompt applies to", "type": "string", "enum": ["Bash"]},
                        "prompt": {"description": "Semantic description of the action, e.g. \"run tests\", \"install dependencies\"", "type": "string"},
                    },
                    "required": ["tool", "prompt"],
                    "additionalProperties": False,
                },
            }
        },
        "additionalProperties": {},
    }

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        plan = str(args.get("plan") or "")
        if not plan.strip():
            # read the plan from the most recent assistant text
            for m in reversed(ctx.agent.messages):
                if m.get("role") == "assistant" and isinstance(m.get("content"), str) and m["content"].strip():
                    plan = m["content"]
                    break
        approved = await ctx.agent.confirm_plan(plan)
        if approved == "approved":
            ctx.agent.permission_mode = "acceptEdits"
            return ToolResult("Plan approved. You can now start coding.")
        if approved == "edited":
            return ToolResult("User edited the plan; proceed with the updated plan on screen.", error=False)
        return ToolResult(
            "The user doesn't want to proceed with this plan. Ask what they'd like changed, "
            "then update the plan and call ExitPlanMode again.",
            error=True,
        )
