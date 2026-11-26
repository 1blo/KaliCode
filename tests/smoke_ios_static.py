"""A static sanity check for the Swift sources.

There is no Swift toolchain on Windows, so the iOS code cannot be
compiled here. This check catches the mistakes that are cheap to make
and expensive to find on a Mac:

  - unbalanced braces / brackets / parentheses
  - a `switch` over an enum that does not handle every case
  - a `ForEach` over a collection without an `id`
  - a pattern match against an enum case whose arity changed
  - TODO / FIXME markers left behind
  - NVIDIA branding in the user-facing strings

Run:  python tests/smoke_ios_static.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IOS = ROOT / "ios"
SOURCES = IOS / "Sources"
TESTS = IOS / "Tests"

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def strip_code(text: str) -> str:
    """Remove strings and comments so the brace counting is reliable.

    Swift string interpolation (`\\(...)`) keeps its contents in the
    code, because those really are balanced expressions. Raw strings
    (`#\"...\"#`) are handled as well.

    The scanner uses an explicit stack so that a string inside an
    interpolation does not end the outer string.
    """
    out: list[str] = []
    i = 0
    n = len(text)

    # Stack of open string contexts. Each entry is the number of '#'
    # that opened it (0 for a normal string), or -1 for an
    # interpolation expression. The interpolation entries also carry a
    # paren depth so that a nested call like String(format:...) does
    # not end the interpolation early.
    strings: list[int] = []
    depths: list[int] = []

    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        # ---- inside an interpolation expression -----------------------
        if strings and strings[-1] == -1:
            if c == '"':
                # A nested string: consume it whole.
                j = i + 1
                while j < n:
                    if text[j] == "\\":
                        j += 2
                        continue
                    if text[j] == '"':
                        break
                    j += 1
                out.append(" ")          # the nested string is data
                i = j + 1
                continue
            if c == "(":
                depths[-1] += 1
                out.append(c)
                i += 1
                continue
            if c == ")":
                if depths[-1] == 0:
                    strings.pop()
                    depths.pop()
                    out.append(c)
                    i += 1
                    continue
                depths[-1] -= 1
                out.append(c)
                i += 1
                continue
            out.append(c)
            i += 1
            continue

        # ---- inside a string -----------------------------------------
        if strings:
            hashes = strings[-1]
            if c == "\\" and nxt == "(" and not hashes:
                # Interpolation: keep the expression, drop only the
                # backslash so the parens stay balanced.
                out.append(" (")
                i += 2
                # Push a marker so the matching ')' ends the interpolation.
                strings.append(-1)
                depths.append(0)
                continue
            if hashes:
                if c == '"' and text[i + 1:i + 1 + hashes] == "#" * hashes:
                    strings.pop()
                    depths.pop()
                    i += 1 + hashes
                    continue
                i += 1
                continue
            if c == "\\":
                i += 2
                continue
            if c == '"':
                strings.pop()
                depths.pop()
                i += 1
                continue
            i += 1
            continue

        # ---- outside any string ---------------------------------------
        if c == "/" and nxt == "/":
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        # A raw string: #"..."#
        if c == "#":
            j = i
            while j < n and text[j] == "#":
                j += 1
            if j < n and text[j] == '"':
                strings.append(j - i)
                depths.append(0)
                i = j + 1
                continue
        if c == '"':
            strings.append(0)
            depths.append(0)
            i += 1
            continue
        out.append(c)
        i += 1

    return "".join(out)


def main() -> int:
    files = sorted(SOURCES.rglob("*.swift")) + sorted(TESTS.rglob("*.swift"))
    check("there are Swift sources to check", len(files) >= 5,
          f"found {len(files)}")

    all_text = ""

    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        all_text += text
        code = strip_code(text)

        # ---- balanced delimiters ------------------------------------
        for open_c, close_c, label in (("{", "}", "braces"),
                                       ("[", "]", "brackets"),
                                       ("(", ")", "parens")):
            o = code.count(open_c)
            c = code.count(close_c)
            check(f"{f.name}: {label} balanced", o == c, f"{o} vs {c}")

        # ---- every case handled in a switch over ChatItem ----------
        if f.name == "KaliApp.swift":
            cases = set(re.findall(r"case \.(user|assistant|thinking|error|tool|plan|toolCall)\b",
                                   code))
            expected = {"user", "assistant", "thinking", "error", "tool",
                        "plan", "toolCall"}
            check("KaliApp.swift handles every ChatItem case",
                  expected <= cases, str(sorted(expected - cases)))

        if f.name == "KaliStore.swift":
            # The row-rebuilding code must carry the trailing `id`,
            # otherwise the row loses its identity on every token.
            check("KaliStore.swift rebuilds an assistant row with the same id",
                  ".assistant(previous + text, id: id)" in text)
            check("KaliStore.swift rebuilds a thinking row with the same id",
                  ".thinking(previous + text, id: id)" in text)
            check("KaliStore.swift keeps the id when a tool finishes",
                  "elapsed: msg.elapsed, output: msg.output,\n                                     id: id)"
                  in text or "output: msg.output, id: id)" in text)

        # ---- ForEach needs an id -------------------------------------
        for m in re.finditer(r"ForEach\(([^)]*)\)\s*\{", code):
            arg = m.group(1)
            check(f"{f.name}: ForEach has an id or a keyed collection",
                  "id:" in arg or "id \\" in arg or "." in arg,
                  arg[:60])

        # ---- no leftover markers -------------------------------------
        check(f"{f.name}: no TODO/FIXME markers",
              not re.search(r"\b(TODO|FIXME|XXX)\b", text))

        # ---- no NVIDIA branding -------------------------------------
        check(f"{f.name}: no NVIDIA branding",
              not re.search(r"powered by NVIDIA", text, re.I))

    # ---- the whole project agrees on the version --------------------
    versions = set(re.findall(r'CFBundleShortVersionString</key>\s*<string>([^<]+)',
                              (IOS / "Resources" / "Info.plist").read_text(
                                  encoding="utf-8", errors="replace")))
    check("the Info.plist has exactly one version", len(versions) == 1,
          str(versions))
    if versions:
        check("the iOS version matches the package",
              versions.pop() == "1.2.0", "expected 1.2.0")

    # ---- the store and the client agree on the protocol fields ------
    protocol = (SOURCES / "KaliCodeKit" / "Protocol.swift").read_text(
        encoding="utf-8", errors="replace")
    store = (SOURCES / "KaliCodeKit" / "KaliStore.swift").read_text(
        encoding="utf-8", errors="replace")
    for field in ("type", "session", "text", "id", "name", "summary",
                  "output", "elapsed", "ok", "reason", "plan", "question",
                  "usage", "meta", "sessions", "model", "cwd"):
        check(f"ServerMessage has the {field} field",
              re.search(rf"public var {field}\b", protocol) is not None)

    # Every message type the store switches on must be a type the
    # server actually sends.
    server = (ROOT / "kali" / "serve.py").read_text(encoding="utf-8",
                                                    errors="replace")
    server_types = set(re.findall(r'"type":\s*"([a-z_]+)"', server))
    handled = set(re.findall(r'case "([a-z_]+)":', store))
    unknown = handled - server_types
    check("the store only handles message types the server sends",
          not unknown, str(sorted(unknown)))

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {', '.join(failures)}")
        return 1
    print("ALL IOS STATIC TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
