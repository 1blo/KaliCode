"""Print the on-disk layout of the PyInstaller extraction directory.

The one-file build unpacks itself into a temp folder when it runs. This
starts the frozen exe, asks it where that folder is, and lists the UI
asset folders inside it.

Usage:
    python tools/show_bundle_layout.py
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "dist" / "KaliCode.exe"

CODE = r'''
import os, sys, json
sys.path.insert(0, r"C:\Users\milanvivas\Documents\KaliCode")
import kali.resources as res
meipass = getattr(sys, "_MEIPASS", None)
print(json.dumps({
    "frozen": getattr(sys, "frozen", False),
    "_MEIPASS": meipass,
    "pkg_dir": str(res.Path(res.__file__).resolve().parent),
    "bundle_dir": str(res.bundle_dir()),
    "ui_base": str(res.ui_base_dir()),
}))
'''


def main() -> int:
    if not EXE.exists():
        print(f"{EXE} not found - build it first")
        return 1

    env = dict(os.environ)
    env["KALI_API_KEY"] = "test-key-not-used"
    env["PYTHONUNBUFFERED"] = "1"

    # Run the frozen exe with a tiny helper that prints the layout. The
    # exe passes unknown args to the CLI, so use the -c form through the
    # module entry point if available; otherwise fall back to inspecting
    # the temp folder directly.
    proc = subprocess.run([str(EXE), "--bundle-info"], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=180)
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out[-4000:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
