"""Tool framework. Every tool mirrors a Claude Code tool (name, schema, semantics)."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..agent import Agent


@dataclass
class ToolContext:
    agent: "Agent"
    cwd: str = ""
    # per-call extras (e.g. subagent restriction)
    allowed_tools: list[str] | None = None
    disallowed_tools: list[str] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class ToolResult:
    def __init__(self, output: str, error: bool = False, system: str | None = None,
                 images: list[dict] | None = None, interrupt: bool = False):
        self.output = output
        self.error = error
        self.system = system      # injected <system-reminder>, like Claude Code
        self.images = images      # list of {"media_type":..., "data":...} for Read tool
        self.interrupt = interrupt

    def render(self, max_chars: int = 30000) -> str:
        text = self.output or ("(no output)" if not self.error else "(error)")
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n... [output truncated, {len(text) - max_chars} chars omitted]"
        return text


class Tool(abc.ABC):
    name: str = ""
    description: str = ""
    schema: dict = {}
    read_only: bool = False          # safe, never needs permission
    is_edit: bool = False            # Edit/Write/NotebookEdit family (acceptEdits mode)
    needs_confirmation_message: str = ""  # custom confirm text

    @abc.abstractmethod
    async def run(self, args: dict, ctx: ToolContext) -> ToolResult: ...

    # ------------------------------------------------------------------ util
    def validate(self, args: dict) -> str | None:
        """Light required-field validation; returns error string or None."""
        required = self.schema.get("required") or []
        missing = [k for k in required if k not in args]
        if missing:
            return f"{self.name}: missing required parameter(s): {', '.join(missing)}"
        props = self.schema.get("properties", {})
        for k, v in args.items():
            if k not in props and self.schema.get("additionalProperties", True) is False:
                return f"{self.name}: unexpected parameter '{k}'"
        return None


def _s(properties: dict, required: list[str] | None = None, **kw) -> dict:
    schema = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    schema.update(kw)
    return schema


STR = {"type": "string"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}
ARR = {"type": "array"}


def arr_of_str(description: str = "", enum: list[str] | None = None) -> dict:
    d: dict = {"type": "array", "items": {"type": "string"} if not enum else {"type": "string", "enum": enum}}
    if description:
        d["description"] = description
    return d
