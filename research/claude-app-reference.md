# Claude app — interface reference

Compiled 2026-11-23. Sources: Anthropic's official documentation
(`code.claude.com/docs/en/desktop*`, `code.claude.com/docs/en/mobile`,
`claude.com/docs/cowork/guide/dispatch`) plus REA analysis of the shipped
Windows installer.

This document records the **observable interface** of the Claude desktop and
mobile apps so Kali Code can present an equivalent experience. It contains no
proprietary code and reproduces no proprietary prose.

---

## 1. What the desktop app is

Anthropic's Windows app is a **native x86-64 PE executable**, not an Electron
wrapper. REA confirmed this on the shipped installer:

| Property | Value |
| :- | :- |
| Artifact | `claude-windows-x64.exe` (181.1 MB) |
| SHA-256 | `379f32a019393d95800166da6151c8c1cc84881a22a6fcbc207e2cf3e19d2b99` |
| Format | `pe` (native x86-64), not `asar` |
| Kind | installer stub — the payload is an embedded container |

Earlier builds (2024-2025) were Electron/Chromium wrappers around
`claude.ai`. The current build is native. **Consequence for Kali Code:** a
web-view shell is the practical route to a matching desktop UI, because
re-implementing a native WinUI client from scratch is disproportionate. The
Kali Code desktop app therefore uses a WebView2 host over the existing
Python agent.

The macOS build is a universal DMG; Linux ships as `.deb`/`.appimage`.

---

## 2. Desktop app structure

The app has three top-level surfaces in the sidebar:

- **Chat** — general conversation with Claude.
- **Code** — Claude Code with a graphical interface (this is the surface
  Kali Code replaces).
- **Cowork** — longer agentic work, Dispatch, computer use.

Kali Code has one surface: **Code**.

### 2.1 The session model

Each conversation is a **session**: its own chat history and project folder,
independent of every other session.

- The sidebar lists sessions; several run in parallel.
- A session may live in a **worktree** — an isolated copy of the project.
  Worktrees are stored under `<project-root>/.claude/worktrees/` by default.
- Sessions can be archived, renamed, grouped and sorted.
- `Ctrl+Tab` / `Ctrl+Shift+Tab` switch between sessions.
- A **side chat** (`Ctrl+;`, or `/btw` in the prompt box) asks a question
  using the session's context without adding to the main conversation.

### 2.2 The prompt row

A row of controls sits directly under the prompt box, in this order:

| Control | Purpose |
| :- | :- |
| Environment selector | Where Claude runs: **Local**, **Cloud**, **SSH** (Windows: also **WSL**) |
| Project folder | The directory Claude works in |
| Worktree toggle | Run the session in an isolated git worktree |
| Permission mode | Manual / Accept edits / Plan / Auto / Bypass permissions |
| Model picker | Which model to use |
| Context ring | Percentage of the context window used; popover shows a per-category breakdown |

`/context` prints the same breakdown in the chat.

### 2.3 Permission modes

| Mode | Behaviour |
| :- | :- |
| **Manual** (`default`) | Asks before editing files or running commands. Shows a diff with approve/reject. |
| **Accept edits** (`acceptEdits`) | Auto-accepts file edits and common filesystem commands (`mkdir`, `touch`, `mv`); still asks for other commands. |
| **Plan** (`plan`) | Reads and explores, proposes a plan, edits nothing until approved. |
| **Auto** (`auto`) | No routine prompts. A background classifier reviews shell/network actions and blocks risky ones. |
| **Bypass permissions** (`bypassPermissions`) | No prompts except the actions no mode auto-approves. Equivalent to `--dangerously-skip-permissions`. |

Kali Code already implements `default`, `acceptEdits`, `plan` and
`bypassPermissions`. **Auto mode is the one missing mode** — it needs a
classifier pass before executing a tool.

### 2.4 Panes

The session is built from draggable, resizable panes:

- **Chat** — the conversation.
- **Changes** — the diff view.
- **Browser** — a tabbed browser for previewing your app and external sites.
- **Terminal** — an integrated terminal sharing the session's working
  directory and environment (`Ctrl+\``).
- **Files** — a file editor (auto-saves by default).
- **Plan** — the current plan.
- **Tasks** — background tasks: subagents, background shell commands.
- **Subagent** — a subagent's own pane.
- **iOS Simulator** (macOS only).

