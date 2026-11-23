"""Roblox publishing via the Open Cloud API.

Headless flow (no Roblox Studio required):

    git repo (Luau source + default.project.json)
        -> rojo build -o build.rbxl
        -> POST /universes/v1/{universeId}/places/{placeId}/versions?versionType=Published
        -> version number

Environment / settings:
    ROBLOX_API_KEY       Open Cloud API key (scope: universe-places:write)
    ROBLOX_UNIVERSE_ID   the experience (universe) id
    ROBLOX_PLACE_ID      the place id to publish to
    ROBLOX_PROJECT_DIR   Rojo project root (defaults to the workspace)
    ROBLOX_ROJO_BIN      path to the rojo binary (default: rojo on PATH)

Why .rbxl and not .rbxlx:
    Open Cloud currently drops the default server-authoritative character
    controls when a place is published from an .rbxlx file; the binary .rbxl
    keeps them. We therefore build binary and fall back to XML only if the
    binary build fails.
"""
from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import httpx

ROJO_VERSION = "7.7.1"
OPEN_CLOUD_BASE = "https://apis.roblox.com"


class RobloxError(Exception):
    """An Open Cloud / build failure with a human-readable message."""


@dataclass
class PublishResult:
    ok: bool
    message: str
    version: int | None = None
    place_id: int | None = None
    universe_id: int | None = None
    detail: str = ""


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def get_credentials() -> tuple[str, int | None, int | None]:
    """(api_key, universe_id, place_id) from env, then ~/.kali/settings.json."""
    key = _env("ROBLOX_API_KEY")
    universe = _env("ROBLOX_UNIVERSE_ID")
    place = _env("ROBLOX_PLACE_ID")

    if not (key and universe and place):
        try:
            from .config import load_settings

            s = load_settings()
            r = s.get("roblox") or {}
            key = key or str(r.get("apiKey", "") or "")
            universe = universe or str(r.get("universeId", "") or "")
            place = place or str(r.get("placeId", "") or "")
        except Exception:
            pass

    def _int(v: str) -> int | None:
        try:
            return int(str(v).strip())
        except (TypeError, ValueError):
            return None

    return key, _int(universe), _int(place)


def is_configured() -> bool:
    key, universe, place = get_credentials()
    return bool(key and universe and place)


# --------------------------------------------------------------------------- #
# Rojo
# --------------------------------------------------------------------------- #
def rojo_binary() -> str | None:
    """Locate the rojo executable."""
    explicit = _env("ROBLOX_ROJO_BIN")
    if explicit and Path(explicit).exists():
        return explicit
    found = shutil.which("rojo")
    if found:
        return found
    # Common install locations.
    for p in (Path("/usr/local/bin/rojo"), Path.home() / ".local" / "bin" / "rojo",
              Path.home() / ".rojo" / "bin" / "rojo"):
        if p.exists():
            return str(p)
    return None


def project_dir() -> Path:
    d = _env("ROBLOX_PROJECT_DIR")
    if d:
        return Path(d).resolve()
    return Path(os.getcwd()).resolve()


def find_rojo_project(root: Path | None = None) -> Path | None:
    """Find the Rojo project root (a dir containing default.project.json)."""
    root = root or project_dir()
    if (root / "default.project.json").exists():
        return root
    # Shallow search (depth 3) for a project file.
    for depth in range(1, 4):
        for cand in root.glob("*/" * depth + "default.project.json"):
            return cand.parent
    return None


async def build_place(project: Path | None = None, binary: bool = True,
                      timeout: float = 180.0) -> Path:
    """Run `rojo build` and return the produced place file."""
    rojo = rojo_binary()
    if not rojo:
        raise RobloxError(
            "Rojo is not installed. Install it with:\n"
            "  curl -L https://github.com/rojo-rbx/rojo/releases/download/"
            f"v{ROJO_VERSION}/rojo-{ROJO_VERSION}-linux-x86_64.zip -o rojo.zip\n"
            "  unzip rojo.zip && chmod +x rojo && mv rojo /usr/local/bin/")

    project = project or find_rojo_project()
    if project is None:
        raise RobloxError(
            "No Rojo project found - expected default.project.json. "
            "Set ROBLOX_PROJECT_DIR to the project root.")

    out = project / ("build.rbxl" if binary else "build.rbxlx")
    cmd = [rojo, "build", str(project), "--output", str(out)]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise RobloxError(f"rojo build timed out after {timeout:.0f}s")

    text = (stdout or b"").decode("utf-8", "replace").strip()
    if proc.returncode != 0:
        raise RobloxError(f"rojo build failed (exit {proc.returncode}):\n{text[:2000]}")
    if not out.exists():
        raise RobloxError(f"rojo build produced no file at {out}\n{text[:1000]}")
    return out


