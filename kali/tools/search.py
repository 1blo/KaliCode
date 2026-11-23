"""Glob and Grep - fast file search, matching Claude Code's semantics."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .base import Tool, ToolResult, ToolContext, STR, INT, BOOL, _s


def _rg() -> str | None:
    """Prefer a real ripgrep binary (Claude Code bundles one)."""
    from shutil import which

    return which("rg")


class Glob(Tool):
    name = "Glob"
    # Spec section 2.2 [RECONSTRUCTED] - Glob was a deferred tool in the
    # captured environments, so the wording follows the official docs.
    description = """Finds files based on pattern matching.

- Supports glob patterns like "**/*.js" or "src/**/*.ts"
- Returns matching file paths sorted by modification time, capped at 100 files with a truncation flag
- Does not respect .gitignore by default
- Use for open-ended file-name searches; for exact known paths, just Read them. NOT for content searching - use Grep."""
    schema = _s(
        {
            "pattern": {**STR, "description": "The glob pattern to match files against"},
            "path": {**STR, "description": "Directory to search in (defaults to cwd)"},
        },
        required=["pattern"],
    )

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        base = Path(args.get("path") or ctx.cwd or os.getcwd()).expanduser()
        pattern = args.get("pattern", "")
        try:
            matches = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0)
        except (OSError, ValueError) as e:
            return ToolResult(f"Glob error: {e}", error=True)
        files = [str(m) for m in matches if m.is_file()][:200]
        if not files:
            return ToolResult("No files found")
        head = "\n".join(files[:100])
        if len(files) > 100:
            head += f"\n(Results are truncated: {len(files)} total. Consider a more specific pattern.)"
        return ToolResult(head)


MODES = ["content", "files_with_matches", "count_matches"]


class Grep(Tool):
    name = "Grep"
    # Spec section 2.2 [RECONSTRUCTED] - Grep was a deferred tool in the
    # captured environments, so the wording follows the official docs
    # (ripgrep-based; respects .gitignore; 2.x renamed include -> glob).
    description = """A powerful content search tool built on ripgrep (ripgrep regex syntax, not POSIX grep).

