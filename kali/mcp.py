"""MCP (Model Context Protocol) client - stdio and HTTP/SSE transports.

Config shape (same as Claude Code settings.json / --mcp-config):
  {"mcpServers": {"roblox-studio": {"command": "npx", "args": ["-y", "pkg"], "env": {}}}}
  {"mcpServers": {"unity": {"type": "http", "url": "http://127.0.0.1:8090/mcp"}}}

Tools are exposed as  mcp__<server>__<tool>  and permission rules like
"mcp__roblox-studio" (whole server) or "mcp__roblox-studio__get_console_output"
(single tool) work in permissions.allow/deny.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "2025-06-18"
LAUNCH_TIMEOUT = 30.0
CALL_TIMEOUT = 120.0

# asyncio's default subprocess StreamReader limit is 64 KiB. MCP servers with
# large tool catalogs emit a single JSON line far bigger than that (Roblox
# Studio's tools/list is ~87 KB), which makes readline() raise
# LimitOverrunError and the response never arrives. 16 MiB is plenty.
STREAM_LIMIT = 16 * 1024 * 1024

MAX_DESCRIPTION = 2000


@dataclass
class McpTool:
    server: str
    name: str          # bare tool name from the server
    qualified: str     # mcp__<server>__<name>
    description: str = ""
    input_schema: dict = field(default_factory=dict)


class StdioTransport:
    """JSON-RPC 2.0 over a subprocess's stdin/stdout (newline-delimited)."""

    def __init__(self, command: str, args: list[str], env: dict | None = None, cwd: str | None = None):
        self.command, self.args, self.env, self.cwd = command, args, env or {}, cwd
        self.proc: asyncio.subprocess.Process | None = None
        self._pending: dict[int | str, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._next_id = 1
        self.log_tail: list[str] = []
        # Server-initiated notifications (e.g. notifications/tools/list_changed)
        self.on_notification = None

    async def start(self) -> None:
        env = {**os.environ, **self.env}
        self.proc = await asyncio.create_subprocess_exec(
            self.command, *self.args,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, env=env, cwd=self.cwd,
            # The default StreamReader limit is 64 KiB. Servers with large
            # tool catalogs (Roblox Studio's tools/list is a single ~87 KB
            # JSON line) blow past it, and readline() then raises
            # LimitOverrunError so the response is never delivered - the
            # request just appears to hang forever. Use a generous limit.
            limit=STREAM_LIMIT,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._read_stderr())

    async def _read_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        while True:
            line = await self.proc.stderr.readline()
            if not line:
                break
            self._remember_err(line)

    async def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        while True:
            try:
                line = await self.proc.stdout.readline()
            except asyncio.LimitOverrunError as e:
                # A line longer than the stream limit: drain it and continue
                # rather than killing the reader task (which would leave every
                # in-flight request hanging forever).
                self._remember_err(f"[limit overrun: {e}]")
                try:
                    await self.proc.stdout.read(e.consumed)
                except Exception:
                    pass
                continue
            except (asyncio.IncompleteReadError, ValueError):
                break
            if not line:
                break
            try:
                msg = json.loads(line.decode("utf-8", "replace"))
            except json.JSONDecodeError:
                self._remember_err(line)
                continue
            if isinstance(msg, dict) and "id" in msg and msg.get("id") in self._pending:
                fut = self._pending.pop(msg["id"])
                if not fut.done():
                    if "error" in msg:
                        fut.set_exception(RuntimeError(msg["error"].get("message", "MCP error")))
                    else:
                        fut.set_result(msg.get("result", {}))
            elif isinstance(msg, dict) and "method" in msg:
                # server -> client notification or request
                if self.on_notification:
                    try:
                        self.on_notification(msg)
                    except Exception:
                        pass

    def _remember_err(self, line: bytes) -> None:
        text = line.decode("utf-8", "replace").strip()
        if text:
            self.log_tail.append(text)
            self.log_tail = self.log_tail[-20:]

    async def request(self, method: str, params: dict | None = None, timeout: float = LAUNCH_TIMEOUT) -> dict:
        if not self.proc:
            raise RuntimeError("transport not started")
        rid = self._next_id
        self._next_id += 1
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        msg = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg).encode() + b"\n")
        await self.proc.stdin.drain()
        return await asyncio.wait_for(fut, timeout=timeout)

    async def notify(self, method: str, params: dict | None = None) -> None:
        if not self.proc:
            return
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        try:
            self.proc.stdin.write(json.dumps(msg).encode() + b"\n")
            await self.proc.stdin.drain()
        except Exception:
            pass

    async def close(self) -> None:
        for task in (self._reader_task, getattr(self, "_stderr_task", None)):
            if task:
                task.cancel()
        self._reader_task = None
        self._stderr_task = None
        proc = self.proc
        self.proc = None
        if proc and proc.returncode is None:
            self._kill_tree(proc)
            # Give the transport a beat to notice the pipes closed. Without
            # this, asyncio's Proactor emits "unclosed transport" warnings on
            # shutdown (the child may still hold the handles for a moment).
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except (asyncio.TimeoutError, Exception):
                pass
        # Close the pipes so asyncio doesn't emit "unclosed transport" warnings.
        if proc:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except Exception:
                    pass

    @staticmethod
    def _kill_tree(proc) -> None:
        """Kill a subprocess AND its children.

        Servers are often launched via `cmd.exe /c wrapper.bat`, so killing
        only the wrapper orphans the real server, which keeps the stdio pipe
        handles open and makes asyncio warn about an unclosed transport.
        """
        pid = proc.pid
        # taskkill /T kills the process tree; /F is force.
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10)
            return
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            pass
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            pass