Panes can be popped out into their own window and docked back. `Ctrl+\`
closes the focused pane. A pane can be **minimized** into the session rail.

### 2.5 The session rail (details panel)

A panel beside the chat with cards:

- **Environment** — where the session runs.
- **Changes** — the `+12 -1` line-count indicator; click to open the diff.
- **Context** — context usage, by category.
- **Running** — what is currently executing.
- **Pull request** — PR state and CI checks.

### 2.6 Diff view

- Click the `+12 -1` indicator to open it.
- Review modifications file by file.
- Hover a line and click the **`+`** beside its line number to leave a
  comment.
- Comment on multiple lines, then submit them all at once
  (`Ctrl+Enter` on Windows).
- Claude reads the comments and revises; the result appears as a new diff.

### 2.7 Code review card

`/code-review` produces a **Code review** card grouped by file with two
actions:

- **Walk through in changes** — open the diff and step through findings; each
  finding shows at its line with **Fix this one** or dismiss.
- **Apply fixes** — ask Claude to fix the open findings.

### 2.8 View modes

Cycled with `Ctrl+O`:

| Mode | Shows |
| :- | :- |
| **Normal** | Tool calls collapsed into summaries, full text responses |
| **Thinking** | Normal + Claude's thinking |
| **Verbose** | Every tool call, file read and intermediate step, plus thinking |

### 2.9 Prompt box behaviour

- `Enter` sends; a correction sent while Claude is working is read as soon
  as the current action completes.
- **Stop button** interrupts immediately (`Esc`).
- **`+` button** → file attachments, skills, connectors, plugins.
- **`@mention`** pulls a file into context.
- **Suggested prompt**: after a reply, gray suggested text appears in the
  empty prompt box. `Tab` or `Right arrow` accepts it; typing dismisses it.
- **`/`** opens the slash-command palette.
- Drag and drop files into the prompt.

### 2.10 Keyboard shortcuts (Windows)

| Shortcut | Action |
| :- | :- |
| `Ctrl+/` | Show all shortcuts |
| `Ctrl+N` | New session |
| `Ctrl+W` | Close session |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | Switch sessions |
| `Esc` | Stop the response |
| `Tab` / `→` | Accept the suggested prompt |
| `Ctrl+Shift+D` | Toggle diff pane |
| `Ctrl+Shift+B` | Toggle Browser pane |
| `Ctrl+`` ` `` | Toggle terminal pane |
| `Ctrl+\` | Close focused pane |
| `Ctrl+Alt+W` | Take the focused session out of split view |
| `Ctrl+;` | Open side chat |
| `Ctrl+O` | Cycle view modes |
| `Ctrl+Shift+M` | Permission mode menu |
| `Ctrl+Shift+I` | Model menu |
| `Ctrl+Shift+E` | Effort menu |
| `1`–`9` | Select item in an open menu |

### 2.11 Other desktop features

- **Scheduled tasks** — recurring work on a cron-ish schedule (Hourly,
  Daily, Weekdays, Weekly, Manual, Custom). Each task is a `SKILL.md` under
  `~/.claude/scheduled-tasks/<name>/`. Only fires while the app is open and
  the machine is awake.
- **Computer use** — Claude opens apps and controls the screen. App access
  tiers are fixed by category: browsers are **view only**, terminals and IDEs
  are **click only**, everything else gets **full access**.
- **Pull request monitoring** — `Auto-fix` and `Merge when ready`. Requires
  the GitHub CLI (`gh`) installed and authenticated.
- **Browser pane** — dev servers, auto-verify (Claude screenshots the page,
  inspects the DOM, clicks, fills forms and fixes what it finds). Dev server
  config lives in `.claude/launch.json`.
- **Cross-session messaging** — Claude can list, read and message its other
  sessions.

---

## 3. Mobile app

> "The Claude app for iOS and Android is a client for Claude Code sessions
> rather than a place where code runs."

This is the key architectural insight: **the phone never runs the agent.** It
is a client that reaches one of four execution surfaces.

| Surface | Where the work runs | Notes |
| :- | :- | :- |
| **Cloud sessions** | Anthropic-managed cloud | Continues after the phone is put away |
| **Projects** | Cloud, parallel threads | Claude coordinates threads and reports back |
| **Remote Control** | A Claude Code session on your own machine | Needs local filesystem, tools, MCP servers |
| **Dispatch** | The Desktop app on your machine | Message a task; Dispatch decides how to run it |

### 3.1 Mobile UI

- Bottom navigation with a **Code** tab (alongside Chat and Cowork).
- The Code tab lists sessions; tap one to open it.
- `claude.ai/code/new` starts a new Code session in the app.
- **Push notifications** when a session finishes or needs approval.
- Sign-in with the same claude.ai account.

### 3.2 Mobile limitations (documented by Anthropic)

- Local-only commands (`/plugin`, `/resume`) do not work from the app.
- **Bypass permissions cannot be selected** from the app — only Manual,
  Accept edits, Plan and Auto.
- Dispatch needs a Pro/Max/Ultra plan and is closed to new users.

### 3.3 The pairing model

Remote Control pairs the phone with a running session:

```
claude remote-control        # or /remote-control inside a session
```

The session stays on your machine; the phone drives it.

### 3.4 Dispatch

A persistent conversation that breaks a high-level outcome into child tasks,
each running as its own session. Child task states: **Running**,
**Awaiting input**, **Awaiting answer**, **Completed**, **Error**,
**Archived**. Permission prompts forwarded to the phone are **auto-denied
after 10 minutes** if unanswered.

---

## 4. What Kali Code must add

Mapping the reference above onto Kali Code's existing code:

### Already present

| Reference feature | Kali Code equivalent |
| :- | :- |
| Session model | `Agent` instance + `session_id` |
| Permission modes | `default`, `acceptEdits`, `plan`, `bypassPermissions` |
| Slash commands | `/model`, `/clear`, `/compact`, `/cost`, `/status`, `/tasks`, `/permissions`, `/alwaysallow`, `/skills`, `/agents`, `/mcp`, `/hooks`, `/doctor`, `/title` |
| Skills | `SKILL.md` discovery and invocation |
| MCP | Full client, stdio + HTTP/WS |
| Plan mode | `EnterPlanMode` / `ExitPlanMode` |
| Worktrees | OpenCode-style `worktree_create` tool exists in the harness |
| Hooks | `PreToolUse` / `PostToolUse` / `UserPromptSubmit` |
| Background tasks | `BackgroundShell`, subagents, `Task*` tools |
| Compact | `/compact` + auto-compact at 82% of context |
| Title | AI-generated session title |
| Remote client | `kali/serve.py` WebSocket server + PWA |

### Missing

| Reference feature | Gap | Effort |
| :- | :- | :- |
| **Auto permission mode** | Needs a classifier pass before tool execution | Medium |
| **Diff view** | No unified-diff renderer with per-line comments | Medium |
| **Code review card** | No `/code-review` command | Medium |
| **Desktop GUI shell** | Terminal-only today | **Large** |
| **Side chat** | No `/btw` | Small |
| **Suggested prompts** | No background suggestion generation | Small |
| **Scheduled tasks** | No scheduler | Medium |
| **Native APK** | PWA only | **Large** |
| **Push notifications** | Service worker exists, no VAPID server | Small |
| **Multi-session** | One agent per connection | Medium |
| **File editor pane** | Read-only file access today | Medium |
| **Integrated terminal** | Terminal-only app, so N/A for the GUI | N/A |

---

## 5. Design decisions for Kali Code's desktop app

### 5.1 Shell choice

| Option | Pros | Cons |
| :- | :- | :- |
| **WebView2 host (recommended)** | One Python process; WebView2 ships with Windows 10/11; reuses the PWA UI; small | Needs the WebView2 runtime (preinstalled on Win11) |
| PyWebView | Similar, less code | Same WebView2 dependency, less control |
| Tauri (Rust) | Small binary, modern | Adds a Rust toolchain and a second runtime |
| Native WinUI | True native | Weeks of work; no leverage over the existing web UI |
| Electron | Easiest | 150 MB+ and slow startup — exactly what Anthropic moved away from |

**Decision:** a **WebView2 host** written in Python, serving the existing
desktop web UI from the local server. The same server backs the phone client,
so there is one protocol and one UI codebase.

### 5.2 The server becomes the core

`kali/serve.py` already exposes the agent over WebSocket. It grows into:

- **Session registry** — many concurrent sessions, each with its own agent,
  working directory, permission mode and model.
- **REST/WS API** — the surface both the desktop shell and the APK use.
- **Diff endpoints** — compute unified diffs for changed files.
- **Push service** — VAPID-signed Web Push for the phone.
- **Auto-mode classifier** — an extra model pass before risky tool calls.

### 5.3 What the desktop UI contains

Reusing the reference layout:

```
┌────────────┬────────────────────────────────────┬────────────────┐
│ Sessions   │  Chat                              │ Session rail   │
│            │                                    │                │
│ + New      │  ┌──────────────────────────────┐  │ Environment    │
│            │  │ message / streaming output   │  │ Changes  +12-1 │
│ ▸ project  │  │ tool cards, permission cards │  │ Context  43%   │
│   session  │  └──────────────────────────────┘  │ Running        │
│   session  │                                    │ Pull request   │
│            │  ┌──────────────────────────────┐  │                │
│            │  │ prompt box  [+][env][folder] │  │                │
│            │  │ [mode][model][ctx%][send]    │  │                │
│            │  └──────────────────────────────┘  │                │
├────────────┴────────────────────────────────────┴────────────────┤
│ Panes: Chat | Changes | Browser | Terminal | Files | Plan | Tasks  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 6. Android APK plan

