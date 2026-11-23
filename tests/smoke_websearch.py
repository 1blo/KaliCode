"""Smoke test: WebSearch actually returns results."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kali.tools.web import WebSearch
from kali.tools.base import ToolContext


async def main() -> int:
    t = WebSearch()
    ctx = ToolContext(agent=None, cwd=os.getcwd())

    print("=== backend probe ===")
    for name, fn in [
        ("bing", t._bing_search),
        ("ddg", t._ddg_search),
        ("ddg_lite", t._ddg_lite_search),
        ("wikipedia", t._wikipedia_search),
    ]:
        r = fn("python asyncio tutorial")
        print(f"  {name}: {len(r)} results")
        if r:
            print(f"      first: {r[0]['title'][:60]}")
            print(f"      url:   {r[0]['url'][:100]}")

    print("\n=== full tool run ===")
    res = await t.run({"query": "latest open source LLM models 2026", "mode": "standard"}, ctx)
    print("error:", res.error)
    text = res.render()
    print(text[:1200])
    assert not res.error, "tool errored"
    assert "http" in text, "no links in output"
    assert "No results" not in text, "no results found"

    print("\n=== domain filtering ===")
    res2 = await t.run({
        "query": "python asyncio tutorial",
        "mode": "standard",
        "allowed_domains": ["docs.python.org"],
    }, ctx)
    t2 = res2.render()
    print(t2[:600])
    assert "docs.python.org" in t2, "allowed_domains filter dropped everything"

    print("\n=== blocked_domains ===")
    res3 = await t.run({
        "query": "python asyncio tutorial",
        "mode": "standard",
        "blocked_domains": ["wikipedia.org"],
    }, ctx)
    t3 = res3.render()
    assert "wikipedia.org/wiki" not in t3, "blocked_domains not honoured"

    print("\nALL WEBSEARCH TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
