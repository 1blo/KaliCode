"""Mobile companion server: expose the Kali Code agent over WebSocket.

Runs the existing agent loop unchanged and relays every UI event to the phone.
The phone sends prompts; the server streams text back and, when the agent needs
permission, parks the turn until the phone answers.

Designed for a stateless-ish host (Render free tier): the working tree is
cloned from git at boot, so there is no persistent disk requirement.

Protocol (JSON over WebSocket, one object per message)
-------------------------------------------------------
client -> server
  {"type": "auth",     "token": "..."}
  {"type": "prompt",   "text": "...", "session": "..."}
  {"type": "reply",    "id": "<request id>", "answer": "allow"|"deny"|"always"|...}
  {"type": "answer",   "id": "<question id>", "value": "..."}
  {"type": "interrupt"}
  {"type": "ping"}

server -> client
  {"type": "ready",        "session": "...", "model": "...", "cwd": "..."}
  {"type": "thinking"}
  {"type": "text",         "text": "..."}
  {"type": "tool_start",   "name": "...", "args": {...}}
  {"type": "tool_result",  "name": "...", "ok": true, "output": "...", "elapsed": 1.2}
  {"type": "tool_denied",  "name": "...", "reason": "..."}
  {"type": "permission",   "id": "...", "name": "...", "args": {...}, "summary": "..."}
  {"type": "question",     "id": "...", "questions": [...]}
  {"type": "plan",         "id": "...", "plan": "..."}
  {"type": "error",        "message": "..."}
  {"type": "done",         "text": "...", "usage": {...}}
  {"type": "pong"}
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agent import Agent
from .config import AgentConfig, load_settings
from .llm import StreamEvent


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
def resolve_token() -> str:
    """The shared secret the phone must present.

    Order: KALI_SERVER_TOKEN env -> ~/.kali/settings.json -> generated.
    A generated token is printed once at startup so the operator can paste it
    into the PWA. It is never written to disk (the free-tier host has no
    persistent disk anyway, so it would not survive a restart).
    """
    token = os.environ.get("KALI_SERVER_TOKEN", "").strip()
    if token:
        return token
    try:
        settings = load_settings()
        token = str((settings.get("server") or {}).get("token", "")).strip()
        if token:
            return token
    except Exception:
        pass
    return secrets.token_urlsafe(32)


def _constant_time_eq(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# --------------------------------------------------------------------------- #
# Remote UI - implements the same contract as kali.ui.ConsoleUI
# --------------------------------------------------------------------------- #
class RemoteUI:
    """Collects agent UI events and forwards them to the connected phone.

    Blocking interactions (permission prompts, AskUserQuestion, plan approval)
    are parked on an asyncio Event until the phone replies.
    """

    def __init__(self, conn: "Connection"):
        self.conn = conn
        self._spinner_active = False
        self._pending_thinking: list[str] = []

    # --------------------------------------------------------------- spinner
    def start_spinner(self, text: str = "thinking...") -> None:
        if self._spinner_active:
            return
        self._spinner_active = True
        self.conn.emit({"type": "thinking", "text": text})

    def stop_spinner(self) -> None:
        self._spinner_active = False

    def refresh_spinner(self, text: str = "thinking...") -> None:
        self.conn.emit({"type": "thinking", "text": text})

    # ------------------------------------------------------------- streaming
    def on_stream_event(self, ev: StreamEvent) -> None:
        if ev.type == "thinking":
            self._pending_thinking.append(ev.text)
        elif ev.type == "text":
            if self._pending_thinking:
                self.conn.emit({"type": "thinking",
                                "text": "".join(self._pending_thinking)})
                self._pending_thinking = []
            self.conn.emit({"type": "text", "text": ev.text})
        elif ev.type == "error":
            self.on_error(ev.text)

    def assistant_end(self) -> None:
        self.stop_spinner()

    def banner(self, model: str, version: str, cwd: str) -> None:
        self.conn.emit({"type": "ready", "model": model, "version": version, "cwd": cwd})

    # ----------------------------------------------------------------- errors
    def on_error(self, message: str) -> None:
        self.conn.emit({"type": "error", "message": str(message)})

    # ------------------------------------------------------------------ tools
    def on_tool_start(self, name: str, args: dict) -> None:
        self.stop_spinner()
        self.conn.emit({"type": "tool_start", "name": name, "args": _safe_args(args)})

    def on_tool_result(self, name: str, args: dict, result, elapsed: float) -> None:
        self.stop_spinner()
        out = getattr(result, "output", "") or ""
        self.conn.emit({
            "type": "tool_result",
            "name": name,
            "ok": not getattr(result, "error", False),
            "output": out[:8000],
            "elapsed": round(float(elapsed), 2),
        })

    def on_tool_denied(self, name: str, args: dict, reason: str) -> None:
        self.conn.emit({"type": "tool_denied", "name": name, "reason": reason})

    def on_subagent_done(self, description: str, final: str, background: bool = False) -> None:
        self.conn.emit({"type": "subagent", "description": description,
                        "final": (final or "")[:4000], "background": background})

    def on_mcp_tools_ready(self, server_name: str, count: int) -> None:
        self.conn.emit({"type": "mcp", "server": server_name, "count": count})

    def on_compact_start(self) -> None:
        self.conn.emit({"type": "thinking", "text": "compacting context..."})

    def on_compact_end(self) -> None:
        self.conn.emit({"type": "thinking", "text": "compaction complete"})

    # ---------------------------------------------------------------- prompts
    async def confirm_tool(self, name: str, args: dict, tool) -> bool:
        req_id = uuid.uuid4().hex[:12]
        self.conn.emit({
            "type": "permission",
            "id": req_id,
            "name": name,
            "args": _safe_args(args),
            "summary": _arg_summary(name, args),
        })
        answer = await self.conn.wait_for_reply(req_id)
        if answer in ("allow", "yes", "y", ""):
            if answer == "always":
                agent = getattr(self.conn, "agent", None)
                if agent is not None:
                    with contextlib.suppress(Exception):
                        agent.permissions.remember_allow(name, args)
            return True
        return False

    async def ask_questions(self, questions: list[dict]) -> list[dict] | None:
        answers: list[dict] = []
        for q in questions:
            req_id = uuid.uuid4().hex[:12]
            self.conn.emit({"type": "question", "id": req_id, "question": q})
            value = await self.conn.wait_for_reply(req_id)
            if value is None:
                return None
            answers.append({"question": q.get("question"), "answer": value,
                            "header": q.get("header")})
        return answers

    async def confirm_plan(self, plan: str) -> str:
        req_id = uuid.uuid4().hex[:12]
        self.conn.emit({"type": "plan", "id": req_id, "plan": plan})
        answer = await self.conn.wait_for_reply(req_id)
        if answer in ("approve", "approved", "yes", "y", ""):
            return "approved"
        if answer == "edit":
            return "edited"
        return "rejected"


def _safe_args(args: Any) -> Any:
    """Make tool arguments JSON-safe and bounded."""
    if not isinstance(args, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in args.items():
        if isinstance(v, str):
            out[k] = v[:2000]
        elif isinstance(v, (int, float, bool)) or v is None:
            out[k] = v
        else:
            try:
                out[k] = json.loads(json.dumps(v, default=str))[:2000]
            except Exception:
                out[k] = str(v)[:2000]
    return out


def _arg_summary(name: str, args: dict) -> str:
    """One-line human summary of a tool call (mirrors kali.ui._arg_summary)."""
    if not isinstance(args, dict):
        return ""
    for key in ("command", "file_path", "path", "notebook_path", "url",
                "pattern", "query", "skill", "description"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            val = val.strip()
            return val if len(val) <= 120 else val[:117] + "..."
    return ""


# --------------------------------------------------------------------------- #
# Connection - one phone
# --------------------------------------------------------------------------- #
@dataclass(eq=False)
class Connection:
    ws: Any
    token: str
    agent: Agent | None = None
    _replies: dict[str, asyncio.Future] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _busy: bool = False

    def emit(self, payload: dict) -> None:
        """Fire-and-forget JSON send (never raises into the agent)."""
        async def _send():
            try:
                await self.ws.send_text(json.dumps(payload, default=str))
            except Exception:
                pass
        asyncio.create_task(_send())

    async def wait_for_reply(self, req_id: str, timeout: float = 900.0) -> str | None:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        async with self._lock:
            self._replies[req_id] = fut
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            async with self._lock:
                self._replies.pop(req_id, None)

    async def resolve(self, req_id: str, value: str) -> bool:
        async with self._lock:
            fut = self._replies.get(req_id)
        if fut is None or fut.done():
            return False
        fut.set_result(value)
        return True

    async def send(self, payload: dict) -> None:
        await self.ws.send_text(json.dumps(payload, default=str))


# --------------------------------------------------------------------------- #
# Server
# --------------------------------------------------------------------------- #
class MobileServer:
    """Starlette app exposing the agent over WebSocket + a small REST API."""

    def __init__(self, token: str | None = None, cwd: str | None = None,
                 model: str | None = None, permission_mode: str | None = None):
        self.token = token or resolve_token()
        self.cwd = Path(cwd or os.environ.get("KALI_WORKSPACE", os.getcwd())).resolve()
        self.model = model or os.environ.get("KALI_MODEL") or ""
        self.permission_mode = permission_mode or os.environ.get("KALI_PERMISSION_MODE", "default")
        self._conns: list[Connection] = []

    # ------------------------------------------------------------------ setup
    def _make_agent(self) -> Agent:
        settings = load_settings()
        cfg = AgentConfig.from_settings(settings)
        if self.model:
            cfg.model = self.model
        if self.permission_mode:
            cfg.permission_mode = self.permission_mode
        cfg.settings = settings
        agent = Agent(cfg, ui=None)
        agent.ui = RemoteUI(self._active_conn)  # type: ignore[attr-defined]
        agent.ui.agent = agent  # type: ignore[attr-defined]
        agent.ui.conn = self._active_conn  # type: ignore[attr-defined]
        return agent

    # ------------------------------------------------------------------- http
    async def health(self, request):
        from starlette.responses import JSONResponse

        return JSONResponse({
            "ok": True,
            "service": "kali-code",
            "version": _version(),
            "connections": len(self._conns),
            "workspace": str(self.cwd),
        })

    async def root(self, request):
        from starlette.responses import FileResponse
        from .resources import resource_dir

        p = Path(resource_dir()) / "mobile" / "index.html"
        if p.exists():
            return FileResponse(str(p))
        from starlette.responses import PlainTextResponse

        return PlainTextResponse("Kali Code mobile companion - PWA assets missing.")

    async def static_asset(self, request):
        """Serve a file from kali/mobile (manifest, icons, app.js, sw.js)."""
        from starlette.exceptions import HTTPException
        from starlette.responses import FileResponse
        from .resources import resource_dir

        # These are fixed routes, so derive the filename from the path.
        name = str(request.url.path).strip("/")
        if not name or "/" in name or ".." in name:
            raise HTTPException(status_code=404)
        p = Path(resource_dir()) / "mobile" / name
        if not p.exists() or not p.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(str(p))

    async def push_subscribe(self, request):
        """Store a Web Push subscription for later notifications."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        self._push_subs.append(body)
        return _json({"ok": True, "count": len(self._push_subs)})

    _push_subs: list[dict] = []

    # -------------------------------------------------------------- websocket
    async def websocket(self, websocket):
        await websocket.accept()
        token = self.token
        conn = Connection(ws=websocket, token=token)
        self._active_conn = conn  # type: ignore[attr-defined]

        # ---- auth handshake (first message must carry the token)
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            hello = json.loads(raw)
        except Exception:
            await conn.send({"type": "error", "message": "handshake timeout"})
            await websocket.close()
            return

        supplied = str(hello.get("token", "")) if isinstance(hello, dict) else ""
        if not supplied or not _constant_time_eq(supplied, token):
            await conn.send({"type": "error", "message": "unauthorized"})
            with contextlib.suppress(Exception):
                await websocket.close()
            return

        self._conns.append(conn)
        try:
            agent = self._make_agent()
            conn.agent = agent
            agent.ui.conn = conn  # type: ignore[attr-defined]
            await conn.send({
                "type": "ready",
                "session": agent.session_id,
                "model": agent.cfg.model,
                "cwd": str(self.cwd),
                "version": _version(),
            })
            await self._pump(websocket, conn, agent)
        except Exception as e:
            with contextlib.suppress(Exception):
                await conn.send({"type": "error", "message": f"{type(e).__name__}: {e}"})
        finally:
            if conn in self._conns:
                self._conns.remove(conn)
            with contextlib.suppress(Exception):
                await websocket.close()

    async def _pump(self, websocket, conn: Connection, agent: Agent) -> None:
        """Read client messages.

        A turn runs as a background task so this loop stays free to read the
        phone's replies (permission approvals, question answers). Blocking here
        would deadlock: the agent parks on wait_for_reply() while the only
        reader of the reply is this loop.
        """
        turn_task: asyncio.Task | None = None

        while True:
            try:
                raw = await websocket.receive_text()
            except Exception:
                if turn_task and not turn_task.done():
                    turn_task.cancel()
                return
            try:
                msg = json.loads(raw)
            except Exception:
                conn.emit({"type": "error", "message": "bad json"})
                continue
            mtype = msg.get("type")

            if mtype == "ping":
                await conn.send({"type": "pong"})
            elif mtype == "prompt":
                if conn._busy:
                    conn.emit({"type": "error", "message": "a turn is already running"})
                    continue
                conn._busy = True
                turn_task = asyncio.create_task(
                    self._run_turn(conn, agent, str(msg.get("text", ""))))
            elif mtype == "reply":
                await conn.resolve(str(msg.get("id", "")), str(msg.get("answer", "")))
            elif mtype == "answer":
                await conn.resolve(str(msg.get("id", "")), str(msg.get("value", "")))
            elif mtype == "interrupt":
                agent.interrupted = True
                conn.emit({"type": "interrupted"})
            elif mtype == "reset":
                agent.messages.clear()
                agent.session_id = uuid.uuid4().hex[:16]
                conn.emit({"type": "ready", "session": agent.session_id,
                           "model": agent.cfg.model, "cwd": str(self.cwd)})

    async def _run_turn(self, conn: Connection, agent: Agent, text: str) -> None:
        if not text.strip():
            conn._busy = False
            return
        t0 = time.time()
        try:
            result = await agent.run_turn(text)
            await conn.send({
                "type": "done",
                "text": result.text,
                "usage": result.usage,
                "elapsed": round(time.time() - t0, 2),
                "session": agent.session_id,
            })
        except asyncio.CancelledError:
            raise
        except Exception as e:
            with contextlib.suppress(Exception):
                await conn.send({"type": "error", "message": f"{type(e).__name__}: {e}"})
        finally:
            conn._busy = False


