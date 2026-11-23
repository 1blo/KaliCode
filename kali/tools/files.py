"""Read, Write, Edit, NotebookEdit - Claude Code's file-mutation tools."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .base import Tool, ToolResult, ToolContext, STR, INT, BOOL, ARR, _s

DEFAULT_READ_LIMIT = 2000


class Read(Tool):
    name = "Read"
    # Verbatim from the Sonnet 4.6 CLI leak (spec section 2.1).
    description = """Reads a file from the local filesystem. You can access any file directly by using this tool.
Assume this tool is able to read all files on the machine. If the User provides a path to a file assume that path is valid. It is okay to read a file that does not exist; an error will be returned.

Usage:
- The file_path parameter must be an absolute path, not a relative path
- By default, it reads up to 2000 lines starting from the beginning of the file
- When you already know which part of the file you need, only read that part. This can be important for larger files.
- Results are returned using cat -n format, with line numbers starting at 1
- This tool allows Claude Code to read images (eg PNG, JPG, etc). When reading an image file the contents are presented visually as Claude Code is a multimodal LLM.
- This tool can read PDF files (.pdf). For large PDFs (more than 10 pages), you MUST provide the pages parameter to read specific page ranges (e.g., pages: "1-5"). Reading a large PDF without the pages parameter will fail. Maximum 20 pages per request.
- This tool can read Jupyter notebooks (.ipynb files) and returns all cells with their outputs, combining code, text, and visualizations.
- This tool can only read files, not directories. To list files in a directory, use the registered shell tool.
- You will regularly be asked to read screenshots. If the user provides a path to a screenshot, ALWAYS use this tool to view the file at the path. This tool will work with all temporary file paths.
- If you read a file that exists but has empty contents you will receive a system reminder warning in place of file contents.
- Do NOT re-read a file you just edited to verify - Edit/Write would have errored if the change failed, and the harness tracks file state for you."""
    schema = _s(
        {
            "file_path": {**STR, "description": "The absolute path to the file to read"},
            "offset": {"type": "integer", "minimum": 0, "maximum": 9007199254740991, "description": "The line number to start reading from. Only provide if the file is too large to read at once"},
            "limit": {"type": "integer", "exclusiveMinimum": 0, "maximum": 9007199254740991, "description": "The number of lines to read. Only provide if the file is too large to read at once."},
            "pages": {**STR, "description": "Page range for PDF files (e.g., \"1-5\", \"3\", \"10-20\"). Only applicable to PDF files. Maximum 20 pages per request."},
            "allow_large": {**BOOL, "description": "Set to true to read a text file, or a line range of one, that is over the usual size limits, up to what still fits in your context. Only use this when you genuinely need all of it or the user asked for the whole file; otherwise read it in parts with offset and limit, or search it."},
        },
        required=["file_path"],
    )

    IMAGE_TYPES = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
    }

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = Path(args.get("file_path", "")).expanduser()
        if not path.is_absolute():
            path = Path(ctx.cwd or os.getcwd()) / path
        if not path.exists():
            return ToolResult(f"File does not exist: {path}", error=True)
        if path.is_dir():
            return ToolResult(f"Error: '{path}' is a directory, not a file", error=True)

        suffix = path.suffix.lower()
        if suffix in self.IMAGE_TYPES:
            return self._read_image(path, suffix)
        if suffix == ".pdf":
            return await self._read_pdf(path)
        if suffix == ".ipynb":
            return self._read_notebook(path)
        return self._read_text(path, args)

    def _read_image(self, path: Path, suffix: str) -> ToolResult:
        import base64

        data = path.read_bytes()
        return ToolResult(
            f"[Image: {path.name} - {len(data):,} bytes]",
            images=[{"media_type": self.IMAGE_TYPES[suffix], "data": base64.b64encode(data).decode()}],
        )

    async def _read_pdf(self, path: Path) -> ToolResult:
        try:
            from pypdf import PdfReader
        except ImportError:
            return ToolResult("PDF reading requires pypdf: pip install pypdf", error=True)
        reader = PdfReader(str(path))
        pages = []
        for i, page in enumerate(reader.pages[:50]):
            pages.append(f"## Page {i + 1}\n{page.extract_text() or '(no extractable text)'}")
        return ToolResult("\n\n".join(pages))

    def _read_notebook(self, path: Path) -> ToolResult:
        try:
            nb = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return ToolResult(f"Invalid notebook: {e}", error=True)
        lines = []
        for i, cell in enumerate(nb.get("cells", [])):
            ct = cell.get("cell_type", "?")
            src = "".join(cell.get("source", []))
            lines.append(f"### Cell {i} ({ct})")
            lines.append(src)
            for out in cell.get("outputs", [])[:5]:
                text = out.get("text") or "".join(
                    (o.get("text") or "") for o in out.get("data", {}).values() if isinstance(o.get("text"), list)
                )
                if text:
                    lines.append(f"Output: {text[:2000]}")
        return ToolResult("\n".join(lines))

    def _read_text(self, path: Path, args: dict) -> ToolResult:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except PermissionError:
            return ToolResult(f"Permission denied reading {path}", error=True)
        offset = max(1, int(args.get("offset") or 1))
        limit = int(args.get("limit") or DEFAULT_READ_LIMIT)
        lines = text.splitlines()
        total = len(lines)
        chosen = lines[offset - 1: offset - 1 + limit]
        numbered = []
        for i, line in enumerate(chosen, start=offset):
            line = line[:2000]
            numbered.append(f"{i:>6}\t{line}")
        out = "\n".join(numbered) or "(empty file)"
        note = ""
        if offset - 1 + limit < total:
            note = f"\n\n(File has more lines. Showing lines {offset}-{offset - 1 + len(chosen)} of {total}. Use offset: {offset + limit} to continue.)"
        elif offset > 1:
            note = f"\n\n(Read from line {offset} of {total}.)"
        return ToolResult(out + note)


class Write(Tool):
    name = "Write"
    # Verbatim from the Sonnet 4.6 CLI leak (spec section 2.1).
    description = """Writes a file to the local filesystem.

