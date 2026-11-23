# Claude Code CLI 2.1.x — Tool & Interface Reference

**Purpose:** consolidated reference for building a compatible agentic coding CLI (v2.1.x era, late 2025 / 2026).
**Compiled:** 2026-11-21. From Anthropic's official documentation (code.claude.com) and observed CLI behaviour.

> **Note on provenance.** This document summarises the *public interface* of the
> upstream CLI — tool names, input schemas, flag names, settings keys, hook
> events, slash commands and MCP configuration. The upstream system prompt and
> tool-description prose are Anthropic's proprietary material and are **not**
> reproduced here; section 3 describes the prompt's structure only.

**Confidence legend**
- **[VERBATIM]** — copied character-for-character from an official doc (source named).
- **[RECONSTRUCTED]** — assembled from multiple doc statements / known behavior; wording not guaranteed exact.
- **[LEGACY]** — 1.x-era (pre-2.0) material, kept for rename mapping.

**Primary sources** — Anthropic's official documentation (all fetched 2026-11-21):
- Tools: https://code.claude.com/docs/en/tools-reference
- CLI flags: https://code.claude.com/docs/en/cli-reference
- Settings: https://code.claude.com/docs/en/settings · https://code.claude.com/docs/en/settings-reference
- Permissions: https://code.claude.com/docs/en/permissions
- Skills: https://code.claude.com/docs/en/skills
- Hooks: https://code.claude.com/docs/en/hooks
- Commands: https://code.claude.com/docs/en/commands
- Subagents: https://code.claude.com/docs/en/sub-agents
- MCP: https://code.claude.com/docs/en/mcp

---

## 1. TOOL INVENTORY

### 1.1 Current built-in tools (v2.1.x) [VERBATIM — tools-reference table, code.claude.com/docs/en/tools-reference]

The tool names below are the exact strings used in permission rules, subagent `tools` lists, and hook matchers.

| Tool | Description (verbatim, doc table) | Permission required |
| :- | :- | :- |
| `Agent` | Spawns a subagent with its own context window to handle a task. With agent teams enabled, a call that carries a `name` can launch a teammate instead. | No |
| `Artifact` | Publishes an HTML or Markdown file to claude.ai as an artifact: a private, interactive page. | Yes |
| `AskUserQuestion` | Asks multiple-choice questions to gather requirements or clarify ambiguity. | No |
| `Bash` | Executes shell commands in your environment. | Yes |
| `CronCreate` | Schedules a recurring or one-shot prompt within the current session. | No |
| `CronDelete` | Cancels a session-scoped scheduled task by ID | No |
| `CronList` | Lists all session-scoped scheduled tasks | No |
| `Edit` | Makes targeted edits to specific files. | Yes |
| `EndConversation` | Ends the session, in rare cases of sustained abusive input or when you ask Claude to end the session and then confirm. | No |
| `EnterPlanMode` | Switches to plan mode to design an approach before coding | No |
| `EnterWorktree` | Creates an isolated git worktree and switches into it, or switches into an existing worktree. | Some worktrees |
| `ExitPlanMode` | Presents a plan for approval and exits plan mode | Yes |
| `ExitWorktree` | Exits a worktree session and returns to the original directory. | No |
| `Glob` | Finds files based on pattern matching. **Absent by default on macOS, Linux, and WSL.** | No |
| `Grep` | Searches for patterns in file contents. **Absent by default on macOS, Linux, and WSL.** | No |
| `ListAgents` | Lists the agents Claude can message with `SendMessage` (subagents, teammates, other local sessions, cloud sessions). Backs `/list-agents`. v2.1.224+ | No |
| `ListMcpResourcesTool` | Lists resources exposed by connected MCP servers. | No |
| `ListPlugins` / `ListSkills` / `SearchPlugins` / `SearchSkills` / `SuggestPluginInstall` / `SuggestSkills` | claude.ai-account plugin/skill catalog tools (cloud/desktop only) | No |
| `LSP` | Code intelligence via language servers: jump to definitions, find references, report type errors. | No |
| `Monitor` | Runs a command in the background and feeds each output line back to Claude; can also open a WebSocket and treat each incoming message as an event. | Yes |
| `NotebookEdit` | Modifies Jupyter notebook cells. | Yes |
| `PowerShell` | Executes PowerShell commands natively (Windows; opt-in elsewhere). | Yes |
| `propose_skills` | Shows a card of proposed skills (some cloud sessions). | No |
| `PushNotification` | Sends a desktop notification (phone push with Remote Control). | No |
| `Read` | Reads the contents of files. | No |
| `ReadMcpResourceTool` | Reads a specific MCP resource by URI. | No |
| `ReadMcpResourceDirTool` | Lists direct children of an MCP directory resource. | No |
| `RemoteTrigger` | Creates, updates, runs, and lists cloud scheduled tasks on claude.ai. Backs `/schedule`. | No |
| `ReportFindings` | Reports code-review findings as a structured list so the UI can render them. | No |
| `ScheduleWakeup` | Reschedules the next iteration of a self-paced `/loop`. | No |
| `SendFeedback` | Drafts a feedback report about Claude Code and queues it locally for review. v2.1.238+ | No |
| `SendMessage` | Sends a message to another agent (teammate, subagent, or another session). | No |
| `SendUserFile` | Sends files from the session to the user with an optional caption (Remote Control / cloud). | No |
| `ShareOnboardingGuide` | Uploads `ONBOARDING.md` and returns a share link. | Yes |
| `Skill` | Executes a skill within the main conversation. | Some skills |
| `SubagentHandback` | Delivers a subagent's final report to the receiving conversation (auto mode only). v2.1.271+ | No |
| `TaskCreate` | Creates a new task in the task list. | No |
| `TaskGet` | Retrieves full details for a specific task. | No |
| `TaskList` | Lists all tasks with their current status. | No |
| `TaskOutput` | **Removed in v2.1.277.** Previously retrieved output from a background task; Claude reads the background task's output file with `Read` instead. | No |
| `TaskStop` | Stops a running background task by ID (also teammates / named background agents). | No |
| `TaskUpdate` | Updates task status, dependencies, details, or deletes tasks. | No |
| `TodoWrite` | Manages the session task checklist. **Disabled by default** in favor of `TaskCreate/TaskGet/TaskList/TaskUpdate`; set `CLAUDE_CODE_ENABLE_TASKS=0` to re-enable. | No |
| `ToolSearch` | Searches for and loads deferred tools when tool search is enabled. | No |
| `WaitForMcpServers` | Waits for MCP servers still connecting (only when tool search is disabled). | No |
| `WebFetch` | Retrieve and extract content from a URL. | Yes |
| `WebSearch` | Performs web searches. | Yes |
| `Workflow` | Runs a dynamic workflow: a script that orchestrates many subagents in the background. | Yes |
| `Write` | Creates or overwrites files. | Yes |

### 1.2 Renames and removals: 1.x → 2.x [VERBATIM where quoted]

| 1.x / 2.0 name | 2.1.x name | Notes |
| :- | :- | :- |
| `Task` | `Agent` | "In version 2.1.63, the Task tool was renamed to Agent. Existing `Task(...)` references in settings and agent definitions still work as aliases." (sub-agents doc) |
| `TodoWrite` + `TodoRead` | `TaskCreate`, `TaskGet`, `TaskList`, `TaskUpdate` | TodoWrite disabled by default; `CLAUDE_CODE_ENABLE_TASKS=0` restores it. Task tools "available by default only on Opus 4.7, Sonnet 4.6, Haiku 4.5, and earlier models"; `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` forces them on everywhere. |
| `exit_plan_mode` (snake_case) | `ExitPlanMode` (+ new `EnterPlanMode` pair) | Plan mode is now symmetric: `EnterPlanMode` to enter, `ExitPlanMode` to present plan. `ExitPlanMode` no longer takes the plan text as a parameter (writes plan to a plan file; deprecated `allowedPrompts` param remains in schema). |
| `LS` | (removed) | Directory listing via Bash `ls` / `Glob`. Read: "Read only reads files, not directories. Claude lists directory contents with a shell command such as `ls`." |
| `MultiEdit` | (merged into `Edit`) | Edit gained `replace_all`; MultiEdit survives only as a legacy alias in permission rules ("legacy `MultiEdit`" — permissions doc: use `Edit(docs/**)` in place of `Write(docs/**)` etc.). |
| `NotebookRead` | (merged into `Read`) | Read handles `.ipynb` directly. |
| `BashOutput` | `TaskOutput` → removed v2.1.277 | Background-command output is now a file Claude reads with `Read`; `/tasks` manages background work. |
| `KillShell` / `kill_bash` | `TaskStop` | Schema kept a deprecated `shell_id` param ("Deprecated: use task_id instead") — verbatim from leak. |
| `SlashCommand` | (folded into `Skill`) | Custom slash commands merged into skills: "Custom commands have been merged into skills. Your existing `.claude/commands/` files keep working." Commands run via the `Skill` tool. |
| `Glob` / `Grep` | unchanged, but **absent by default** on macOS/Linux/WSL | "Claude Code leaves Glob and Grep out of the default tool set, and Claude searches with `find` and `grep` through the Bash tool instead. In Claude's shell those two commands run embedded versions of `bfs` and `ugrep`." Restored by naming them in `--tools`/`--allowedTools`, by removing Bash, or by a subagent listing them with no Bash. Present by default on Windows. |
| `mcp__tools__report_findings` | `ReportFindings` | Promoted to a built-in tool (v2.1.x). |

