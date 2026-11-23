"""Rich-powered terminal UI - streaming output, tool cards, permission prompts."""
from __future__ import annotations

import json
import os

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from .llm import StreamEvent

TOOL_ICON = {
    "Bash": "$", "Read": "()", "Edit": "+", "Write": "+", "Grep": "*", "Glob": "*",
    "TodoWrite": "[]", "TaskCreate": "[]", "TaskUpdate": "[]", "TaskList": "[]",
    "TaskGet": "[]", "Agent": ">", "TaskStop": "x", "WebFetch": "@", "WebSearch": "@",
    "Skill": "s", "ToolSearch": "?", "EnterPlanMode": "plan", "ExitPlanMode": "plan",
}


class UI:
    def __init__(self, verbose: bool = False):
        self.console = Console(highlight=False, soft_wrap=True)
        self.verbose = verbose
        self._live: Live | None = None
        self._thinking_inline = False
        # Streaming state: the spinner renders in place while text streams
        # below it. We never let a spinner overwrite already-printed text.
        self._spinner_active = False
        self._stream_started = False
        self._pending_thinking: list[str] = []

    # --------------------------------------------------------------- spinner
    def start_spinner(self, text: str = "thinking...") -> None:
        """Start a spinner that coexists with streamed output."""
        if self._spinner_active:
            return
        self._spinner_active = True
        self._live = Live(
            Spinner("dots", text=f"[dim]{text}[/]"),
            console=self.console, refresh_per_second=12, transient=True,
        )
        try:
            self._live.start()
        except Exception:
            self._spinner_active = False
            self._live = None

    def stop_spinner(self) -> None:
        if self._live is not None:
            try:
                self._live.stop()
            except Exception:
                pass
        self._live = None
        self._spinner_active = False

    def refresh_spinner(self, text: str = "thinking...") -> None:
        if self._live is not None:
            try:
                self._live.update(Spinner("dots", text=f"[dim]{text}[/]"))
            except Exception:
                pass

    # ---------------------------------------------------------------- banner
    def banner(self, model: str, version: str, cwd: str) -> None:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_row("[bold magenta]Kali Code[/]", f"[dim]v{version}[/]")
        table.add_row("", f"[dim]model:[/] {model}")
        table.add_row("", f"[dim]cwd:[/] {cwd}")
        self.console.print(Panel(table, border_style="magenta", padding=(0, 1)))

    # -------------------------------------------------------------- streaming
    def on_stream_event(self, ev: StreamEvent) -> None:
        if ev.type == "thinking":
            # Thinking is hidden by default (Claude Code behaviour); --verbose
            # shows it live as a dim block above the answer.
            if self.verbose:
                self._pending_thinking.append(ev.text)
        elif ev.type == "text":
            # Stop the spinner before the first real token so the answer
            # streams on clean lines (a live spinner would overwrite it).
            if self._spinner_active:
                self.stop_spinner()
            if self._pending_thinking:
                self._stream_thinking()
            self._stream_started = True
            self.console.print(ev.text, end="", markup=False, highlight=False)
        elif ev.type == "error":
            self.stop_spinner()
            self.on_error(ev.text)

    def _stream_thinking(self) -> None:
        if not self._pending_thinking:
            return
        text = "".join(self._pending_thinking)
        if self._spinner_active:
            self.stop_spinner()
        self.console.print(Text(text, style="dim italic"), end="")
        self._pending_thinking = []

    def on_error(self, message: str) -> None:
        self.console.print(f"\n[bold red]error:[/] {message}")

    def assistant_end(self) -> None:
        self.stop_spinner()
        if self._pending_thinking:
            self._stream_thinking()
        self.console.print()

    # -------------------------------------------------------------- tool cards
    def on_tool_start(self, name: str, args: dict) -> None:
        # Never print tool cards on top of a live spinner.
        if self._spinner_active:
            self.stop_spinner()
        key = _arg_summary(name, args)
        icon = TOOL_ICON.get(name, "+")
        self.console.print(f"[cyan]{icon}[/] [bold]{name}[/]([italic]{key}[/])")
        # Show what the tool is doing while it runs.
        self.start_spinner(f"running {name}...")

    def on_tool_result(self, name: str, args: dict, result, elapsed: float) -> None:
        if self._spinner_active:
            self.stop_spinner()
        self._pending_thinking = []
        style = "red" if result.error else "dim"
        text = result.output.strip()
        lines = text.count("\n") + 1
        shown = text if (self.verbose or lines <= 12) else (
            "\n".join(text.splitlines()[:12]) + f"\n... (+{lines - 12} lines)")
        if shown:
            self.console.print(Text(shown[:6000], style=style))
        mark = "[red]✗[/]" if result.error else "[green]✓[/]"
        self.console.print(f"{mark} [dim]{name} done in {elapsed:.1f}s[/]\n")

    def on_tool_denied(self, name: str, args: dict, reason: str) -> None:
        self.console.print(f"[yellow]⊘ {name} denied[/] [dim]({reason})[/]\n")

    def on_subagent_done(self, description: str, final: str, background: bool = False) -> None:
        tag = "background " if background else ""
        self.console.print(f"[bold magenta]<[/] [magenta]subagent {tag}'{description}' finished[/]")
        self.console.print(Text(final[:4000], style="dim"))
        self.console.print("[magenta]>[/]\n")

    def on_mcp_tools_ready(self, server_name: str, count: int) -> None:
        self.stop_spinner()
        self.console.print(f"[green]MCP server '{server_name}' attached - {count} tools available[/]")

    def on_compact_start(self) -> None:
        self.console.print("[yellow]context nearly full - compacting...[/]")

    def on_compact_end(self) -> None:
        self.console.print("[green]compaction complete[/]")

    # -------------------------------------------------------------- prompts
    def prompt(self) -> str:
        try:
            return self.console.input("[bold magenta]❯ [/]")
        except (EOFError, KeyboardInterrupt):
            return "/exit"

    async def confirm_tool(self, name: str, args: dict, tool) -> bool:
        detail = _arg_summary(name, args)
        self.console.print(
            Panel(f"[bold]{name}[/] [dim]{detail}[/]",
                  title="permission needed", border_style="yellow"))
        choice = self.console.input(
            "[yellow]Allow? yes / always / no:[/] ").strip().lower()
        if choice in ("y", "yes", ""):
            return True
        if choice in ("a", "always"):
            try:
                from .permissions import _rule_for

                agent = tool.__self__ if hasattr(tool, "__self__") else None
            except Exception:
                agent = None
            # persist via agent callback injected by cli (ui.agent set below)
            if getattr(self, "agent", None):
                self.agent.permissions.remember_allow(name, args)
                self.console.print(f"[green]saved rule for {name}[/]")
            return True
        return False

    async def ask_questions(self, questions: list[dict]) -> list[dict] | None:
        answers = []
        for q in questions:
            self.console.print(f"\n[bold]{q.get('question')}[/]")
            options = q.get("options", [])
            for i, opt in enumerate(options, 1):
                self.console.print(f"  {i}. [bold]{opt.get('label')}[/] - [dim]{opt.get('description', '')}[/]")
            self.console.print("  (or type your own answer)")
            try:
                raw = self.console.input("[magenta]❯ [/]").strip()
            except (EOFError, KeyboardInterrupt):
                return None
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                answers.append({"question": q.get("question"), "answer": options[int(raw) - 1]["label"],
                                "header": q.get("header")})
            else:
                answers.append({"question": q.get("question"), "answer": raw, "header": q.get("header")})
        return answers

    async def confirm_plan(self, plan: str) -> str:
        self.console.print(Panel(Markdown(plan), title="plan", border_style="magenta"))
        choice = self.console.input(
            "[magenta]Approve plan? yes / no / edit:[/]").strip().lower()
        if choice in ("y", "yes", ""):
            return "approved"
        if choice in ("e", "edit"):
            edited = _open_editor(plan)
            if edited is not None:
                self.console.print("[green]plan updated[/]")
                return "edited"
        return "rejected"

    def todo_panel(self, todos: list[dict]) -> None:
        if not todos:
            return
        marks = {"completed": "[green]✓[/]", "in_progress": "[cyan]›[/]", "pending": "[dim]○[/]"}
        lines = [f"{marks.get(t.get('status'), '○')} #{t.get('id', '?')} "
                 f"{('[dim]' if t.get('status') == 'pending' else '[white]')}"
                 f"{t.get('subject') or t.get('content') or ''}[/]"
                 for t in todos]
        self.console.print(Panel("\n".join(lines), title="tasks", border_style="cyan", padding=(0, 1)))


