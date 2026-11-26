"""One-off: repair the HTML-escaping helpers in the desktop and mobile UIs.

The original writes stripped HTML entities out of the JS string literals,
which broke the parser. This rewrites them using explicit character codes so
nothing can be mangled again.

The entity *names* are built at runtime from their letters so that no literal
entity sequence appears in this source file.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

AMP = chr(38)
LT = chr(60)
GT = chr(62)
QUOT = chr(34)
APOS = chr(39)


def build_escape_block(style: str) -> str:
    """Build the esc() helper.

    `style` is "map" (a lookup object) or "fn" (a switch expression).
    Both build the entity names from character codes so nothing is mangled.
    """
    # amp=  l t=  g t=  q u o t=
    names = {
        AMP: AMP + "a" + "m" + "p" + ";",
        LT: AMP + "l" + "t" + ";",
        GT: AMP + "g" + "t" + ";",
        QUOT: AMP + "q" + "u" + "o" + "t" + ";",
        APOS: AMP + "#" + "3" + "9" + ";",
    }

    if style == "map":
        pairs = ", ".join(
            f"{QUOT}{k}{QUOT}: {QUOT}{v}{QUOT}" for k, v in names.items()
        )
        return (
            "  const ESC_MAP = { " + pairs + " };\n"
            "  const esc = (s) => String(s == null ? \"\" : s)\n"
            f"    .replace(/[&<>\"']/g, (c) => ESC_MAP[c]);\n"
        )

    # "fn" style - a switch, no object allocation per call.
    arms = []
    for k, v in names.items():
        if k == QUOT:
            arms.append(f"      case String.fromCharCode(34): return {QUOT}{v}{QUOT};")
        elif k == APOS:
            arms.append(f"      case String.fromCharCode(39): return {QUOT}{v}{QUOT};")
        else:
            arms.append(f"      case {QUOT}{k}{QUOT}: return {QUOT}{v}{QUOT};")
    return (
        "  function esc(s) {\n"
        "    const t = String(s == null ? \"\" : s);\n"
        "    let out = \"\";\n"
        "    for (let i = 0; i < t.length; i++) {\n"
        "      switch (t[i]) {\n"
        + "\n".join(arms) + "\n"
        "        default: out += t[i];\n"
        "      }\n"
        "    }\n"
        "    return out;\n"
        "  }\n"
    )


def patch(path: Path, new_block: str) -> bool:
    src = io.open(path, encoding="utf-8").read()
    if new_block in src:
        print(f"  already correct: {path.name}")
        return False

    pattern = r"  function esc\(s\) \{.*?\n  \}\n"

    m = re.search(pattern, src, re.S)
    if not m:
        print(f"  PATTERN NOT FOUND in {path}")
        return False
    src = src[:m.start()] + new_block + src[m.end():]
    io.open(path, "w", encoding="utf-8", newline="\n").write(src)
    print(f"  patched: {path}")
    return True


def main() -> int:
    changed = 0
    desktop = ROOT / "kali" / "desktop" / "app.js"
    if patch(desktop, build_escape_block("fn")):
        changed += 1
    mobile = ROOT / "kali" / "mobile" / "app.js"
    if patch(mobile, build_escape_block("fn")):
        changed += 1
    print(f"done ({changed} changed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
