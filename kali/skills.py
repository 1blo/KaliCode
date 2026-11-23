"""Skills - SKILL.md loader with YAML frontmatter (Claude Code-compatible format).

Locations, in order (later overrides earlier by name):
  kali package built-ins
  ~/.kali/skills/
  <project>/.kali/skills/
Frontmatter: name, description, allowed-tools (optional), model (optional).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import USER_DIR, project_kali_dir, _read_json
from .resources import resource_dir


@dataclass
class Skill:
    name: str
    description: str
    path: Path
    allowed_tools: list[str] = field(default_factory=list)
    model: str | None = None
    body: str = ""

    def render(self, args: str | None = None) -> str:
        out = self.body.strip()
        if args:
            out += f"\n\n<user-args>\n{args}\n</user-args>"
        return out


def parse_skill_md(path: Path) -> Skill | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if not m:
        # body-only skill: use directory name
        return Skill(name=path.parent.name, description="", path=path, body=text)
    front, body = m.group(1), m.group(2)
    fm = _parse_frontmatter(front)
    name = fm.get("name") or path.parent.name
    return Skill(
        name=str(name),
        description=str(fm.get("description", "")),
        path=path,
        allowed_tools=[t.strip() for t in str(fm.get("allowed-tools", "")).split(",") if t.strip()],
        model=fm.get("model"),
        body=body,
    )


def _parse_frontmatter(front: str) -> dict:
    """Tiny YAML subset parser: key: value lines (values may be quoted)."""
    out: dict = {}
    for line in front.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip().strip("'\"")
    return out


class SkillRegistry:
    def __init__(self) -> None:
        self.skills: dict[str, Skill] = {}

    def load_all(self) -> None:
        base = resource_dir("skills")
        for folder in (
            base,
            USER_DIR / "skills",
            project_kali_dir() / "skills",
        ):
            if not folder.exists():
                continue
            for md in sorted(folder.rglob("SKILL.md")):
                skill = parse_skill_md(md)
                if skill:
                    self.skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        return self.skills.get(name)

    def prompt_block(self) -> str:
        """The <available-skills> block for the system prompt."""
        if not self.skills:
            return ""
        lines = []
        for name in sorted(self.skills):
            s = self.skills[name]
            lines.append(f"  <skill>\n    <name>{name}</name>\n    <description>{s.description}</description>\n  </skill>")
        return (
            "<available-skills>\nSkills provide specialized instructions for specific tasks. "
            "Use the Skill tool to load one when a task matches.\n"
            + "\n".join(lines)
            + "\n</available-skills>"
        )
