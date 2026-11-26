"""Resource path helpers that work in every deployment shape.

Kali Code ships three ways:
  1. source checkout / editable install   -> files live next to this module
  2. regular wheel install (site-packages) -> files live next to this module
  3. PyInstaller one-file .exe             -> files live in the bundle's
                                             extraction dir (sys._MEIPASS)

`__file__` alone breaks case 3 for one-file builds, so every bundled-resource
lookup goes through `resource_path()`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """Root directory of the PyInstaller bundle (or the package dir)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent


def resource_path(*parts: str) -> Path:
    """Resolve a bundled resource path.

    In a frozen build the resource lives under sys._MEIPASS. Otherwise it
    lives next to this module (source checkout or site-packages install).
    """
    base = bundle_dir()
    candidate = base.joinpath(*parts)
    if candidate.exists():
        return candidate
    # Fall back to the package dir when running from source even if the
    # bundle dir differs (e.g. PyInstaller --onedir with a data root).
    pkg = Path(__file__).resolve().parent
    alt = pkg.joinpath(*parts)
    if alt.exists():
        return alt
    return candidate


def resource_dir(*parts: str) -> Path:
    """Resolve a bundled resource directory (may not exist)."""
    base = bundle_dir()
    candidate = base.joinpath(*parts)
    if candidate.exists():
        return candidate
    pkg = Path(__file__).resolve().parent
    alt = pkg.joinpath(*parts)
    if alt.exists():
        return alt
    return candidate


def ui_base_dir() -> Path:
    """The directory that holds the `desktop/` and `mobile/` UI folders.

    In a source checkout or a wheel install those folders sit next to this
    module. In a PyInstaller bundle they are extracted to
    `sys._MEIPASS/kali/...`, one level below the bundle root, so the
    package directory is resolved from `__file__` rather than from
    `bundle_dir()`.
    """
    pkg = Path(__file__).resolve().parent
    if (pkg / "desktop").is_dir() or (pkg / "mobile").is_dir():
        return pkg
    # A frozen bundle: `__file__` points at the extracted package.
    base = bundle_dir()
    for cand in (base / "kali", base):
        if (cand / "desktop").is_dir() or (cand / "mobile").is_dir():
            return cand
    return pkg


def resource_text(*parts: str, default: str = "") -> str:
    """Read a bundled text resource, returning `default` when missing."""
    try:
        return resource_path(*parts).read_text(encoding="utf-8")
    except Exception:
        return default


def exe_dir() -> Path:
    """Directory the running executable lives in (for .exe deployments)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def user_data_dir() -> Path:
    """Per-user writable data directory (settings, logs, caches)."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / "KaliCode"
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / "kali-code"


def ensure_user_data_dir() -> Path:
    """Create and return the per-user data directory."""
    d = user_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d