class HttpTransport:
    """Streamable-HTTP / SSE transport for remote MCP servers."""

    def __init__(self, url: str, headers: dict | None = None):
        self.url, self.headers = url, headers or {}
        self._next_id = 1

    async def start(self) -> None:  # stateless per request
        pass

    async def request(self, method: str, params: dict | None = None, timeout: float = CALL_TIMEOUT) -> dict:
        import httpx

        rid = self._next_id
        self._next_id += 1
        msg: dict = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        headers = {"Accept": "application/json, text/event-stream", **self.headers}
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=15.0)) as client:
            resp = await client.post(self.url, json=msg, headers=headers)
            if resp.status_code >= 400:
                raise RuntimeError(f"MCP HTTP {resp.status_code}: {resp.text[:300]}")
            ctype = resp.headers.get("content-type", "")
            if "text/event-stream" in ctype:
                result, done = None, False
                for line in resp.text.splitlines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        payload = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    if payload.get("id") == rid:
                        if "error" in payload:
                            raise RuntimeError(payload["error"].get("message", "MCP error"))
                        result, done = payload.get("result", {}), True
                        break
                if not done:
                    raise RuntimeError("MCP stream ended without a response")
                return result or {}
            data = resp.json()
            if "error" in data:
                raise RuntimeError(data["error"].get("message", "MCP error"))
            return data.get("result", {})

    async def notify(self, method: str, params: dict | None = None) -> None:
        try:
            import httpx

            msg: dict = {"jsonrpc": "2.0", "method": method}
            if params is not None:
                msg["params"] = params
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(self.url, json=msg, headers={"Accept": "application/json", **self.headers})
        except Exception:
            pass

    async def close(self) -> None:
        pass


