"""One-off: move `_make_handler` out of the `_HandlerBase` class body.

The function was accidentally indented into the class when the file was
rewritten. It is a module-level helper.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "kali" / "webview2.py"

src = io.open(TARGET, encoding="utf-8").read()

# Pull the block out of the class.
m = re.search(
    r"\n[ \t]*def _make_handler\(invoke_proto.*?\n[ \t]*return obj, holder\n",
    src, re.S)
if not m:
    print("pattern not found - nothing to do")
    raise SystemExit(0)

block = m.group(0)
src = src[:m.start()] + "\n" + src[m.end():]

# De-indent by four spaces.
lines = block.split("\n")
fixed = []
for line in lines:
    if line.startswith("    "):
        fixed.append(line[4:])
    else:
        fixed.append(line)
block = "\n".join(fixed)

# Insert it before the "The IUnknown stubs" comment.
marker = "# The IUnknown stubs are shared by every handler."
if marker not in src:
    print("marker not found")
    raise SystemExit(1)
src = src.replace(marker, block.rstrip() + "\n\n\n" + marker, 1)

io.open(TARGET, "w", encoding="utf-8", newline="\n").write(src)
print("moved _make_handler to module level")