def _arg_summary(name: str, args: dict) -> str:
    keys = {
        "Bash": ("command",), "Read": ("file_path",), "Edit": ("file_path", "old_string"),
        "Write": ("file_path",), "Glob": ("pattern",), "Grep": ("pattern", "path"),
        "WebFetch": ("url",), "WebSearch": ("query",),
        "Agent": ("description", "subagent_type"),
        "Skill": ("skill",), "NotebookEdit": ("notebook_path",),
        "TaskCreate": ("subject",), "TaskUpdate": ("taskId", "status"),
        "TaskGet": ("taskId",), "TaskStop": ("task_id", "shell_id"),
        "ToolSearch": ("query",), "EnterPlanMode": (), "ExitPlanMode": (),
    }
    parts = []
    for k in keys.get(name, ("command", "file_path", "url", "query", "pattern", "skill",
                             "subject", "taskId", "description")):
        if k in args:
            v = str(args[k]).replace("\n", " ")[:100]
            parts.append(v)
    if not parts and args:
        first = next(iter(args))
        parts.append(str(args[first])[:80])
    return " · ".join(parts)


def _open_editor(text: str) -> str | None:
    import subprocess
    import tempfile

    editor = os.environ.get("EDITOR", "notepad" if os.name == "nt" else "vi")
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(text)
        path = f.name
    try:
        subprocess.run([editor, path], check=False)
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
