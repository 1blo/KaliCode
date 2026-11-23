"""The agent loop - Claude Code's conversation engine.

Messages use the OpenAI wire format (native). The loop:
  stream -> thinking/text deltas -> tool_calls -> permissions/hooks -> execute
  -> tool results -> repeat until no tool calls, max turns, or interrupt.
Supports auto-compact, subagents, background shells, plan mode and MCP tools.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import mcp as mcp_mod
from .config import AgentConfig, MODELS, DEFAULT_MODEL, EAGER_MCP_SERVERS
from .hooks import HookEngine
from .llm import StreamEvent, estimate_tokens, stream_chat, LLMError
from .permissions import PermissionManager, Decision
from .skills import SkillRegistry
from .systemprompt import build_system_prompt
from .tools import default_tools, Tool, ToolContext, ToolResult
from .tools.web import WebFetch  # noqa: F401  (registry completeness)

AUTO_COMPACT_FRACTION = 0.82


@dataclass
class BackgroundShell:
    id: str
    command: str
    cwd: str
    proc: asyncio.subprocess.Process
    created: float
    output: str = ""
    output_file: str = ""   # tee target: <tempdir>/kali-tasks/<id>.output
    _read_pos: int = 0
    status: str = "running"  # running|completed|killed
    _fh: object | None = None

    def poll(self) -> tuple[str, str]:
        chunk = self.output[self._read_pos:]
        self._read_pos = len(self.output)
        if self.proc.returncode is not None:
            self.status = "completed" if self.status == "running" else self.status
        return chunk, self.status


@dataclass
class TurnResult:
    text: str = ""
    tool_uses: int = 0
    usage: dict = field(default_factory=dict)
    interrupted: bool = False


# Friendly one-liners for the Discord Rich Presence "details" line.
_PRESENCE_ACTIONS = {
    "Bash": "Running a shell command",
    "Read": "Reading a file",
    "Write": "Writing a file",
    "Edit": "Editing a file",
    "NotebookEdit": "Editing a notebook",
    "Glob": "Searching for files",
    "Grep": "Searching the codebase",
    "WebFetch": "Fetching a web page",
    "WebSearch": "Searching the web",
    "TaskCreate": "Creating a task",
    "TaskGet": "Reading a task",
    "TaskList": "Listing tasks",
    "TaskUpdate": "Updating a task",
    "TaskStop": "Stopping a task",
    "Agent": "Running a subagent",
    "Skill": "Loading a skill",
    "ToolSearch": "Looking up a tool",
    "AskUserQuestion": "Asking a question",
    "EnterPlanMode": "Entering plan mode",
    "ExitPlanMode": "Presenting a plan",
}


def _presence_activity(tool_name: str, args: dict) -> str:
    """Short human-readable status for the Discord presence line."""
    base = _PRESENCE_ACTIONS.get(tool_name)
    if base is None:
        if tool_name.startswith("mcp__"):
            parts = tool_name.split("__")
            return f"Using {parts[-1]}" if len(parts) >= 2 else "Using an MCP tool"
        return f"Using {tool_name}"
    # Add the target file for file tools, when there is an obvious one.
    target = ""
    if isinstance(args, dict):
        for key in ("file_path", "path", "notebook_path", "command", "url", "pattern", "query"):
            val = args.get(key)
            if isinstance(val, str) and val.strip():
                target = val.strip()
                break
    if not target:
        return base
    if len(target) > 40:
        target = "..." + target[-37:]
    return f"{base}: {target}"


@dataclass
class TurnResult:
    text: str = ""
    tool_uses: int = 0
    usage: dict = field(default_factory=dict)
    interrupted: bool = False


class Agent:
    def __init__(self, cfg: AgentConfig, ui=None, is_subagent: bool = False):
        self.cfg = cfg
        self.ui = ui
        self.is_subagent = is_subagent
        self.settings = cfg.settings
        self.messages: list[dict] = []
        self.read_files: set[str] = set()
        self.edits: list[str] = []
        self.loaded_skills: set[str] = set()
        self.interrupted = False
        self.session_id = uuid.uuid4().hex[:16]
        self.permission_mode = cfg.permission_mode
        self.total_usage = {"input_tokens": 0, "output_tokens": 0, "requests": 0}
        self.compacted_count = 0
        # shared task store for TaskCreate/TaskGet/TaskList/TaskUpdate
        # ({id, subject, description, activeForm, status, blocks, blockedBy})
        self.tasks: list[dict] = []

        self.permissions = PermissionManager(
            self.settings, cfg.permission_mode, cfg.allowed_tools, cfg.disallowed_tools
        )
        self.hooks = HookEngine(self.settings)
        self.skills = SkillRegistry()
        self.skills.load_all()
        self.tools: dict[str, Tool] = default_tools()
        # Claude Code 2.1.x tool-search model: MCP tools live here by name
        # only; ToolSearch promotes them into self.tools on demand
        self.deferred_tools: dict[str, Tool] = {}
        self.mcp = mcp_mod.McpManager()
        self._bg_shells: dict[str, BackgroundShell] = {}
        self._custom_agents: dict[str, str] = {}
        # AI-generated chat title (shown in Discord Rich Presence + /title)
        self.session_title: str = ""
        self._title_generated = False
        # Optional Discord Rich Presence controller
        self.presence = None
        self._load_custom_agents()

    # ------------------------------------------------------------------ setup
    def _load_custom_agents(self) -> None:
        from .config import USER_DIR, project_kali_dir

        for folder in (USER_DIR / "agents", project_kali_dir() / "agents"):
            if not folder.exists():
                continue
            for md in folder.glob("*.md"):
                try:
                    self._custom_agents[md.stem] = md.read_text(encoding="utf-8")
                except OSError:
                    pass

    def load_custom_agent(self, name: str) -> str | None:
        return self._custom_agents.get(name)

    async def connect_mcp(self, extra_configs: dict | None = None) -> list[str]:
        from .config import load_settings

        configs = mcp_mod.McpManager.collect_configs(
            load_settings(), self.cfg.mcp_config_files, self.cfg.strict_mcp
        )
        if extra_configs:
            configs.update(extra_configs)
        return await self.mcp.connect_all(configs)

    def _register_mcp_tools(self, eager: bool = False) -> None:
        """Register MCP tools.

        eager=True  -> listed to the model in full (server in EAGER_MCP_SERVERS)
        eager=False -> deferred; ToolSearch fetches their schemas on demand
        """
        for qualified, mt in self.mcp.tools.items():
            if qualified in self.tools:
                continue
            tool = self._make_mcp_tool(mt)
            if eager:
                self.tools[qualified] = tool
            elif qualified not in self.deferred_tools:
                self.deferred_tools[qualified] = tool

    def on_mcp_tools_updated(self, server) -> None:
        """Called when a server pushes notifications/tools/list_changed."""
        self._register_mcp_tools(eager=server.name in EAGER_MCP_SERVERS)
        if self.ui:
            self.ui.on_mcp_tools_ready(server.name, len(server.tools))

    def _make_mcp_tool(self, mt: mcp_mod.McpTool) -> Tool:
        server, name = mt.server, mt.name
        schema = mt.input_schema or {"type": "object"}
        schema.setdefault("type", "object")

        class McpToolProxy(Tool):
            """Wraps a remote MCP tool so the agent can call it like a local tool."""

            async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
                try:
                    result = await ctx.agent.mcp.servers[server].call(name, args)
                except Exception as e:
                    return ToolResult(f"MCP tool '{name}' failed: {type(e).__name__}: {e}", error=True)
                if isinstance(result, str):
                    if result.startswith("Error calling") or result.startswith("Error: MCP server"):
                        return ToolResult(result, error=True)
                    return ToolResult(result)
                # Defensive: a non-string payload still renders sensibly.
                return ToolResult(json.dumps(result, indent=2)[:8000])

        proxy = McpToolProxy()
        proxy.name = mt.qualified
        proxy.description = (f"[MCP server: {server}] {mt.description}".strip()
                             or f"Tool {name} from MCP server {server}")
        proxy.schema = schema
        proxy.read_only = False
        proxy._server, proxy._tool_name = server, name
        return proxy

    # ----------------------------------------------------------------- prompt
    def build_system(self) -> str:
        memory = self._memory_text()
        mcp_note = ""
        eager_servers = [s for s in self.mcp.servers
                         if any(t.startswith(f"mcp__{s}__") for t in self.tools)]
        if eager_servers:
            eager_names = sorted(t for t in self.tools if t.startswith("mcp__"))
            mcp_note = (
                f"# MCP servers\nConnected MCP servers with tools available directly: "
                f"{', '.join(eager_servers)}. Their tools are named mcp__<server>__<tool> "
                f"and are callable like built-in tools.\n"
                f"The full schema of each of these tools is already in your tool list above. "
                f"Call them DIRECTLY - do NOT use ToolSearch for them. "
                f"Available MCP tools: {', '.join(eager_names[:60])}"
                + (f" (+{len(eager_names) - 60} more)" if len(eager_names) > 60 else "")
                + "."
            )
        if self.deferred_tools:
            names = sorted(self.deferred_tools)
            preview = ", ".join(names[:40])
            more = f" (+{len(names) - 40} more)" if len(names) > 40 else ""
            mcp_note += (
                f"\n\nOther MCP tools are DEFERRED - only their names are known until loaded. "
                f"Available deferred tools: {preview}{more}.\n"
                f"Before calling a deferred tool for the first time, fetch its schema with "
                f"ToolSearch (e.g. query \"select:{names[0]}\" or a keyword query); once its "
                f"<function> schema appears in a ToolSearch result it is callable."
            )
        return build_system_prompt(
            cwd=os.getcwd(),
            model=self.cfg.model,
            tools=list(self.tools.values()),
            skill_block=self.skills.prompt_block(),
            mcp_note=mcp_note,
            memory_text=memory,
            permission_mode=self.permission_mode,
            custom_prompt=self.cfg.system_prompt,
            append_prompt=self.cfg.append_system_prompt,
            is_subagent=self.is_subagent,
        )

    def _memory_text(self) -> str:
        from .config import memory_files

        chunks = []
        for p in memory_files():
            try:
                chunks.append(p.read_text(encoding="utf-8"))
            except OSError:
                pass
        return "\n\n".join(chunks)

    # ------------------------------------------------------------- api format
    def _tool_schemas(self, allowed: list[str] | None = None) -> list[dict]:
        out = []
        for name, t in self.tools.items():
            if allowed is not None and name not in allowed:
                continue
            if name in self.cfg.disallowed_tools:
                continue
            out.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": t.description[:8000],
                    "parameters": t.schema,
                },
            })
        return out

    # ----------------------------------------------------------------- turns
    async def generate_title(self, user_input: str) -> str:
        """Ask the model for a short chat title (Claude Code names each chat).

        The title is used for the Discord Rich Presence line and /title.
        It is generated once per session, in the background, and never
        blocks the main turn.
        """
        if self._title_generated:
            return self.session_title
        self._title_generated = True
        prompt = (
            "Generate a short title for this coding conversation. "
            "Reply with ONLY the title: 3-6 words, no quotes, no punctuation "
            "at the end, no explanation.\n\n"
            f"User's first message:\n{user_input[:600]}"
        )
        try:
            # A low token budget is not enough: reasoning models spend the
            # first tokens thinking, so the title would never be emitted.
            # Use a roomier budget and a dedicated message.
            resp = await stream_chat({
                "model": self.cfg.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2048,
                "stream": True,
            })
            text = (resp.content or "").strip()
            if not text:
                # Some models answer in the reasoning channel when the
                # instruction is very short; fall back to it.
                text = (resp.reasoning or "").strip()
            title = text.strip().strip('"').strip("'")
            # keep it to one line and reasonably short
            title = title.splitlines()[0].strip() if title else ""
            if len(title) > 60:
                title = title[:60].rsplit(" ", 1)[0]
            self.session_title = title
            if self.presence is not None and title:
                self.presence.set_title(title)
        except Exception:
            self.session_title = ""
        return self.session_title

    async def run_turn(self, user_input: str, images: list[dict] | None = None,
                       max_turns: int | None = None) -> TurnResult:
        """One user turn (may span many model/tool cycles)."""
        self.interrupted = False
        if user_input or images:
            content: object = user_input
            if images:
                parts: list[dict] = [{"type": "text", "text": user_input or "[image]"}]
                for img in images:
                    parts.append({"type": "image_url", "image_url": {
                        "url": f"data:{img['media_type']};base64,{img['data']}"}})
                content = parts
            self.messages.append({"role": "user", "content": content})

        hook_out = await self.hooks.emit("UserPromptSubmit", {"prompt": user_input})
        if hook_out and hook_out.get("decision") == "block":
            return TurnResult(text=hook_out.get("reason", "blocked by hook"))

        result = TurnResult()
        turns = max_turns or self.cfg.max_turns or 10_000
        budget_note_shown = False

        for turn_no in range(turns):
            await self._auto_compact()
            delta_text, n_tools, usage, interrupted = await self._single_cycle(turn_no)
            result.text += delta_text
            result.tool_uses += n_tools
            result.usage = usage
            result.interrupted = result.interrupted or interrupted
            if interrupted:
                result.text += "\n[Interrupted by user]"
                break
            if n_tools == 0:
                break
            if turn_no + 1 >= turns:
                result.text += f"\n[Turn limit of {turns} reached]"
        else:
            pass

        stop_hook = await self.hooks.emit("Stop", {"stop_hook_active": result.interrupted})
        if stop_hook and stop_hook.get("decision") == "block":
            self.messages.append({"role": "user", "content":
                                  f"[Stop hook] {stop_hook.get('reason', 'continue working')}"})
        return result

    async def _single_cycle(self, turn_no: int):
        system = self.build_system()
        messages = [{"role": "system", "content": system}] + self.messages
        payload = {
            "model": self.cfg.model,
            "messages": messages,
            "max_tokens": self.cfg.max_tokens,
            "stream": True,
            "tools": self._tool_schemas() or None,
            "tool_choice": "auto" if self._tool_schemas() else None,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        if self.cfg.reasoning_effort:
            payload["reasoning_effort"] = self.cfg.reasoning_effort

        events = []

        def on_event(ev: StreamEvent):
            events.append(ev)
            if self.ui:
                self.ui.on_stream_event(ev)

        try:
            resp = await stream_chat(payload, on_event)
        except LLMError as e:
            if self.ui:
                self.ui.on_error(str(e))
            self.messages.append({"role": "user", "content":
                                  f"[API error, tell the user] {e}"})
            return "", 0, {}, False

        usage = resp.usage or {}
        if usage:
            self.total_usage["input_tokens"] += usage.get("prompt_tokens", 0)
            self.total_usage["output_tokens"] += usage.get("completion_tokens", 0)
            self.total_usage["requests"] += 1

        assistant_msg: dict = {"role": "assistant", "content": resp.content or None}
        if resp.tool_calls:
            assistant_msg["tool_calls"] = [
                {"id": tc.id or f"call_{i}", "type": "function",
                 "function": {"name": tc.name, "arguments": tc.arguments or "{}"}}
                for i, tc in enumerate(resp.tool_calls)
            ]
        self.messages.append(assistant_msg)

        if self.ui and resp.reasoning:
            pass  # already streamed live

        if not resp.tool_calls:
            return resp.content, 0, usage, self.interrupted

        # ---- dispatch tool calls (sequentially, like Claude Code's default)
        n = 0
        for call in resp.tool_calls:
            if self.interrupted:
                self.messages.append({"role": "tool", "tool_call_id": call.id or "x",
                                      "content": "[interrupted by user]"})
                continue
            try:
                args = json.loads(call.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
                self.messages.append({"role": "tool", "tool_call_id": call.id or "x",
                                      "content": "Error: malformed tool arguments (invalid JSON)"})
                continue

            tool = self.tools.get(call.name) or self.deferred_tools.get(call.name)
            if tool is None:
                self.messages.append({"role": "tool", "tool_call_id": call.id or "x",
                                      "content": f"Error: unknown tool '{call.name}'"})
                continue

            # hooks: PreToolUse
            pre = await self.hooks.emit("PreToolUse", {"tool_name": call.name, "tool_input": args})
            if pre and pre.get("decision") == "block":
                self.messages.append({"role": "tool", "tool_call_id": call.id or "x",
                                      "content": f"Blocked by hook: {pre.get('reason', '')}"})
                continue
            if pre and isinstance(pre.get("permissionDecision"), str) and pre["permissionDecision"] == "allow":
                decision = Decision("allow", "hook approved")
            else:
                decision = self.permissions.check(call.name, args, tool)

            if decision.behavior == "deny":
                self.messages.append({"role": "tool", "tool_call_id": call.id or "x",
                                      "content": f"Permission denied: {decision.reason}"})
                if self.ui:
                    self.ui.on_tool_denied(call.name, args, decision.reason)
                continue
            if decision.behavior == "ask":
                ok = await self.ui.confirm_tool(call.name, args, tool) if self.ui else True
                if not ok:
                    self.messages.append({"role": "tool", "tool_call_id": call.id or "x",
                                          "content": "The user doesn't want to proceed with this tool use. Stop what you're doing and wait for the user's next instruction."})
                    if self.ui:
                        self.ui.on_tool_denied(call.name, args, "user rejected")
                    continue

            if self.ui:
                self.ui.on_tool_start(call.name, args)
            if self.presence is not None:
                self.presence.set_activity(_presence_activity(call.name, args))
            ctx = ToolContext(agent=self, cwd=os.getcwd())
            t0 = time.time()
            try:
                if hasattr(tool, "_server"):
                    result = await tool.run(args, ctx)
                else:
                    result = await tool.run(args, ctx)
            except Exception as e:
                result = ToolResult(f"Tool error: {type(e).__name__}: {e}", error=True)
            elapsed = time.time() - t0
            if self.presence is not None:
                # Fall back to the chat title once the tool is done.
                self.presence.set_activity("")
            if self.ui:
                self.ui.on_tool_result(call.name, args, result, elapsed)
                # Resume the spinner: the model is about to stream its next
                # response after the tool result.
                if self.ui._spinner_active is False:
                    self.ui.start_spinner("thinking...")

            content = result.render()
            if result.system:
                content += f"\n<system-reminder>{result.system}</system-reminder>"
            self.messages.append({"role": "tool", "tool_call_id": call.id or "x", "content": content})

            # images from Read go back as a user vision message
            if result.images:
                parts = [{"type": "text", "text": f"[Image result for tool {call.name}]"}]
                for img in result.images:
                    parts.append({"type": "image_url", "image_url":
                                  {"url": f"data:{img['media_type']};base64,{img['data']}"}})
                self.messages.append({"role": "user", "content": parts})

            post = await self.hooks.emit("PostToolUse", {
                "tool_name": call.name, "tool_input": args,
                "tool_response": content[:2000],
            })
            if post and post.get("decision") == "block":
                self.messages.append({"role": "user", "content":
                                      f"[PostToolUse hook] {post.get('reason', '')}"})
            n += 1
        return resp.content, n, usage, self.interrupted

    # ------------------------------------------------------------- compaction
    def estimate_context_tokens(self) -> int:
        total = sum(estimate_tokens(json.dumps(m, default=str)) for m in self.messages)
        return total + estimate_tokens(self.build_system())

    async def _auto_compact(self) -> None:
        if self.is_subagent:
            return
        limit = MODELS.get(self.cfg.model, {}).get("context", 131072)
        threshold = int(limit * AUTO_COMPACT_FRACTION)
        if self.estimate_context_tokens() < threshold:
            return
        if self.ui:
            self.ui.on_compact_start()
        summary = await self._summarize()
        # keep recent tool exchanges intact
        tail = self.messages[-12:]
        self.messages = [{"role": "user", "content":
                          f"<compacted-summary>\n{summary}\n</compacted-summary>\n\n"
                          "The conversation was compacted. Continue from the summary; recent messages follow."}] + tail
        self.compacted_count += 1
        if self.ui:
            self.ui.on_compact_end()

    async def compact(self) -> str:
        summary = await self._summarize()
        self.messages = [{"role": "user", "content":
                          f"<compacted-summary>\n{summary}\n</compacted-summary>"}]
        return summary

    async def _summarize(self) -> str:
        convo = json.dumps(self.messages[-80:], default=str)[:120000]
        payload = {
            "model": self.cfg.model,
            "max_tokens": 4096,
            "messages": [
                {"role": "system", "content": "Summarize this coding-agent conversation into a dense handoff: user goal, decisions, files touched, commands run, current state, next steps. Be factual and compact."},
                {"role": "user", "content": convo},
            ],
        }
        if self.cfg.reasoning_effort:
            payload["reasoning_effort"] = self.cfg.reasoning_effort
        try:
            resp = await stream_chat(payload, timeout=300.0)
            return resp.content.strip() or "(empty summary)"
        except LLMError:
            return "(compaction summary failed; prior context dropped)"

    # -------------------------------------------------------------- subagents
    async def run_subagent(self, *, prompt: str, model: str, description: str,
                           restricted_tools: list[str] | None, system_prompt: str | None,
                           background: bool) -> str:
        cfg = AgentConfig(
            model=model,
            max_tokens=self.cfg.max_tokens,
            reasoning_effort=self.cfg.reasoning_effort,
            permission_mode="bypassPermissions" if self.permissions.mode == "bypassPermissions" else self.permission_mode,
            allowed_tools=list(restricted_tools) if restricted_tools else None,
            settings=self.settings,
            append_system_prompt=system_prompt,
        )
        sub = Agent(cfg, ui=None if background else self.ui, is_subagent=True)
        if restricted_tools:
            task_tools = ("TaskCreate", "TaskGet", "TaskList", "TaskUpdate")
            sub.tools = {k: v for k, v in sub.tools.items() if k in restricted_tools or k in task_tools}
        sub.messages.append({"role": "user", "content": prompt})

        if background:
            task = asyncio.create_task(self._run_subagent_bg(sub, description))
            self._bg_subagents[description] = task
            return f"background:{description}"

        await sub.run_turn(prompt)
        final = sub.messages[-1].get("content", "") if sub.messages else ""
        if self.ui:
            self.ui.on_subagent_done(description, final)
        return sub.session_id

    async def _run_subagent_bg(self, sub: "Agent", description: str) -> None:
        await sub.run_turn(sub.messages[-1]["content"] if sub.messages else "")
        final = sub.messages[-1].get("content", "") if sub.messages else ""
        self.messages.append({"role": "user", "content":
                              f"<background-subagent result task='{description}'>\n{final}\n</background-subagent>"})
        if self.ui:
            self.ui.on_subagent_done(description, final, background=True)

    _bg_subagents: dict = {}

    # ---------------------------------------------------------- bg shells api
    def _task_output_path(self, shell_id: str) -> str:
        out_dir = os.path.join(tempfile.gettempdir(), "kali-tasks")
        os.makedirs(out_dir, exist_ok=True)
        return os.path.join(out_dir, f"{shell_id}.output")

    def background_output_file(self, shell_id: str) -> str:
        return self._task_output_path(shell_id)

    async def start_background_shell(self, command: str, cwd: str) -> str:
        shell_id = f"bg_{uuid.uuid4().hex[:8]}"
        out_path = self._task_output_path(shell_id)
        out_file = open(out_path, "w", encoding="utf-8")
        proc = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            cwd=cwd or None,
            env={**os.environ, "KALICODE": "1"},
        )
        shell = BackgroundShell(id=shell_id, command=command, cwd=cwd, proc=proc,
                                created=time.time(), output_file=out_path, _fh=out_file)

        async def _pump():
            assert proc.stdout
            async for line in proc.stdout:
                text = line.decode("utf-8", "replace")
                shell.output += text
                try:
                    out_file.write(text)
                    out_file.flush()
                except ValueError:
                    pass
                if len(shell.output) > 1_000_000:
                    shell.output = shell.output[-500_000:]
                    shell._read_pos = 0
            if shell.status == "running":
                shell.status = "completed"
            try:
                out_file.close()
            except Exception:
                pass

        asyncio.create_task(_pump())
        self._bg_shells[shell_id] = shell
        return shell_id

    def background_output(self, shell_id: str) -> str:
        sh = self._bg_shells.get(shell_id)
        return sh.output if sh else ""

    def poll_background_shell(self, shell_id: str) -> tuple[str, str]:
        sh = self._bg_shells.get(shell_id)
        if sh is None:
            return "", "not found"
        chunk, status = sh.poll()
        return (chunk or "(no new output)"), status

    def kill_background_shell(self, shell_id: str) -> tuple[bool, str]:
        sh = self._bg_shells.get(shell_id)
        if sh is None:
            return False, f"Unknown shell id: {shell_id}"
        try:
            sh.proc.kill()
            sh.status = "killed"
            return True, f"Killed shell {shell_id}"
        except ProcessLookupError:
            return True, f"Shell {shell_id} already exited"

    # ------------------------------------------------------------- user I/O
    async def ask_user_questions(self, questions: list[dict]) -> list[dict] | None:
        if self.ui is None:
            return [{"question": q.get("question", ""), "answer": "(subagent: no user)"} for q in questions]
        return await self.ui.ask_questions(questions)

    async def confirm_plan(self, plan: str) -> str:
        if self.ui is None:
            return "approved"
        return await self.ui.confirm_plan(plan)

    # ------------------------------------------------------------------ edits
    def record_edit(self, path: Path, kind: str) -> None:
        self.edits.append(f"{kind}:{path}")

    @property
    def todos(self) -> list[dict]:
        """Legacy view of the task store (TodoWrite/UI compatibility)."""
        return self.tasks

    @todos.setter
    def todos(self, value: list[dict]) -> None:
        self.tasks = value

    # ------------------------------------------------------------------ usage
    def cost_line(self) -> str:
        u = self.total_usage
        return (f"requests: {u['requests']}  in: {u['input_tokens']:,} tok  "
                f"out: {u['output_tokens']:,} tok  compactions: {self.compacted_count}")


class _LazyShell:
    """Deprecated placeholder kept for import compatibility."""

    def __init__(self, sid, pending, command, cwd):
        self.id = sid
        self.command, self.cwd = command, cwd
        self.proc = None
        self.output = ""
        self._read_pos = 0
        self.status = "running"
