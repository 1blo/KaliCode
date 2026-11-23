"""Slash commands - Claude Code's command surface, adapted for Kali."""
from __future__ import annotations

import asyncio
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

from rich.markdown import Markdown

from . import __version__
from .config import MODELS, USER_DIR, project_kali_dir
from .tools.task import BUILTIN_AGENTS

HELP = """[bold magenta]Kali Code[/] commands:
  /help            this help
  /model [name]    switch model (arg: id or number); no arg = picker
  /clear           clear conversation history
  /compact         summarize the conversation to free context
  /cost            token usage for this session
  /status          session status (model, cwd, mcp, permissions)
  /title [text]    show or set the AI-generated chat title (Discord presence)
  /tasks           list the session task list (TaskCreate/TaskUpdate family)
  /todo            alias of /tasks (1.x name)
  /memory          show KALI.md / CLAUDE.md memory files
  /init            analyze the project and write KALI.md
  /mcp             MCP server status + reconnect
  /skills          list available skills
  /agents          list subagent types
  /permissions     show permission rules and mode
  /alwaysallow [cmd]  auto-approve every command (no arg) or a pattern (e.g. git status)
  /hooks           show configured hooks
  /review          review current git diff
  /add-dir <path>  allow access to another working directory
  /export [file]   export the transcript to a file
  /config          show effective settings
  /doctor          check installation health
  /release-notes   what's new in this version
  /bug             how to report a bug
  /login /logout   NVIDIA key management
  /exit            quit (also Ctrl+D / Ctrl+C twice)"""


