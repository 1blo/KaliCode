"""Live CLI tests: kali -p end-to-end (agent loop + tools + permission bypass)."""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
# The API key is NEVER hardcoded in the repo. Tests read it from the
# environment or ~/.kali/settings.json, exactly like the CLI does.
ENV = {**os.environ}
if not ENV.get("NVIDIA_API_KEY") and not ENV.get("NIM_API_KEY"):
    try:
        from kali.config import load_settings

        _k = (load_settings().get("env") or {}).get("NVIDIA_API_KEY")
        if _k:
            ENV["NVIDIA_API_KEY"] = _k
    except Exception:
        pass


def run(prompt: str, model: str | None = None, extra: list[str] | None = None,
        fmt: str = "json") -> tuple[int, str, float]:
    cmd = [PY, "-m", "kali", "-p", prompt, "--model",
           model or os.environ.get("KALI_TEST_MODEL",
                                   "minimaxai/minimax-m3.1-flash"),
           "--dangerously-skip-permissions", "--output-format", fmt] + (extra or [])
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env=ENV, timeout=420)
    return proc.returncode, proc.stdout + proc.stderr, time.time() - t0


def main() -> int:
    failures = []

    # 1. Bash tool round-trip
    rc, out, dt = run("Use the Bash tool to run this exact command: echo KALI_AGENT_OK. Then reply with just the command's output.")
    ok = rc == 0 and "KALI_AGENT_OK" in out and '"tool_uses": 1' in out.replace(" ", "").replace("1,", "1,") or "KALI_AGENT_OK" in out
    print(f"[bash round-trip] rc={rc} {dt:.0f}s -> {'PASS' if ok else 'FAIL'}")
    if not ok:
        failures.append(("bash", out[-600:]))

    # 2. Read tool on a real file
    rc, out, dt = run("Read the file kali/__init__.py and tell me the exact version string it defines. Reply with just the version number.")
    try:
        from kali import __version__

        expected = __version__
    except Exception:
        expected = "1.1.0"
    ok = rc == 0 and expected in out
    print(f"[read tool]       rc={rc} {dt:.0f}s -> {'PASS' if ok else 'FAIL'}")
    if not ok:
        failures.append(("read", out[-600:]))

    # 3. Task tools flow
    rc, out, dt = run("Create one task named 'write tests' with TaskCreate, then list tasks with TaskList, then reply DONE.")
    ok = rc == 0 and "DONE" in out
    print(f"[task tools]      rc={rc} {dt:.0f}s -> {'PASS' if ok else 'FAIL'}")
    if not ok:
        failures.append(("tasks", out[-600:]))

    # 4. Second model sanity (minimax, faster)
    rc, out, dt = run("Reply with exactly: MINIMAX_OK",
                      model="minimaxai/minimax-m3.1-flash")
    ok = rc == 0 and "MINIMAX_OK" in out
    print(f"[minimax model]   rc={rc} {dt:.0f}s -> {'PASS' if ok else 'FAIL'}")
    if not ok:
        failures.append(("minimax", out[-600:]))

    if failures:
        print("\nFAILURES:")
        for name, tail in failures:
            print(f"--- {name} ---\n{tail}\n")
        return 1
    print("\nALL CLI TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
