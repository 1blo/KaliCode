# Kali Code

An accurate copy of the Claude Code agentic coding CLI, reimplemented from scratch in Python. Same tools, same skills, same commands, same behaviour.

> **Kali Code** — an accurate Python copy of the Claude Code agentic coding CLI, with tool/skill parity, MCP support, streaming output, and Discord Rich Presence.

---

## Features

| | |
|---|---|
| **Streaming** | True token-by-token streaming (no buffering, no swallowed output) |
| **Models** | Step 5 Preview, Kimi K3.1 Pro, MiniMax M3.1 Flash |
| **Tools** | 20+ Claude Code–compatible built-ins with verbatim upstream descriptions & schemas |
| **MCP** | Full Model Context Protocol client — stdio + HTTP/WS transports, lazy/eager servers, live tool-list refresh |
| **Skills** | `SKILL.md` discovery and invocation, same frontmatter format as Claude Code |
| **Permissions** | Rule-based allow/ask/deny, plan mode, `bypassPermissions`, `/alwaysallow` |
| **Web search** | Multi-backend search engine with relevance checking and domain filtering |
| **Discord** | Optional Rich Presence — logo, "Using Kali Code", AI-generated chat title, elapsed timer |

---

## Install

```bash
git clone https://github.com/YOUR_USER/KaliCode.git
cd KaliCode

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
```

### Configure your API key

Kali Code ships with the API key already wired up. To use your own key, run Kali
once and use the slash command:

```
/login          # paste your key -> stored in ~/.kali/settings.json
```

or set it in the environment:

```bash
export NVIDIA_API_KEY=nvapi-...          # Linux/macOS
setx NVIDIA_API_KEY nvapi-...            # Windows (new shell required)
```

> The key is **never** stored in this repository. `.kali/settings.local.json` and
> `.kali/settings.json` are git-ignored for exactly this reason.

---

## Usage

```bash
kali                            # interactive REPL
kali "fix the failing test"     # interactive with an initial prompt
kali -p "what does this repo do"          # headless one-shot
kali -p "run tests" --output-format json  # machine-readable output
kali --model moonshotai/kimi-k3.1-pro     # pick a model
kali --permission-mode plan               # plan mode (read-only until approved)
kali --dangerously-skip-permissions       # no permission prompts
```

### Models

| Picker label | Model id | Context |
|---|---|---|
| Step 5 Preview (default) | `stepfun-ai/step-5-preview` | 131k |
| Kimi K3.1 Pro | `moonshotai/kimi-k3.1-pro` | 1M |
| MiniMax M3.1 Flash | `minimaxai/minimax-m3.1-flash` | 131k |

---

## Built-in tools

`Bash` (incl. background execution) · `Read` (text/images/PDF/notebook) · `Edit` · `Write` · `NotebookEdit` · `Glob` · `Grep` · `WebFetch` · `WebSearch` · `TaskCreate` · `TaskGet` · `TaskList` · `TaskUpdate` · `TaskStop` · `Agent` (subagents) · `Skill` · `ToolSearch` · `EnterPlanMode` · `ExitPlanMode` · `AskUserQuestion` · `TodoWrite`

Every tool from your **MCP servers** is exposed as `mcp__server__tool`.

---

## Slash commands

```
/help /model /clear /compact /cost /status /title /tasks /todo /memory /init
/mcp /skills /agents /permissions /alwaysallow /hooks /review /add-dir /export
/config /doctor /release-notes /bug /login /logout /exit
```

`/alwaysallow` auto-approves every command (persisted), or a scoped pattern:

```
/alwaysallow            # blanket bypass - every command auto-approved
/alwaysallow git status # only matching commands skip the prompt
```

---

## MCP servers

Add servers to `~/.kali/settings.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "Roblox_Studio": {
      "command": "cmd.exe",
      "args": ["/c", "C:\\Users\\YOU\\AppData\\Local\\Roblox\\mcp.bat"],
      "timeout": 120000
    },
    "my_server": {
      "command": "npx",
      "args": ["-y", "@scope/my-mcp-server"]
    }
  }
}
```

- Servers listed in `EAGER_MCP_SERVERS` (default: `Roblox_Studio`) expose their
  tools to the model in full.
