"""PyInstaller build script for Kali Code.

Produces a single-file Windows executable:

    dist/KaliCode.exe

Usage:
    python build_exe.py              # one-file build
    python build_exe.py --onedir     # faster, folder distribution
    python build_exe.py --clean      # wipe build/ dist/ first

The app bundles:
  - the `kali` package (code, skills, system prompt files, Discord assets)
  - rich + httpx and their dependencies
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_NAME = "KaliCode"


def clean() -> None:
    for d in ("build", "dist"):
        p = ROOT / d
        if p.exists():
            print(f"  removing {d}/")
            shutil.rmtree(p, ignore_errors=True)


def collect_data() -> list[tuple[str, str]]:
    """(source, destination) pairs for PyInstaller --add-data.

    The `assets` folder carries the WebView2 loader DLL. It is bundled as
    data (not a binary) because it is loaded by absolute path at runtime
    rather than being imported - Windows resolves the loader's own
    dependencies from the WebView2 runtime folder anyway.
    """
    pairs: list[tuple[str, str]] = []
    for sub in ("skills", "assets", "systemprompt", "mobile", "desktop"):
        src = ROOT / "kali" / sub
        if src.exists():
            pairs.append((str(src), f"kali/{sub}"))
    return pairs


def build(onefile: bool = True, console: bool = True) -> int:
    pyinstaller = ROOT / ".venv" / "Scripts" / "pyinstaller.exe"
    if not pyinstaller.exists():
        pyinstaller = ROOT / ".venv" / "Scripts" / "pyinstaller"
    if not pyinstaller.exists():
        print("PyInstaller not found. Install it with:")
        print("  uv pip install pyinstaller")
        return 1

    icon = ROOT / "kali" / "assets" / "app_icon.ico"
    icon_arg = []
    if icon.exists():
        icon_arg = ["--icon", str(icon)]
    else:
        png = ROOT / "kali" / "assets" / "app_icon.png"
        if png.exists():
            icon_arg = ["--icon", str(png)]

    cmd = [
        str(pyinstaller),
        "--noconfirm",
        "--clean",
        "--name", APP_NAME,
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        "--paths", str(ROOT),
    ]
    cmd.append("--onefile" if onefile else "--onedir")
    if not console:
        cmd.append("--windowed")
    cmd += icon_arg

    for src, dest in collect_data():
        cmd += ["--add-data", f"{src}{os.pathsep}{dest}"]

    # Hidden imports that are imported dynamically.
    cmd += ["--hidden-import", "kali.tools.web"]
    cmd += ["--hidden-import", "kali.tools.task"]
    cmd += ["--hidden-import", "kali.discord_presence"]
    cmd += ["--hidden-import", "httpx._transports.default"]
    cmd += ["--hidden-import", "httpcore._async.connection_pool"]
    cmd += ["--hidden-import", "rich._windows"]

    # Keep the binary small.
    cmd += ["--exclude-module", "tkinter"]
    cmd += ["--exclude-module", "matplotlib"]
    cmd += ["--exclude-module", "numpy"]
    cmd += ["--exclude-module", "PIL"]
    cmd += ["--exclude-module", "pytest"]
    cmd += ["--exclude-module", "setuptools"]

    cmd.append(str(ROOT / "kali" / "__main__.py"))

    print("running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    exe = ROOT / "dist" / (f"{APP_NAME}.exe" if onefile else f"{APP_NAME}")
    if exe.exists():
        size_mb = exe.stat().st_size / (1024 * 1024)
        print(f"\nBuilt: {exe}  ({size_mb:.1f} MB)")
    else:
        print("\nBuild finished (check dist/ for output)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Build Kali Code executable")
    ap.add_argument("--onedir", action="store_true",
                    help="folder distribution instead of one file")
    ap.add_argument("--windowed", action="store_true",
                    help="no console window (GUI mode)")
    ap.add_argument("--clean", action="store_true",
                    help="remove build/ and dist/ first")
    args = ap.parse_args()

    if args.clean:
        clean()
    return build(onefile=not args.onedir, console=not args.windowed)


if __name__ == "__main__":
    raise SystemExit(main())