class McpServer:
    def __init__(self, name: str, cfg: dict, cwd: str | None = None):
        self.name = name
        self.cfg = cfg
        self.cwd = cwd
        self.tools: dict[str, McpTool] = {}
        self.status = "disconnected"  # disconnected|connected|error
        self.error: str = ""
        self.pending_tools: bool = False
        self._transport: StdioTransport | HttpTransport | None = None
        self._refresh_task: asyncio.Task | None = None
        self.on_tools_updated = None  # callback(server) when the tool list changes

    def _handle_notification(self, msg: dict) -> None:
        method = msg.get("method", "")
        if method in ("notifications/tools/list_changed", "notifications/tools/list_changed/"
                      "notifications/tools/list_changed"):
            # The server's tool list changed (e.g. Roblox Studio attached).
            # Re-fetch it in the background so the UI updates without blocking.
            self._schedule_refresh()
        elif method == "notifications/tools/list_changed":
            self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        if self._refresh_task and not self._refresh_task.done():
            return
        try:
            self._refresh_task = asyncio.create_task(self._refresh_tools())
        except RuntimeError:
            pass

    async def _refresh_tools(self) -> None:
        try:
            result = await self._transport.request("tools/list", {}, timeout=30)  # type: ignore[union-attr]
        except Exception:
            return
        new_tools: dict[str, McpTool] = {}
        for t in result.get("tools") or []:
            name = t.get("name", "")
            if not name:
                continue
            new_tools[name] = McpTool(
                server=self.name, name=name,
                qualified=f"mcp__{self.name}__{name}",
                description=(t.get("description") or "")[:MAX_DESCRIPTION],
                input_schema=t.get("inputSchema") or {"type": "object"},
            )
        if new_tools and new_tools != self.tools:
            self.tools = new_tools
            self.pending_tools = False
            self.error = ""
            if self.on_tools_updated:
                try:
                    self.on_tools_updated(self)
                except Exception:
                    pass

    def _make_transport(self):
        stype = (self.cfg.get("type") or "stdio").lower()
        if stype in ("http", "sse", "streamable-http"):
            headers = self.cfg.get("headers") or {}
            return HttpTransport(self.cfg["url"], headers)
        command = self.cfg.get("command")
        if not command:
            raise ValueError(f"server '{self.name}' has no command or url")
        args = [str(a) for a in (self.cfg.get("args") or [])]
        env = {k: str(v) for k, v in (self.cfg.get("env") or {}).items()}
        return StdioTransport(command, args, env, self.cwd)

    async def connect(self) -> None:
        try:
            self._transport = self._make_transport()
            if isinstance(self._transport, StdioTransport):
                self._transport.on_notification = self._handle_notification
            await self._transport.start()
            await self._transport.request(
                "initialize",
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "kali-code", "version": "1.0.0"},
                },
            )
            await self._transport.notify("notifications/initialized")
            # cfg["timeout"] is in milliseconds (matches OpenCode's convention);
            # default 120s covers uvx/npm cold starts.
            init_timeout = min(int(self.cfg.get("timeout") or 120000), 600000) / 1000
            # tools/list gets its own (shorter) budget; a server that answers
            # initialize but stalls on tools/list (e.g. Roblox's bridge when
            # another MCP client holds the Studio plugin) stays "connected"
            # with zero tools instead of failing startup.
            tools_timeout = min(init_timeout, int(self.cfg.get("toolsTimeout") or 30000) / 1000)
            self.status = "connected"
            self.error = ""
            try:
                result = await self._transport.request("tools/list", {}, timeout=tools_timeout)
            except Exception as e:
                # Some servers (Roblox Studio) answer initialize immediately but
                # hold tools/list until their host app attaches a client. The
                # transport stays alive: when the server pushes
                # notifications/tools/list_changed we refresh automatically.
                self.pending_tools = True
                self.error = (
                    f"handshake OK, but tools/list timed out after {int(tools_timeout)}s "
                    f"({type(e).__name__}). The server may be waiting on its host app "
                    f"(e.g. Roblox Studio attached to another MCP client). "
                    f"Kali stays connected and will pick up the tools automatically "
                    f"when the server notifies."
                )
                return
            self.tools = {}
            for t in result.get("tools") or []:
                name = t.get("name", "")
                if not name:
                    continue
                desc = (t.get("description") or "")[:MAX_DESCRIPTION]
                self.tools[name] = McpTool(
                    server=self.name, name=name,
                    qualified=f"mcp__{self.name}__{name}",
                    description=desc, input_schema=t.get("inputSchema") or {"type": "object"},
                )
        except Exception as e:
            self.status = "error"
            self.error = str(e)[:500]
            self.tools = {}
            if isinstance(self._transport, StdioTransport):
                tail = "\n".join(self._transport.log_tail[-5:])
                if tail:
                    self.error += f"\nserver stderr:\n{tail}"

    async def call(self, tool_name: str, arguments: dict) -> str:
        if self.status != "connected" or tool_name not in self.tools:
            await self.connect()
        if self.status != "connected":
            return f"Error: MCP server '{self.name}' unavailable: {self.error or 'not connected'}"
        try:
            result = await self._transport.request("tools/call", {  # type: ignore[union-attr]
                "name": tool_name,
                "arguments": arguments,
            }, timeout=CALL_TIMEOUT)
        except Exception as e:
            self.status = "error"
            self.error = str(e)
            return f"Error calling {self.name}/{tool_name}: {e}"
        return render_mcp_result(result)

    async def close(self) -> None:
        if self._transport:
            try:
                await self._transport.notify("notifications/cancelled", {})
            except Exception:
                pass
            await self._transport.close()