Anthropic's own APK cannot be fetched without an authenticated session (the
download URL redirects to `claude.ai/login`). REA's Android tools
(`inspect_android_package`, `inspect_android_class`,
`search_android_classes`, `inspect_apk_signature`) are ready for analysing
an APK once one is available.

### 6.1 Build route

| Route | Result | Notes |
| :- | :- | :- |
| **Native Kotlin + Jetpack Compose** | True native APK, best performance, Google Play ready | Needs Android SDK + Gradle (not installed yet); Java 21 is present |
| **Capacitor (web → APK)** | Wraps the existing PWA; one codebase | Ships a WebView; Play Store accepts it with caveats |
| **React Native** | Native feel, shared JS logic | Heavier toolchain, more setup than Compose |

**Decision:** **Kotlin + Jetpack Compose** for a real native app, talking to
the same `kali/serve.py` WebSocket API. The Compose UI mirrors the desktop
UI; the server is unchanged.

### 6.2 What the APK does

Mirrors Claude's mobile app model — the phone is a **client**, never the
executor:

- Session list, open a session, send a prompt.
- Stream output, tool cards, permission cards.
- **Approve / deny / always-allow** from the phone.
- Push notification when a session finishes or needs approval.
- Roblox publish button with the version number and game link.
- Token login (the `KALI_SERVER_TOKEN` from the server).

