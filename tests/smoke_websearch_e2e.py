"""End-to-end: the model actually calls WebSearch and gets usable results."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kali.agent import Agent
from kali.config import AgentConfig, load_settings
from kali.ui import UI


async def main() -> int:
    settings = load_settings()
    ui = UI(verbose=True)
    agent = Agent(AgentConfig(model="stepfun-ai/step-5-preview",
                              permission_mode="bypassPermissions",
                              settings=settings), ui=ui)

    print("=== asking the model to use WebSearch ===")
    result = await agent.run_turn(
        "Use the WebSearch tool to find the official Python documentation page for "
        "the asyncio module. Then tell me the exact URL you found."
    )
    print("\n--- answer ---")
    print(result.text[:900])

    tool_msgs = [m for m in agent.messages if m.get("role") == "tool"]
    print(f"\n=== tool calls made: {len(tool_msgs)} ===")
    for m in tool_msgs:
        content = str(m.get("content", ""))
        print("  tool result:", content[:300].replace("\n", " | "))
        assert "http" in content, "WebSearch returned no links!"

    assert tool_msgs, "model never called WebSearch"
    print("\nWEBSEARCH E2E PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
