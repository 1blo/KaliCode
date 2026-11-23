"""Smoke test: MCP connectivity - connects to configured servers, lists tools."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kali.config import load_settings
from kali.mcp import McpManager


async def main() -> int:
    settings = load_settings()
    only = sys.argv[1] if len(sys.argv) > 1 else None
    configs = McpManager.collect_configs(settings, [])
    if only:
        configs = {k: v for k, v in configs.items() if k.lower() == only.lower()}
    if not configs:
        print("no MCP servers configured")
        return 1
    mgr = McpManager()
    try:
        statuses = await mgr.connect_all(configs)
        for line in statuses:
            print(f"  {line}")
        ok = False
        for name, server in mgr.servers.items():
            print(f"\n[{name}] {server.status} - {len(server.tools)} tools"
                  + (" (pending: bridge busy or host app not attached)" if server.pending_tools else ""))
            for t in list(server.tools.values())[:12]:
                print(f"   mcp__{t.server}__{t.name}")
            if len(server.tools) > 12:
                print(f"   ... +{len(server.tools) - 12} more")
            if server.status == "connected" and server.tools:
                ok = True
        return 0 if ok else 1
    finally:
        await mgr.close_all()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
