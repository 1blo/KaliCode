"""ToolSearch - loads deferred tools (MCP) on demand, Claude Code 2.1.x model.

MCP tools are NOT registered eagerly: agent.connect_mcp()/_register_mcp_tools()
put them in agent.deferred_tools (name -> Tool). ToolSearch matches a query
against that list, returns each match's full schema in a <functions> block, and
promotes the matched Tool objects into agent.tools so subsequent calls work.
"""
from __future__ import annotations

import json

from .base import Tool, ToolResult, ToolContext, STR, _s


class ToolSearch(Tool):
    name = "ToolSearch"
    # Verbatim from the Sonnet 4.6 CLI leak (spec section 2.1).
    description = """Fetches full schema definitions for deferred tools so they can be called.

Deferred tools appear by name in `<system-reminder>` messages. Until fetched, only the name is known - there is no parameter schema, so the tool cannot be invoked. This tool takes a query, matches it against the deferred tool list, and returns the matched tools' complete JSONSchema definitions inside a `<functions>` block. Once a tool's schema appears in that result, it is callable exactly like any tool defined at the top of the prompt.

Result format: each matched tool appears as one `<function>{"description": "...", "name": "...", "parameters": {...}}</function>` line inside the `<functions>` block - the same encoding as the tool list at the top of this prompt.

Query forms:
- "select:Read,Edit,Grep" - fetch these exact tools by name
- "notebook jupyter" - keyword search, up to max_results best matches
- "+slack send" - require "slack" in the name, rank by remaining terms"""
    schema = _s(
        {
            "query": {**STR, "description": "Query to find deferred tools. Use \"select:<tool_name>\" for direct selection, or keywords to search."},
            "max_results": {"type": "number", "description": "Maximum number of results to return (default: 5)", "default": 5},
        },
        required=["query", "max_results"],
    )
    read_only = True

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        agent = ctx.agent
        deferred: dict = getattr(agent, "deferred_tools", {}) or {}
        # Eagerly-registered MCP tools (e.g. Roblox_Studio) are already
        # callable, but a model may still search for them. Include them so the
        # search returns their schema instead of a bare "(no matches)".
        eager_mcp: dict = {
            n: t for n, t in (getattr(agent, "tools", {}) or {}).items()
            if n.startswith("mcp__")
        }
        query = str(args.get("query") or "")
        select = args.get("select")
        try:
            max_results = int(float(args.get("max_results") or 5))
        except (TypeError, ValueError):
            max_results = 5
        max_results = max(1, min(max_results, 50))

        matched: list[Tool] = []

        def _add(t: Tool) -> None:
            if t is not None and all(existing.name != t.name for existing in matched):
                matched.append(t)

        if isinstance(select, list) and select:
            for name in select:
                _add(deferred.get(str(name)))
                _add(eager_mcp.get(str(name)))
        elif query.lower().startswith("select:"):
            for name in query[len("select:"):].split(","):
                name = name.strip()
                _add(deferred.get(name))
                _add(eager_mcp.get(name))
        else:
            require = ""
            terms = query.lower().split()
            if query.startswith("+"):
                parts = query[1:].split()
                if parts:
                    require = parts[0].lower()
                    terms = parts[1:]
            whole = query.lstrip("+").strip().lower()
            scored: list[tuple[int, str, Tool]] = []
            for source in (deferred, eager_mcp):
                for name, t in source.items():
                    name_l = name.lower()
                    desc_l = (t.description or "").lower()
                    if require and require not in name_l:
                        continue
                    score = 0
                    for term in terms:
                        if term and term in name_l:
                            score += 3
                        if term and term in desc_l:
                            score += 1
                    if not terms and whole and (whole in name_l or whole in desc_l):
                        score = 2
                    if score > 0:
                        scored.append((score, name, t))
            scored.sort(key=lambda s: (-s[0], s[1]))
            matched = [t for _, _, t in scored[:max_results]]

        if not matched:
            available = sorted(eager_mcp)
            hint = ""
            if available:
                hint = ("\nCurrently available MCP tools: "
                        + ", ".join(available[:40])
                        + (f" (+{len(available) - 40} more)" if len(available) > 40 else "")
                        + "\nCall one directly - it is already available.")
            return ToolResult("(no matches)" + hint)

        lines = ["<functions>"]
        loaded: list[str] = []
        for t in matched:
            # promote into the live registry so subsequent calls resolve
            agent.tools[t.name] = t
            loaded.append(t.name)
            lines.append("<function>" + json.dumps(
                {"name": t.name, "description": t.description, "input_schema": t.schema},
                ensure_ascii=False,
            ) + "</function>")
        lines.append("</functions>")
        lines.append(f"Loaded {len(loaded)} tool(s): {', '.join(loaded)}. They are now callable.")
        return ToolResult("\n".join(lines))
