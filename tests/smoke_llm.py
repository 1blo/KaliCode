"""Live test of the NVIDIA NIM streaming client (kali/llm.py) on all 3 models."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kali.llm import stream_chat

MODELS = [
    "stepfun-ai/step-5-preview",
    "moonshotai/kimi-k3.1-pro",
    "minimaxai/minimax-m3.1-flash",
]


async def test_model(model: str) -> bool:
    payload = {
        "model": model,
        "max_tokens": 512,
        "reasoning_effort": "low",
        "stream": True,
        "messages": [{"role": "user", "content": "Reply with exactly: KALI_LLM_OK"}],
    }
    counts = {"thinking": 0, "text": 0}
    resp = await stream_chat(payload, on_event=lambda ev: counts.__setitem__(
        ev.type, counts.get(ev.type, 0) + 1) if ev.type in counts else None)
    ok = "KALI_LLM_OK" in resp.content
    print(f"  {model}")
    print(f"    content   : {resp.content.strip()!r}")
    print(f"    reasoning : {resp.reasoning[:60]!r}... ({len(resp.reasoning)} chars, {counts['thinking']} deltas)")
    print(f"    text      : {counts['text']} deltas")
    print(f"    usage     : {resp.usage}")
    print(f"    finish    : {resp.finish_reason}  -> {'PASS' if ok else 'FAIL'}")
    return ok


async def test_tool_call() -> bool:
    payload = {
        "model": "stepfun-ai/step-5-preview",
        "max_tokens": 1024,
        "reasoning_effort": "low",
        "stream": True,
        "messages": [{"role": "user", "content": "Use the get_weather tool for Paris."}],
        "tools": [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather for a city",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }],
        "tool_choice": "auto",
    }
    resp = await stream_chat(payload)
    ok = bool(resp.tool_calls) and resp.tool_calls[0].name == "get_weather" \
        and "Paris" in resp.tool_calls[0].arguments
    for tc in resp.tool_calls:
        print(f"    tool_call: {tc.name}({tc.arguments})")
    print(f"    finish   : {resp.finish_reason}  -> {'PASS' if ok else 'FAIL'}")
    return ok


async def main() -> int:
    results = []
    for m in MODELS:
        try:
            results.append(await test_model(m))
        except Exception as e:
            print(f"  {m} -> EXCEPTION: {type(e).__name__}: {e}")
            results.append(False)
    print("  tool-calling (step-5):")
    try:
        results.append(await test_tool_call())
    except Exception as e:
        print(f"    EXCEPTION: {type(e).__name__}: {e}")
        results.append(False)
    print(f"\n{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
