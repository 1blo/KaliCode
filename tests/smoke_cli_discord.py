"""CLI integration: `kali` starts the Discord presence and clears it on exit."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kali.cli import main

if __name__ == "__main__":
    # Interactive mode with a prompt, then EOF to exit.
    sys.argv = ["kali", "Say hi in one short sentence.", "--permission-mode", "bypassPermissions"]
    raise SystemExit(main())
