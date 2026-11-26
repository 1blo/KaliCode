"""Package a Kali Code release: the Windows .exe, the APK and the checksums.

Produces a `release/` directory (git-ignored) containing:
    KaliCode.exe
    KaliCode-<version>-win64.zip
    KaliCode-<version>-android.apk
    RELEASE-NOTES.md
    SHA256SUMS.txt

Usage:
    python tools/package_release.py
    python tools/package_release.py --skip-exe --skip-apk
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def version() -> str:
    try:
        import tomllib
    except ImportError:
        import re
        text = (ROOT / "pyproject.toml").read_text("utf-8")
        m = re.search(r'version\s*=\s*"([^"]+)"', text)
        return m.group(1) if m else "0.0.0"
    with (ROOT / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def build_exe() -> Path | None:
    exe = ROOT / "dist" / "KaliCode.exe"
    if exe.exists():
        print(f"  exe already built: {exe}")
        return exe
    print("  building the exe (this takes a few minutes)...")
    result = subprocess.run([sys.executable, str(ROOT / "build_exe.py")],
                            cwd=ROOT)
    if result.returncode != 0 or not exe.exists():
        print("  exe build failed")
        return None
    return exe


def build_apk() -> Path | None:
    apk = ROOT / "android" / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
    if apk.exists():
        print(f"  apk already built: {apk}")
        return apk
    print("  building the android apk...")
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "build_apk.py"),
                             "--release"], cwd=ROOT)
    if result.returncode != 0 or not apk.exists():
        print("  apk build failed")
        return None
    return apk


def main() -> int:
    ap = argparse.ArgumentParser(description="Package a Kali Code release")
    ap.add_argument("--skip-exe", action="store_true")
    ap.add_argument("--skip-apk", action="store_true")
    args = ap.parse_args()

    ver = version()
    RELEASE.mkdir(parents=True, exist_ok=True)
    print(f"Packaging Kali Code {ver}")

    artefacts: list[Path] = []

    # ---- Windows executable ------------------------------------------------
    exe = None
    if not args.skip_exe:
        exe = build_exe()
        if exe:
            dest = RELEASE / "KaliCode.exe"
            shutil.copy2(exe, dest)
            artefacts.append(dest)

            zip_path = RELEASE / f"KaliCode-{ver}-win64.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(dest, "KaliCode.exe")
                for extra in ("LICENSE", "README.md"):
                    p = ROOT / extra
                    if p.exists():
                        z.write(p, extra)
            artefacts.append(zip_path)

    # ---- Android APK -------------------------------------------------------
    if not args.skip_apk:
        apk = build_apk()
        if apk:
            dest = RELEASE / f"KaliCode-{ver}-android.apk"
            shutil.copy2(apk, dest)
            artefacts.append(dest)

    # ---- Notes + checksums -------------------------------------------------
    notes = RELEASE / "RELEASE-NOTES.md"
    lines = [
        f"# Kali Code {ver}",
        "",
        f"Released {date.today().isoformat()}.",
        "",
        "## What's new in 1.1.0",
        "",
        "### A desktop app",
        "",
        "Kali Code is no longer terminal-only. `KaliCode.exe --gui` opens a",
        "native window with a session rail, the conversation, a details panel",
        "and a row of panes for changes, files, the plan and tasks - the",
        "same shape as the Claude app. It runs on the WebView2 runtime that",
        "ships with Windows, so there is nothing extra to install.",
        "",
        "The window starts its own server and connects by itself, so there is",
        "no access token to copy. If WebView2 is missing it falls back to your",
        "default browser.",
        "",
        "### A native Android app",
        "",
        "A Kotlin + Jetpack Compose client for the same server: streaming",
        "chat, tool cards, permission prompts, model and permission-mode",
        "pickers, and automatic reconnection. The phone is always a client -",
        "the agent runs on the server.",
        "",
        "### One session-aware server",
        "",
        "The server keeps a registry of sessions. The desktop app, the phone",
        "app and the browser PWA all talk to the same server over the same",
        "protocol, and can watch the same session at the same time.",
        "",
        "## Included",
        "",
    ]
    if exe:
        lines += [
            "### Windows",
            "",
            "- `KaliCode.exe` - the single-file executable.",
            "- `KaliCode-%s-win64.zip` - the executable in a zip." % ver,
            "",
            "Run `KaliCode.exe --gui` for the desktop app, or `KaliCode.exe` "
            "for the terminal.",
            "",
        ]
    if not args.skip_apk:
        lines += [
            "### Android",
            "",
            "- `KaliCode-%s-android.apk` - the native phone client." % ver,
            "",
            "Install it on the phone, then enter your server URL and the "
            "access token printed by the server. The desktop app writes both "
            "to `%LOCALAPPDATA%\\KaliCode\\desktop.json`.",
            "",
        ]
    lines += [
        "### iOS",
        "",
        "Two iOS clients are included, both in the repository:",
        "",
        "- The **native SwiftUI app** in `ios/` - a complete Xcode project",
        "  with the same feature set as the Android app. It has to be built",
        "  and signed on a Mac, because Apple does not allow an `.ipa` to be",
        "  compiled on Windows.",
        "- The **installable PWA** - open the server URL in Safari and tap",
        "  Share > Add to Home Screen. It runs full screen, follows the",
        "  safe areas, keeps the composer above the keyboard and supports",
        "  Web Push on iOS 16.4+.",
        "",
        "There is no `.ipa` in this release; the iOS project ships as source.",
        "",
        "## Checksums",
        "",
        "```",
    ]
    for a in sorted(artefacts):
        lines.append(f"{sha256(a)}  {a.name}")
    lines += ["```", ""]
    notes.write_text("\n".join(lines), encoding="utf-8")

    sums = RELEASE / "SHA256SUMS.txt"
    sums.write_text(
        "\n".join(f"{sha256(a)}  {a.name}" for a in sorted(artefacts)) + "\n",
        encoding="utf-8")

    print()
    for a in sorted(artefacts) + [notes, sums]:
        print(f"  {a.relative_to(ROOT)}  ({a.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
