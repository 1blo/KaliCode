"""Diagnostic: corrupt the WebView2 profile cache on purpose.

The desktop shell has a watchdog that notices a UI that never connects
and wipes the profile. This creates the broken state the watchdog has to
recover from: a profile whose HTTP cache holds a stale copy of the page.

Usage:
    python tools/diag_stale_profile.py corrupt   # break the profile
    python tools/diag_stale_profile.py check     # report the state
"""
from __future__ import annotations

import sys
from pathlib import Path


def profile() -> Path:
    try:
        from kali.resources import user_data_dir

        return user_data_dir() / "webview"
    except Exception:
        return Path.home() / "AppData/Local/KaliCode/webview"


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "check"
    p = profile()
    print("profile:", p)
    print("exists:", p.exists())

    if not p.exists():
        return 0

    cache = p / "EBWebView" / "Default" / "Cache"
    files = list(cache.rglob("*")) if cache.exists() else []
    total = sum(f.stat().st_size for f in files if f.is_file())
    print(f"cache files: {len([f for f in files if f.is_file()])}, "
          f"{total / 1024:.0f} KB")

    if action == "corrupt":
        # Fill the cache with a huge blob so the browser has to evict
        # stale entries, and drop a marker file the app can detect.
        try:
            cache.mkdir(parents=True, exist_ok=True)
            (cache / "stale.marker").write_bytes(b"stale" * 100000)
            print("marked the profile as stale")
        except OSError as e:
            print("could not corrupt:", e)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
