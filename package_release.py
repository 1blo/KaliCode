"""Package Kali Code into distributable release artifacts.

Produces in dist/:
  KaliCode.exe            - the single-file executable (built by build_exe.py)
  KaliCode-<version>-win64.zip  - portable zip
  KaliCode-Setup.exe      - a self-extracting portable launcher stub
  RELEASE-NOTES.md        - checksums + instructions
"""
from __future__ import annotations

import hashlib
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
APP = "KaliCode"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_version() -> str:
    import re

    txt = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', txt, re.M)
    return m.group(1) if m else "0.0.0"


def make_zip(version: str) -> Path | None:
    exe = DIST / f"{APP}.exe"
    if not exe.exists():
        print("  no exe found - run build_exe.py first")
        return None
    out = DIST / f"{APP}-{version}-win64.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(exe, f"{APP}.exe")
        for extra in ("README.md", "LICENSE"):
            p = ROOT / extra
            if p.exists():
                zf.write(p, extra)
    return out


def make_portable_folder(version: str) -> Path | None:
    """A folder with the exe + a config helper + readme."""
    exe = DIST / f"{APP}.exe"
    if not exe.exists():
        return None
    folder = DIST / f"{APP}-{version}-win64"
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe, folder / f"{APP}.exe")
    for extra in ("README.md", "LICENSE"):
        p = ROOT / extra
        if p.exists():
            shutil.copy2(p, folder / extra)
    (folder / "START-HERE.txt").write_text(
        "Kali Code - portable build\n"
        "==========================\n\n"
        "1. Run KaliCode.exe\n"
        "2. Type /login and paste your API key\n"
        "   (or set the NVIDIA_API_KEY environment variable)\n"
        "3. Start typing a task.\n\n"
        "Settings live in  %USERPROFILE%\\.kali\\settings.json\n"
        "MCP servers and permissions are configured in the same file.\n",
        encoding="utf-8",
    )
    return folder


def make_release_notes(version: str, artifacts: list[Path]) -> Path:
    lines = [
        f"# Kali Code {version} - Windows Release",
        "",
        f"Built: {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "## Downloads",
        "",
    ]
    for a in artifacts:
        lines.append(f"### {a.name}")
        lines.append("")
        lines.append(f"- Size: {a.stat().st_size / 1024 / 1024:.1f} MB")
        lines.append(f"- SHA256: `{sha256(a)}`")
        lines.append("")
    lines += [
        "## Quick start",
        "",
        "1. Download and extract `KaliCode-<version>-win64.zip`",
        "2. Run `KaliCode.exe`",
        "3. Type `/login` and paste your API key",
        "4. Ask Kali Code to do something",
        "",
        "## Requirements",
        "",
        "- Windows 10 or newer (64-bit)",
        "- A valid API key (set NVIDIA_API_KEY or run /login)",
        "- Discord (optional) if you want the Rich Presence",
        "",
        "## Verify the download",
        "",
        "```powershell",
        "Get-FileHash .\\KaliCode.exe -Algorithm SHA256",
        "```",
        "",
    ]
    out = DIST / "RELEASE-NOTES.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> int:
    if not DIST.exists():
        print("dist/ not found - run build_exe.py first")
        return 1
    version = read_version()
    print(f"packaging Kali Code {version}")

    artifacts: list[Path] = []
    zip_path = make_zip(version)
    if zip_path:
        artifacts.append(zip_path)
        print(f"  zip    -> {zip_path.name} "
              f"({zip_path.stat().st_size / 1024 / 1024:.1f} MB)")
    folder = make_portable_folder(version)
    if folder:
        print(f"  folder -> {folder.name}")
    exe = DIST / f"{APP}.exe"
    if exe.exists():
        artifacts.append(exe)
        print(f"  exe    -> {exe.name} "
              f"({exe.stat().st_size / 1024 / 1024:.1f} MB)")

    notes = make_release_notes(version, artifacts)
    print(f"  notes  -> {notes.name}")

    print("\nartifacts in dist/:")
    for p in sorted(DIST.iterdir()):
        print(f"  {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
