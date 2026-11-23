"""Tests for /alwaysallow and the fixed WebSearch."""
import asyncio
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kali.permissions import PermissionManager, _update_user_settings
from kali.tools.web import WebSearch, _decode_bing_url
from kali.tools.base import ToolContext


def test_always_allow_bypass():
    print("=== /alwaysallow (no args) ===")
    pm = PermissionManager({})
    assert pm.check("Bash", {"command": "rm -rf /"}).behavior == "ask", "baseline should ask"

    msg = pm.always_allow("")
    print("  ", msg)
    d = pm.check("Bash", {"command": "rm -rf /"})
    print("   check ->", d.behavior, "|", d.reason)
    assert d.behavior == "allow", "always allow did not bypass"
    assert pm.allow_all is True
    assert pm.mode == "bypassPermissions"

    # every tool type is allowed
    for tool in ("Bash", "Write", "Edit", "WebFetch", "WebSearch"):
        assert pm.check(tool, {}).behavior == "allow", f"{tool} not allowed"
    print("   all tools allowed: OK")


def test_always_allow_pattern():
    print("\n=== /alwaysallow 'git status' ===")
    pm = PermissionManager({})
    msg = pm.always_allow("git status")
    print("  ", msg)
    assert pm.check("Bash", {"command": "git status --short"}).behavior == "allow"
    assert pm.check("Bash", {"command": "git status"}).behavior == "allow"
    other = pm.check("Bash", {"command": "del important.txt"})
    print("   unrelated command ->", other.behavior)
    assert other.behavior == "ask", "unrelated command should still ask"
    print("   pattern scoped correctly: OK")


def test_settings_not_polluted():
    print("\n=== settings file integrity ===")
    from kali.config import USER_DIR

    path = USER_DIR / "settings.json"
    original = path.read_text(encoding="utf-8")
    before = json.loads(original)
    try:
        pm = PermissionManager({})
        pm.always_allow("")
        after = json.loads(path.read_text(encoding="utf-8"))
        print("   permissionMode:", after.get("permissionMode"))
        assert after.get("permissionMode") == "bypassPermissions"
        # the NVIDIA key and mcpServers must survive untouched
        assert after.get("env", {}).get("NVIDIA_API_KEY") == before.get("env", {}).get("NVIDIA_API_KEY")
        assert "Roblox_Studio" in (after.get("mcpServers") or {}), "mcpServers lost!"
        assert after.get("discord", {}).get("clientId") == before.get("discord", {}).get("clientId")
        print("   env/mcpServers/discord preserved: OK")
    finally:
        # restore the file byte-for-byte
        path.write_text(original, encoding="utf-8")
        restored = json.loads(path.read_text(encoding="utf-8"))
        print("   restored permissionMode ->", restored.get("permissionMode"))
        assert restored.get("permissionMode") == before.get("permissionMode")


def test_bing_url_decode():
    print("\n=== bing redirect decode ===")
    sample = ("https://www.bing.com/ck/a?!&&p=abc&u=a1aHR0cHM6Ly9yZWFscHl0aG9uLmNvbS9hc3luYy1pby1weXRob24v"
              "&ntb=1")
    out = _decode_bing_url(sample)
    print("   ->", out)
    assert out == "https://realpython.com/async-io-python/", f"bad decode: {out}"
    # non-bing urls pass through
    assert _decode_bing_url("https://example.com/x") == "https://example.com/x"
    print("   OK")


async def test_websearch():
    print("\n=== WebSearch ===")
    t = WebSearch()
    ctx = ToolContext(agent=None, cwd=os.getcwd())
    res = await t.run({"query": "python asyncio tutorial", "mode": "standard"}, ctx)
    text = res.render()
    assert not res.error
    assert "http" in text, "no links"
    print("   results:", text.count("http"))
    print("   sample:", text.split("\n")[2][:80] if len(text.split("\n")) > 2 else "")

    # empty query
    bad = await t.run({"query": "", "mode": "standard"}, ctx)
    assert bad.error, "empty query should error"
    print("   empty query guarded: OK")

    # domain filter
    f = await t.run({"query": "python asyncio tutorial", "mode": "standard",
                     "allowed_domains": ["docs.python.org"]}, ctx)
    ft = f.render()
    assert "docs.python.org" in ft
    assert "realpython.com" not in ft, "allowed_domains leaked a result"
    print("   allowed_domains honoured: OK")

    # blocked domain
    b = await t.run({"query": "python asyncio tutorial", "mode": "standard",
                     "blocked_domains": ["realpython.com"]}, ctx)
    bt = b.render()
    assert "realpython.com" not in bt, "blocked_domains leaked a result"
    print("   blocked_domains honoured: OK")


def main():
    test_always_allow_bypass()
    test_always_allow_pattern()
    test_settings_not_polluted()
    test_bing_url_decode()
    asyncio.run(test_websearch())
    print("\nALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