### 6.3 APK distribution

- Signed with a generated keystore; the keystore and its passwords stay out
  of git (a `keystore.properties.example` is committed instead).
- Debug APK for immediate sideloading; a release APK signed with the
  release key for distribution.
- `adb install` sideload, or a GitHub release asset.

### 6.4 Toolchain to install

1. Android command-line tools (`cmdline-tools`) → `sdkmanager`
2. Platform-tools (adb), platform android-35/36, build-tools
3. Gradle (via the wrapper, so no global install)
4. Accept the SDK licences

---

## 7. Milestones

| # | Milestone | Depends on |
| :- | :- | :- |
| 1 | Multi-session server + session registry | — |
| 2 | Desktop web UI (Claude Code tab layout) | 1 |
| 3 | WebView2 desktop shell (`KaliCode.exe --gui`) | 2 |
| 4 | Diff view + code review card | 2 |
| 5 | Android SDK setup + Compose project skeleton | — |
| 6 | APK client (chat, stream, permissions) | 1, 5 |
| 7 | Push notifications (VAPID) | 6 |
| 8 | Auto permission mode | 1 |
| 9 | Scheduled tasks, side chat, suggested prompts | 1 |

---

## 8. Evidence

| Claim | Source | Type |
| :- | :- | :- |
| Desktop app is a native PE, not Electron | REA `open_binary` on `claude-windows-x64.exe` | observed |
| Installer SHA-256 `379f32a0…` | REA artifact digest | observed |
| Session / pane / permission-mode structure | `code.claude.com/docs/en/desktop.md` | documentation |
| Shortcuts, view modes, diff view | `code.claude.com/docs/en/desktop.md` | documentation |
| Mobile is a client, not an executor | `code.claude.com/docs/en/mobile` | documentation |
| Cloud / Remote Control / Dispatch / Projects | `code.claude.com/docs/en/mobile` | documentation |
| Dispatch task states, 10-minute auto-deny | `claude.com/docs/cowork/guide/dispatch` | documentation |
| Scheduled task SKILL.md layout, schedules | `code.claude.com/docs/en/desktop-scheduled-tasks.md` | documentation |
| Anthropic APK download requires sign-in | HTTP 403 / redirect to `claude.ai/login` | observed |
| Anthropic's Windows build is native (not the 2024 Electron wrapper) | PE header analysis + vendor docs | observed + documented |
