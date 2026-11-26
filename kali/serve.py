"""Kali Code server: the agent, exposed over WebSocket and REST.

This is the core that both the desktop GUI and the Android APK talk to. The
phone and the desktop app are *clients* - neither executes the agent.

Architecture
------------
    ┌──────────────┐   HTTP + WebSocket   ┌─────────────────────────┐
    │ Desktop GUI  │◄────────────────────►│                         │
    │ Android APK  │◄────────────────────►│  kali.serve (this)      │
    │ PWA client   │◄────────────────────►│                         │
    └──────────────┘                       │  SessionRegistry        │
                                           │  └─ Agent per session  │
                                           └─────────────────────────┘

Protocol (JSON over WebSocket, one object per message)
-------------------------------------------------------
client -> server
  {"type": "auth",     "token": "..."}
  {"type": "hello",    "session": "<id>"|null, "cwd": "...", ...}
  {"type": "prompt",   "text": "...", "session": "<id>"}
  {"type": "reply",    "id": "<request id>", "answer": "allow"|"deny"|"always"}
  {"type": "answer",   "id": "<question id>", "value": "..."}
  {"type": "interrupt", "session": "<id>"}
  {"type": "new_session", "cwd": "...", "model": "...", ...}
  {"type": "switch_session", "session": "<id>"}
  {"type": "set_model", "model": "..."}
  {"type": "set_mode",  "mode": "..."}
  {"type": "reset"}
  {"type": "ping"}

server -> client
  {"type": "ready",        "session": "...", "model": "...", "cwd": "..."}
  {"type": "sessions",     "sessions": [...]}
  {"type": "thinking"}
  {"type": "text",         "text": "..."}
  {"type": "tool_start",   "name": "...", "args": {...}}
  {"type": "tool_result",  "name": "...", "ok": true, "output": "...", "elapsed": 1.2}
  {"type": "tool_denied",  "name": "...", "reason": "..."}
  {"type": "permission",   "id": "...", "name": "...", "args": {...}, "summary": "..."}
  {"type": "question",     "id": "...", "question": {...}}
  {"type": "plan",         "id": "...", "plan": "..."}
  {"type": "diff",         "path": "...", "diff": "..."}
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
from .sessions import Session, SessionRegistry


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
def resolve_token() -> str:
    """The shared secret every client must present.

    Order: KALI_SERVER_TOKEN env -> ~/.kali/settings.json -> generated.
    A generated token is printed once at startup. It is never written to disk.
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
# Remote UI - implements the same contract as kali.ui.UI
# --------------------------------------------------------------------------- #
class RemoteUI:
    """Collects agent UI events and forwards them to the connected client.

    Blocking interactions (permission prompts, AskUserQuestion, plan
    approval) are parked on an asyncio Event until the client replies.
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
    """One-line human summary of a tool call."""
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
# Connection - one client (desktop, phone, or PWA)
# --------------------------------------------------------------------------- #
@dataclass(eq=False)
class Connection:
    ws: Any
    token: str
    registry: SessionRegistry
    session: Session | None = None
    agent: Agent | None = None
    _replies: dict[str, asyncio.Future] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # ------------------------------------------------------------------ send
    def emit(self, payload: dict) -> None:
        """Fire-and-forget JSON send (never raises into the agent)."""
        async def _send():
            try:
                await self.ws.send_text(json.dumps(payload, default=str))
            except Exception:
                pass
        asyncio.create_task(_send())

    async def send(self, payload: dict) -> None:
        try:
            await self.ws.send_text(json.dumps(payload, default=str))
        except Exception:
            pass

    # ---------------------------------------------------------------- replies
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

    # --------------------------------------------------------------- sessions
    def bind(self, sess: Session) -> None:
        """Attach this connection to a session."""
        if self.session is not None:
            self.session.unsubscribe(self.emit)
        self.session = sess
        self.agent = sess.agent
        sess.subscribe(self.emit)

    def unbind(self) -> None:
        if self.session is not None:
            self.session.unsubscribe(self.emit)
        self.session = None
        self.agent = None


# --------------------------------------------------------------------------- #
# Server
# --------------------------------------------------------------------------- #
class KaliServer:
    """Starlette app exposing sessions over WebSocket + REST."""

    def __init__(self, token: str | None = None, cwd: str | None = None,
                 model: str | None = None, permission_mode: str | None = None):
        self.token = token or resolve_token()
        self.cwd = Path(cwd or os.environ.get("KALI_WORKSPACE", os.getcwd())).resolve()
        self.model = model or os.environ.get("KALI_MODEL") or ""
        self.permission_mode = permission_mode or os.environ.get("KALI_PERMISSION_MODE", "default")
        self.registry = SessionRegistry(
            default_cwd=self.cwd,
            default_model=self.model,
            default_permission_mode=self.permission_mode,
        )
        self._conns: list[Connection] = []
        self._push_subs: list[dict] = []

    # ------------------------------------------------------------------- http
    def connected_clients(self) -> int:
        """How many clients are currently attached."""
        return len(self._conns)

    async def health(self, request):
        from starlette.responses import JSONResponse

        return JSONResponse({
            "ok": True,
            "service": "kali-code",
            "version": _version(),
            "connections": len(self._conns),
            "sessions": len(self.registry.list(include_archived=True)),
            "workspace": str(self.cwd),
        })

    async def root(self, request):
        """Serve the desktop GUI (or the PWA on a phone)."""
        from .resources import ui_base_dir

        base = Path(ui_base_dir())
        # The desktop UI wins on a large screen; the PWA is the mobile build.
        ua = str(request.headers.get("user-agent", "")).lower()
        is_mobile = any(m in ua for m in ("android", "iphone", "mobile"))
        name = "mobile/index.html" if is_mobile else "desktop/index.html"
        p = base / name
        if p.exists():
            return _ui_response(p)
        p = base / "mobile" / "index.html"
        if p.exists():
            return _ui_response(p)
        from starlette.responses import PlainTextResponse

        return PlainTextResponse("Kali Code - UI assets missing.")

    async def static_asset(self, request):
        """Serve a file from kali/desktop or kali/mobile.

        The bare routes (`/app.js`, `/style.css`, `/icon.svg`, ...) are
        ambiguous: both UIs have a file with that name. The desktop UI is
        served at `/desktop/...` and the mobile shell links its assets
        relatively, so a bare request is resolved by the User-Agent.
        """
        from starlette.exceptions import HTTPException
        from starlette.responses import FileResponse
        from .resources import ui_base_dir

        rel = str(request.url.path).strip("/")
        if not rel or ".." in rel:
            raise HTTPException(status_code=404)

        base = Path(ui_base_dir())
        parts = rel.split("/")

        if len(parts) == 1:
            # A bare asset name - pick the shell that matches the client.
            ua = str(request.headers.get("user-agent", "")).lower()
            is_mobile = any(m in ua for m in ("android", "iphone", "mobile"))
            order = ("mobile", "desktop") if is_mobile else ("desktop", "mobile")
            for sub in order:
                cand = base / sub / rel
                if cand.exists() and cand.is_file():
                    return _ui_response(cand)
            raise HTTPException(status_code=404)

        if parts[0] not in ("desktop", "mobile"):
            raise HTTPException(status_code=404)
        cand = base.joinpath(*parts)
        if not cand.exists() or not cand.is_file():
            raise HTTPException(status_code=404)
        return _ui_response(cand)

    async def push_subscribe(self, request):
        """Store a Web Push subscription for later notifications."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        self._push_subs.append(body)
        return _json({"ok": True, "count": len(self._push_subs)})

    # ------------------------------------------------------------------- REST
    async def api_sessions(self, request):
        """List sessions."""
        include_archived = request.query_params.get("archived") == "1"
        items = [i.to_dict() for i in self.registry.list(include_archived)]
        return _json({"sessions": items})

    async def api_session_create(self, request):
        """Create a session."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        sess = self.registry.create(
            cwd=body.get("cwd"),
            model=body.get("model"),
            permission_mode=body.get("permissionMode"),
            title=body.get("title"),
            worktree=bool(body.get("worktree")),
        )
        return _json({"session": sess.info.to_dict()})

    async def api_session_get(self, request):
        sid = request.path_params.get("sid", "")
        sess = self.registry.get(sid)
        if not sess:
            return _json({"error": "not found"}, status=404)
        self.registry.refresh_usage(sess)
        return _json({"session": sess.info.to_dict()})

    async def api_session_delete(self, request):
        sid = request.path_params.get("sid", "")
        ok = self.registry.delete(sid)
        return _json({"ok": ok})

    async def api_session_archive(self, request):
        sid = request.path_params.get("sid", "")
        ok = self.registry.archive(sid)
        return _json({"ok": ok})

    async def api_diff(self, request):
        """Unified diff for a session's changed files."""
        sid = request.query_params.get("session", "")
        sess = self.registry.get(sid)
        if not sess or not sess.agent:
            return _json({"error": "not found"}, status=404)
        diffs = []
        for entry in sess.agent.edits[:50]:
            try:
                path = entry.split(":", 1)[1]
                diffs.append({"path": path, "diff": _file_diff(path)})
            except Exception:
                continue
        return _json({"diffs": diffs})

    # ------------------------------------------------------------- files
    async def api_files(self, request):
        """Directory listing for the Files pane."""
        raw = request.query_params.get("cwd", "")
        root = Path(raw).resolve() if raw else self.cwd
        if not root.is_dir():
            return _json({"error": "not a directory"}, status=400)

        def walk(d: Path, depth: int = 0):
            if depth > 3:
                return []
            out = []
            try:
                entries = sorted(d.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except OSError:
                return []
            for p in entries:
                if p.name.startswith(".") or p.name in ("node_modules", "__pycache__",
                                                      "venv", ".venv", "dist", "build"):
                    continue
                if p.is_dir():
                    out.append({"name": p.name, "dir": True, "children": walk(p, depth + 1)})
                else:
                    out.append({"name": p.name, "dir": False, "size": p.stat().st_size})
            return out

        return _json({"root": str(root), "entries": walk(root)})

    async def api_file(self, request):
        """Read one file for the Files pane."""
        raw_cwd = request.query_params.get("cwd", "")
        rel = request.query_params.get("path", "")
        root = Path(raw_cwd).resolve() if raw_cwd else self.cwd
        target = (root / rel).resolve()
        # Never serve anything outside the project folder.
        try:
            target.relative_to(root)
        except ValueError:
            return _json({"error": "outside the workspace"}, status=403)
        if not target.is_file():
            return _json({"error": "not found"}, status=404)
        try:
            content = target.read_text("utf-8", errors="replace")
        except OSError as e:
            return _json({"error": str(e)}, status=400)
        return _json({"path": str(target), "content": content[:400000]})

    # --------------------------------------------------------- side chat
    async def api_side_chat(self, request):
        """Answer a question using the session's context, without adding to it."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        sid = str(body.get("session", ""))
        question = str(body.get("question", "")).strip()
        if not question:
            return _json({"error": "no question"}, status=400)
        sess = self.registry.get(sid)
        if not sess:
            return _json({"error": "no session"}, status=404)
        agent = self.registry.ensure_agent(sess)
        answer = await agent.side_chat(question)
        return _json({"answer": answer})

    # -------------------------------------------------------------- websocket
    async def websocket(self, websocket):
        await websocket.accept()
        conn = Connection(ws=websocket, token=self.token, registry=self.registry)
        self._conns.append(conn)

        try:
            # ---- auth handshake (first message must carry the token)
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                hello = json.loads(raw)
            except Exception:
                await conn.send({"type": "error", "message": "handshake timeout"})
                await websocket.close()
                return

            supplied = str(hello.get("token", "")) if isinstance(hello, dict) else ""
            if not supplied or not _constant_time_eq(supplied, self.token):
                await conn.send({"type": "error", "message": "unauthorized"})
                with contextlib.suppress(Exception):
                    await websocket.close()
                return

            # ---- pick or create a session
            sess = self._session_for(conn, hello)
            await conn.send({
                "type": "ready",
                "session": sess.info.id,
                "model": sess.info.model,
                "cwd": sess.info.cwd,
                "version": _version(),
                "sessions": [i.to_dict() for i in self.registry.list()],
            })
            await self._pump(websocket, conn, sess)
        except Exception as e:
            with contextlib.suppress(Exception):
                await conn.send({"type": "error", "message": f"{type(e).__name__}: {e}"})
        finally:
            conn.unbind()
            if conn in self._conns:
                self._conns.remove(conn)
            with contextlib.suppress(Exception):
                await websocket.close()

    def _session_for(self, conn: Connection, hello: dict) -> Session:
        """Resolve the session a client wants, creating one if needed."""
        sid = hello.get("session")
        sess = self.registry.get(sid) if sid else None
        if sess is None:
            sess = self.registry.create(
                cwd=hello.get("cwd"),
                model=hello.get("model"),
                permission_mode=hello.get("permissionMode"),
                worktree=bool(hello.get("worktree")),
            )
        agent = self.registry.ensure_agent(sess)
        conn.bind(sess)
        conn.agent = agent
        agent.ui = RemoteUI(conn)  # type: ignore[attr-defined]
        agent.ui.agent = agent  # type: ignore[attr-defined]
        agent.ui.conn = conn  # type: ignore[attr-defined]
        return sess

    async def _pump(self, websocket, conn: Connection, sess: Session) -> None:
        """Read client messages.

        A turn runs as a background task so this loop stays free to read the
        client's replies (permission approvals, question answers). Blocking
        here would deadlock: the agent parks on wait_for_reply() while the
        only reader of the reply is this loop.
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
                if sess._busy:
                    conn.emit({"type": "error", "message": "a turn is already running"})
                    continue
                sess._busy = True
                sess.info.status = "running"
                turn_task = asyncio.create_task(
                    self._run_turn(conn, sess, str(msg.get("text", ""))))
            elif mtype == "reply":
                await conn.resolve(str(msg.get("id", "")), str(msg.get("answer", "")))
            elif mtype == "answer":
                await conn.resolve(str(msg.get("id", "")), str(msg.get("value", "")))
            elif mtype == "interrupt":
                if sess.agent:
                    sess.agent.interrupted = True
                conn.emit({"type": "interrupted"})
            elif mtype == "new_session":
                new = self.registry.create(
                    cwd=msg.get("cwd"),
                    model=msg.get("model"),
                    permission_mode=msg.get("permissionMode"),
                    worktree=bool(msg.get("worktree")),
                )
                self.registry.ensure_agent(new)
                conn.bind(new)
                sess = new
                conn.agent = new.agent
                new.agent.ui = RemoteUI(conn)  # type: ignore[attr-defined]
                new.agent.ui.agent = new.agent  # type: ignore[attr-defined]
                new.agent.ui.conn = conn  # type: ignore[attr-defined]
                await conn.send({"type": "ready", "session": new.info.id,
                                 "model": new.info.model, "cwd": new.info.cwd,
                                 "version": _version(),
                                 "sessions": [i.to_dict() for i in self.registry.list()]})
            elif mtype == "switch_session":
                target = self.registry.get(str(msg.get("session", "")))
                if target is None:
                    conn.emit({"type": "error", "message": "no such session"})
                    continue
                self.registry.ensure_agent(target)
                conn.bind(target)
                sess = target
                conn.agent = target.agent
                target.agent.ui = RemoteUI(conn)  # type: ignore[attr-defined]
                target.agent.ui.agent = target.agent  # type: ignore[attr-defined]
                target.agent.ui.conn = conn  # type: ignore[attr-defined]
                await conn.send({"type": "ready", "session": target.info.id,
                                 "model": target.info.model, "cwd": target.info.cwd,
                                 "version": _version(),
                                 "sessions": [i.to_dict() for i in self.registry.list()]})
            elif mtype == "set_model":
                if self.registry.set_model(sess.info.id, str(msg.get("model", ""))):
                    conn.emit({"type": "session_meta",
                               "session": sess.info.id,
                               "meta": sess.info.to_dict()})
                else:
                    conn.emit({"type": "error", "message": "unknown model"})
            elif mtype == "set_mode":
                if self.registry.set_permission_mode(sess.info.id, str(msg.get("mode", ""))):
                    conn.emit({"type": "session_meta",
                               "session": sess.info.id,
                               "meta": sess.info.to_dict()})
                else:
                    conn.emit({"type": "error", "message": "unknown permission mode"})
            elif mtype == "rename":
                if self.registry.rename(sess.info.id, str(msg.get("title", ""))):
                    conn.emit({"type": "session_meta",
                               "session": sess.info.id,
                               "meta": sess.info.to_dict()})
            elif mtype == "sessions":
                await conn.send({"type": "sessions",
                                 "sessions": [i.to_dict() for i in self.registry.list()]})
            elif mtype == "reset":
                if sess.agent:
                    sess.agent.messages.clear()
                    sess.agent.session_id = uuid.uuid4().hex[:16]
                conn.emit({"type": "ready", "session": sess.info.id,
                           "model": sess.info.model, "cwd": sess.info.cwd})

    async def _run_turn(self, conn: Connection, sess: Session, text: str) -> None:
        if not text.strip():
            sess._busy = False
            return
        agent = self.registry.ensure_agent(sess)
        t0 = time.time()
        try:
            result = await agent.run_turn(text)
            self.registry.refresh_usage(sess)
            if not sess.info.title or sess.info.title == "New session":
                title = agent.session_title or text.strip()[:60]
                if title:
                    sess.info.title = title
            await conn.send({
                "type": "done",
                "text": result.text,
                "usage": result.usage,
                "elapsed": round(time.time() - t0, 2),
                "session": sess.info.id,
                "meta": sess.info.to_dict(),
            })
        except asyncio.CancelledError:
            raise
        except Exception as e:
            with contextlib.suppress(Exception):
                await conn.send({"type": "error", "message": f"{type(e).__name__}: {e}"})
        finally:
            sess._busy = False
            sess.info.status = "idle"
            sess.info.updated = time.time()


def _file_diff(path: str, context: int = 3) -> str:
    """Unified diff of a file against its git HEAD (or empty for new files)."""
    import difflib
    import subprocess

    p = Path(path)
    try:
        new = p.read_text("utf-8", errors="replace").splitlines(keepends=True)
    except OSError:
        return ""
    old: list[str] = []
    try:
        proc = subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=30)
        if proc.returncode == 0:
            old = proc.stdout.splitlines(keepends=True)
    except Exception:
        pass
    diff = difflib.unified_diff(old, new, fromfile=f"a/{path}", tofile=f"b/{path}",
                                n=context)
    return "".join(diff)


