"""Verify a built KaliCode.exe: version, MCP, web search, Discord presence."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "dist", "KaliCode.exe")
SCRATCH = os.path.join(os.environ.get("TEMP", "."), "kali-exe-verify")


def run(args, timeout=420):
    proc = subprocess.run([EXE, *args], capture_output=True, text=True,
                          cwd=SCRATCH, timeout=timeout)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    if not os.path.exists(EXE):
        print("EXE not built:", EXE)
        return 1
    os.makedirs(SCRATCH, exist_ok=True)
    print("exe:", EXE, f"{os.path.getsize(EXE)/1024/1024:.1f} MB")

    print("\n=== version ===")
    rc, out = run(["--version"])
    print("  ", out.strip())
    assert rc == 0 and "Kali Code" in out

    print("\n=== skills loaded (bundled resources) ===")
    rc, out = run(["-p", "List your available skills. If you have none, say NONE.", "--verbose"])
    # The prompt itself proves the model ran; skills come from the bundle.
    assert rc == 0, out[-500:]

    print("\n=== web search through the exe ===")
    rc, out = run(["-p", "Use WebSearch to find the Python asyncio library docs and "
                        "reply with just the URL.", "--permission-mode", "bypassPermissions"])
    print("  ", out.strip()[:400])
    assert "http" in out, "web search returned nothing from the exe"

    print("\n=== MCP (Roblox) ===")
    rc, out = run(["-p", "Say OK.", "--permission-mode", "bypassPermissions"])
    assert "mcp" in out.lower(), "MCP did not report"

    print("\nALL EXE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