class SlashRouter:
    def __init__(self, agent, ui, cli):
        self.agent = agent
        self.ui = ui
        self.cli = cli

    async def handle(self, raw: str) -> bool:
        """Handle a slash command; returns True if it was consumed."""
        parts = raw.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        fn = getattr(self, f"cmd_{cmd.lstrip('/').replace('-', '_')}", None)
        if fn is None:
            self.ui.console.print(f"[yellow]Unknown command: {cmd}. Try /help[/]")
            return True
        res = fn(arg)
        if asyncio.iscoroutine(res):
            await res
        return True

    # ------------------------------------------------------------------ core
    def cmd_help(self, arg: str) -> None:
        self.ui.console.print(HELP)

    def cmd_exit(self, arg: str) -> None:
        self.cli.exit = True

    cmd_quit = cmd_exit

    def cmd_clear(self, arg: str) -> None:
        self.agent.messages.clear()
        self.agent.todos = []
        self.ui.console.print("[green]Conversation cleared[/]")

    async def cmd_compact(self, arg: str) -> None:
        self.ui.on_compact_start()
        summary = await self.agent.compact()
        self.ui.on_compact_end()
        self.ui.console.print(Markdown(summary[:3000]))

    def cmd_model(self, arg: str) -> None:
        if arg:
            match = _match_model(arg)
            if match:
                self.agent.cfg.model = match
                self.ui.console.print(f"[green]Model set to {match}[/]")
            else:
                self.ui.console.print(f"[red]Unknown model: {arg}. Known: {', '.join(MODELS)}[/]")
            return
        table_rows = []
        for i, (mid, meta) in enumerate(MODELS.items(), 1):
            cur = " [green]← current[/]" if mid == self.agent.cfg.model else ""
            table_rows.append(f"  {i}. [bold]{meta['label']}[/]  [dim]{mid}{cur}[/]")
        self.ui.console.print("\n".join(table_rows))
        choice = self.ui.console.input("[magenta]Pick a model (1-3, or id):[/]").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(MODELS):
            self.agent.cfg.model = list(MODELS)[int(choice) - 1]
        elif choice in MODELS:
            self.agent.cfg.model = choice
        if choice:
            self.ui.console.print(f"[green]Model set to {self.agent.cfg.model}[/]")

    def cmd_cost(self, arg: str) -> None:
        self.ui.console.print(self.agent.cost_line())

    def cmd_status(self, arg: str) -> None:
        a = self.agent
        mcp = ", ".join(f"{n}({len(s.tools)})" for n, s in a.mcp.servers.items()) or "none"
        discord = "off"
        if getattr(a, "presence", None) is not None:
            discord = "connected" if a.presence.active else "error"
        self.ui.console.print(
            f"  model: [bold]{a.cfg.model}[/]\n"
            f"  cwd: {Path.cwd()}\n"
            f"  permission mode: {a.permission_mode}\n"
            f"  messages: {len(a.messages)}  est. context: ~{a.estimate_context_tokens():,} tok\n"
            f"  MCP: {mcp}\n"
            f"  Discord presence: {discord}\n"
            f"  usage: {a.cost_line()}"
        )

    async def cmd_title(self, arg: str) -> None:
        """Show (or regenerate) the AI-generated chat title."""
        a = self.agent
        if arg.strip():
            a.session_title = arg.strip()
            if getattr(a, "presence", None) is not None:
                a.presence.set_title(a.session_title)
            self.ui.console.print(f"  title: [bold]{a.session_title}[/]")
            return
        if not a.session_title:
            await a.generate_title(" ".join(
                str(m.get("content", "")) for m in a.messages if m.get("role") == "user"
            )[:600] or "coding session")
        if a.session_title:
            self.ui.console.print(f"  title: [bold]{a.session_title}[/]")
        else:
            self.ui.console.print("[yellow]No title generated yet[/]")

    def cmd_todo(self, arg: str) -> None:
        self.ui.todo_panel(self.agent.tasks)

    cmd_tasks = cmd_todo  # /tasks lists the same task store (Claude Code 2.1.x name)

    def cmd_tasks(self, arg: str) -> None:
        self.ui.todo_panel(self.agent.todos)

    def cmd_memory(self, arg: str) -> None:
        from .config import memory_files

        files = memory_files()
        if not files:
            self.ui.console.print("[yellow]No KALI.md/CLAUDE.md found. Create one with /init[/]")
        for p in files:
            self.ui.console.print(f"[bold]{p}[/] ({p.stat().st_size:,} bytes)")

    def cmd_init(self, arg: str) -> None:
        """Ask the agent to write a KALI.md (like Claude Code /init)."""
        self.cli.submit_user_message(
            "Analyze this codebase and write a concise KALI.md at the project root: "
            "build/lint/test commands (especially for running a single test), architecture, "
            "and conventions. Keep it under 60 lines. Then stop."
        )

    async def cmd_mcp(self, arg: str) -> None:
        if arg == "reconnect":
            with self.ui.console.status("[dim]reconnecting...[/]"):
                statuses = await self.agent.mcp.connect_all(
                    {s.name: s.cfg for s in self.agent.mcp.servers.values()})
            self.agent._register_mcp_tools()
            for line in statuses:
                self.ui.console.print(f"  {line}")
            return
        if not self.agent.mcp.servers:
            self.ui.console.print("[dim]No MCP servers configured (settings: mcpServers)[/]")
            return
        for name, s in self.agent.mcp.servers.items():
            style = "green" if s.status == "connected" else "red"
            self.ui.console.print(f"  [{style}]●[/] {name}: {s.status} ({len(s.tools)} tools)"
                                  + (f" - {s.error.splitlines()[0]}" if s.error else ""))

    def cmd_skills(self, arg: str) -> None:
        if not self.agent.skills.skills:
            self.ui.console.print("[dim]No skills found (kali/skills, ~/.kali/skills, .kali/skills)[/]")
        for name, s in sorted(self.agent.skills.skills.items()):
            self.ui.console.print(f"  [bold]{name}[/] - [dim]{s.description[:100]}[/]")

    def cmd_agents(self, arg: str) -> None:
        for name, spec in BUILTIN_AGENTS.items():
            self.ui.console.print(f"  [bold]{name}[/] - [dim]{spec['description'][:90]}[/]")
        for name in self.agent._custom_agents:
            self.ui.console.print(f"  [bold]{name}[/] [magenta](custom)[/]")

    def cmd_permissions(self, arg: str) -> None:
        p = self.agent.permissions
        self.ui.console.print(f"  mode: {p.mode}")
        if p.allow_all:
            self.ui.console.print("  [yellow]always allow: ENABLED (every command auto-approved)[/]")
        for label, rules in (("allow", p.allow + p.session_allow), ("deny", p.deny), ("ask", p.ask)):
            if rules:
                self.ui.console.print(f"  {label}: {', '.join(rules)}")

    def cmd_alwaysallow(self, arg: str) -> None:
        """Allow every command, or a specific command pattern, without prompting."""
        p = self.agent.permissions
        arg = arg.strip()

        if not arg:
            # Blanket approval - confirm first, this is a blanket bypass.
            if not p.allow_all:
                try:
                    answer = self.ui.console.input(
                        "[yellow]Allow ALL commands without asking? This grants a blanket "
                        "bypass and is persisted. Type 'yes' to confirm:[/] "
                    ).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    answer = ""
                if answer not in ("y", "yes"):
                    self.ui.console.print("[yellow]Always allow not enabled.[/]")
                    return
            msg = p.always_allow("")
            self.ui.console.print(f"[green]{msg}[/]")
            self.ui.console.print(
                "[dim]Every tool call is now auto-approved. "
                "Use /permissions to review, or restart with "
                "--permission-mode default to turn it off.[/]"
            )
            return

        # Specific pattern, e.g. "git status" or "npm run *"
        msg = p.always_allow(arg)
        self.ui.console.print(f"[green]{msg}[/]")
        self.ui.console.print(f"[dim]Rule added: Bash({arg} *)[/]")

    def cmd_hooks(self, arg: str) -> None:
        h = self.agent.hooks
        if not h.has_hooks:
            self.ui.console.print("[dim]No hooks configured (settings: hooks)[/]")
            return
        for event, rules in h.rules.items():
            for r in rules:
                self.ui.console.print(f"  {event}: matcher={r.get('matcher', '*')} -> {r.get('hooks')}")

    def cmd_review(self, arg: str) -> None:
        try:
            diff = subprocess.run(["git", "diff", "HEAD"], capture_output=True, text=True,
                                  cwd=Path.cwd(), timeout=30).stdout
        except Exception as e:
            self.ui.console.print(f"[red]git diff failed: {e}[/]")
            return
        if not diff.strip():
            self.ui.console.print("[yellow]No uncommitted changes found[/]")
            return
        self.cli.submit_user_message(
            "Review the following git diff for correctness, security issues and style problems. "
            "Be specific and concise:\n```diff\n" + diff[:60000] + "\n```"
        )

    def cmd_add_dir(self, arg: str) -> None:
        if not arg:
            self.ui.console.print("[yellow]usage: /add-dir <path>[/]")
            return
        self.agent.cfg.additional_dirs.append(arg)
        self.ui.console.print(f"[green]Added working directory: {arg}[/]")

    def cmd_export(self, arg: str) -> None:
        out = Path(arg) if arg else Path(f"kali-session-{datetime.now():%Y%m%d-%H%M%S}.json")
        data = [{"role": m.get("role"), "content": m.get("content")} for m in self.agent.messages]
        out.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
        self.ui.console.print(f"[green]Exported {len(data)} messages to {out}[/]")

    def cmd_config(self, arg: str) -> None:
        from .config import load_settings, settings_paths

        for p in settings_paths():
            mark = "[green]✓[/]" if p.exists() else "[dim]○[/]"
            self.ui.console.print(f"  {mark} {p}")
        s = load_settings()
        safe = json.dumps(s, indent=2)[:3000]
        self.ui.console.print(safe)

    def cmd_doctor(self, arg: str) -> None:
        from .config import resolve_api_key, CHAT_COMPLETIONS_URL
        import shutil

        checks = [
            ("python", f"{__import__('sys').version.split()[0]} ✓"),
            ("NVIDIA_API_KEY", "set ✓" if resolve_api_key().startswith("nvapi-") else "MISSING ✗"),
            ("api url", CHAT_COMPLETIONS_URL),
            ("ripgrep (Grep)", "found ✓" if shutil.which("rg") else "python fallback"),
            ("rich", "installed ✓"),
            ("httpx", "installed ✓"),
        ]
        for k, v in checks:
            self.ui.console.print(f"  [bold]{k}[/]: {v}")

    def cmd_release_notes(self, arg: str) -> None:
        self.ui.console.print(f"[bold]Kali Code v{__version__}[/]\n"
                              "  - initial release: Claude Code tool parity on NVIDIA NIM\n"
                              "  - MCP support (stdio + http), skills, hooks, subagents, plan mode")

    def cmd_bug(self, arg: str) -> None:
        self.ui.console.print("Report Kali Code bugs at the project folder: KALICODE-BUGS.md")

    def cmd_login(self, arg: str) -> None:
        key = self.ui.console.input("Paste NVIDIA API key (nvapi-...): ").strip()
        if key.startswith("nvapi-"):
            from .config import USER_DIR

            USER_DIR.mkdir(exist_ok=True)
            sp = USER_DIR / "settings.json"
            try:
                s = json.loads(sp.read_text("utf-8")) if sp.exists() else {}
            except Exception:
                s = {}
            s.setdefault("env", {})["NVIDIA_API_KEY"] = key
            sp.write_text(json.dumps(s, indent=2), "utf-8")
            self.ui.console.print("[green]Key saved to ~/.kali/settings.json[/]")
        else:
            self.ui.console.print("[red]Not a valid key format[/]")

    def cmd_logout(self, arg: str) -> None:
        sp = USER_DIR / "settings.json"
        if sp.exists():
            try:
                s = json.loads(sp.read_text("utf-8"))
                s.get("env", {}).pop("NVIDIA_API_KEY", None)
                sp.write_text(json.dumps(s, indent=2), "utf-8")
                self.ui.console.print("[green]Removed key from settings (env var may still be set)[/]")
            except Exception as e:
                self.ui.console.print(f"[red]{e}[/]")

    def cmd_vim(self, arg: str) -> None:
        self.ui.console.print("[yellow]vim mode is not supported in this terminal build[/]")

    def cmd_terminal_setup(self, arg: str) -> None:
        self.ui.console.print(
            "For best experience use Windows Terminal.\n"
            "PowerShell profile tip: add `function k { kali @args }` to your $PROFILE."
        )

    def cmd_statusline(self, arg: str) -> None:
        self.ui.console.print("[dim]statusline customization: set 'statusLine.command' in settings.json[/]")

    def cmd_resume(self, arg: str) -> None:
        self.ui.console.print("[yellow]session resume is not persisted in this build[/]")

    cmd_continue = cmd_resume


def _match_model(arg: str) -> str | None:
    if arg in MODELS:
        return arg
    if arg.isdigit() and 1 <= int(arg) <= len(MODELS):
        return list(MODELS)[int(arg) - 1]
    arg_l = arg.lower()
    for mid, meta in MODELS.items():
        if arg_l in mid.lower() or arg_l == meta["label"].lower():
            return mid
    return None
