"""Agent - launches subagents (Claude Code 2.1.x renamed Task -> Agent)."""
from __future__ import annotations

from .base import Tool, ToolResult, ToolContext, STR, BOOL, _s
from ..config import SUBAGENT_MODEL

# NOTE: the spec's `model` enum is ["sonnet", "opus", "haiku", "fable"]
# (Anthropic alias names). This clone runs on NVIDIA NIM, so the enum is
# substituted with the models this build can actually route to.
AGENT_MODEL_ENUM = [
    "stepfun-ai/step-5-preview",
    "moonshotai/kimi-k3.1-pro",
    "minimaxai/minimax-m3.1-flash",
]

BUILTIN_AGENTS = {
    "general-purpose": {
        "description": "General-purpose agent for researching complex questions and executing multi-step tasks",
        "tools": None,  # all
    },
    "Explore": {
        "description": "Fast agent specialized for exploring codebases - find files by pattern, search keywords, answer questions about the codebase",
        "tools": ["Read", "Glob", "Grep", "Bash", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"],
    },
    "Plan": {
        "description": "Software architect agent for designing implementation strategies before writing code",
        "tools": ["Read", "Glob", "Grep", "Bash", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"],
    },
    "code-reviewer": {
        "description": "Reviews code changes for quality, correctness and security",
        "tools": ["Read", "Glob", "Grep", "Bash"],
    },
    "output-style-setup": {
        "description": "Updates Kali Code output styles",
        "tools": ["Read", "Write", "Edit", "Glob"],
    },
}


class Agent(Tool):
    name = "Agent"
    # Verbatim from the Sonnet 4.6 CLI leak (spec section 2.1), with the
    # sentences referencing fork / SendMessage / isolation (worktree, remote)
    # removed - those features do not exist in this build.
    description = """Launch a new agent to handle complex, multi-step tasks. Each agent type has specific capabilities and tools available to it.

Available agent types are listed in `<system-reminder>` messages in the conversation.

When using the Agent tool, specify a subagent_type to select an agent; any other type - or omitting it - starts a fresh agent (general-purpose by default).

### When to use

A fresh agent costs more than it looks. It knows only what you put in the prompt, and you see only the summary it sends back - both handoffs drop detail, and neither of you can tell what the other missed. You can't watch it work, only wait or cancel. Its mistakes come back in the same confident register as its findings, and an agent handed your hypothesis tends to return it confirmed. Several at once spend tokens in a burst the user didn't ask for. Weigh those tokens against the accuracy they buy: the user pays for agents you did not need, and pays again for work you redo because you skipped one.

Reach for this when you have independent work to run in parallel, when the user asks for a side quest that shouldn't block your main thread, or when answering would mean reading across several files - delegate that and you keep the conclusion, not the file dumps.

Do the work yourself when it is a handful of tool calls or a lookup whose target you already know; don't delegate a check you could run inline. Delegate review only when you want a read that isn't anchored on yours - then give it the code, not your conclusion. Once you've delegated something, don't also run it yourself; wait for the result. When in doubt, don't spawn.

When you do spawn one, brief it like the peer it is: state the goal and what you have already ruled out, point it at the files and docs worth reading instead of retyping them, and keep the scope explicit and narrow. That brief is the only context it will have, so it is your first lever on every cost above - and if you cannot write a clear one, you do not understand the task well enough to hand it off.

Subagents run in the background; you'll be notified when one completes. Never fabricate or predict a pending agent's results - the notification is never something you write yourself; if the user asks before it arrives, say it's still running.

- The agent's final report is not shown to the user - relay what matters.
- Each agent type's model, reasoning effort, and tools come from its definition (`.kali/agents/*.md` frontmatter)."""
    schema = _s(
        {
            "description": {**STR, "description": "A short (3-5 word) description of the task"},
            "prompt": {**STR, "description": "The task for the agent to perform"},
            "subagent_type": {**STR, "description": "The type of specialized agent to use for this task"},
            "model": {
                **STR,
                "description": (
                    "Optional model override for this agent. Takes precedence over the agent "
                    "definition's model frontmatter and the configured default subagent model. "
                    "If omitted, uses the agent definition's model, else the default (inherits "
                    "from the parent unless a default subagent model is configured)."
                ),
                "enum": AGENT_MODEL_ENUM,
            },
            # from the headless-variant note in the spec
            "run_in_background": {
                "type": "boolean",
                "description": (
                    "Agents run in the background by default; you will be notified when one "
                    "completes. Set to false only when your very next action depends on this "
                    "agent's result and nothing else could usefully happen while it runs - "
                    "otherwise leave it in the background so the user can hand you other work."
                ),
            },
        },
        required=["description", "prompt"],
    )

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent_type = args.get("subagent_type", "general-purpose")
        spec = BUILTIN_AGENTS.get(agent_type, BUILTIN_AGENTS["general-purpose"])
        prompt = args.get("prompt", "")
        description = args.get("description", "task")
        model = args.get("model") or SUBAGENT_MODEL

        # Custom agents from .kali/agents/*.md
        custom_system = None
        if agent_type not in BUILTIN_AGENTS:
            custom_system = ctx.agent.load_custom_agent(agent_type)
            if custom_system is None:
                return ToolResult(
                    f"Unknown agent type: {agent_type}. Available: {', '.join(BUILTIN_AGENTS)} "
                    f"(or add .kali/agents/{agent_type}.md)", error=True,
                )

        session_id = await ctx.agent.run_subagent(
            prompt=prompt,
            model=model,
            description=description,
            restricted_tools=spec["tools"],
            system_prompt=custom_system,
            background=bool(args.get("run_in_background")),
        )
        return ToolResult(
            f"Subagent '{description}' ({agent_type}) finished. session_id: {session_id}\n"
            f"(final response was delivered to the conversation above)"
        )
