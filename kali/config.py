"""Configuration: paths, settings.json, model catalog, API key resolution.

Mirrors Claude Code's layered settings:
  ~/.kali/settings.json          (user)
  <project>/.kali/settings.json  (project, shared)
  <project>/.kali/settings.local.json (project, personal)
  enterprise managed: KALI_CODE_SETTINGS path (lowest friction here: user only)
Merged in Claude Code's order: user < project < local (later wins).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# NOTE: never embed a real API key here. It is resolved at runtime from
#   1. $NVIDIA_API_KEY / $NIM_API_KEY (environment)
#   2. env.NVIDIA_API_KEY in ~/.kali/settings.json  (set via `kali /login`)
NVIDIA_BASE_URL = os.environ.get("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
CHAT_COMPLETIONS_URL = f"{NVIDIA_BASE_URL}/chat/completions"
MODELS_URL = f"{NVIDIA_BASE_URL}/models"

USER_DIR = Path.home() / ".kali"
CLAUDE_DIR = Path.home() / ".claude"  # read-only compatibility import


def project_dir() -> Path:
    return Path.cwd()


def project_kali_dir() -> Path:
    return project_dir() / ".kali"


def find_project_root(start: Path | None = None) -> Path:
    """Walk up to the closest ancestor containing .git or KALI.md, else cwd."""
    p = (start or Path.cwd()).resolve()
    for candidate in [p, *p.parents]:
        if (candidate / ".git").exists() or (candidate / "KALI.md").exists():
            return candidate
    return p


# --------------------------------------------------------------------------- #
# Model catalog - mirrors the user's Claude Code modelPicker
# --------------------------------------------------------------------------- #
MODELS: dict[str, dict] = {
    "stepfun-ai/step-5-preview": {
        "label": "Step 5 Preview",
        "description": "StepFun Step 5 (default)",
        "context": 131072,
    },
    "moonshotai/kimi-k3.1-pro": {
        "label": "Kimi K3.1 Pro",
        "description": "Moonshot Kimi K3.1 Pro (1M context)",
        "context": 1048576,
    },
    "minimaxai/minimax-m3.1-flash": {
        "label": "MiniMax M3.1 Flash",
        "description": "MiniMax M3.1 Flash (fast / subagents)",
        "context": 131072,
    },
}
DEFAULT_MODEL = os.environ.get("KALI_DEFAULT_MODEL", "stepfun-ai/step-5-preview")
SUBAGENT_MODEL = os.environ.get("KALI_SUBAGENT_MODEL", "minimaxai/minimax-m3.1-flash")


def resolve_api_key() -> str:
    """Resolve the API key.

    Order: environment -> ~/.kali/settings.json env block -> empty.
    No key is ever embedded in the source; an empty result makes the CLI
    print setup instructions instead of making a doomed request.
    """
    key = os.environ.get("NVIDIA_API_KEY") or os.environ.get("NIM_API_KEY")
    if key:
        return key.strip()
    settings = load_settings()
    key = (settings.get("env") or {}).get("NVIDIA_API_KEY")
    if key:
        return str(key).strip()
    return ""


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
def _read_json(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"warning: could not parse {path}: {e}", file=sys.stderr)
        return {}


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def settings_paths() -> list[Path]:
    root = find_project_root()
    return [
        USER_DIR / "settings.json",
        root / ".kali" / "settings.json",
        root / ".kali" / "settings.local.json",
    ]


def load_settings() -> dict:
    merged: dict = {}
    for path in settings_paths():
        if path.exists():
            merged = _deep_merge(merged, _read_json(path))
    return merged


# Servers listed here are connected EAGERLY (their tools are listed to the model
# in full, not deferred behind ToolSearch). Everything else stays opt-in.
EAGER_MCP_SERVERS = ["Roblox_Studio"]


def save_settings(value: dict, scope: str = "local") -> Path:
    if scope == "user":
        path = USER_DIR / "settings.json"
    elif scope == "project":
        path = project_kali_dir() / "settings.json"
    else:
        path = project_kali_dir() / "settings.local.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2)
    return path


def apply_env(settings: dict) -> None:
    """Apply the settings `env` block (like Claude Code) without clobbering."""
    for k, v in (settings.get("env") or {}).items():
        os.environ.setdefault(str(k), str(v))


# --------------------------------------------------------------------------- #
# Memory files (KALI.md / CLAUDE.md compatibility)
# --------------------------------------------------------------------------- #
def memory_files() -> list[Path]:
    """Ordered: enterprise (user) -> project root -> cwd (like CLAUDE.md chain)."""
    out = []
    for p in (USER_DIR / "KALI.md",):
        if p.exists():
            out.append(p)
    root = find_project_root()
    for name in ("KALI.md", "CLAUDE.md"):
        p = root / name
        if p.exists():
            out.append(p)
            break
    cwd = Path.cwd().resolve()
    if cwd != root:
        for name in ("KALI.md", "CLAUDE.md"):
            p = cwd / name
            if p.exists():
                out.append(p)
                break
    return out


@dataclass
class AgentConfig:
    """Runtime knobs resolved once per launch."""

    model: str = DEFAULT_MODEL
    max_tokens: int = 16384
    reasoning_effort: str | None = "low"
    permission_mode: str = "default"  # default|acceptEdits|plan|bypassPermissions
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    system_prompt: str | None = None
    append_system_prompt: str | None = None
    max_turns: int = 0  # 0 = unlimited
    verbose: bool = False
    additional_dirs: list[str] = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    mcp_config_files: list[str] = field(default_factory=list)
    strict_mcp: bool = False
    agents_files: list[str] = field(default_factory=list)

    @classmethod
    def from_settings(cls, settings: dict) -> "AgentConfig":
        env = settings.get("env") or {}
        return cls(
            model=settings.get("model", DEFAULT_MODEL),
            max_tokens=int(env.get("KALI_MAX_TOKENS", settings.get("maxTokens", 16384))),
            reasoning_effort=env.get("KALI_REASONING_EFFORT", "low"),
            permission_mode=settings.get("permissionMode", "default"),
        )