def render_mcp_result(result: dict) -> str:
    """Flatten a tools/call result: content items, isError, structuredContent."""
    if not isinstance(result, dict):
        return str(result)
    if result.get("isError"):
        texts = [_content_text(c) for c in result.get("content", [])]
        msg = "\n".join(t for t in texts if t) or "tool reported an error"
        return f"Error: {msg}"
    parts: list[str] = []
    for item in result.get("content", []):
        t = _content_text(item)
        if t:
            parts.append(t)
        if item.get("type") == "image":
            parts.append(f"[image: {item.get('mimeType', 'unknown')}]")
    if not parts and result.get("structuredContent"):
        parts.append(json.dumps(result["structuredContent"], indent=2)[:10000])
    return "\n".join(parts) or "(empty result)"


def _content_text(item: dict) -> str:
    if item.get("type") == "text":
        return item.get("text", "")
    if item.get("type") == "resource":
        res = item.get("resource", {})
        return str(res.get("text", ""))[:5000]
    return ""


class McpManager:
    """Owns all configured servers and the merged tool namespace."""

    def __init__(self) -> None:
        self.servers: dict[str, McpServer] = {}
        self.tools: dict[str, McpTool] = {}
        self.on_tools_updated = None  # callback(server) when a server's tools change

    @staticmethod
    def collect_configs(settings: dict, extra_files: list[str], strict: bool = False) -> dict[str, dict]:
        """Merge MCP server definitions from settings + --mcp-config files.

        strict=True  -> ONLY the --mcp-config files are used (settings ignored),
                        matching Claude Code's --strict-mcp-config.
        """
        merged: dict[str, dict] = {}
        sources = [_load_mcp_file(f) for f in extra_files]
        if not strict:
            sources.insert(0, settings)
        for source in sources:
            for name, cfg in (source.get("mcpServers") or {}).items():
                if cfg is None:
                    merged.pop(name, None)
                else:
                    merged[name] = cfg
        return merged

    async def connect_all(self, configs: dict[str, dict], cwd: str | None = None) -> list[str]:
        """Connect to every server concurrently; returns human-readable status lines."""
        self.servers = {name: McpServer(name, cfg, cwd) for name, cfg in configs.items()}
        for s in self.servers.values():
            s.on_tools_updated = self._server_tools_updated
        if not self.servers:
            return []
        await asyncio.gather(*(s.connect() for s in self.servers.values()))
        self._rebuild_tools()
        lines = []
        for name, s in self.servers.items():
            if s.status == "connected":
                if s.pending_tools:
                    lines.append(f"  {name}: connected (waiting for host app to attach tools)")
                else:
                    lines.append(f"  {name}: connected ({len(s.tools)} tools)")
            else:
                first = s.error.splitlines()[0] if s.error else "failed"
                lines.append(f"  {name}: failed - {first}")
        return lines

    def _rebuild_tools(self) -> None:
        self.tools = {}
        for server in self.servers.values():
            for t in server.tools.values():
                self.tools[t.qualified] = t

    def _server_tools_updated(self, server: McpServer) -> None:
        self._rebuild_tools()
        if self.on_tools_updated:
            try:
                self.on_tools_updated(server)
            except Exception:
                pass

    async def close_all(self) -> None:
        await asyncio.gather(*(s.close() for s in self.servers.values()), return_exceptions=True)


def _load_mcp_file(path: str) -> dict:
    try:
        with open(Path(path).expanduser(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"warning: could not load MCP config {path}: {e}", file=sys.stderr)
        return {}
