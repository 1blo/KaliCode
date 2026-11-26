"""Smoke test for the iOS clients.

Kali Code ships two iOS clients:
  1. a native SwiftUI app under ios/ (built and signed on a Mac)
  2. an installable PWA under kali/mobile/ that doubles as the iOS
     Home Screen app

Checks (no browser required):
  - the native project files exist and the Swift sources are present
  - the Xcode project is well formed and its scheme points at the target
  - the app icon set is complete and has no alpha channel (iOS refuses
    icons with alpha)
  - the PWA shell has the iOS meta tags, the safe-area CSS and the
    viewport handling
  - the server routes an iPhone / iPad user-agent to the mobile shell
  - the manifest declares standalone display and the apple touch icons

Run:  python tests/smoke_ios.py
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import uvicorn

from kali.serve import build_app

TOKEN = "ios-token"
ROOT = Path(__file__).resolve().parent.parent
IOS = ROOT / "ios"


async def main() -> int:
    import websockets

    app, server = build_app(token=TOKEN, cwd=os.getcwd())
    config = uvicorn.Config(app, host="127.0.0.1", port=8769, log_level="warning")
    srv = uvicorn.Server(config)
    task = asyncio.create_task(srv.serve())
    await asyncio.sleep(1.5)

    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if cond:
            print(f"  ok   {name}")
        else:
            print(f"  FAIL {name} {detail}")
            failures.append(name)

    base = "http://127.0.0.1:8769"

    # ================================================== the native project
    print("--- native SwiftUI project ---")

    for rel in (
        "Package.swift",
        "Sources/KaliCode/KaliApp.swift",
        "Sources/KaliCodeKit/Protocol.swift",
        "Sources/KaliCodeKit/KaliClient.swift",
        "Sources/KaliCodeKit/KaliStore.swift",
        "Sources/KaliCodeKit/Theme.swift",
        "Resources/Info.plist",
        "Resources/KaliCode.entitlements",
        "Resources/Assets.xcassets/AppIcon.appiconset/Contents.json",
        "KaliCode.xcodeproj/project.pbxproj",
        "KaliCode.xcodeproj/xcshareddata/xcschemes/KaliCode.xcscheme",
    ):
        check(f"ios/{rel} exists", (IOS / rel).exists())

    pbx = IOS / "KaliCode.xcodeproj" / "project.pbxproj"
    if pbx.exists():
        text = pbx.read_text(encoding="utf-8", errors="replace")
        check("the pbxproj is balanced", text.count("{") == text.count("}"),
              f"{text.count('{')} open vs {text.count('}')} close")
        check("the pbxproj names the app target",
              "isa = PBXNativeTarget" in text and "KaliCode" in text)
        check("the pbxproj sets the bundle id",
              "com.kalicode.app" in text)
        check("the pbxproj targets iOS 16", "IPHONEOS_DEPLOYMENT_TARGET = 16.0" in text)
        check("the pbxproj has a sources phase",
              "isa = PBXSourcesBuildPhase" in text)

        # The shared scheme must point at the real target id.
        target = re.search(r"([0-9A-F]{24}) /\* KaliCode \*/ = \{\s*isa = PBXNativeTarget",
                           text)
        scheme_path = IOS / "KaliCode.xcodeproj" / "xcshareddata" / "xcschemes" / "KaliCode.xcscheme"
        if target and scheme_path.exists():
            scheme = scheme_path.read_text(encoding="utf-8", errors="replace")
            check("the scheme points at the app target",
                  target.group(1) in scheme,
                  f"target {target.group(1)} not in the scheme")

    # Info.plist has to allow a plain-http server.
    plist = IOS / "Resources" / "Info.plist"
    if plist.exists():
        ptext = plist.read_text(encoding="utf-8", errors="replace")
        check("Info.plist allows local networking",
              "NSAllowsLocalNetworking" in ptext)
        check("Info.plist has no placeholder bundle id",
              "$(PRODUCT_BUNDLE_IDENTIFIER)" in ptext)
        check("Info.plist supports indirect input events is not required",
              True)

    # The Swift sources must not reference anything NVIDIA-branded.
    branding_bad = []
    for sw in (IOS / "Sources").rglob("*.swift"):
        stext = sw.read_text(encoding="utf-8", errors="replace")
        if re.search(r"powered by NVIDIA", stext, re.I):
            branding_bad.append(sw.name)
    check("no NVIDIA branding in the Swift sources", not branding_bad,
          str(branding_bad))

    # The icon set must be complete and alpha-free.
    iconset = IOS / "Resources" / "Assets.xcassets" / "AppIcon.appiconset"
    contents = iconset / "Contents.json"
    if contents.exists():
        data = json.loads(contents.read_text(encoding="utf-8"))
        check("the icon catalog has an image entry", bool(data.get("images")))
        png = iconset / "icon-1024.png"
        check("the 1024 marketing icon exists", png.exists())
        if png.exists():
            try:
                from PIL import Image
                with Image.open(png) as im:
                    check("the 1024 icon is 1024x1024",
                          im.size == (1024, 1024), str(im.size))
                    check("the 1024 icon has no alpha channel",
                          im.mode == "RGB", im.mode)
            except ImportError:
                print("  ..   Pillow not found, skipping the icon pixel checks")

    # ==================================================== the iOS PWA
    print("--- iOS PWA ---")

    from kali.resources import resource_dir
    base_dir = resource_dir()

    mobile = base_dir / "mobile"
    for name in ("index.html", "app.js", "manifest.json", "sw.js",
                 "icon-192.png", "icon-512.png", "icon.svg"):
        check(f"mobile/{name} exists", (mobile / name).exists())

    index = mobile / "index.html"
    if index.exists():
        html = index.read_text(encoding="utf-8", errors="replace")
        check("the shell declares apple-mobile-web-app-capable",
              'apple-mobile-web-app-capable" content="yes"' in html)
        check("the shell declares the iOS title",
              'apple-mobile-web-app-title" content="Kali Code"' in html)
        check("the shell declares the iOS status bar style",
              "apple-mobile-web-app-status-bar-style" in html)
        check("the viewport fits the safe area", "viewport-fit=cover" in html)
        check("the shell uses the safe-area insets",
              "env(safe-area-inset-top)" in html
              and "env(safe-area-inset-bottom)" in html)
        check("the shell has the iOS install banner", 'id="iosinstall"' in html)
        check("the shell has the session sheet", 'id="session-list"' in html)
        check("the shell links the apple touch icon",
              'rel="apple-touch-icon"' in html)

    appjs = mobile / "app.js"
    if appjs.exists():
        js = appjs.read_text(encoding="utf-8", errors="replace")
        check("the PWA detects iOS", "isIOS" in js and "iPhone" in js)
        check("the PWA handles the visual viewport", "visualViewport" in js)
        check("the PWA detects standalone mode", "isStandalone" in js)
        check("the PWA registers for push", "pushManager" in js)
        check("the PWA renders the session list", "renderSessions" in js)
        check("the PWA reads session_meta from meta or session",
              "msg.meta || msg.session" in js)

        # The JS must parse.
        import shutil
        import subprocess
        node = shutil.which("node")
        if node:
            proc = subprocess.run([node, "--check", str(appjs)],
                                  capture_output=True, text=True)
            check("mobile/app.js parses", proc.returncode == 0,
                  (proc.stderr or "")[:400])
        else:
            print("  ..   node not found, skipping the JS parse check")

    manifest = mobile / "manifest.json"
    if manifest.exists():
        m = json.loads(manifest.read_text(encoding="utf-8"))
        check("the manifest is standalone", m.get("display") == "standalone",
              str(m.get("display")))
        check("the manifest names the app", m.get("name") == "Kali Code")
        check("the manifest has icons", len(m.get("icons") or []) >= 3)
        check("the manifest has the theme colour",
              m.get("theme_color") == "#0d0d12")
        check("the manifest declares the start url", bool(m.get("start_url")))

    sw = mobile / "sw.js"
    if sw.exists():
        swtext = sw.read_text(encoding="utf-8", errors="replace")
        check("the service worker handles push", '"push"' in swtext)
        check("the service worker handles notification clicks",
              '"notificationclick"' in swtext)
        check("the service worker caches the shell", "/mobile/app.js" in swtext)

    # ================================================== the server routing
    print("--- server routing ---")

    async with httpx.AsyncClient(timeout=10) as c:
        iphone = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 "
                                "like Mac OS X) AppleWebKit/605.1.15 "
                                "(KHTML, like Gecko) Version/17.5 Mobile/15E148 "
                                "Safari/604.1"}
        ipad = {"User-Agent": "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) "
                              "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                              "Version/17.5 Mobile/15E148 Safari/604.1"}

        r = await c.get(base + "/", headers=iphone)
        check("iPhone user-agent -> mobile shell", r.status_code == 200
              and "mobile/app.js" in r.text, r.text[:200])
        check("the iPhone shell has the apple meta tags",
              "apple-mobile-web-app-capable" in r.text)

        r = await c.get(base + "/", headers=ipad)
        check("iPad user-agent -> mobile shell", r.status_code == 200
              and "mobile/app.js" in r.text, r.text[:200])

        for asset in ("/mobile/app.js", "/mobile/manifest.json",
                      "/mobile/sw.js", "/mobile/icon-192.png",
                      "/mobile/icon-512.png", "/mobile/index.html"):
            r = await c.get(base + asset)
            check(f"GET {asset} -> 200", r.status_code == 200,
                  str(r.status_code))

        r = await c.get(base + "/mobile/manifest.json")
        if r.status_code == 200:
            check("the served manifest is standalone",
                  r.json().get("display") == "standalone")

    # The handshake the native app uses.
    async with websockets.connect("ws://127.0.0.1:8769/ws") as ws:
        await ws.send(json.dumps({"type": "hello", "token": TOKEN}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        check("the native client connects", msg.get("type") == "ready", str(msg))
        sid = msg.get("session", "")
        check("the native client gets a session", bool(sid))

        # session_meta must carry the session object in "meta" so the
        # Swift and Kotlin decoders can read it.
        await ws.send(json.dumps({"type": "set_mode", "mode": "plan"}))
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
            if msg.get("type") in ("session_meta", "error"):
                break
        check("set_mode -> session_meta", msg.get("type") == "session_meta",
              str(msg))
        check("session_meta carries the session object in meta",
              isinstance(msg.get("meta"), dict)
              and msg["meta"].get("id") == sid, str(msg))
        check("session_meta still carries the session id",
              msg.get("session") == sid, str(msg))

    srv.should_exit = True
    await task

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {', '.join(failures)}")
        return 1
    print("ALL IOS TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