# --------------------------------------------------------------------------- #
# Open Cloud
# --------------------------------------------------------------------------- #
async def publish_place(place_file: Path, universe_id: int, place_id: int,
                        api_key: str, published: bool = True,
                        timeout: float = 120.0) -> PublishResult:
    """Publish a place file via the Open Cloud Place Publishing API.

    POST /universes/v1/{universeId}/places/{placeId}/versions?versionType=Published
    Scope required: universe-places:write
    """
    version_type = "Published" if published else "Saved"
    url = (f"{OPEN_CLOUD_BASE}/universes/v1/{universe_id}/places/{place_id}/versions"
           f"?versionType={version_type}")

    content_type = ("application/octet-stream"
                    if place_file.suffix.lower() == ".rbxl"
                    else "application/xml")
    if not place_file.exists():
        return PublishResult(
            False, f"Place file not found: {place_file}",
            place_id=place_id, universe_id=universe_id,
            detail="The build did not produce a place file.")
    try:
        data = place_file.read_bytes()
    except OSError as e:
        return PublishResult(
            False, f"Could not read place file {place_file}: {e}",
            place_id=place_id, universe_id=universe_id)
    if len(data) > 10 * 1024 * 1024:
        return PublishResult(
            False, f"Place file is too large: {len(data)} bytes (max 10 MiB)",
            place_id=place_id, universe_id=universe_id)

    headers = {
        "x-api-key": api_key,
        "Content-Type": content_type,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(url, headers=headers, content=data)
        except httpx.HTTPError as e:
            return PublishResult(False, f"Network error contacting Roblox: {e}")

    if resp.status_code == 200:
        version = None
        try:
            payload = resp.json()
            version = int(payload.get("versionNumber")) if payload.get("versionNumber") else None
        except Exception:
            pass
        return PublishResult(
            True,
            f"Published version {version}" if version else "Published successfully",
            version=version, place_id=place_id, universe_id=universe_id)

    body = resp.text[:1200]
    hint = ""
    if resp.status_code == 401:
        hint = ("The API key was rejected. Check ROBLOX_API_KEY and make sure the key "
                "has the 'universe-places:write' scope.")
    elif resp.status_code == 403:
        hint = ("The API key is not allowed to publish this place. Grant it access to "
                "this experience in the Creator Dashboard (API Keys > Access Permissions).")
    elif resp.status_code == 404:
        hint = "Place or universe not found - check ROBLOX_UNIVERSE_ID and ROBLOX_PLACE_ID."
    elif resp.status_code == 409:
        hint = ("Conflict - the place may not belong to this universe, or the daily "
                "publish limit was reached (Roblox allows ~5 new public games per day).")
    elif resp.status_code == 413:
        hint = "Place file too large (max 10 MiB)."
    return PublishResult(False, f"HTTP {resp.status_code}: {body}",
                         place_id=place_id, universe_id=universe_id, detail=hint)


async def publish(unpublished: bool = False, binary: bool = True) -> PublishResult:
    """Full pipeline: build with Rojo, then publish to Roblox."""
    key, universe_id, place_id = get_credentials()
    if not key:
        return PublishResult(False, "ROBLOX_API_KEY is not set.")
    if not universe_id:
        return PublishResult(False, "ROBLOX_UNIVERSE_ID is not set.")
    if not place_id:
        return PublishResult(False, "ROBLOX_PLACE_ID is not set.")

    try:
        place_file = await build_place(binary=binary)
    except RobloxError as e:
        # Binary build failed - retry as XML before giving up.
        if binary:
            try:
                place_file = await build_place(binary=False)
            except RobloxError:
                return PublishResult(False, str(e))
        else:
            return PublishResult(False, str(e))

    result = await publish_place(place_file, universe_id, place_id, key,
                                 published=not unpublished)
    result.detail = (result.detail + f"\nBuilt {place_file.name} "
                     f"({place_file.stat().st_size} bytes)").strip()
    return result


def game_link(universe_id: int | None = None) -> str:
    u = universe_id
    if u is None:
        _, u, _ = get_credentials()
    if not u:
        return ""
    return f"https://www.roblox.com/games/{u}/"


# --------------------------------------------------------------------------- #
# Git helpers (the agent commits its work before publishing)
# --------------------------------------------------------------------------- #
def git(*args: str, cwd: Path | None = None, timeout: float = 60.0) -> tuple[int, str]:
    """Run a git command synchronously; returns (returncode, combined output)."""
    import subprocess

    cwd = cwd or project_dir()
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd), capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return 124, f"git {' '.join(args)} timed out"
    except FileNotFoundError:
        return 127, "git is not installed"
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def git_status(cwd: Path | None = None) -> str:
    rc, out = git("status", "--porcelain", cwd=cwd)
    return out if rc == 0 else ""


def git_sync(cwd: Path | None = None, message: str = "Kali Code: update") -> tuple[bool, str]:
    """Commit any changes and push. Returns (ok, message)."""
    cwd = cwd or project_dir()
    if not (cwd / ".git").exists():
        return False, f"{cwd} is not a git repository"

    rc, out = git("status", "--porcelain", cwd=cwd)
    if rc != 0:
        return False, out
    if out.strip():
        rc, out = git("add", "-A", cwd=cwd)
        if rc != 0:
            return False, out
        rc, out = git("commit", "-m", message, cwd=cwd)
        if rc != 0 and "nothing to commit" not in out.lower():
            return False, out

    rc, out = git("push", cwd=cwd, timeout=120.0)
    if rc != 0:
        return False, out
    return True, out
