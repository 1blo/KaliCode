"""Kali Code CLI - mirrors `claude`'s flags and REPL behavior."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from . import __version__
from .agent import Agent
from .config import (AgentConfig, MODELS, DEFAULT_MODEL, SUBAGENT_MODEL,
                     apply_env, load_settings, resolve_api_key, EAGER_MCP_SERVERS)
from .slash import SlashRouter
from .ui import UI

BANNER_NOTE = "Welcome to Kali Code! Type /help for commands."


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kali",
        description="Kali Code - an accurate copy of the Claude Code agentic coding CLI",
        epilog='Examples: kali "fix the bug"   kali -p "what does this repo do"',
    )
    p.add_argument("prompt", nargs="*", help="optional initial prompt")
    p.add_argument("-p", "--print", dest="print_mode", action="store_true",
                   help="non-interactive: print response and exit")
    p.add_argument("-c", "--continue", dest="continue_session", action="store_true",
                   help="continue the most recent conversation (advisory in this build)")
    p.add_argument("-r", "--resume", dest="resume", metavar="ID", default=None)
    p.add_argument("--model", "-m", dest="model", default=None,
                   help=f"model id (default: {DEFAULT_MODEL})")
    p.add_argument("--permission-mode", dest="permission_mode",
                   choices=["default", "acceptEdits", "plan", "bypassPermissions"], default=None)
    p.add_argument("--allowedTools", "--allowed-tools", dest="allowed_tools",
                   nargs="+", default=[], metavar="TOOL")
    p.add_argument("--disallowedTools", "--disallowed-tools", dest="disallowed_tools",
                   nargs="+", default=[], metavar="TOOL")
    p.add_argument("--verbose", action="store_true", help="show thinking and full tool output")
    p.add_argument("--max-turns", type=int, default=0, dest="max_turns")
    p.add_argument("--system-prompt", dest="system_prompt", default=None,
                   help="replace the whole system prompt")
    p.add_argument("--append-system-prompt", dest="append_system_prompt", default=None)
    p.add_argument("--dangerously-skip-permissions", action="store_true",
                   help="bypass all permission prompts")
    p.add_argument("--mcp-config", dest="mcp_config", action="append", default=[],
                   metavar="FILE", help="extra MCP config JSON file (repeatable)")
    p.add_argument("--strict-mcp-config", action="store_true", dest="strict_mcp",
                   help="only use --mcp-config servers, ignore settings")
    p.add_argument("--add-dir", dest="add_dirs", action="append", default=[])
    p.add_argument("--agents", dest="agents_files", action="append", default=[],
                   help="load custom agent definitions from file")
    p.add_argument("--output-format", choices=["text", "json", "stream-json"], default="text")
    p.add_argument("--input-format", choices=["text", "stream-json"], default="text")
    p.add_argument("--serve", action="store_true",
                   help="run the server instead of the REPL (for the desktop app, "
                        "the phone or the APK)")
    p.add_argument("--serve-host", default="0.0.0.0", dest="serve_host",
                   help="bind address for --serve (default: 0.0.0.0)")
    p.add_argument("--serve-port", type=int, default=8000, dest="serve_port",
                   help="port for --serve (default: 8000)")
    p.add_argument("--serve-token", default=None, dest="serve_token",
                   help="access token the phone must present (default: generated)")
    p.add_argument("--gui", action="store_true",
                   help="launch the desktop graphical interface")
    p.add_argument("--gui-port", type=int, default=0, dest="gui_port",
                   help="port for --gui (default: an available one)")
    p.add_argument("--version", action="version", version=f"Kali Code {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    # Windows pipes default to cp1252 and rich's unicode glyphs crash it.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        print()
        return 130


async def _amain(args) -> int:
    settings = load_settings()
    apply_env(settings)

    # Desktop graphical interface.
    if args.gui:
        from .desktop_shell import run_gui

        mode = args.permission_mode or settings.get("permissionMode", "default")
        return run_gui(cwd=os.getcwd(), port=args.gui_port,
                       token=args.serve_token,
                       model=args.model or settings.get("model"),
                       permission_mode=mode)

    # Mobile companion server: a different entry point, not a REPL mode.
    if args.serve:
        from .serve import serve

        serve(host=args.serve_host, port=args.serve_port,
              token=args.serve_token, cwd=os.getcwd(),
              model=args.model, permission_mode=args.permission_mode)
        return 0

    mode = args.permission_mode or settings.get("permissionMode", "default")
    if args.dangerously_skip_permissions:
        mode = "bypassPermissions"

    cfg = AgentConfig(
        model=args.model or settings.get("model") or DEFAULT_MODEL,
        max_tokens=int((settings.get("env") or {}).get("KALI_MAX_TOKENS", 16384)),
        reasoning_effort=(settings.get("env") or {}).get("KALI_REASONING_EFFORT", "low"),
        permission_mode=mode,
        allowed_tools=list(args.allowed_tools),
        disallowed_tools=list(args.disallowed_tools),
        system_prompt=args.system_prompt,
        append_system_prompt=args.append_system_prompt,
        max_turns=args.max_turns,
        verbose=args.verbose,
        additional_dirs=list(args.add_dirs),
        settings=settings,
        mcp_config_files=list(args.mcp_config),
        strict_mcp=args.strict_mcp,
    )
    if cfg.model not in MODELS:
        cfg.model = DEFAULT_MODEL

    ui = UI(verbose=args.verbose)
    agent = Agent(cfg, ui=ui)
    ui.agent = agent

    if not resolve_api_key().startswith("nvapi-"):
        ui.on_error("No API key is set. Run /login or set the NVIDIA_API_KEY environment variable.")
        return 1

    # ---- Discord Rich Presence ("Using Kali Code" + timer + chat title)
    presence = None
    try:
        from .discord_presence import DiscordPresence, load_config as load_discord_config

        dcfg = load_discord_config(settings)
        if dcfg.enabled and dcfg.client_id:
            presence = DiscordPresence(dcfg)
            agent.presence = presence
            if presence.start():
                if args.verbose:
                    ui.console.print("[dim]  discord presence connected[/]")
            else:
                agent.presence = None
                presence = None
                if args.verbose and presence is not None:
                    ui.console.print(f"[dim]  discord presence unavailable: {presence.last_error}[/]")
    except Exception:
        presence = None
        agent.presence = None

    # ---- MCP connect: interactive = background (never blocks the prompt);
    #      print mode connects synchronously (no prompt to race against).
    #      --mcp-config ADDS servers on top of ~/.kali/settings.json, and
    #      --strict-mcp-config makes it exclusive.
    mcp_configs = agent.mcp.collect_configs(settings, cfg.mcp_config_files, cfg.strict_mcp)

    if mcp_configs:
        eager = [n for n in mcp_configs if n in EAGER_MCP_SERVERS]
        lazy = {n: c for n, c in mcp_configs.items() if n not in EAGER_MCP_SERVERS}

        async def _connect_eager():
            agent.mcp.on_tools_updated = agent.on_mcp_tools_updated
            with ui.console.status("[dim]connecting MCP servers...[/]"):
                statuses = await agent.mcp.connect_all({n: mcp_configs[n] for n in eager})
            agent._register_mcp_tools(eager=True)
            for line in statuses:
                ui.console.print(f"[dim]  mcp {line}[/]")

        if eager and not args.print_mode:
            asyncio.create_task(_connect_eager())
        elif eager:
            await _connect_eager()

        if lazy:
            async def _connect_lazy():
                await asyncio.sleep(2)
                agent.mcp.on_tools_updated = agent.on_mcp_tools_updated
                with ui.console.status("[dim]connecting MCP servers...[/]"):
                    statuses = await agent.mcp.connect_all(lazy)
                agent._register_mcp_tools()
                for line in statuses:
                    ui.console.print(f"[dim]  mcp {line}[/]")

            if not args.print_mode:
                asyncio.create_task(_connect_lazy())

    # ---- headless mode
    prompt = " ".join(args.prompt).strip()
    if args.print_mode:
        if not prompt:
            print("Error: --print requires a prompt", file=sys.stderr)
            await agent.mcp.close_all()
            _stop_presence(agent)
            return 1
        try:
            return await run_print(agent, prompt, args)
        finally:
            await agent.mcp.close_all()
            _stop_presence(agent)

    # ---- interactive REPL
    ui.banner(cfg.model, __version__, os.getcwd())
    ui.console.print(f"[dim]{BANNER_NOTE}[/]\n")

    router = SlashRouter(agent, ui, cli=KaliCLI(agent, ui, args))
    cli = router.cli
    try:
        if prompt:
            await process_input(agent, ui, prompt)

        ctrl_c_count = 0
        while not cli.exit:
            try:
                raw = await asyncio.get_running_loop().run_in_executor(None, ui.prompt)
                ctrl_c_count = 0
            except (KeyboardInterrupt, EOFError):
                break
            raw = raw.strip()
            if not raw:
                continue
            if raw.startswith("/"):
                await router.handle(raw)
                if cli.pending_message:
                    pending, cli.pending_message = cli.pending_message, None
                    try:
                        await process_input(agent, ui, pending)
                    except KeyboardInterrupt:
                        agent.interrupted = True
                        ui.console.print("\n[yellow]Interrupted.[/]")
                continue
            try:
                await process_input(agent, ui, raw)
            except KeyboardInterrupt:
                agent.interrupted = True
                ui.console.print("\n[yellow]Interrupted.[/]")
    finally:
        ui.console.print("[dim]Goodbye![/]")
        await agent.mcp.close_all()
        _stop_presence(agent)
    return 0


def _stop_presence(agent: Agent) -> None:
    """Clear the Discord presence when Kali exits."""
    presence = getattr(agent, "presence", None)
    if presence is not None:
        try:
            presence.stop()
        except Exception:
            pass
        agent.presence = None


class KaliCLI:
    """Shared state handed to the slash router."""

    def __init__(self, agent: Agent, ui: UI, args):
        self.agent = agent
        self.ui = ui
        self.args = args
        self.exit = False
        self.pending_message: str | None = None

    def submit_user_message(self, text: str) -> None:
        self.pending_message = text


async def process_input(agent: Agent, ui: UI, raw: str) -> None:
    # Spinner runs until the first real token arrives; then the answer
    # streams cleanly to the console.
    ui.start_spinner("thinking...")
    try:
        # Ask the model to name the chat (used by the Discord presence and
        # /title). Runs in the background so it never delays the turn.
        if agent.presence is not None and not agent._title_generated:
            asyncio.create_task(agent.generate_title(raw))
        result = await agent.run_turn(raw)
    finally:
        ui.stop_spinner()
    ui.assistant_end()
    if agent.tasks:
        ui.todo_panel(agent.tasks)
    if ui.verbose:
        ui.console.print(f"[dim]{agent.cost_line()}[/]")


async def run_print(agent: Agent, prompt: str, args) -> int:
    try:
        if args.output_format == "stream-json":
            print(json.dumps({"type": "system", "subtype": "init",
                              "model": agent.cfg.model, "session_id": agent.session_id}))
        result = await agent.run_turn(prompt)
    except KeyboardInterrupt:
        return 130
    if args.output_format == "text":
        if result.text.strip():
            print(result.text.strip())
    elif args.output_format == "json":
        print(json.dumps({
            "type": "result", "subtype": "success",
            "result": result.text.strip(),
            "session_id": agent.session_id,
            "usage": agent.total_usage,
            "tool_uses": result.tool_uses,
        }, indent=2, default=str))
    else:  # stream-json
        print(json.dumps({"type": "result", "subtype": "success",
                          "result": result.text.strip(), "usage": agent.total_usage},
                         default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
