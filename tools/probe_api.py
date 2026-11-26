"""Probe the NIM chat completions endpoint directly.

Usage:
    python tools/probe_api.py [model]
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "https://integrate.api.nvidia.com/v1/chat/completions"


def key() -> str:
    k = os.environ.get("NVIDIA_API_KEY", "").strip()
    if k:
        return k
    try:
        from kali.settings import load_settings

        return str((load_settings().get("apiKey") or "")).strip()
    except Exception:
        return ""


def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else "minimaxai/minimax-m3.1-flash"
    k = key()
    if not k:
        print("no API key")
        return 1
    print("model:", model)

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Say hi in three words."}],
        "max_tokens": 64,
        "stream": False,
    }
    req = urllib.request.Request(
        BASE,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {k}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read().decode("utf-8", "replace")
        print(f"status {r.status} in {time.time() - t0:.1f}s")
        data = json.loads(raw)
        print(json.dumps(data.get("choices", [{}])[0], indent=2)[:800])
        return 0
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} in {time.time() - t0:.1f}s")
        print(e.read().decode("utf-8", "replace")[:1200])
        return 2
    except Exception as e:
        print(f"error after {time.time() - t0:.1f}s: {type(e).__name__}: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