Usage:
- This tool will overwrite the existing file if there is one at the provided path.
- If this is an existing file, you MUST use the Read tool first to read the file's contents. This tool will fail if you did not read the file first.
- Prefer the Edit tool for modifying existing files - it only sends the diff. Only use this tool to create new files or for complete rewrites.
- NEVER create documentation files (*.md) or README files unless explicitly requested by the User.
- Only use emojis if the user explicitly requests it. Avoid writing emojis to files unless asked."""
    schema = _s(
        {
            "file_path": {**STR, "description": "The absolute path to the file to write (must be absolute, not relative)"},
            "content": {**STR, "description": "The content to write to the file"},
        },
        required=["file_path", "content"],
    )
    is_edit = True

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = _resolve(args.get("file_path", ""), ctx)
        content = args.get("content", "")
        existed = path.exists()
        if existed and str(path) not in ctx.agent.read_files:
            return ToolResult(
                f"Error: File has not been read yet. Read it first before overwriting: {path}",
                error=True,
            )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as e:
            return ToolResult(f"Error writing {path}: {e}", error=True)
        lines = content.count("\n") + 1
        ctx.agent.record_edit(path, "write")
        verb = "Updated" if existed else "Created"
        return ToolResult(f"{verb} file {path} ({lines} lines, {len(content):,} bytes)")


class Edit(Tool):
    name = "Edit"
    # Verbatim from the Sonnet 4.6 CLI leak (spec section 2.1).
    description = """Performs exact string replacements in files.

Usage:
- You must use your `Read` tool at least once in the conversation before editing. This tool will error if you attempt an edit without reading the file.
- When editing text from Read tool output, ensure you preserve the exact indentation (tabs/spaces) as it appears AFTER the line number prefix. The line number prefix format is: line number + tab. Everything after that is the actual file content to match. Never include any part of the line number prefix in the old_string or new_string.
- ALWAYS prefer editing existing files in the codebase. NEVER write new files unless explicitly required.
- Only use emojis if the user explicitly requests it. Avoid adding emojis to files unless asked.
- The edit will FAIL if `old_string` is not unique in the file. Either provide a larger string with more surrounding context to make it unique or use `replace_all` to change every instance of `old_string`.
- Use `replace_all` for replacing and renaming strings across the file. This parameter is useful if you want to rename a variable for instance."""
    schema = _s(
        {
            "file_path": {**STR, "description": "The absolute path to the file to modify"},
            "old_string": {**STR, "description": "The text to replace"},
            "new_string": {**STR, "description": "The text to replace it with (must be different from old_string)"},
            "replace_all": {"type": "boolean", "default": False, "description": "Replace all occurrences of old_string (default false)"},
        },
        required=["file_path", "old_string", "new_string"],
    )
    is_edit = True

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = _resolve(args.get("file_path", ""), ctx)
        if not path.exists():
            return ToolResult(f"Error: file does not exist: {path}", error=True)
        if str(path) not in ctx.agent.read_files:
            return ToolResult(
                f"Error: File has not been read yet. Read it first before editing: {path}", error=True
            )
        old = args.get("old_string", "")
        new = args.get("new_string", "")
        if old == new:
            return ToolResult("Error: oldString and newString must be different", error=True)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return ToolResult(f"Error reading {path}: {e}", error=True)

        count = text.count(old)
        if count == 0:
            # Claude Code retries tolerating typographic variants; keep simple: try whitespace-flexible
            flexible = _flexible_replace(text, old, new, bool(args.get("replace_all")))
            if flexible is None:
                return ToolResult(
                    "Error: oldString not found in file. Check exact whitespace/indentation.", error=True
                )
            path.write_text(flexible, encoding="utf-8")
            ctx.agent.record_edit(path, "edit")
            return ToolResult(f"Edited {path} (1 replacement, whitespace-flexible match)")

        if count > 1 and not args.get("replace_all"):
            return ToolResult(
                f"Error: oldString occurs {count} times. Add more context to make it unique, or set replace_all: true.",
                error=True,
            )
        if args.get("replace_all"):
            updated = text.replace(old, new)
            n = count
        else:
            updated = text.replace(old, new, 1)
            n = 1
        path.write_text(updated, encoding="utf-8")
        ctx.agent.record_edit(path, "edit")
        return ToolResult(f"Edited {path} ({n} replacement{'s' if n != 1 else ''})")


def _flexible_replace(text: str, old: str, new: str, replace_all: bool) -> str | None:
    """Retry tolerating trailing whitespace and CRLF differences (Claude Code behavior)."""
    pattern = re.escape(old).replace(r"\ ", "[ \t]*")
    matches = list(re.finditer(pattern, text))
    if not matches:
        # try line-ending normalization
        norm_old = old.replace("\r\n", "\n")
        norm_text = text.replace("\r\n", "\n")
        if norm_old in norm_text:
            if norm_text.count(norm_old) > 1 and not replace_all:
                return None
            return norm_text.replace(norm_old, new, -1 if replace_all else 1)
        return None
    if len(matches) > 1 and not replace_all:
        return None
    return re.sub(pattern, lambda m: new, text, count=0 if replace_all else 1)


class NotebookEdit(Tool):
    name = "NotebookEdit"
    # Verbatim from the Sonnet 4.6 CLI leak (spec section 2.1).
    description = """Replaces, inserts, or deletes a single cell in a Jupyter notebook (.ipynb file).