### 1.3 Tool availability mechanics (verbatim doc facts)

- **Bare `--tools` list**: `claude --tools "Bash,Edit,Read"` restricts built-ins; `""` disables all; `"default"` is the default set. Default set on macOS/Linux/WSL leaves out `Glob` and `Grep`.
- **`--disallowedTools "Edit"`** removes Edit from Claude's context entirely (bare tool name); `"*"` removes every tool; `"mcp__*"` removes every MCP tool; scoped `Bash(rm *)` leaves the tool available but denies matching calls.
- `EndConversation` cannot be removed while any other tool remains.
- **Deferred tools / ToolSearch**: with tool search enabled (default on current models), non-core tools (e.g. MCP tools, browser tools) appear by name only and are loaded via `ToolSearch` with `select:` or keyword queries.
- **Bare mode** (`--bare`): "Claude has access to Bash, file read, and file edit tools" only.

## 2. TOOL REFERENCE (schemas + behaviour)

> The upstream tool-description prose is Anthropic's proprietary material and
> is **not** reproduced here. This section lists every tool's **input schema**
> (the functional contract you need to write a custom tool or MCP server) and
> a short behavioural summary.
>
> Kali Code's live tool definitions live in `kali/tools/` - that is the
> authoritative implementation.

### 2.1 Tool inventory

| Tool | Purpose | Key inputs |
| :- | :- | :- |
| `Agent` | Delegate complex multi-step work to a subagent | `description`, `prompt`, `subagent_type`, `model`, `isolation` |
| `AskUserQuestion` | Ask the user a multiple-choice question | `questions[]` |
| `Bash` | Run a shell command (foreground or background) | `command`, `description`, `timeout`, `run_in_background` |
| `Edit` | Exact string replacement in a file | `file_path`, `old_string`, `new_string`, `replace_all` |
| `EnterPlanMode` | Switch into plan mode (read-only until approved) | - |
| `ExitPlanMode` | Present a plan for approval | `plan` |
| `Glob` | Find files by glob pattern | `pattern`, `path` |
| `Grep` | Search file contents (ripgrep) | `pattern`, `path`, `glob`, `output_mode` |
| `NotebookEdit` | Edit a Jupyter notebook cell | `notebook_path`, `new_source`, `cell_id` |
| `Read` | Read a file (text / image / PDF / notebook) | `file_path`, `offset`, `limit` |
| `Skill` | Load a skill by name | `skill` |
| `TaskCreate` | Create a task in the session task list | `subject`, `description`, `activeForm` |
| `TaskGet` | Read one task | `taskId` |
| `TaskList` | List all tasks | - |
| `TaskStop` | Stop a running background task | `task_id`, `shell_id` |
| `TaskUpdate` | Update a task's status or fields | `taskId`, `status`, `subject`, `owner` |
| `TodoWrite` | Write the todo list | `todos[]` |
| `ToolSearch` | Discover deferred / MCP tools by keyword | `query` |
| `WebFetch` | Fetch a URL and extract content | `url`, `prompt` |
| `WebSearch` | Search the web | `query`, `allowed_domains`, `blocked_domains`, `mode` |
| `Write` | Write a file | `file_path`, `content` |

### 2.2 Behavioural notes

**`Agent`** - Spawns a subagent with its own context and tool set. A fresh
agent sees only its prompt and returns only a summary, so brief it
explicitly (goal, what has been ruled out, which files to read). Prefer
doing small work inline; delegate multi-step or parallel work. The
subagent's final report is not shown to the user - relay what matters.
Subagent types come from `.claude/agents/*.md` frontmatter.

**`AskUserQuestion`** - Presents structured multiple-choice options. Use for
choices the user should make, not for information you can look up.

**`Bash`** - Runs a command in the user's shell. Prefer dedicated tools
(Read/Edit/Write/Glob/Grep) over shell equivalents. Quote paths containing
spaces. Prefer absolute paths over `cd`. `run_in_background` returns
immediately and notifies on completion - never poll for it. Do not use
`--no-verify` or skip commit signing unless explicitly asked. Avoid
`sleep`; use background execution instead.

**`Edit`** - Exact string replacement. `old_string` must match the file
uniquely unless `replace_all` is set. Read the file first.

**`EnterPlanMode` / `ExitPlanMode`** - Plan mode blocks edits and
non-read-only commands until the user approves the plan.

**`Glob` / `Grep`** - `Glob` matches paths, `Grep` matches contents. `Grep`
prefers ripgrep when installed. `output_mode` selects `files_with_matches`,
`content`, or `count`.

**`NotebookEdit`** - Replaces a notebook cell's source. Read the notebook
first to get the cell id.

**`Read`** - Supports text, images, PDFs and notebooks. `offset`/`limit` are
line-based. Large files are truncated with a notice.

**`Skill`** - Loads a skill's instructions by name. Skills are discovered
from `~/.kali/skills/<name>/SKILL.md` or `.kali/skills/`.

**`Task*` family** - A shared session task list. `TaskCreate` adds,
`TaskGet` reads, `TaskList` enumerates, `TaskUpdate` changes status or
fields, `TaskStop` stops a background task.

**`ToolSearch`** - Discovers tools that are not listed directly (deferred
MCP servers). Returns matching tool names and schemas.

**`WebFetch`** - Fetches a URL, converts HTML to text, and returns it with
the prompt attached. HTTP URLs are upgraded to HTTPS. Results may be
summarised if very large.

**`WebSearch`** - Returns search results with links. Honours
`allowed_domains` / `blocked_domains`. `mode` is `standard` or `extended`.
The assistant should list the URLs it used as a "Sources:" section.

**`Write`** - Writes a file, creating parent directories as needed.

### 2.3 Input schemas

The JSON Schemas are published with Anthropic's official tools reference:
https://code.claude.com/docs/en/tools-reference

Kali Code's own schemas are visible at runtime with `/tools`, and live in
`kali/tools/*.py`.

---

## 3. SYSTEM PROMPT STRUCTURE (SUMMARY)

> The actual upstream prompt text is proprietary to Anthropic and is not
> reproduced here. Kali Code implements its own prompt following this
> structure - see `kali/systemprompt.py` for the live implementation.

The upstream CLI system prompt is assembled in this order:

1. Identity line ("You are <agent>, an agentic coding CLI ...")
2. Security preamble (authorized security testing only; never guess URLs)
3. `## System` - output visibility, permission modes, `<system-reminder>`
   semantics, pasted-content handling, hooks, context auto-compression
4. `## Doing tasks` - investigate before acting, prefer dedicated tools
5. `## Executing actions with care` - side effects, destructive operations,
   scope limits, security-sensitive content
6. `## Using your tools` - parallel calls, tool selection, MCP guidance
7. `## Tone and style` - concise output, no filler, markdown conventions
8. `## Text output` - formatting rules for assistant messages
9. `## Session-specific guidance` - feature-specific hints
10. `## auto memory` - persistent memory directory behaviour
11. `## Environment` - cwd, git status, platform, date, model
12. `## Context management` - compaction and context-window rules
13. `## Session context` - CLAUDE.md / KALI.md contents injected as reminders
14. `## Agents` - available subagent types
15. `## MCP Server Instructions` - configured MCP servers
16. `## Skills` - available skills
17. `# Tools` - the JSON-schema function list

