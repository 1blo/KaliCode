---
name: project-init
description: Analyze an unfamiliar codebase and write a concise KALI.md memory file with build/test commands, architecture and conventions. Use when the user asks to "initialize", "onboard", or wants the project documented for future sessions.
allowed-tools: Read, Glob, Grep, Bash, Write, TaskCreate, TaskUpdate
---

# Project initialization

Create a KALI.md at the project root so future sessions start with context.

Steps:
1. Explore the repo: package manifests (`package.json`, `pyproject.toml`, `Cargo.toml`, `*.csproj`), READMEs, CI configs, Makefiles.
2. Identify: build command, lint command, test command (especially "run a single test"), dev-server command.
3. Note architecture: entry points, main modules, framework, language(s).
4. Write KALI.md (max ~60 lines) with sections: Commands, Architecture, Conventions.
5. Do not invent commands - only document what you verified in manifests/CI.

Keep it factual. If a command cannot be verified, omit it rather than guessing.
