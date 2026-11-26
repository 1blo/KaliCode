"""Verify that the server actually starts through every entry point.

The `kali --serve` CLI path used to crash immediately: the CLI runs
inside an event loop and the server called `uvicorn.run`, which calls
`asyncio.run` and fails with "asyncio.run() cannot be called from a
running event loop".

This test starts the server the way a user does - as a subprocess -
and checks that it answers on /health. Both entry points are covered:

    kali --serve ...
    python -m kali.serve ...

Run:  python tests/smoke_serve_cli.py
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_health(port: int, proc: subprocess.Popen,
                    timeout: float = 25.0) -> tuple[bool, str]:
    """Poll /health until the server answers or the process dies."""
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            return False, f"the process exited with {proc.returncode}"
        try:
            r = httpx.get(base + "/health", timeout=2)
            if r.status_code == 200:
                return True, r.text
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)
        time.sleep(0.4)
    return False, last


def run_case(name: str, argv_fn, env: dict | None = None) -> None:
    """Start a server subprocess and check that it answers.

    `argv_fn` receives the port to use, so each entry point gets its
    own free port.
    """
    print(f"--- {name} ---")
    port = free_port()
    full_env = dict(os.environ)
    full_env["PYTHONUNBUFFERED"] = "1"
    if env:
        full_env.update(env)

    proc = subprocess.Popen(
        argv_fn(port),
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=full_env,
    )
    ok, detail = wait_for_health(port, proc)
    check(f"{name} answers on /health", ok, detail)
    if ok:
        check(f"{name} reports the right version", '"version":"1.2.0"' in detail
              or '"version": "1.2.0"' in detail, detail)
        # The iPhone shell must be served too.
        ua = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like "
                            "Mac OS X) AppleWebKit/605.1.15"}
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/", headers=ua, timeout=5)
            check(f"{name} serves the mobile shell to an iPhone",
                  r.status_code == 200 and "mobile/app.js" in r.text,
                  str(r.status_code))
        except Exception as e:
            check(f"{name} serves the mobile shell to an iPhone", False, str(e))

    if proc.poll() is None:
        proc.terminate()
        try:
            out = proc.communicate(timeout=10)[0]
        except subprocess.TimeoutExpired:
            proc.kill()
            out = proc.communicate()[0]
    else:
        out = proc.communicate()[0]

    if not ok:
        # A crash in the output is the most useful clue.
        tail = (out or "").strip().splitlines()[-6:]
        for line in tail:
            print(f"       | {line}")
    check(f"{name} did not crash", "RuntimeError" not in (out or ""))


def main() -> int:
    python = sys.executable

    # The CLI entry point: `kali --serve`.
    run_case("kali --serve",
             lambda port: [python, "-m", "kali.cli", "--serve",
                           "--serve-host", "127.0.0.1",
                           "--serve-port", str(port),
                           "--serve-token", "cli-test"])

    # The module entry point: `python -m kali.serve`.
    run_case("python -m kali.serve",
             lambda port: [python, "-m", "kali.serve", "--host", "127.0.0.1",
                           "--port", str(port), "--token", "module-test"])

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {', '.join(failures)}")
        return 1
    print("ALL SERVE CLI TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
