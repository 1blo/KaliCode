"""Chat-completions client with SSE streaming and tool-call accumulation.

Speaks the OpenAI wire format directly to the configured endpoint - no
translation proxy needed.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

import httpx

from .config import CHAT_COMPLETIONS_URL, resolve_api_key

RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


class LLMError(Exception):
    pass


@dataclass
class ToolCall:
    index: int = 0
    id: str = ""
    name: str = ""
    arguments: str = ""  # accumulated JSON fragment

    def complete(self) -> bool:
        if not self.name:
            return False
        if not self.arguments:
            return True
        try:
            json.loads(self.arguments)
            return True
        except Exception:
            return False


@dataclass
class StreamEvent:
    type: str  # "thinking" | "text" | "tool_start" | "tool_delta" | "tool_end" | "finish" | "usage" | "error"
    text: str = ""
    tool_call: ToolCall | None = None
    finish_reason: str | None = None
    usage: dict | None = None


@dataclass
class LLMResponse:
    content: str = ""
    reasoning: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict = field(default_factory=dict)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {resolve_api_key()}",
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "User-Agent": "kali-code/1.0",
    }


def estimate_tokens(text: str) -> int:
    """Cheap heuristic (~4 chars/token); good enough for auto-compact."""
    return max(1, len(text) // 4)


def build_payload(
    messages: list[dict],
    model: str,
    max_tokens: int,
    reasoning_effort: str | None = None,
    tools: list[dict] | None = None,
    stream: bool = True,
) -> dict:
    payload: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    return payload


async def stream_chat(
    payload: dict,
    on_event: Callable[[StreamEvent], None] | None = None,
    timeout: float = 600.0,
    max_retries: int = 2,
) -> LLMResponse:
    """Stream a completion, invoke on_event per delta, return the accumulated response."""
    result = LLMResponse()
    tool_map: dict[int, ToolCall] = {}
    api_key = resolve_api_key()

    last_error = ""
    for attempt in range(max_retries + 1):
        headers = dict(_headers())
        headers["Authorization"] = f"Bearer {api_key}"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=30.0)) as client:
                async with client.stream("POST", CHAT_COMPLETIONS_URL, headers=headers, json=payload) as resp:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", "replace")
                        if resp.status_code in RETRYABLE_STATUS and attempt < max_retries:
                            last_error = f"HTTP {resp.status_code}: {body[:300]}"
                            await _backoff(attempt)
                            continue
                        raise LLMError(f"HTTP {resp.status_code} from the API: {body[:800]}")

                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except Exception:
                            continue

                        if chunk.get("usage"):
                            result.usage = chunk["usage"]
                            if on_event:
                                on_event(StreamEvent(type="usage", usage=chunk["usage"]))

                        for choice in chunk.get("choices") or []:
                            fr = choice.get("finish_reason")
                            if fr:
                                result.finish_reason = fr
                            delta = choice.get("delta") or {}

                            if (rc := delta.get("reasoning_content")):
                                result.reasoning += rc
                                if on_event:
                                    on_event(StreamEvent(type="thinking", text=rc))
                            if (c := delta.get("content")):
                                result.content += c
                                if on_event:
                                    on_event(StreamEvent(type="text", text=c))
                            for tc in delta.get("tool_calls") or []:
                                idx = int(tc.get("index", 0))
                                call = tool_map.get(idx)
                                if call is None:
                                    call = ToolCall(index=idx)
                                    tool_map[idx] = call
                                if tc.get("id"):
                                    call.id = tc["id"]
                                fn = tc.get("function") or {}
                                if fn.get("name"):
                                    call.name += fn["name"]
                                if fn.get("arguments"):
                                    call.arguments += fn["arguments"]
                                if on_event:
                                    on_event(StreamEvent(type="tool_delta", tool_call=call))
            break  # success
        except (httpx.TransportError, httpx.RemoteProtocolError) as e:
            last_error = str(e)
            if attempt < max_retries:
                await _backoff(attempt)
                continue
            raise LLMError(f"connection error: {e}") from e

    result.tool_calls = [tool_map[k] for k in sorted(tool_map)]
    for tc in result.tool_calls:
        if not tc.complete():
            raise LLMError(
                f"model returned malformed tool call '{tc.name}': arguments incomplete"
            )
    if last_error and not (result.content or result.tool_calls):
        raise LLMError(last_error)
    if on_event:
        on_event(StreamEvent(type="finish", finish_reason=result.finish_reason, usage=result.usage))
    return result


async def _backoff(attempt: int) -> None:
    import asyncio

    await asyncio.sleep(min(2 ** attempt, 8) + 0.25)


def extract_reasoning(message: dict) -> str:
    """Pull reasoning_content out of a non-streaming choice message."""
    return message.get("reasoning_content") or message.get("reasoning") or ""