Usage:
- ALWAYS use Grep for search tasks. NEVER use Bash grep/rg.
- Searches file contents using regular expressions, e.g. "log.*Error", "function\\s+\\w+"
- Filter files by pattern with the include parameter (e.g. "*.js", "*.{ts,tsx}")
- Respects .gitignore - to search a gitignored file, pass its path directly
- Returns file paths with at least one match sorted by modification time (files_with_matches, the default), or matching lines with line numbers (content), or per-file match counts (count_matches)
- If you need to identify/count the number of matches within files, use this tool's count_matches mode
- Multi-line matching: use multiline: true with \n in patterns"""
    schema = _s(
        {
            "pattern": {**STR, "description": "The regular expression pattern to search for (ripgrep syntax)"},
            "path": {**STR, "description": "File or directory to search (defaults to cwd)"},
            "include": {**STR, "description": "Glob filter for files, e.g. \"*.ts\" or \"*.{ts,tsx}\""},
            "caseSensitive": {**BOOL, "description": "Case-insensitive matching when false (default true)"},
            "literal": {**BOOL, "description": "Treat pattern as exact text, not regex (default false)"},
            "output_mode": {"type": "string", "enum": MODES, "description": "files_with_matches (default) | content | count_matches"},
            "-A": {**INT, "description": "Lines after match (content mode)"},
            "-B": {**INT, "description": "Lines before match (content mode)"},
            "-C": {**INT, "description": "Lines of context around match (content mode)"},
            "multiline": {**BOOL, "description": "Allow patterns spanning lines (default false)"},
            "limit": {**INT, "description": "Max matches to return (default 100)"},
        },
        required=["pattern"],
    )
    read_only = True

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = Path(args.get("path") or ctx.cwd or os.getcwd()).expanduser()
        pattern = args.get("pattern", "")
        mode = args.get("output_mode", "files_with_matches")
        limit = int(args.get("limit") or 100)

        if (rg := _rg()):
            return self._run_rg(rg, pattern, path, args, mode, limit)
        return self._run_python(pattern, path, args, mode, limit)

    # ------------------------------------------------------------------ rg
    def _run_rg(self, rg: str, pattern: str, path: Path, args: dict, mode: str, limit: int) -> ToolResult:
        cmd = [rg, "--no-require-git", "--hidden", "--glob", "!.git"]
        if args.get("include"):
            cmd += ["--glob", args["include"]]
        if not args.get("caseSensitive", True):
            cmd.append("-i")
        if args.get("literal"):
            cmd.append("-F")
        if args.get("multiline"):
            cmd += ["-U", "--multiline-dotall"]
        if mode == "files_with_matches":
            cmd.append("-l")
        elif mode == "count_matches":
            cmd.append("-c")
        else:
            cmd.append("-n")
            for flag in ("-A", "-B", "-C"):
                if args.get(flag):
                    cmd += [flag, str(args[flag])]
        cmd += ["-m", str(limit), "--", pattern, str(path)]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=60)
        except (subprocess.TimeoutExpired, OSError) as e:
            return ToolResult(f"rg failed ({e}); falling back to python search",
                              ) if False else self._run_python(pattern, path, args, mode, limit)
        out = proc.stdout.decode("utf-8", "replace")
        if proc.returncode not in (0, 1):
            err = proc.stderr.decode("utf-8", "replace")
            return ToolResult(f"rg error: {err or proc.returncode}", error=True)
        if not out.strip():
            return ToolResult("No matches found")
        if len(out) > 30000:
            out = out[:30000] + "\n... [truncated]"
        return ToolResult(out)

    # -------------------------------------------------------------- python
    def _run_python(self, pattern: str, path: Path, args: dict, mode: str, limit: int) -> ToolResult:
        flags = 0 if args.get("caseSensitive", True) else re.IGNORECASE
        if args.get("literal"):
            regex = re.compile(re.escape(pattern), flags)
        else:
            try:
                regex = re.compile(pattern, flags | (re.DOTALL if args.get("multiline") else 0))
            except re.error as e:
                return ToolResult(f"Invalid regex: {e}", error=True)

        if path.is_file():
            files = [path]
        else:
            files = list(self._iter(path, args.get("include")))[:4000]

        results: list[str] = []
        count_out: list[str] = []
        for f in files:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lines = text.splitlines()
            n = 0
            for i, line in enumerate(lines, start=1):
                rx = regex.search(line) if not args.get("multiline") else regex.search(text)
                if not rx:
                    continue
                n += 1
                if mode == "content":
                    ctx_lines = []
                    for flag in ("-C", "-B", "-A"):
                        pass
                    before = int(args.get("-B") or args.get("-C") or 0)
                    after = int(args.get("-A") or args.get("-C") or 0)
                    lo, hi = max(1, i - before), min(len(lines), i + after)
                    for j in range(lo, hi + 1):
                        ctx_lines.append(f"{j:5}:{lines[j - 1][:500]}")
                    results.append("\n".join(ctx_lines))
                elif mode == "files_with_matches":
                    results.append(str(f))
                    break
                else:
                    results.append(f"{f}:{n}")
                if n >= limit and mode == "count_matches":
                    break
            if mode == "count_matches" and n:
                count_out.append(f"{f}:{n}")
            if len(results) >= limit:
                break

        if mode == "count_matches":
            body = "\n".join(count_out)
        else:
            body = "\n".join(results)
        return ToolResult(body[:30000] or "No matches found")

    @staticmethod
    def _iter(base: Path, include: str | None):
        import fnmatch

        pats = [include] if include else None
        skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for fn in files:
                if pats is None or any(fnmatch.fnmatch(fn, p) or fnmatch.fnmatch(str(Path(root) / fn), p) for p in pats):
                    yield Path(root) / fn
