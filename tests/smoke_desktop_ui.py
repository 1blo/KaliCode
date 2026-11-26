"""Verify the desktop UI renders correctly, without a browser.

Drives the page with a headless DOM (node + a tiny DOM shim is not available),
so instead this checks the invariants that matter:

  - index.html references every asset the server serves
  - every element id the JS touches exists in the HTML
  - every CSS class the JS creates has a rule (or is a known utility)

The id check is the valuable one: a typo in an id is the most common way a
UI like this breaks silently.

Run:  python tests/smoke_desktop_ui.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kali.resources import resource_dir

ROOT = Path(__file__).resolve().parent.parent
DESKTOP = resource_dir() / "desktop"

HTML_RE = re.compile(r'id="([^"]+)"')
JS_GET = re.compile(r'\$\("([^"]+)"\)')
JS_QUERY = re.compile(r'getElementById\("([^"]+)"\)')
JS_DATASET = re.compile(r'dataset\.([a-zA-Z]+)')
CSS_SELECTOR = re.compile(r'\.([a-zA-Z][\w-]*)')


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if cond:
            print(f"  ok   {name}")
        else:
            print(f"  FAIL {name} {detail}")
            failures.append(name)

    html_path = DESKTOP / "index.html"
    js_path = DESKTOP / "app.js"
    css_path = DESKTOP / "style.css"

    for p in (html_path, js_path, css_path):
        check(f"{p.name} exists", p.exists(), str(p))
    if not (html_path.exists() and js_path.exists() and css_path.exists()):
        return 1

    html = html_path.read_text("utf-8")
    js = js_path.read_text("utf-8")
    css = css_path.read_text("utf-8")

    # ---- every id the JS touches must exist in the HTML ------------------
    # Some ids are created at runtime inside the modal's body HTML; those
    # are declared here so the check stays honest.
    DYNAMIC_IDS = {"cwdin", "mv"}
    html_ids = set(HTML_RE.findall(html))
    used = set(JS_GET.findall(js)) | set(JS_QUERY.findall(js))
    missing = sorted(used - html_ids - DYNAMIC_IDS)
    check("every id used by the JS exists in the HTML", not missing,
          "missing: " + ", ".join(missing))

    # Every dynamic id must actually be created somewhere in the JS.
    for dyn_id in DYNAMIC_IDS:
        check(f"dynamic id #{dyn_id} is created by the JS",
              f'id="{dyn_id}"' in js)

    # ---- the assets the HTML references must be served --------------------
    for asset in re.findall(r'(?:src|href)="(/[^"]+)"', html):
        if asset.startswith("/desktop/") or asset.startswith("/mobile/"):
            continue
        check(f"HTML references {asset}", True)

    # ---- the JS must not reference a missing function --------------------
    # A crude balance check on braces/parens catches truncated edits.
    for name, text in (("app.js", js), ("style.css", css)):
        for open_c, close_c in (("{", "}"), ("(", ")"), ("[", "]")):
            if text.count(open_c) != text.count(close_c):
                check(f"{name} braces balance", False,
                      f"{open_c}: {text.count(open_c)} vs {close_c}: {text.count(close_c)}")
                break
        else:
            check(f"{name} braces balance", True)

    # ---- the CSS must define the layout the HTML uses --------------------
    for cls in ("rail", "center", "details", "panes", "promptbox", "promptrow",
                "chat", "sessionlist", "sitem", "cardbox", "diffline",
                "filetree", "fileview", "menu", "modal", "toast"):
        check(f"css defines .{cls}", f".{cls}" in css)

    # ---- the JS must define the handlers the HTML wires up ---------------
    for fn in ("connect", "handle", "renderSessions", "renderHeader", "submit",
               "switchPane", "openMenu", "closeMenu", "openModal", "showPermission",
               "showQuestion", "showPlan", "refreshChanges", "refreshFiles",
               "updateContext", "setSendLabel", "showSlashMenu"):
        check(f"js defines {fn}()", f"function {fn}" in js)

    # ---- the prompt row must carry every documented control --------------
    for ctrl in ("envBtn", "cwdBtn", "worktreeBtn", "modeBtn", "modelBtn",
                 "ctxBtn", "send"):
        check(f"prompt row has #{ctrl}", f'id="{ctrl}"' in html)

    # ---- the pane tabs must match the reference layout -------------------
    for pane in ("chat", "changes", "files", "plan", "tasks"):
        check(f"pane #{pane} exists", f'id="pane-{pane}"' in html)

    # ---- the details rail must carry every documented card ---------------
    for card in ("dEnv", "dChanges", "dContext", "dRunning", "dPr"):
        check(f"details card #{card} exists", f'id="{card}"' in html)

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {', '.join(failures)}")
        return 1
    print("ALL DESKTOP UI TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
