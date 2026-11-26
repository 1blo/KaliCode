"""Session registry - the shared foundation for the desktop GUI and the APK.

A session is an independent agent with its own conversation, working
directory, permission mode and model. The desktop app and the phone are both
*clients* of these sessions; neither executes the agent.

Mirrors the Claude Code session model:
  - sessions are independent and can run in parallel
  - each may have its own project folder and git worktree
  - permission mode and model can change mid-session
  - a session can be archived, renamed and listed
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .agent import Agent
from .config import AgentConfig, MODELS, DEFAULT_MODEL, load_settings


# --------------------------------------------------------------------------- #
# Session record
# --------------------------------------------------------------------------- #
@dataclass
class SessionInfo:
    """Everything a client needs to list a session without loading its state."""

    id: str
    title: str = "New session"
    cwd: str = ""
    model: str = DEFAULT_MODEL
    permission_mode: str = "default"
    worktree: bool = False
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    archived: bool = False
    parent: str | None = None          # for side chats
    status: str = "idle"              # idle|running|awaiting_permission|error
    total_usage: dict = field(default_factory=dict)
    message_count: int = 0
    branch: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "cwd": self.cwd,
            "model": self.model,
            "permissionMode": self.permission_mode,
            "worktree": self.worktree,
            "created": self.created,
            "updated": self.updated,
            "archived": self.archived,
            "parent": self.parent,
            "status": self.status,
            "usage": self.total_usage,
            "messageCount": self.message_count,
            "branch": self.branch,
        }


@dataclass
class Session:
    """A live agent plus its metadata."""

    info: SessionInfo
    agent: Agent | None = None
    listeners: list[Callable[[dict], Any]] = field(default_factory=list)
    _busy: bool = False
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # ------------------------------------------------------------------ events
    def subscribe(self, cb: Callable[[dict], Any]) -> None:
        if cb not in self.listeners:
            self.listeners.append(cb)

    def unsubscribe(self, cb: Callable[[dict], Any]) -> None:
        if cb in self.listeners:
            self.listeners.remove(cb)

    def emit(self, payload: dict) -> None:
        """Fan an event out to every listener (never raises)."""
        for cb in list(self.listeners):
            try:
                cb(payload)
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# Worktrees
# --------------------------------------------------------------------------- #
def _git(*args: str, cwd: Path | None = None, timeout: float = 60.0) -> tuple[int, str]:
    cwd = cwd or Path.cwd()
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return 124, f"git {' '.join(args)} timed out"
    except FileNotFoundError:
        return 127, "git is not installed"
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def current_branch(path: Path) -> str:
    rc, out = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=path)
    return out.strip() if rc == 0 else ""


def create_worktree(repo: Path, name: str | None = None) -> tuple[bool, str, str]:
    """Create a git worktree for a session.

    Returns (ok, path, branch).
    """
    repo = Path(repo).resolve()
    if not is_git_repo(repo):
        return False, "", f"{repo} is not a git repository"

    safe = name or f"kali-{uuid.uuid4().hex[:8]}"
    safe = "".join(c for c in safe if c.isalnum() or c in "-_").strip("-_") or "kali-session"
    branch = f"kali/{safe}"
    wt_dir = repo / ".kali" / "worktrees" / safe

    try:
        wt_dir.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return False, "", f"could not create {wt_dir.parent}: {e}"

    rc, out = _git("worktree", "add", "-b", branch, str(wt_dir), cwd=repo)
    if rc != 0:
        # The branch may already exist - reuse it.
        rc2, out2 = _git("worktree", "add", str(wt_dir), branch, cwd=repo)
        if rc2 != 0:
            return False, "", out or out2
        out = out2
    return True, str(wt_dir), branch


def remove_worktree(repo: Path, wt_path: str, branch: str = "") -> tuple[bool, str]:
    repo = Path(repo).resolve()
    rc, out = _git("worktree", "remove", "--force", wt_path, cwd=repo)
    if rc != 0:
        return False, out
    if branch:
        _git("branch", "-D", branch, cwd=repo)
    return True, out


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
class SessionRegistry:
    """Owns every live session."""

    def __init__(self, default_cwd: Path | None = None,
                 default_model: str | None = None,
                 default_permission_mode: str | None = None):
        self.default_cwd = Path(default_cwd or os.getcwd()).resolve()
        self.default_model = default_model or ""
        self.default_permission_mode = default_permission_mode or "default"
        self._sessions: dict[str, Session] = {}
        self._meta_dir = Path(
            os.environ.get("KALI_SESSION_DIR",
                           str(Path.home() / ".kali" / "sessions")))
        self._meta_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- lifecycle
    def create(self, cwd: str | None = None, model: str | None = None,
               permission_mode: str | None = None, title: str | None = None,
               worktree: bool = False, parent: str | None = None) -> Session:
        sid = uuid.uuid4().hex[:16]
        folder = Path(cwd).resolve() if cwd else self.default_cwd
        branch = ""

        if worktree and is_git_repo(folder):
            ok, wt, branch = create_worktree(folder)
            if ok:
                folder = Path(wt)

        info = SessionInfo(
            id=sid,
            title=title or "New session",
            cwd=str(folder),
            model=model or self.default_model or DEFAULT_MODEL,
            permission_mode=permission_mode or self.default_permission_mode,
            worktree=bool(branch),
            parent=parent,
            branch=branch,
        )
        sess = Session(info=info)
        self._sessions[sid] = sess
        self._save_meta(info)
        return sess

    def get(self, sid: str) -> Session | None:
        return self._sessions.get(sid)

    def list(self, include_archived: bool = False) -> list[SessionInfo]:
        items = [s.info for s in self._sessions.values()]
        if not include_archived:
            items = [i for i in items if not i.archived]
        items.sort(key=lambda i: i.updated, reverse=True)
        return items

    def archive(self, sid: str) -> bool:
        s = self._sessions.get(sid)
        if not s:
            return False
        s.info.archived = True
        s.info.updated = time.time()
        self._save_meta(s.info)
        return True

    def rename(self, sid: str, title: str) -> bool:
        s = self._sessions.get(sid)
        if not s:
            return False
        s.info.title = title[:120]
        s.info.updated = time.time()
        self._save_meta(s.info)
        return True

    def delete(self, sid: str) -> bool:
        s = self._sessions.get(sid)
        if not s:
            return False
        if s.info.worktree and s.info.branch:
            # Find the owning repo from the worktree path.
            wt = Path(s.info.cwd)
            repo = wt.parent.parent.parent if wt.parent.name == "worktrees" else None
            if repo and repo.exists():
                remove_worktree(repo, str(wt), s.info.branch)
        self._sessions.pop(sid, None)
        self._meta_dir.joinpath(f"{sid}.json").unlink(missing_ok=True)
        return True

    # --------------------------------------------------------------- settings
    def set_model(self, sid: str, model: str) -> bool:
        s = self._sessions.get(sid)
        if not s or model not in MODELS:
            return False
        s.info.model = model
        s.info.updated = time.time()
        if s.agent:
            s.agent.cfg.model = model
        self._save_meta(s.info)
        return True

    def set_permission_mode(self, sid: str, mode: str) -> bool:
        s = self._sessions.get(sid)
        if not s or mode not in ("default", "acceptEdits", "plan", "bypassPermissions", "auto"):
            return False
        s.info.permission_mode = mode
        s.info.updated = time.time()
        if s.agent:
            s.agent.permission_mode = mode
            s.agent.permissions.mode = mode
        self._save_meta(s.info)
        return True

    # ------------------------------------------------------------------ agent
    def ensure_agent(self, sess: Session) -> Agent:
        """Create the session's agent on first use."""
        if sess.agent is not None:
            return sess.agent
        settings = load_settings()
        cfg = AgentConfig.from_settings(settings)
        cfg.model = sess.info.model or cfg.model
        cfg.permission_mode = sess.info.permission_mode
        cfg.settings = settings
        agent = Agent(cfg, ui=None)
        agent.session_id = sess.info.id
        sess.agent = agent
        return agent

    # ----------------------------------------------------------------- usage
    def refresh_usage(self, sess: Session) -> None:
        if sess.agent:
            sess.info.total_usage = dict(sess.agent.total_usage)
            sess.info.message_count = len(sess.agent.messages)

    # ------------------------------------------------------------------ meta
    def _save_meta(self, info: SessionInfo) -> None:
        try:
            self._meta_dir.joinpath(f"{info.id}.json").write_text(
                json.dumps(info.to_dict(), indent=2), "utf-8")
        except OSError:
            pass

    def load_meta(self) -> list[SessionInfo]:
        """Restore session metadata from disk (agents are recreated lazily)."""
        out: list[SessionInfo] = []
        for p in sorted(self._meta_dir.glob("*.json")):
            try:
                d = json.loads(p.read_text("utf-8"))
            except Exception:
                continue
            info = SessionInfo(
                id=d.get("id", p.stem),
                title=d.get("title", "New session"),
                cwd=d.get("cwd", str(self.default_cwd)),
                model=d.get("model", DEFAULT_MODEL),
                permission_mode=d.get("permissionMode", "default"),
                worktree=bool(d.get("worktree")),
                created=d.get("created", time.time()),
                updated=d.get("updated", time.time()),
                archived=bool(d.get("archived")),
                parent=d.get("parent"),
                status="idle",
            )
            out.append(info)
        return out