def _version() -> str:
    try:
        from . import __version__

        return __version__
    except Exception:
        return "0.0.0"


def _json(payload: dict, status: int = 200):
    from starlette.responses import JSONResponse

    return JSONResponse(payload, status_code=status)


def _ui_response(path: Path):
    """Serve a UI asset, telling the browser not to cache it.

    The desktop and mobile shells are served from a local server that is
    restarted on every launch. A cached `app.js` from a previous run would
    speak a stale protocol, so the assets are always revalidated.
    """
    from starlette.responses import FileResponse

    return FileResponse(
        str(path),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


# --------------------------------------------------------------------------- #
# ASGI app factory
# --------------------------------------------------------------------------- #
def build_app(token: str | None = None, cwd: str | None = None,
              model: str | None = None, permission_mode: str | None = None):
    """Return a Starlette ASGI app plus the KaliServer instance."""
    from starlette.applications import Starlette
    from starlette.routing import Route, WebSocketRoute

    server = KaliServer(token=token, cwd=cwd, model=model,
                        permission_mode=permission_mode)
    routes = [
        Route("/", server.root, methods=["GET"]),
        Route("/health", server.health, methods=["GET"]),
        Route("/push/subscribe", server.push_subscribe, methods=["POST"]),
        Route("/api/sessions", server.api_sessions, methods=["GET"]),
        Route("/api/sessions", server.api_session_create, methods=["POST"]),
        Route("/api/sessions/{sid}", server.api_session_get, methods=["GET"]),
        Route("/api/sessions/{sid}", server.api_session_delete, methods=["DELETE"]),
        Route("/api/sessions/{sid}/archive", server.api_session_archive, methods=["POST"]),
        Route("/api/diff", server.api_diff, methods=["GET"]),
        Route("/api/files", server.api_files, methods=["GET"]),
        Route("/api/file", server.api_file, methods=["GET"]),
        Route("/api/side-chat", server.api_side_chat, methods=["POST"]),
        WebSocketRoute("/ws", server.websocket),
    ]

    # Static UI assets.
    for name in ("app.js", "style.css", "manifest.json", "icon.svg",
                 "icon-192.png", "icon-512.png", "sw.js"):
        routes.append(Route(f"/{name}", server.static_asset, methods=["GET"]))
    routes.append(Route("/desktop/{path:path}", server.static_asset, methods=["GET"]))
    routes.append(Route("/mobile/{path:path}", server.static_asset, methods=["GET"]))

    app = Starlette(routes=routes)
    app.state.server = server
    return app, server


def serve(host: str = "0.0.0.0", port: int = 8000, token: str | None = None,
          cwd: str | None = None, model: str | None = None,
          permission_mode: str | None = None) -> None:
    """Run the Kali Code server (blocking).

    This may be called from inside a running event loop (the CLI runs
    it from an async entry point), so it never calls `asyncio.run`
    itself - `uvicorn.run` is only safe outside a loop.
    """
    import uvicorn

    app, server = build_app(token=token, cwd=cwd, model=model,
                             permission_mode=permission_mode)
    print(f"Kali Code server listening on http://{host}:{port}")
    print(f"Workspace: {server.cwd}")
    print(f"Access token: {server.token}")
    print("Open the URL in a browser, or scan the QR code in the terminal.")

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No loop is running: uvicorn can start its own.
        uvicorn.run(app, host=host, port=port, log_level="info")
        return

    # A loop is already running, so the server has to be driven by it.
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    uvicorn.Server(config).run()


async def serve_async(host: str = "0.0.0.0", port: int = 8000,
                      token: str | None = None, cwd: str | None = None,
                      model: str | None = None,
                      permission_mode: str | None = None) -> None:
    """Run the server from inside an event loop."""
    import uvicorn

    app, server = build_app(token=token, cwd=cwd, model=model,
                             permission_mode=permission_mode)
    print(f"Kali Code server listening on http://{host}:{port}")
    print(f"Workspace: {server.cwd}")
    print(f"Access token: {server.token}")
    print("Open the URL in a browser, or scan the QR code in the terminal.")

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    await uvicorn.Server(config).serve()


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Kali Code server")
    p.add_argument("--host", default=os.environ.get("KALI_SERVER_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    p.add_argument("--token", default=None)
    p.add_argument("--cwd", default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--permission-mode", default=None)
    a = p.parse_args()
    serve(host=a.host, port=a.port, token=a.token, cwd=a.cwd,
          model=a.model, permission_mode=a.permission_mode)
