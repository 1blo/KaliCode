"""CLI integration: /alwaysallow command + WebSearch through the real agent."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kali.cli import main

if __name__ == "__main__":
    # Interactive: exercise /alwaysallow, /permissions, then a real web search.
    sys.argv = ["kali", "--permission-mode", "default"]
    raise SystemExit(main())
