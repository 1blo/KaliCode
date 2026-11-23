"""End-to-end: Kali's Agent calls a real Roblox Studio MCP tool."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kali.agent import Agent
from kali.config import AgentConfig
from kali.ui import UI


async def main() -> int:
    ui = UI(verbose=False)
    agent = Agent(AgentConfig(model="stepfun-ai/step-5-preview",
                              permission_mode="bypassPermissions", settings={}), ui=ui)

    # Roblox's MCP bridge path is machine specific, so read it from the
    # user's settings instead of hardcoding a path.
    roblox_bat = os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "Roblox", "mcp.bat")
    cfg = {
        "mcpServers": {
            "Roblox_Studio": {
                "command": "cmd.exe",
                "args": ["/c", roblox_bat],
                "timeout": 120000,
                "toolsTimeout": 90000,
            }
        }
    }
    statuses = await agent.mcp.connect_all(cfg["mcpServers"])
    for s in statuses:
        print("MCP:", s, flush=True)
    agent._register_mcp_tools(eager=True)
    print(f"registered tools: {len(agent.tools)}", flush=True)
    print(f"roblox tools: {[t for t in agent.tools if 'Roblox' in t][:5]}", flush=True)

    # Call list_roblox_studios directly through the agent's tool wrapper.
    name = "mcp__Roblox_Studio__list_roblox_studios"
    if name not in agent.tools:
        print("MISSING TOOL", flush=True)
        return 1
    from kali.tools.base import ToolContext
    res = await agent.tools[name].run({}, ToolContext(agent=agent, cwd=os.getcwd()))
    print("call error:", res.error, flush=True)
    print("result:", (res.output or "")[:700], flush=True)

    await agent.mcp.close_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