- All other servers are **deferred** behind `ToolSearch` — the model discovers
  and loads their tools on demand, keeping the context window small.
- `--mcp-config <file>` adds servers on top of your settings.
- `--strict-mcp-config` ignores your settings and uses only the given file.

See [`research/claude-code-spec.md`](research/claude-code-spec.md) for the
authoritative **interface** reference this project was built against — tool
names, input schemas, CLI flags, settings keys, hook events, slash commands
and MCP configuration.

---

## Settings

Layered, Claude Code–compatible:

```
~/.kali/settings.json            (user)
<project>/.kali/settings.json    (project, shared)
<project>/.kali/settings.local.json  (project, personal - git-ignored)
```

```json
{
  "model": "stepfun-ai/step-5-preview",
  "permissionMode": "default",
  "env": { "NVIDIA_API_KEY": "nvapi-..." },
  "permissions": {
    "allow": ["Bash(git status *)", "Read", "WebSearch"],
    "deny": ["Bash(rm *)"]
  },
  "mcpServers": { "...": {} },
  "hooks": {
    "PreToolUse": [{ "matcher": "Bash", "hooks": [{ "type": "command", "command": "echo %*" }] }]
  }
}
```

Skills live in `~/.kali/skills/<name>/SKILL.md` or `.kali/skills/`.
Custom subagents live in `.kali/agents/<name>.md`.

---

## Discord Rich Presence (optional)

Create a Discord application, then add the application id to your settings:

```json
{
  "discord": {
    "enabled": true,
    "clientId": "YOUR_DISCORD_APPLICATION_ID",
    "appName": "Kali Code",
    "stateText": "Using Kali Code",
    "largeImage": "kali",
    "largeText": "Kali Code"
  }
}
```

Kali shows your logo, the AI-generated chat title, and an elapsed timer.
The IPC client is implemented natively over the local named pipe — no
third-party runtime dependency.

---

## Architecture

```
kali/
├── cli.py             # argument parsing, REPL, print mode, presence hooks
├── agent.py           # the agent loop: tool dispatch, permissions, titles
├── llm.py             # streaming chat-completions client (OpenAI wire format)
├── config.py          # layered settings, model catalog, key resolution
├── permissions.py     # rule engine: allow / ask / deny, modes
├── mcp.py             # MCP client: stdio + HTTP/WS transports
├── skills.py          # SKILL.md discovery + invocation
├── hooks.py           # PreToolUse / PostToolUse / UserPromptSubmit hooks
├── systemprompt.py    # system prompt construction
├── ui.py              # rich console, streaming renderer, spinners
├── slash.py           # slash command router
├── discord_presence.py# Discord IPC Rich Presence client
└── tools/             # the built-in tool implementations
```

### Design notes

- **Native wire format.** Requests are sent straight to the chat-completions
  endpoint with `stream: true`, `max_tokens: 16384`, and
  `reasoning_effort: "low"`. No proxy, no translation layer.
- **Streaming correctness.** The spinner is a *transient* `rich.Live` that is
  stopped before the first text token, so streamed output is never swallowed
  or overwritten.
- **Large MCP payloads.** Subprocess reads use a 16 MiB stream limit with
  `LimitOverrunError` recovery — some MCP servers emit single JSON lines
  larger than asyncio's default 64 KiB buffer.
- **Tool descriptions are verbatim.** Every built-in tool's description and
  JSON schema was transcribed from Claude Code 2.1.x so prompting behaviour
  matches upstream.

---

## Tests

```bash
python tests/smoke_agent.py             # agent internals
python tests/smoke_llm.py               # streaming / tool-calling
python tests/smoke_cli.py               # end-to-end CLI
python tests/smoke_mcp.py Roblox_Studio # MCP client
python tests/smoke_websearch.py         # search backends
python tests/smoke_alwaysallow_websearch.py
```

Live tests require a valid `NVIDIA_API_KEY`.

---

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

Tool names, descriptions and schemas follow
[Claude Code](https://github.com/anthropics/claude-code) by Anthropic.
This is an independent reimplementation; it is not affiliated with or
endorsed by Anthropic.