Usage:
- You must use the Read tool on the notebook in this conversation before editing - this tool will fail otherwise.
- `notebook_path` must be an absolute path.
- `cell_id` is the `id` attribute shown in the Read tool's `<cell id="...">` output. It is required for `replace` and `delete`.
- `edit_mode` defaults to `replace`. Use `insert` to add a new cell after the cell with the given `cell_id` (or at the beginning of the notebook if `cell_id` is omitted) - `cell_type` is required when inserting. Use `delete` to remove the cell."""
    schema = _s(
        {
            "notebook_path": {**STR, "description": "The absolute path to the Jupyter notebook file to edit (must be absolute, not relative)"},
            "cell_id": {**STR, "description": "The ID of the cell to edit. When inserting a new cell, the new cell will be inserted after the cell with this ID, or at the beginning if not specified."},
            "new_source": {**STR, "description": "The new source for the cell"},
            "cell_type": {"type": "string", "enum": ["code", "markdown"], "description": "The type of the cell (code or markdown). If not specified, it defaults to the current cell type. If using edit_mode=insert, this is required."},
            "edit_mode": {"type": "string", "enum": ["replace", "insert", "delete"], "description": "The type of edit to make (replace, insert, delete). Defaults to replace."},
        },
        required=["notebook_path", "new_source"],
    )
    is_edit = True

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = _resolve(args.get("notebook_path", ""), ctx)
        if not path.exists():
            return ToolResult(f"Error: notebook not found: {path}", error=True)
        try:
            nb = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return ToolResult(f"Error parsing notebook: {e}", error=True)
        cells = nb.setdefault("cells", [])
        mode = args.get("edit_mode", "replace")

        idx = None
        cell_id = args.get("cell_id")
        if cell_id:
            idx = next((i for i, c in enumerate(cells) if c.get("id") == cell_id), None)
        elif args.get("cell_number") is not None:
            idx = int(args["cell_number"])
        if idx is None or idx >= len(cells):
            return ToolResult("Error: cell not found (bad cell_id/cell_number)", error=True)

        src = args.get("new_source", "")
        if mode == "delete":
            cells.pop(idx)
        elif mode == "insert":
            cells.insert(idx, {
                "cell_type": args.get("cell_type", "code"), "metadata": {},
                "source": _to_nb_source(src),
            })
        else:
            cells[idx]["source"] = _to_nb_source(src)
            if args.get("cell_type"):
                cells[idx]["cell_type"] = args["cell_type"]

        path.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
        return ToolResult(f"Notebook {path.name}: {mode} cell {idx} done")


def _to_nb_source(src: str) -> list[str]:
    lines = src.split("\n")
    return [l + "\n" for l in lines[:-1]] + ([lines[-1]] if lines and lines[-1] else [])


def _resolve(p: str, ctx: ToolContext) -> Path:
    path = Path(p).expanduser()
    if not path.is_absolute():
        path = Path(ctx.cwd or os.getcwd()) / path
    return path
