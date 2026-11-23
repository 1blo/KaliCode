"""Interactive REPL smoke test: feed a prompt through the real REPL loop
and confirm the Roblox MCP tool is called and streaming output appears.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kali.cli import main

if __name__ == "__main__":
    # The REPL accepts a prompt as a positional arg (same as `kali "..."`).
    sys.argv = ["kali",
                "List the open Roblox Studio instances using the MCP tool, then "
                "print only their names, one per line.",
                "--permission-mode", "bypassPermissions"]
    raise SystemExit(main())