def _version() -> str:
    try:
        from . import __version__

        return __version__
    except Exception:
        return "0.0.0"


def _json(payload: dict):
    from starlette.responses import JSONResponse

    return JSONResponse(payload)


# --------------------------------------------------------------------------- #
# ASGI app factory
# --------------------------------------------------------------------------- #
def build_app(token: str | None = None, cwd: str | None = None,
              model: str | None = None, permission_mode: str | None = None):
    """Return a Starlette ASGI app plus the MobileServer instance."""
    from starlette.applications import Starlette
    from starlette.routing import Route, WebSocketRoute

    server = MobileServer(token=token, cwd=cwd, model=model,
                          permission_mode=permission_mode)
    routes = [
        Route("/", server.root, methods=["GET"]),
        Route("/health", server.health, methods=["GET"]),
        Route("/push/subscribe", server.push_subscribe, methods=["POST"]),
        Route("/app.js", server.static_asset, methods=["GET"]),
        Route("/sw.js", server.static_asset, methods=["GET"]),
        Route("/manifest.json", server.static_asset, methods=["GET"]),
        Route("/icon.svg", server.static_asset, methods=["GET"]),
        Route("/icon-192.png", server.static_asset, methods=["GET"]),
        Route("/icon-512.png", server.static_asset, methods=["GET"]),
        WebSocketRoute("/ws", server.websocket),
    ]
    app = Starlette(routes=routes)
    app.state.server = server
    return app, server


def serve(host: str = "0.0.0.0", port: int = 8000, token: str | None = None,
          cwd: str | None = None, model: str | None = None,
          permission_mode: str | None = None) -> None:
    """Run the mobile companion server (blocking)."""
    import uvicorn

    app, server = build_app(token=token, cwd=cwd, model=model,
                             permission_mode=permission_mode)
    print(f"Kali Code mobile companion listening on http://{host}:{port}")
    print(f"Workspace: {server.cwd}")
    print(f"Access token: {server.token}")
    print("Paste the token into the mobile app to connect.")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Kali Code mobile companion server")
    p.add_argument("--host", default=os.environ.get("KALI_SERVER_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    p.add_argument("--token", default=None)
    p.add_argument("--cwd", default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--permission-mode", default=None)
    a = p.parse_args()
    serve(host=a.host, port=a.port, token=a.token, cwd=a.cwd,
          model=a.model, permission_mode=a.permission_mode)
