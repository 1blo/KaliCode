"""Full CLI end-to-end: streaming text + a live Roblox Studio MCP tool call."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kali.cli import main

if __name__ == "__main__":
    # Ask the model to list Roblox studios using the MCP tool.
    prompt = ("Use the mcp__Roblox_Studio__list_roblox_studios tool to list the open "
              "Roblox Studio instances. Then tell me their names, one per line.")
    sys.argv = ["kali", "-p", prompt, "--permission-mode", "bypassPermissions"]
    raise SystemExit(main())