### 3.1 Kali Code deviations from the upstream structure

Kali Code keeps the same section ordering and intent, with these changes:

| Upstream | Kali Code |
| :- | :- |
| Upstream identity line (names Claude Code and Anthropic) | Kali Code's own identity line (names Kali Code, no vendor reference) |
| References to the agent as "Claude" | References to the agent as "Kali Code" (references to the *user* are untouched) |
| `## Environment` placeholders | Filled with live facts (cwd, git status, date, platform, python version, model) |
| `## Session-specific guidance` for fork subagents, `!` bash prefix, `/code-review` | Omitted - this build does not implement those features |
| Attribution reminder to Anthropic | Rebranded to Kali Code |
| `## auto memory` | Replaced by Kali's `KALI.md` / `CLAUDE.md` memory chain |

### 3.2 Version drift notes (1.x -> 2.x)

Useful for understanding how the prompt evolved between major versions:

- Older 1.x prompts carried extra boilerplate preambles
  ("IMPORTANT: You should NOT answer with 'Understood...'", "IMPORTANT:
  Refuse to write code..."). These map onto the two security/identity lines
  above and are not reproduced separately.
- The 2.x prompt moved most task-management guidance out of the system
  prompt and into the `TodoWrite` tool description.
- The 2.x prompt dropped the hard "DO NOT use Bash for file operations"
  wording in favour of a softer "prefer dedicated tools" guidance.

---

## 4. CLI FLAGS

### 4.1 Commands [VERBATIM — cli-reference]

| Command | Purpose |
| :- | :- |
| `claude` / `claude "query"` | Start interactive session (optionally with initial prompt) |
| `claude -p "query"` | Query via SDK/print mode, then exit |
| `cat file \| claude -p "query"` | Process piped content |
| `claude -c` / `claude -c -p "query"` | Continue most recent conversation in current directory |
| `claude -r "<session>" "query"` | Resume session by ID or name |
| `claude update` | Update to latest version |
| `claude install [version]` | Install/reinstall native binary (`stable`, `latest`, or e.g. `2.1.118`) |
| `claude auth login` / `logout` / `status` | Account auth (`--console`, `--sso`, `--email` flags) |
| `claude agents` | Open agent view (background sessions); `--json`, `--cwd`, `--permission-mode`, `--model`, `--effort`, `--agent` |
| `claude attach <id\|name>` | Attach to a background session |
| `claude auto-mode defaults/config/reset` | Print/reset auto-mode classifier rules |
| `claude daemon logs/run/status/stop` | Background-session supervisor control |
| `claude doctor` | Read-only installation/settings diagnostics |
| `claude import [source]` | Run `/import` (codex/gemini/cursor config import); `--dry-run`, `--yes` |
| `claude logs <id>` | Print recent output from a background session |
| `claude mcp` / `claude mcp login <name>` / `logout <name>` | MCP server management and OAuth |
| `claude plugin` (alias `claude plugins`) | Plugin management subcommands |
| `claude purge [path]` | Delete all local state for a project; `--dry-run`, `-y`, `-i`, `--all` |
| `claude remote-control` (alias `claude rc`) | Remote Control server |
| `claude respawn <id>` | Restart a background session with conversation intact |
| `claude rm <id>` | Remove a background session from the list |
| `claude self-hosted-runner setup/doctor/orchestrator` | Self-hosted environment runners |
| `claude setup-token` | Long-lived OAuth token for CI |
| `claude stop <id>` (alias `claude kill`) | Stop a background session |
| `claude ultrareview [target]` | Non-interactive ultrareview; `--json`, `--timeout`, `--post`/`--no-post` |

### 4.2 Flags [VERBATIM — full list, descriptions condensed; see cli-reference for full text]

| Flag | Purpose |
| :- | :- |
| `--add-dir` | Additional working directories |
| `--advisor <model>` | Server-side advisor tool for the session (`fable`/`opus`/`sonnet`/model ID) |
| `--agent` | Session agent (overrides `agent` setting) |
| `--agents` | Define subagents via JSON (or JSON file path with `-p`, v2.1.281+) |
| `--allow-dangerously-skip-permissions` | Add bypassPermissions to Shift+Tab cycle without starting in it |
| `--allowedTools`, `--allowed-tools` | Tools that run without permission prompts |
| `--append-subagent-system-prompt` / `--append-subagent-system-prompt-file` | Append text to every subagent system prompt (`-p` only) |
| `--append-system-prompt` / `--append-system-prompt-file` | Append to default system prompt |
| `--autocompact <auto\|tokens>` | Auto-compact window for the session |
| `--ax-screen-reader` | Screen-reader friendly output |
| `--bare` | Minimal mode: skip auto-discovery of hooks/skills/commands/agents/plugins/MCP/CLAUDE.md |
| `--betas` | Beta headers for API requests |
| `--bg`, `--background` | Start as a background agent and return immediately |
| `--channels` | MCP channel plugins to listen to (research preview) |
| `--chrome` / `--no-chrome` | Enable/disable Chrome integration |
| `--cloud` | Create or message a cloud session |
| `--continue`, `-c` | Load most recent conversation |
| `--correlation-id <id>`, `--environment <id>`, `--metadata k=v`, `--ref <branch>` | Self-hosted environment dispatch |
| `--dangerously-load-development-channels` | Non-allowlisted channels |
| `--dangerously-skip-permissions` | Skip permission prompts (≡ `--permission-mode bypassPermissions`) |
| `--debug [filter]`, `--debug-file <path>` | Debug logging |
| `--desktop` | Open session in Desktop app |
| `--disable-slash-commands` | Disable all skills/commands |
| `--disallowedTools`, `--disallowed-tools` | Deny rules (bare name removes tool from context) |
| `--effort` | `low`/`medium`/`high`/`xhigh`/`max`/`ultracode` |
| `--exclude-dynamic-system-prompt-sections` | Move per-user context out of system prompt (cache reuse) |
| `--exec` | Run a shell command as background job (with `--bg`) |
| `--fallback-model` | Comma-separated fallback chain |
| `--fork-session` | New session ID when resuming |
| `--forward-subagent-text` | Emit subagent text in stream-json |
| `--from-pr` | Session picker filtered to a PR |
| `--ide` | Auto-connect IDE |
| `--init` / `--init-only` / `--maintenance` | Setup/SessionStart hooks in print mode |
| `--include-hook-events`, `--include-partial-messages` | stream-json extras |
| `--input-format` | `text` \| `stream-json` |
| `--json-schema` | Validated JSON output (print mode) |
| `--max-budget-usd` | Spend cap (print mode) |
| `--max-turns` | Agentic-turn cap (print mode) |
| `--mcp-config` | MCP servers from JSON files/strings |
| `--model` | Model alias or full ID (overrides `model` setting + `ANTHROPIC_MODEL`) |
| `--name`, `-n` | Session display name |
| `--no-session-persistence` | Don't save session |
| `--output-format` | `text` \| `json` \| `stream-json` |
| `--permission-mode` | `default`(`manual` alias), `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions` |
| `--permission-prompt-tool` | MCP tool handling prompts (non-interactive) |
| `--permission-prompts` | `host` \| `none` (print mode) |
| `--plugin-dir`, `--plugin-url` | Sideload plugins for one session |
| `--print`, `-p` | Non-interactive mode |
| `--prompt-suggestions` | Emit `prompt_suggestion` events |
| `--remote` | Deprecated alias of `--cloud` |
| `--remote-control`, `--rc` | Interactive session with Remote Control |
| `--replay-user-messages` | Echo stdin messages (stream-json) |
| `--restricted` | No command-running tools; managed settings only |
| `--resume`, `-r` | Resume by ID/name/transcript path, or picker |
| `--safe-mode` | Disable all customizations for troubleshooting |
| `--session-id` | Fixed UUID session ID |
| `--setting-sources` | `user,project,local` subset |
| `--settings` | Inline JSON or file of settings overrides |
| `--strict-mcp-config` | Only `--mcp-config` servers |
| `--system-prompt` / `--system-prompt-file` | Replace default system prompt |
| `--system-prompt-snapshot off` | Rebuild system prompt per request |
| `--teleport` | Resume a cloud session locally |
| `--teammate-mode` | `in-process` \| `auto` \| `tmux` \| `iterm2` |
| `--tmux` | tmux session for `--worktree` |
| `--tools` | Restrict built-in tools (`""` / `"default"` / list) |
| `--verbose` | Full turn-by-turn output |
| `--version`, `-v` | Version |
| `--worktree`, `-w` | Isolated git worktree at `<repo>/.claude/worktrees/<name>` |

System-prompt flag notes (verbatim): "With `--system-prompt`/`--system-prompt-file` combined with append flags, Claude receives the replacement prompt, then appended text. A line containing only `__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__` splits cached static text from per-run dynamic text" (v2.1.275+).

## 5. SETTINGS.JSON SCHEMA AND PERMISSION RULES

### 5.1 Files and precedence [VERBATIM]

| Scope | File | Who it affects |
| :- | :- | :- |
| User | `~/.claude/settings.json` | You, every project on the machine |
| Shared project | `.claude/settings.json` | Everyone in the folder (commit it) |
| Project local | `.claude/settings.local.json` | You, this project (auto-gitignored) |
| Managed | `managed-settings.json` / MDM / server-managed | Org-enforced; top precedence |

Precedence (highest first): **managed → command line (`--settings`) → project local → shared project → user**. List keys (e.g. `permissions.allow`) **merge** across files instead of overriding. Settings are strict JSON (no comments/trailing commas). Published JSON Schema for editor autocomplete: `https://json.schemastore.org/claude-code-settings.json` (referenced via the `"$schema"` key). A fifth file, `~/.claude.json`, holds global config keys `/config` writes, account details, MCP servers, per-project trust.

### 5.2 Known settings keys (from the full settings index; ★ = most clone-relevant)

- **Model**: `model`, `fallbackModel`, `availableModels`, `deniedModels`, `modelPicker`, `modelSettings`, `modelOverrides`, `effortLevel`, `maxEffortLevel`, `alwaysThinkingEnabled`, `language`, `outputStyle`, `fastMode`, `promptCacheTtl`, `subagentPromptCacheTtl`, `advisorModel`
- **Permissions**: `permissions.allow`, `permissions.ask`, `permissions.deny`, `permissions.defaultMode` (`default|acceptEdits|plan|auto|dontAsk|bypassPermissions`), `permissions.additionalDirectories`, `permissions.disableBypassPermissionsMode`, `permissions.disableAutoMode`, `permissions.blockReadsOutsideWorkingDirectories`, `permissions.blockWritesOutsideWorkingDirectories`, `permissions.denyInsteadOfPrompting`
- **Hooks & automation**: `hooks` (see §9), `allowedHttpHookUrls`, `httpHookAllowedEnvVars`, `disableAllHooks`, `enableWorkflows`, `disableWorkflows`
- **Git/attribution**: `attribution.commit`, `attribution.pr`, `attribution.sessionUrl`, `includeCoAuthoredBy` (deprecated), `includeGitInstructions`, `prUrlTemplate`
- **Memory/context**: `env` (env vars for every session + subprocesses), `autoCompactEnabled`, `autoCompactWindow`, `autoMemoryEnabled`, `autoMemoryDirectory`, `claudeMd` (managed org-wide CLAUDE.md), `claudeMdExcludes`, `plansDirectory`, `fileCheckpointingEnabled`, `bashOutputMaxChars`, `skillListingBudgetFraction`, `skillListingMaxDescChars`
- **Interface**: `statusLine` (command that renders the status line; receives JSON on stdin), `spinnerTipsEnabled`, `spinnerTipsOverride`, `spinnerVerbs`, `editorMode` (vim), `theme`-family keys, `verbose`, `autoScrollEnabled`, `viewMode`, `maxProseWidth`, `preferredNotifChannel`, `defaultShell`, `respondToBashCommands`, `respectGitignore`, `fileSuggestion`, `spellcheck`
- **Tools**: `disableBundledSkills`, `skillOverrides`, `disableSkillShellExecution`, `enableArtifact`/`disableArtifact`, `strictPluginOnlyCustomization(.agents/.hooks/.mcp/.skills)`
- **MCP**: `enableAllProjectMcpServers`, `enabledMcpjsonServers`, `disabledMcpjsonServers`, `allowedMcpServers`, `deniedMcpServers`, `allowAllClaudeAiMcps`, `managedMcpServers`, `allowManagedMcpServersOnly`, `disableClaudeAiConnectors`
- **Privacy/telemetry**: `cleanupPeriodDays`, `feedbackDrafts`, `feedbackSurveyRate`, `skipWebFetchPreflight`
- **Updates**: `autoUpdatesChannel`, `minimumVersion`, `requiredMinimumVersion`, `requiredMaximumVersion`
- **Plugins**: `enabledPlugins`, `extraKnownMarketplaces`, `pluginConfigs`, `blockedMarketplaces`, `strictKnownMarketplaces`
- **Sandbox**: `sandbox.enabled`, `sandbox.autoAllowBashIfSandboxed`, `sandbox.allowUnsandboxedCommands`, `sandbox.excludedCommands`, `sandbox.network.*`, `sandbox.filesystem.*`, `sandbox.credentials.*`
- **Agents/sessions**: `agent`, `disableAgentView`, `crossSessionInbound`, `isolatePeerMachines`, `processWrapper`, `remoteControlAtStartup`
- **Misc**: `apiKeyHelper`, `awsAuthRefresh`, `awsCredentialExport`, `gcpAuthRefresh`, `otelHeadersHelper`, `forceLoginMethod`, `forceLoginOrgUUID`, `askUserQuestionTimeout`, `autoContinueAtUsageLimit`, `showThinkingSummaries`, `alwaysThinkingEnabled`, `companyAnnouncements`, `sshConfigs`, `policyHelper.*`, `allowManagedPermissionRulesOnly`, `allowManagedHooksOnly`

Example (verbatim from docs):

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "allow": [
      "Bash(npm run lint)",
      "Bash(npm run test *)"
    ],
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)"
    ]
  }
}
```

### 5.3 Permission rule syntax [VERBATIM — permissions doc]

Format: `Tool` or `Tool(specifier)`. Evaluation order: **deny → ask → allow**; first match wins; specificity never reorders. A bare tool name (or `Bash(*)`) as a **deny** removes the tool from Claude's context entirely; a scoped rule like `Bash(rm *)` leaves the tool available but blocks matching calls.

Rule formats:

| Rule format | Applies to |
| :- | :- |
| `Bash(npm run *)` | Bash, Monitor |
| `PowerShell(Get-ChildItem *)` | PowerShell (aliases canonicalized, case-insensitive) |
| `Read(~/secrets/**)` | Read, Grep, Glob, LSP |
| `Edit(/src/**)` | Edit, Write, NotebookEdit |
| `Skill(deploy *)` | Skill |
| `Agent(Explore)` | Agent (subagent type) |
| `WebFetch(domain:example.com)` | WebFetch (also `domain:*.example.com`, bare `WebFetch`, `WebFetch(domain:*)`) |
| `WebSearch` | WebSearch (no specifier) |
| `Tool(param:value)` | Any tool's top-level scalar param: `Agent(model:opus)`, `Agent(isolation:worktree)`, `Bash(run_in_background:true)`; `*` wildcard supported; omitted params never match; primary content fields (Bash `command`, Read/Edit/Write `file_path`, Grep/Glob `path`, WebFetch `url`) are unmatchable |

**Bash wildcards** (verbatim facts): `*` matches any text including spaces; `Bash(ls *)` also matches bare `ls` (trailing `*` with leading space); `Bash(ls*)` matches `lsof` too; `:*` suffix ≡ trailing ` *`; `*` before the subcommand (e.g. `Bash(git * main)`) warns and matches broadly. Compound commands split on `&&`, `||`, `;`, `|`, `|&`, `&`, newlines — every subcommand must be allowed. Wrappers stripped before matching: `timeout`, `time`, `nice`, `nohup`, `stdbuf`, `command`, `builtin`, `noglob`, bare `xargs`, and leading assignments of known-safe env vars (`NODE_ENV=test npm test` matches `Bash(npm test *)`). Deny/ask rules match past any leading assignment. Built-in read-only set runs without prompting: `ls, cat, echo, pwd, head, tail, grep, find, wc, which, diff, stat, du, cd`, read-only `git` (plus caveats for globs with write-capable flags, `docker -H`, `file -m`, `ps auxe`, `which -i`, UNC paths, special shell vars, >10,000-char commands).

**Path patterns** (gitignore syntax, verbatim table):

| Pattern | Meaning | Example |
| :- | :- | :- |
| `//path` | Absolute from filesystem root | `Read(//Users/alice/secrets/**)` |
| `~/path` | From home directory | `Read(~/Documents/*.pdf)` |
| `/path` | Relative to the settings source (project/local → primary working directory; user → `~/.claude/path`) | `Edit(/src/**/*.ts)` |
| `path` or `./path` | Relative to current directory | `Read(*.env)` |

Additional facts: `!` negation carves out prior same-source rules (`Read(*.env)` + `Read(!sample.env)`); single-segment dir patterns match at any depth for deny/ask but only at the anchor for allow (`Edit(src/**)` allow = `<cwd>/src` only; `Edit(**/src/**)` = any depth); symlink resolution checks both requested and resolved paths (allow = both must match; deny = either); `Write(path)`/`Glob(path)`/`Grep(path)` rules **don't match** — use `Edit(...)`/`Read(...)`; an `Edit(...)` allow implies read; a `Read(...)` deny blocks Edit/Write on the path too. Windows paths normalized to POSIX (`C:\Users\alice` → `/c/Users/alice`).

**Permission modes** [VERBATIM]: `default` (Manual — prompts before most edits/commands/network), `acceptEdits` (auto-accepts edits + `mkdir/touch/mv/cp` in working dirs), `plan` (read-only exploration; no source edits), `auto` (background classifier reviews actions), `dontAsk` (auto-denies anything that would prompt), `bypassPermissions` (skips prompts; use in containers/VMs).

## 6. SKILL.MD FORMAT

### 6.1 Locations [VERBATIM]

| Location | Path | Loads in |
| :- | :- | :- |
| Enterprise | `.claude/skills/<skill-name>/SKILL.md` in the managed settings directory | All org machines |
| Personal | `~/.claude/skills/<skill-name>/SKILL.md` | All your projects |
| Project | `.claude/skills/<skill-name>/SKILL.md` | This repo (commit to share) |
| Nested | `<subdir>/.claude/skills/<skill-name>/SKILL.md` | Sessions started in/below `<subdir>`; lazy-load on first file touch there |
| Additional directory | `.claude/skills/…` in an `--add-dir`/`/add-dir` directory | That session |
| Plugin | `<plugin>/skills/<skill-name>/SKILL.md` | Wherever plugin enabled, as `/plugin-name:skill-name` |
| claude.ai account | synced to `~/.claude/skills/synced/` (reserved name) | Signed-in sessions |

Custom commands (`.claude/commands/*.md`) are the legacy format, still supported, same frontmatter except `name` and `paths`. Reserved folder names: `synced`, `anthropic-skills`. Skill directories are watched — edits apply mid-session (`/reload-skills` to force).

### 6.2 Frontmatter reference [VERBATIM — skills doc]

All fields optional; only `description` recommended. Format: YAML between `---` markers, first line of the file; unparsable YAML = skill loads with no fields. Combined `description` + `when_to_use` truncated at 1,536 chars in the skill listing.

| Field | Required | Description |
| :- | :- | :- |
| `name` | No | Command name in the `/` menu; defaults to directory name |
| `description` | Recommended | What the skill does and when to use it; drives automatic invocation |
| `when_to_use` | No | Extra trigger phrases; appended to `description` in the listing |
| `argument-hint` | No | Autocomplete hint, e.g. `[issue-number]` |
| `arguments` | No | Named positional args for `$name` substitution (space-separated string or list) |
| `disable-model-invocation` | No | `true` = Claude can't auto-load it (manual `/name` only) |
| `user-invocable` | No | `false` = hidden from `/` menu, Claude-only |
| `allowed-tools` | No | Tools usable without prompting during the skill's turn (space/comma-separated or YAML list) |
| `disallowed-tools` | No | Tools removed from the pool while the skill is active |
| `model` | No | Model for the skill's turn (same values as `/model`, or `inherit`) |
| `effort` | No | `low|medium|high|xhigh|max` for the turn |
| `context` | No | `fork` = run in a forked subagent |
| `agent` | No | Subagent type when `context: fork` |
| `background` | No | With `context: fork`; `false` waits for the result (default `true`) |
| `hooks` | No | Hooks registered while the skill is invoked (settings-format) |
| `paths` | No | Glob patterns of files that activate the skill |
| `shell` | No | `bash` (default) or `powershell` for `` !`command` `` blocks |
| `metadata` | No | Free-form YAML map for your own tooling |

### 6.3 Body conventions [VERBATIM examples]

```yaml
---
description: Summarizes uncommitted changes and flags anything risky. Use when the user asks what changed, wants a commit message, or asks to review their diff.
---

## Current changes

!`git diff HEAD`

## Instructions

Summarize the changes above in two or three bullet points, then list any risks you notice…
```

- **Dynamic context injection**: a `` !`command` `` line runs before Claude sees the skill and is replaced by its output. `` ```! `` fenced blocks run multi-command shell. `${CLAUDE_PROJECT_DIR}` and `${CLAUDE_SESSION_ID}` placeholders available. Disabled by `disableSkillShellExecution` / Cowork handling.
- **Argument substitution**: `$ARGUMENTS`, or named `$1`-style via `arguments:` frontmatter.
- **Task-style skills** (deploy, commit): add `disable-model-invocation: true`; optionally `context: fork`.
- **Reference-style skills**: pure knowledge loaded inline when relevant.
- Skill body stays in context across turns after loading — keep it concise.
- Invoke with `/name args`, chainable: `/skill-a /skill-b do XYZ` (up to six).
- The Skill tool passes `{ skill, args }` (see §2.1).

### 6.4 Bundled skills [VERBATIM list]

`/doctor`, `/code-review` (+`/review` alias), `/simplify`, `/batch`, `/debug`, `/loop` (alias `/proactive`), `/claude-api`, `/dataviz`, `/run`, `/verify`, `/run-skill-generator`, `/fewer-permission-prompts`, `/security-review`, `/deep-research` (bundled Workflow), `/design`, `/design-sync`, `/slides`, `/artifact-capabilities`, `/artifact-diagramming`, `/claude-in-chrome`, `/plugin-authoring`, `/update-config`, `/keybindings-help`, `/schedule`, `/workflow-authoring`, `/init`. Off-switch: `disableBundledSkills: true`.

## 7. SLASH COMMANDS [VERBATIM — commands doc]

The table below lists all built-in commands (v2.1.x). **Skill** = bundled skill (prompt-based), **Workflow** = bundled dynamic workflow. `<arg>` required, `[arg]` optional.

| Command | Purpose |
| :- | :- |
| `/add-dir <path>` | Add a working directory for file access |
| `/advisor [model\|off]` | Enable/disable the advisor tool |
| `/agents` | Print reminder to create/manage subagents (interactive wizard removed in v2.1.198+) |
| `/artifact-capabilities`, `/artifact-diagramming` | **Skill** — artifact references |
| `/artifacts` | List artifacts, attach/open/copy link |
| `/auto-mode-setup` | Draft `autoMode.environment` entries |
| `/autocompact [auto\|<tokens>]` | Set the auto-compact window |
| `/autofix-pr [prompt]` | Cloud session that fixes CI failures on the current PR |
| `/background [prompt]` (alias `/bg`) | Detach session as background agent |
| `/batch <instruction>` | **Skill** — decompose large change into 5–30 worktree subagents |
| `/branch [name]` | Branch the conversation at this point |
| `/btw [question]` | Side question that doesn't enter history |
| `/bug [report]` (alias `/share`) | Report a bug with session context (consent screen) |
| `/cd <path>` | Move session to a new working directory |
| `/chrome` | Configure Claude in Chrome |
| `/claude-api [subcommand]` | **Skill** — Claude API reference (migrate/upgrade/…) |
| `/claude-in-chrome [task]` | **Skill** — browser task |
| `/clear [name]` (aliases `/reset`, `/new`) | Start a new conversation with empty context |
| `/code-review [level] [--fix] [--comment] [--max-findings] [target]` (alias `/review`) | **Skill** — correctness review of diff/PR; `ultra` = cloud review |
| `/color [color\|default]` | Prompt-bar color for the session |
| `/compact [instructions]` | Summarize conversation to free context |
| `/config [key=value …]` (alias `/settings`) | Settings interface |
| `/context [all]` | Visualize context usage |
| `/copy [N]` | Copy last (or Nth-latest) assistant response |
| `/cost` | Alias for `/usage` |
| `/dataviz [request]` | **Skill** — chart/dashboard design guidance |
| `/debug [description]` | **Skill** — debug logging + session log analysis |
| `/deep-research <question>` | **Workflow** — fan-out web research, cited report |
| `/design [brief]` / `/design consent` / `/design revoke` / `/design-login` / `/design-sync [hint]` | **Skill** — Claude Design artifact flows |
| `/desktop` (alias `/app`) | Continue in Desktop app |
| `/diff` | Review working-tree changes |
| `/doctor [prompt-audit]` (alias `/checkup`) | **Skill** — setup checkup |
| `/effort [level\|auto\|status\|ultracode on\|off]` | Set effort level |
| `/exit` (alias `/quit`) | Exit CLI (detach if attached to background session) |
| `/export [filename]` | Export conversation as plain text |
| `/fast [on\|off]` | Toggle fast mode |
| `/feedback [report]` | Product feedback dialog / drafts queue |
| `/fewer-permission-prompts` | **Skill** — build allowlist from transcripts |
| `/focus` | Focus view toggle (fullscreen) |
| `/fork [prompt]` | Copy conversation into a new background session |
| `/goal [condition\|clear]` | Keep working across turns until condition met |
| `/heapdump` | Heap snapshot for memory debugging (hidden command) |
| `/help` | Show help and available commands |
| `/hooks` | View hook configurations |
| `/ide` | Manage IDE integrations |
| `/import [codex\|gemini\|cursor] [--dry-run] [--yes]` | Import config from other coding agents |
| `/init` | Initialize project with a `CLAUDE.md` guide |
| `/insights` | HTML report analyzing recent sessions |
| `/install-github-app` / `/install-slack-app` | Install integrations |
| `/keybindings` | Open keybindings file |
| `/list-agents` (alias `/peers`) | List messageable agents/sessions |
| `/login` / `/logout` | Sign in/out |
| `/loop [interval] [prompt]` | **Skill** — recurring prompt (self-pacing without interval) |
| `/mcp [reconnect\|enable\|disable]` | Manage MCP servers and OAuth |
| `/memory` | Edit CLAUDE.md files; auto-memory on/off |
| `/mobile` (aliases `/ios`, `/android`) | QR code for mobile app |
| `/model [model]` | Switch model (saves default; `s` = session-only) |
| `/output-style [style]` | List/switch output styles |
| `/passes` | Share free week (eligible accounts) |
| `/permissions` (alias `/allowed-tools`) | Manage allow/ask/deny rules, working dirs, auto-mode denials |
| `/plan [description]` | Enter plan mode |
| `/plugin [subcommand]` | Plugin management |
| `/plugin-authoring` | **Skill** — write a mod |
| `/powerup` | Interactive feature lessons |
| `/pr-comments [PR]` | **Removed in v2.1.91** (ask Claude to view PR comments instead) |
| `/privacy-settings` | Privacy settings (Pro/Max/Ultra) |
| `/radio` | Claude FM lo-fi radio |
| `/rate-limit-options` | Options when a usage limit blocks a request |
| `/recap` | One-line session summary |
| `/release-notes` | Interactive changelog |
| `/reload-plugins [--force]` | Reload plugins without restart |
| `/reload-skills` | Re-scan skill directories |
| `/remote-control` (alias `/rc`) | Enable Remote Control on this session |
| `/remote-env` | Default cloud environment |
| `/rename [name]` | Rename session |
| `/restart` (alias `/update`) | Restart and resume (applies update) |
| `/resume [session]` (alias `/continue`) | Resume by ID/name or picker |
| `/review [level] [target]` | Alias of `/code-review` |
| `/rewind` (aliases `/checkpoint`, `/undo`) | Rewind code and/or conversation to checkpoint |
| `/run` / `/run-skill-generator` / (`/verify`) | **Skill** — launch and verify your app |
| `/sandbox` | Toggle sandbox mode |
| `/schedule [description]` (alias `/routines`) | **Skill** — cloud scheduled tasks |
| `/scroll-speed` | Mouse-wheel scroll speed (fullscreen) |
| `/security-review` | Analyze branch diff for security vulnerabilities |
| `/setup-bedrock` / `/setup-vertex` | Provider setup wizards (hidden unless env set) |
| `/simplify [target]` | **Skill** — cleanup review (reuse/simplify/efficiency/altitude), applies fixes |
| `/skill-doctor` | Skill context cost + usage report |
| `/skills` | List available skills |
| `/slides [brief]` | **Skill** — Claude Slides artifact |
| `/stats` | Alias for `/usage` (Stats tab) |
| `/status` | Version, model, account, connectivity |
| `/statusline` | Configure status line (uses `statusline-setup` agent) |
| `/stickers` | Sticker availability |
| `/stop` | Stop attached background session |
| `/subtask <task>` | Spawn a forked subagent inheriting full context |
| `/tasks` (alias `/bashes`) | View/manage background work |
| `/team-onboarding` | Generate team onboarding guide |
| `/teleport` (alias `/tp`) | Pull a cloud session into this terminal |
| `/terminal-setup` | Install Shift+Enter keybinding / bell / clipboard fixes |
| `/theme` | Change color theme |
| `/tui [classic\|fullscreen]` | Switch renderer |
| `/ultraplan <prompt>` | **Removed** — use plan mode |

## 8. SUBAGENTS

### 8.1 Built-in agent types [VERBATIM]

| Agent | Model | Tools | Purpose |
| :- | :- | :- | :- |
| `Explore` | Parent's model (or the `opus`-alias model on subscription/console/gateway connections; stays on Fable on Bedrock/Vertex/Foundry/gateway) | Read-only; Write and Edit denied | "A fast, read-only agent optimized for searching and analyzing codebases… file discovery, code search, codebase exploration." Claude specifies thoroughness: **quick** / **medium** / **very thorough**. Starts without CLAUDE.md and git-status snapshot. |
| `Plan` | Inherits from parent | Read-only; Write/Edit denied | "A research agent used during plan mode to gather context before presenting a plan." |
| `general-purpose` | Parent's model | Every tool available to subagents | "A capable agent for complex, multi-step tasks that require both exploration and action." Default `subagent_type` when omitted. |
| `claude` | None of its own | Every tool available to subagents | Catch-all when no specialized agent fits; default for dispatched background sessions. |
| `statusline-setup` | Sonnet | Read, Edit | Configuring the status line via `/statusline`. |
| `claude-code-guide` | Haiku | Bash, Read, WebFetch, WebSearch | Questions about Claude Code / Agent SDK / Claude API. |
| `web-fetch` | Haiku (or parent's model) | WebFetch | Reads web pages when the session routes fetches through the subagent (v2.1.287+; off for `-p`/SDK). |

Env knobs: `CLAUDE_CODE_DISABLE_EXPLORE_PLAN_AGENTS=1` removes built-in Explore/Plan; `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1` (SDK) removes all built-ins; deny `Agent(web-fetch)` to restore direct WebFetch. Agent tool call without `subagent_type` fails with `subagent_type is required` when no general-purpose fallback exists.

### 8.2 `.claude/agents/*.md` frontmatter [VERBATIM]

Locations & priority: managed settings (1) > `--agents` CLI JSON (2) > `.claude/agents/` project (3) > `~/.claude/agents/` user (4) > plugin `agents/` (5). Directories scanned recursively; `name` is identity (subfolder path irrelevant, except plugin scoping `my-plugin:review:security`). Only `name` and `description` required.

| Field | Required | Description |
| :- | :- | :- |
| `name` | Yes | Unique id ≤256 chars; can't start with `-` or contain `:` (reserved for plugin scoping); hooks receive it as `agent_type` |
| `description` | Yes | When Claude should delegate to this subagent |
| `tools` | No | Comma-separated string or YAML list; inherits all subagent tools if omitted |
| `disallowedTools` | No | Denylist; wins over `tools`; specifier entries remove the whole tool |
| `model` | No | `sonnet`/`opus`/`haiku`/`fable`, full model ID, or `inherit` |
| `permissionMode` | No | `default`/`acceptEdits`/`auto`/`dontAsk`/`bypassPermissions`/`plan`/`manual` (alias of default). Ignored for plugin subagents |
| `maxTurns` | No | Turn cap; output marked partial, resumable |
| `autoCompactWindow` | No | ≥100000 tokens (v2.1.296+) |
| `skills` | No | Skills preloaded (full content injected) |
| `mcpServers` | No | Server-name references or inline definitions (stdio/http/sse/ws) scoped to the subagent |
| `hooks` | No | Hooks scoped to the subagent (a `Stop` here converts to `SubagentStop`). Ignored for plugin subagents |
| `memory` | No | `user`/`project`/`local` persistent memory scope |
| `background` | No | `true` keeps it in background even when asked to wait |
| `omitClaudeMd` | No | `true` starts without user/project/local CLAUDE.md (v2.1.271+) |
| `effort` | No | `low`…`max` |
| `isolation` | No | `worktree` = isolated copy of repo, auto-cleaned if unchanged |
| `color` | No | `red|blue|green|yellow|purple|orange|pink|cyan` |
| `initialPrompt` | No | First user turn when run as main agent via `--agent` |
| `experimental` | No | Map; `cacheTtl: 5m|1h` prompt-cache TTL |

Example (verbatim):

```markdown
---
name: code-reviewer
description: Reviews code for quality and best practices
tools: Read, Glob, Grep
model: sonnet
---

You are a code reviewer. When invoked, analyze the code and provide
specific, actionable feedback on quality, security, and best practices.
```

CLI-defined (`--agents` JSON) fields: `prompt` (system prompt), plus all frontmatter fields except `color`/`experimental` (ignored).

### 8.3 Tool pool rules (verbatim facts)

- The first filter removes from **every** subagent: `Agent` (at depth limit), `AskUserQuestion`, `EndConversation`, `EnterPlanMode`, `ExitPlanMode` (unless `permissionMode: plan`), `propose_skills`, `ScheduleWakeup`, `WaitForMcpServers`, `Workflow`.
- Background subagents keep only: MCP tools, `SubagentHandback`, `Read, Grep, Glob, LSP, Bash, PowerShell, Edit, Write, NotebookEdit, WebFetch, WebSearch, TodoWrite, Skill, ToolSearch, EnterWorktree, ExitWorktree, Monitor, TaskStop, SendMessage, Artifact, ListPlugins, ListSkills, SearchPlugins, SearchSkills` — most other built-ins are removed silently.
- Teammates additionally keep `TaskCreate, TaskGet, TaskList, TaskUpdate, CronCreate, CronDelete, CronList`.
- Depth limit governs nested subagents; forks skip both filters and get the parent's exact tool pool.
- `tools: Agent(worker, researcher)` (main-thread agents only) is a spawn allowlist.

## 9. HOOKS

### 9.1 Event names [VERBATIM — hooks reference]

Cadence grouping (verbatim): per session: `SessionStart`, `SessionEnd`; per turn: `UserPromptSubmit`, `Stop`, `StopFailure`; per tool call: `PreToolUse`, `PostToolUse` (except `EndConversation` calls).

| Event | When it fires |
| :- | :- |
| `SessionStart` | Session begins or resumes (matchers: `startup`, `resume`, `clear`, `compact`, `fork`) |
| `Setup` | `--init-only` / `--init` / `--maintenance` (matchers `init`, `maintenance`) |
| `UserPromptSubmit` | Prompt submitted, before Claude processes it |
| `UserPromptExpansion` | A typed command expands into a prompt; can block the expansion |
| `PreToolUse` | Before a tool call executes; can block it |
| `PermissionRequest` | Tool call needs a permission decision |
| `PermissionDenied` | Auto mode denies a call (`hookSpecificOutput.retry: true` allows retry) |
| `PostToolUse` | After a tool call succeeds |
| `PostToolUseFailure` | After a tool call fails |
| `PostToolBatch` | After a parallel tool-call batch resolves |
| `Notification` | Notification sent (matchers: `permission_prompt`, `idle_prompt`, `auth_success`, …) |
| `MessageDisplay` | While assistant text is displayed |
| `SubagentStart` / `SubagentStop` | Subagent spawned / finished (matcher = agent type) |
| `TaskCreated` / `TaskCompleted` | `TaskCreate` / completion |
| `Stop` | Claude finishes responding |
| `StopFailure` | Turn ended on API error (matcher = error type: `rate_limit`, `authentication_failed`, …) |
| `TeammateIdle` | Agent-team teammate about to go idle |
| `InstructionsLoaded` | CLAUDE.md / `.claude/rules/*.md` loaded (matchers `session_start`, `nested_traversal`, …) |
| `ConfigChange` | Settings file changed (matchers `user_settings`, `project_settings`, `local_settings`, `policy_settings`, `skills`) |
| `CwdChanged` | Working directory changed (e.g. `cd`) |
| `DirectoryAdded` | `/add-dir` or SDK `register_repo_root` (matchers `slash_command`, `register_repo_root`) |
| `FileChanged` | Watched file changed (matcher = literal filenames) |
| `WorktreeCreate` / `WorktreeRemove` | Worktree lifecycle |
| `PreCompact` / `PostCompact` | Before/after compaction (matchers `manual`, `auto`) |
| `PreModelSwitch` / `PostModelSwitch` | Model switch (matcher = canonical model name) |
| `Elicitation` / `ElicitationResult` | MCP server asks for user input / response |
| `SessionEnd` | Session terminates (matchers `clear`, `resume`, `logout`, `prompt_input_exit`, `other`) |

**1.x/2.0-era set** (what older clones implemented — the current list is a superset): `PreToolUse`, `PostToolUse`, `Notification`, `UserPromptSubmit`, `Stop`, `SubagentStop`, `SessionStart`, `SessionEnd`, `PreCompact` (+ `PostCompact`). `SessionEnd` matcher `prompt_input_exit`; `SessionStart` `compact` and `fork` are later additions.

### 9.2 Configuration schema [VERBATIM]

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "if": "Bash(rm *)",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/block-rm.sh",
            "args": []
          }
        ]
      }
    ]
  }
}
```

Levels: event → matcher group → handler array. Handler types: `command` (stdin JSON in, exit codes/stdout out), `http` (POST JSON body), `mcp_tool` (`server` + `tool` + `input` with `${tool_input.x}` substitution), `prompt` (LLM single-turn evaluation; `prompt` + optional `model`), `agent` (experimental subagent verifier).

Common fields: `type`, `if` (one permission rule, tool events only), `timeout` (seconds; defaults 600 command/http/mcp_tool, 30 prompt, 60 agent; lowered to 30 on UserPromptSubmit/PreModelSwitch/PostModelSwitch and 10 on MessageDisplay; SessionEnd shares a 1.5s budget), `statusMessage`, `once` (skill frontmatter only). Command fields: `command`, `args` (exec form — no shell; otherwise shell form `sh -c`/Git Bash), `async` (background, non-blocking), `asyncRewake` (background, wakes Claude on exit 2), `shell` (`bash`|`powershell`), `onFailure` (`continue`|`block`). Path placeholders: `${CLAUDE_PROJECT_DIR}`, `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`.

**Matcher syntax** (verbatim): `"*"`, `""`, or omitted = match all; chars limited to letters/digits/`_`/`-`/spaces/`,`/`|` = exact string or `|`/`,`-separated list; any other character = unanchored JavaScript regex (`mcp__memory__.*`; `.*` required for server-wide matches; plugin-bundled servers are `mcp__plugin_<plugin-name>_<server-name>__<tool>`). A `Bash` matcher on `PreToolUse`/`PermissionRequest` also covers Monitor commands (v2.1.314+).

### 9.3 Hook I/O JSON shapes [VERBATIM structure; some field details reconstructed from doc examples]

**Input** (stdin for command hooks / POST body for http): common fields include `session_id`, `transcript_path`, `cwd`, `hook_event_name`, plus per-event fields — tool events carry `tool_name` and `tool_input` (e.g. `{ "tool_name": "Bash", "tool_input": { "command": "rm -rf /tmp/build" }, ... }`); subagent events carry `agent_id` / `agent_type`. [RECONSTRUCTED detail: 1.x/2.0-era tool inputs also carried `permission_mode`, `match_tool_input` for `PreToolUse` with matchers, and `stop_hook_active` on `Stop`.]

**Output** (stdout JSON; exit codes): exit `0` = success (stdout shown to Claude in transcript mode for `UserPromptSubmit`/`SessionStart`); exit `2` = blocking error (stderr fed back to Claude); other non-zero = non-blocking error, execution continues.

JSON decision output (verbatim example):

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Destructive command blocked by hook"
  }
}
```

Known decision fields across events [RECONSTRUCTED from docs + classic hooks docs]:
- Top-level: `continue` (boolean; `false` prevents Claude from continuing after the hook), `stopReason` (string shown alongside), `suppressOutput` (hide stdout from transcript), `decision` (`"block"` or `"approve"`), `reason`.
- `PreToolUse`/`PermissionRequest`: `hookSpecificOutput.permissionDecision` ∈ `"allow" | "deny" | "ask"` + `permissionDecisionReason`; `hookSpecificOutput.updatedInput` rewrites the tool input; `hookSpecificOutput.additionalContext` injects text.
- `UserPromptSubmit`: `hookSpecificOutput.hookEventName: "UserPromptSubmit"` + `additionalContext`; exit 2 blocks the prompt.
- `PermissionDenied`: `hookSpecificOutput.retry: true` lets the model retry the denied call.
- `Stop`: input includes `session_crons` (pending wakeups); a `decision: "block"` with `reason` makes Claude continue working on the reason.
- `SessionStart`/`UserPromptSubmit` stdout is added to context (transcript mode).

### 9.4 Locations [VERBATIM]

`~/.claude/settings.json` (all projects) · `.claude/settings.json` (project, committable) · `.claude/settings.local.json` · managed policy · plugin `hooks/hooks.json` · skill frontmatter (live until `/clear`/`/resume`; `once` honored) · subagent frontmatter (live while subagent runs; `Stop` → `SubagentStop`). Hook entries **merge** across levels. `allowManagedHooksOnly` (managed) restricts to managed hooks. Hooks also fire inside subagents for tool events (input carries `agent_id`/`agent_type`).

## 10. MCP INTEGRATION

### 10.1 Config shapes [VERBATIM]

Scopes: `local` (default, per-project in `~/.claude.json`), `project` (`.mcp.json` at repo root, committable, requires approval/trust), `user` (all projects). Reserved server names: `workspace`, `claude-in-chrome`, `computer-use`, `Claude Preview`, `Claude Browser`.

```bash
claude mcp add --transport http notion https://mcp.notion.com/mcp
claude mcp add --transport http secure-api https://api.example.com/mcp --header "Authorization: Bearer <token>"
claude mcp add --transport stdio airtable --env AIRTABLE_API_KEY=KEY -- npx -y airtable-mcp-server   # -- separates claude flags from server command
claude mcp add-json events-server '{"type":"ws","url":"wss://mcp.example.com/socket","headers":{…}}'
claude mcp add --transport sse asana https://mcp.asana.com/sse    # SSE deprecated; HTTP tried first on v2.1.265+
claude mcp list | get <name> | remove <name>
```

JSON entry schema (`.mcp.json`, `~/.claude.json`, `add-json`, subagent `mcpServers`):

```json
{
  "mcpServers": {
    "<name>": {
      "type": "stdio",                    // stdio | http (alias streamable-http) | sse | ws ; "sdk" host-only
      "command": "npx",                   // stdio only
      "args": ["-y", "@example/mcp-server"],
      "env": { "KEY": "value" },
      "url": "https://…",                 // http/sse/ws only
      "headers": { "Authorization": "Bearer $MY_TOKEN" },   // http/sse/ws; env interpolation via headersHelper/allowedEnvVars
      "timeout": 600000                   // per-server tool-call wall-clock limit, ms
    }
  }
}
```

Facts: a `url` with no `type` is a config error ("add \"type\": \"http\" (or \"sse\" / \"ws\")"); `${VAR}` expansion in config (stdio needs `${VAR:-default}` in project files); `CLAUDE_PROJECT_DIR` set in stdio servers' env; stdio shutdown = SIGINT → (100ms) SIGTERM → (400ms) SIGKILL on macOS/Linux, stdin close → (300ms) tree kill on Windows; `MCP_TIMEOUT` startup timeout (30s default), `MCP_TOOL_TIMEOUT`, `CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT` (5 min remote / 30 min stdio), `MCP_SDK_GENERATION` v1/v2; tool calls >2 min auto-background; settings keys `enableAllProjectMcpServers`, `enabledMcpjsonServers`, `disabledMcpjsonServers`, `allowedMcpServers`/`deniedMcpServers`, `managedMcpServers`.

### 10.2 Tool naming [VERBATIM]

- Standard: `mcp__<server>__<tool>` — e.g. `mcp__memory__create_entities`, `mcp__filesystem__read_file`.
- Plugin-bundled server: `mcp__plugin_<plugin-name>_<server-name>__<tool>` — e.g. `mcp__plugin_my-plugin_db__query`.
- Match all tools from a server: `mcp__<server>__.*` (the `.*` is required — `mcp__memory` alone matches nothing).
- Subagent `tools`/`disallowedTools` accept whole-server entries: `mcp__github__*` (grant), `mcp__github` or `mcp__github__*` (withhold), `mcp__*` (withhold all).
- Deny rules with `mcp__` + parentheses are skipped when loading settings files; use `--disallowedTools` for per-parameter MCP denies.
- Tool names >128 chars are dropped.
- MCP prompts appear as commands; MCP resources via `ListMcpResourcesTool`/`ReadMcpResourceTool`/`ReadMcpResourceDirTool`; MCP elicitation via `Elicitation` hooks; tool search (`ToolSearch`) is the default way deferred MCP tools load.

## 11. PROVENANCE SUMMARY

| Section | Status | Source of record |
| :- | :- | :- |
| §1 Tool inventory + renames | **Verbatim** (tools-reference table + version notes) | code.claude.com/docs/en/tools-reference; sub-agents doc (Task→Agent v2.1.63) |
| §2 Tool reference (names, schemas, behaviour) | **Interface** (names/schemas verbatim; description prose summarised here) | code.claude.com/docs/en/tools-reference; live implementation in `kali/tools/` |
| §3 System prompt structure | **Summary** (section ordering and intent only; upstream prose not reproduced) | code.claude.com/docs/en/cli-reference + observed CLI behaviour |
| §4 CLI flags + commands | **Verbatim** (condensed descriptions) | code.claude.com/docs/en/cli-reference |
| §5 Settings + permission syntax | **Verbatim** | docs/en/settings, settings-reference, permissions |
| §6 SKILL.md | **Verbatim** | docs/en/skills |
| §7 Slash commands | **Verbatim** | docs/en/commands |
| §8 Subagents | **Verbatim** | docs/en/sub-agents |
| §9 Hooks (events, config, matcher) | **Verbatim**; hook I/O field-level shapes partly **reconstructed** | docs/en/hooks (+ classic hooks schema for decision fields) |
| §10 MCP | **Verbatim** | docs/en/mcp |

### Known gaps / caveats for implementers

1. **Tool descriptions** are the upstream CLI's prompting text and are
   Anthropic's proprietary material. This project ships its own
   implementations in `kali/tools/` - consult those for the live wording.
2. **MultiEdit** was merged into **Edit** in 2.1.x (`Edit` gained a
   `replace_all` flag). It survives only as a permission-rule alias.
3. Hook **JSON output** shapes are stable
   (`hookSpecificOutput.permissionDecision` etc.), but the full per-event
   input field list lives in the hooks reference's per-event sections.
4. Platform tools (`Artifact`, `ArtifactComments`, `ArtifactData`,
   `DesignSync`, `Cron*`, `RemoteTrigger`, `PushNotification`,
   `ListAgents`, `ListPlugins`…) exist only on claude.ai-authenticated
   surfaces - exclude them from a generic clone.
5. Model-name strings rotate per generation; keep them templated.
6. `BashOutput` / `TaskOutput` were **removed** in 2.1.x - background work is
   read with `Read` against the task output file, and stopped with
   `TaskStop`.

## 12. SOURCES

- Official docs (fetched 2026-11-21): https://code.claude.com/docs/en/tools-reference · /cli-reference · /settings · /settings-reference · /permissions · /skills · /hooks · /commands · /sub-agents · /mcp
- 2.0 prompt diff (structure analysis only): https://mikhail.io/2025/09/sonnet-4-5-system-prompt-changes/









