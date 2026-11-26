"""Verify the mobile PWA's iOS behaviour without a browser.

The iOS-specific code paths in kali/mobile/app.js are the ones most
likely to break silently, so they get exercised here against a small
DOM stub: the iOS detection, the visual-viewport handling, the install
banner and the session sheet.

Run:  python tests/smoke_ios_pwa.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kali.resources import resource_dir

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


# A tiny DOM stub: enough for the mobile app to boot and for the iOS
# paths to run.
STUB = r"""
// ---- minimal DOM -------------------------------------------------------
class ClassList {
  constructor(el) { this.el = el; this.set = new Set(); }
  add(...c) { c.forEach(x => this.set.add(x)); }
  remove(...c) { c.forEach(x => this.set.delete(x)); }
  toggle(c, on) { if (on === undefined) { this.set.has(c) ? this.set.delete(c) : this.set.add(c); } else if (on) this.set.add(c); else this.set.delete(c); }
  contains(c) { return this.set.has(c); }
}
class El {
  constructor(tag) {
    this.tagName = (tag || "div").toUpperCase();
    this.children = [];
    this.parent = null;
    this._html = "";
    this._text = "";
    this.style = {};
    this.dataset = {};
    this.classList = new ClassList(this);
    this.className = "";
    this.handlers = {};
    this.value = "";
    this.disabled = false;
  }
  set className(v) {
    this._className = String(v);
    this.classList.set = new Set(String(v).split(/\s+/).filter(Boolean));
  }
  get className() { return this._className || ""; }
  set innerHTML(v) { this._html = String(v); }
  get innerHTML() { return this._html; }
  set textContent(v) { this._text = String(v); }
  get textContent() { return this._text; }
  appendChild(c) { c.parent = this; this.children.push(c); return c; }
  removeChild(c) { this.children = this.children.filter(x => x !== c); }
  remove() { if (this.parent) this.parent.removeChild(this); }
  querySelector(sel) { return this._q(sel)[0] || null; }
  querySelectorAll(sel) { return this._q(sel); }
  _q(sel) {
    const out = [];
    const walk = (el) => {
      for (const c of el.children) {
        if (matches(c, sel)) out.push(c);
        walk(c);
      }
    };
    walk(this);
    return out;
  }
  setAttribute(k, v) { this[k] = v; }
  addEventListener(k, fn) { (this.handlers[k] ||= []).push(fn); }
  fire(k, ev) { (this.handlers[k] || []).forEach(fn => fn(ev || {})); }
  scrollIntoView() {}
}
function matches(el, sel) {
  if (sel.startsWith(".")) return el.classList.contains(sel.slice(1));
  if (sel.startsWith("#")) return el.id === sel.slice(1);
  return el.tagName === sel.toUpperCase();
}

// ---- the document ------------------------------------------------------
const IDS = ["log", "input", "send", "status", "title", "token", "connect",
             "lockerr", "lock", "reset", "hint", "iosinstall", "iosok",
             "ioslater", "sessions-btn", "sheet", "sheet-close", "sheet-new",
             "sheet-disconnect", "session-list"];
const byId = {};
IDS.forEach(id => {
  const e = new El(id === "input" || id === "token" ? "input" : "div");
  e.id = id;
  byId[id] = e;
});
const body = new El("body");
IDS.forEach(id => body.appendChild(byId[id]));

global.document = {
  getElementById: (id) => byId[id] || null,
  createElement: (tag) => new El(tag),
  addEventListener: (k, fn) => { (document._h ||= {})[k] = fn; },
  _h: {},
  body: body,
  documentElement: {
    style: { setProperty: (k, v) => { document._vars ||= {}; document._vars[k] = v; } },
  },
  _vars: {},
};
// Node 24 has a built-in read-only `navigator`, so it has to be
// replaced with defineProperty rather than assignment.
Object.defineProperty(global, "navigator", {
  configurable: true,
  writable: true,
  value: {
    userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15",
    platform: "iPhone",
    maxTouchPoints: 5,
    standalone: false,
    serviceWorker: { register: () => Promise.resolve(), ready: Promise.resolve({ pushManager: { getSubscription: () => Promise.resolve(null) } }) },
    sendBeacon: () => true,
  },
});
global.Notification = undefined;
global.location = { protocol: "https:", host: "example.onrender.com", search: "" };
global.URLSearchParams = URLSearchParams;
global.WebSocket = class {
  constructor() { this.readyState = 0; }
  send() {} close() {}
};
global.requestAnimationFrame = (fn) => fn();
global.setTimeout = (fn, ms) => 0;   // do not run the deferred timers
global.console = console;

global.localStorage = {
  _d: {},
  getItem(k) { return this._d[k] ?? null; },
  setItem(k, v) { this._d[k] = String(v); },
  removeItem(k) { delete this._d[k]; },
};

global.window = {
  innerHeight: 800,
  innerWidth: 390,
  matchMedia: (q) => ({ matches: false, media: q, addEventListener() {} }),
  addEventListener: (k, fn) => { (global.window._h ||= {})[k] = fn; },
  _h: {},
  visualViewport: null,
  navigator: global.navigator,
};

// ---- run the app -------------------------------------------------------
const SRC = require("fs").readFileSync(process.argv[2], "utf8");
eval(SRC);

// ---- report -----------------------------------------------------------
const K = global.window.KaliMobile || {};
const out = {
  isIOS: K.isIOS ?? null,
  isStandalone: K.isStandalone ?? null,
  vvh: document._vars["--vvh"] || null,
  iosinstallShown: byId["iosinstall"].classList.contains("show"),
  sheetExists: !!byId["sheet"],
  sessionListChildren: byId["session-list"].children.length,
  sessionsBtn: !!byId["sessions-btn"],
};
console.log("__RESULT__" + JSON.stringify(out));
"""


def main() -> int:
    node = shutil.which("node")
    if not node:
        print("  ..   node not found, skipping the PWA behaviour check")
        return 0

    mobile = resource_dir() / "mobile" / "app.js"
    check("mobile/app.js exists", mobile.exists(), str(mobile))

    script = Path(os.environ.get("TEMP", ".")) / "kali_ios_pwa_stub.js"
    script.write_text(STUB, encoding="utf-8")

    proc = subprocess.run([node, str(script), str(mobile)],
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        check("the PWA boots without an exception", False,
              (proc.stderr or "")[-800:])
        return report()

    line = ""
    for ln in (proc.stdout or "").splitlines():
        if ln.startswith("__RESULT__"):
            line = ln[len("__RESULT__"):]
    check("the PWA boots without an exception", bool(line),
          (proc.stderr or "")[-800:])
    if not line:
        return report()

    data = json.loads(line)
    check("the PWA detects iOS", data["isIOS"] is True, str(data))
    check("the PWA is not in standalone mode in a normal tab",
          data["isStandalone"] is False, str(data))
    check("the PWA sets the visual viewport height",
          data["vvh"] is not None, str(data))
    check("the PWA has the session sheet", data["sheetExists"] is True, str(data))
    check("the PWA has a sessions button", data["sessionsBtn"] is True, str(data))

    return report()


def report() -> int:
    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {', '.join(failures)}")
        return 1
    print("ALL IOS PWA TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
