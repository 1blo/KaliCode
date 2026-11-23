"""Bash and TaskStop - Claude Code 2.1.x shell toolset, Windows-aware.

Background output model (matches Claude Code v2.1.277+): a background command
tees its output to a file under <tempdir>/kali-tasks/<shell_id>.output which
the model reads with Read. BashOutput/TaskOutput are gone; KillShell became
TaskStop (which keeps the deprecated shell_id param).
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import time

from .base import Tool, ToolResult, ToolContext, STR, INT, BOOL, _s

MAX_OUTPUT = 30000


def _default_shell() -> str:
    return os.environ.get("KALI_SHELL", "powershell") if os.name == "nt" else "bash"


class Bash(Tool):
    name = "Bash"
    # Verbatim from the Sonnet 4.6 CLI leak (spec section 2.1), including the
    # built-in git commit / PR instructions.
    description = """Executes a given bash command and returns its output.

`cd` carries to the next call only in the main session, if the command succeeds and ends inside the working directories. Outside them the shell returns to the start folder; otherwise it stays where it was. Shell state does not persist. The shell environment is initialized from the user's profile (bash or zsh).

IMPORTANT: Avoid using this tool to run `cat`, `head`, `tail`, `sed`, `awk`, or `echo` commands, unless explicitly instructed or after you have verified that a dedicated tool cannot accomplish your task. Instead, use the appropriate dedicated tool as this will provide a much better experience for the user:

 - Read files: Use Read (NOT cat/head/tail)
 - Edit files: Use Edit (NOT sed/awk)
 - Write files: Use Write (NOT echo >/cat <<EOF)
 - Communication: Output text directly (NOT echo/printf)

While the Bash tool can do similar things, it's better to use the built-in tools as they provide a better user experience and make it easier to review tool calls and give permission.

### Instructions
 - If your command will create new directories or files, first use this tool to run `ls` to verify the parent directory exists and is the correct location.
 - Always quote file paths that contain spaces with double quotes in your command (e.g., cd "path with spaces/file.txt")
 - Try to maintain your current working directory throughout the session by using absolute paths and avoiding usage of `cd`. You may use `cd` if the User explicitly requests it. In particular, never prepend `cd <current-directory>` to a `git` command - `git` already operates on the current working tree, and the compound triggers a permission prompt.
 - You may specify an optional timeout in milliseconds (up to 600000ms / 10 minutes for a foreground command). By default, your command will timeout after 120000ms (2 minutes).
 - You can use the `run_in_background` parameter to run the command in the background. Only use this if you don't need the result immediately and are OK being notified when the command completes later. You do not need to check the output right away - you'll be notified when it finishes. You do not need to use '&' at the end of the command when using this parameter.
 - For git commands:
  - Prefer to create a new commit rather than amending an existing commit.
  - Before running destructive operations (e.g., git reset --hard, git push --force, git checkout --), consider whether there is a safer alternative that achieves the same goal. Only use destructive operations when they are truly the best approach.
  - Never skip hooks (--no-verify) or bypass signing (--no-gpg-sign, -c commit.gpgsign=false) unless the user has explicitly asked for it. If a hook fails, investigate and fix the underlying issue.
 - Avoid unnecessary `sleep` commands:
  - Do not sleep between commands that can run immediately - just run them.
  - If your command is long running and you would like to be notified when it finishes - use `run_in_background`. No sleep needed.
  - Do not retry failing commands in a sleep loop - diagnose the root cause.
  - If waiting for a background task you started with `run_in_background`, you will be notified when it completes - do not poll.
 - When running `find`, search from `.` (or a specific path), not `/` - scanning the full filesystem can exhaust system resources on large trees.
 - When using `find -regex` with alternation, put the longest alternative first. Example: use `'.*\\(tsx\\|ts\\)'` not `'.*\\(ts\\|tsx\\)'` - the second form silently skips `.tsx` files.

### Committing changes with git

Only create commits when requested by the user. If unclear, ask first. When the user asks you to create a new git commit, follow these steps carefully:

You can call multiple tools in a single response. When multiple independent pieces of information are requested and all commands are likely to succeed, run multiple tool calls in parallel for optimal performance. The numbered steps below indicate which commands should be batched in parallel.

Git Safety Protocol:
- NEVER update the git config
- NEVER run destructive git commands (push --force, reset --hard, checkout ., restore ., clean -f, branch -D) unless the user explicitly requests these actions. Taking unauthorized destructive actions is unhelpful and can result in lost work, so it's best to ONLY run these commands when given direct instructions
- NEVER skip hooks (--no-verify, --no-gpg-sign, etc) unless the user explicitly requests it
- NEVER run force push to main/master, warn the user if they request it
- CRITICAL: Always create NEW commits rather than amending, unless the user explicitly requests a git amend. When a pre-commit hook fails, the commit did NOT happen - so --amend would modify the PREVIOUS commit, which may result in destroying work or losing previous changes. Instead, after hook failure, fix the issue, re-stage, and create a NEW commit
- When staging files, prefer adding specific files by name rather than using "git add -A" or "git add .", which can accidentally include sensitive files (.env, credentials) or large binaries
- NEVER commit changes unless the user explicitly asks you to. It is VERY IMPORTANT to only commit when explicitly asked, otherwise the user will feel that you are being too proactive

1. Run the following bash commands in parallel, each using the Bash tool:
  - Run a git status command to see all untracked files. IMPORTANT: Never use the -uall flag as it can cause memory issues on large repos.
  - Run a git diff command to see both staged and unstaged changes that will be committed.
  - Run a git log command to see recent commit messages, so that you can follow this repository's commit message style.
2. Analyze all staged changes (both previously staged and newly added) and draft a commit message:
  - Summarize the nature of the changes (eg. new feature, enhancement to an existing feature, bug fix, refactoring, test, docs, etc.). Ensure the message accurately reflects the changes and their purpose (i.e. "add" means a wholly new feature, "update" means an enhancement to an existing feature, "fix" means a bug fix, etc.).
  - Do not commit files that likely contain secrets (.env, credentials.json, .kali/settings.local.json, etc). Warn the user if they specifically request to commit those files
  - Draft a concise (1-2 sentences) commit message that focuses on the "why" rather than the "what"
  - Ensure it accurately reflects the changes and their purpose
3. Run the following commands in parallel:
   - Add relevant untracked files to the staging area.
   - Create the commit with a message, ending with the attribution lines given in the conversation's system-reminder, when one is present.
   - Run git status after the commit completes to verify success.
   Note: git status depends on the commit completing, so run it sequentially after the commit.
4. If the commit fails due to pre-commit hook: fix the issue and create a NEW commit

Important notes:
- NEVER run additional commands to read or explore code, besides git bash commands
- NEVER use the TaskCreate or Agent tools
- DO NOT push to the remote repository unless the user explicitly asks you to do so
- IMPORTANT: Never use git commands with the -i flag (like git rebase -i or git add -i) since they require interactive input which is not supported.
- IMPORTANT: Do not use --no-edit with git rebase commands, as the --no-edit flag is not a valid option for git rebase.
- If there are no changes to commit (i.e., no untracked files and no modifications), do not create an empty commit
- In order to ensure good formatting, ALWAYS pass the commit message via a HEREDOC, a la this example:

```xml
<example>
git commit -m "$(cat <<'EOF'
   Commit message here.
   EOF
   )"
</example>
```

### Creating pull requests
Use the gh command via the Bash tool for ALL GitHub-related tasks including working with issues, pull requests, checks, and releases. If given a Github URL use the gh command to get the information needed.

GitHub notifies the owner of any `@name` written in a PR, issue, or comment. Write a bare `@name` only for a real login you mean to notify. Put roles, placeholders, and code (`@human`, `@reviewer`, `@types/node`) in backticks or drop the `@`, even when copied from project files.

IMPORTANT: When the user asks you to create a pull request, follow these steps carefully:

1. Run the following bash commands in parallel using the Bash tool, in order to understand the current state of the branch since it diverged from the main branch:
   - Run a git status command to see all untracked files (never use -uall flag)
   - Run a git diff command to see both staged and unstaged changes that will be committed
   - Check if the current branch tracks a remote branch and is up to date with the remote, so you know if you need to push to the remote
   - Run a git log command and `git diff [base-branch]...HEAD` to understand the full commit history for the current branch (from the time it diverged from the base branch)
2. Analyze all changes that will be included in the pull request, making sure to look at all relevant commits (NOT just the latest commit, but ALL commits that will be included in the pull request!!!), and draft a pull request title and summary:
   - Keep the PR title short (under 70 characters)
   - Use the description/body for details, not the title
3. Run the following commands in parallel:
   - Create new branch if needed
   - Push to remote with -u flag if needed
   - Create PR using gh pr create with the format below. Use a HEREDOC to pass the body to ensure correct formatting. End the body with the attribution lines given in the conversation's system-reminder, when one is present.
```xml
<example>
gh pr create --title "the pr title" --body "$(cat <<'EOF'
#### Summary
<1-3 bullet points>

#### Test plan
[Bulleted markdown checklist of TODOs for testing the pull request...]
EOF
)"
</example>
```

Important:
- DO NOT use the TaskCreate or Agent tools
- Return the PR URL when you're done, so the user can see it

### Other common operations
- View comments on a Github PR: gh api repos/foo/bar/pulls/123/comments"""
    schema = _s(
        {
            "command": {**STR, "description": "The command to execute"},
            "timeout": {**INT, "description": "Optional timeout in milliseconds (max 600000 for a foreground command)"},
            "description": {
                **STR,
                "description": (
                    "Clear, concise description of what this command does in active voice. Never use words like \"complex\" or \"risk\" in the description - just describe what it does.\n\n"
                    "Say what the command does in plain words: do not echo the command's text, its flags, or file paths - the user reads this description, often without seeing the command.\n\n"
                    "For simple commands (git, npm, standard CLI tools), keep it brief (5-10 words):\n"
                    "- ls -> \"List files in current directory\"\n"
                    "- git status -> \"Show working tree status\"\n"
                    "- npm install -> \"Install package dependencies\"\n\n"
                    "For commands that are harder to parse at a glance (piped commands, obscure flags, etc.), add enough context to clarify what it does:\n"
                    "- find . -name \"*.tmp\" -exec rm {} \\; -> \"Find and delete all .tmp files recursively\"\n"
                    "- git reset --hard origin/main -> \"Discard all local changes and match remote main\"\n"
                    "- curl -s url | jq '.data[]' -> \"Fetch JSON from URL and extract data array elements\""
                ),
            },
            "run_in_background": {**BOOL, "description": "Set to true to run this command in the background."},
            "dangerouslyDisableSandbox": {**BOOL, "description": "Set this to true to dangerously override sandbox mode and run commands without sandboxing."},
        },
        required=["command"],
    )

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        command = str(args.get("command", "")).strip()
        if not command:
            return ToolResult("Error: empty command", error=True)
        timeout_ms = min(int(args.get("timeout") or 120000), 600000)
        background = bool(args.get("run_in_background"))
        # dangerouslyDisableSandbox: accepted and ignored - this build has no
        # sandbox, commands always run unsandboxed.

        if background:
            shell_id = await ctx.agent.start_background_shell(command, ctx.cwd)
            out_file = ctx.agent.background_output_file(shell_id)
            return ToolResult(
                f"Background task started: {shell_id}\n"
                f"Output file: {out_file}\n"
                f"You will be notified when it completes; read the output file with Read to check progress."
            )
        return await self._run_foreground(command, timeout_ms, ctx)

    async def _run_foreground(self, command: str, timeout_ms: int, ctx: ToolContext) -> ToolResult:
        started = time.time()
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=ctx.cwd or None,
                env={**os.environ, "KALICODE": "1"},
            )
            try:
                out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_ms / 1000)
                timed_out = False
            except asyncio.TimeoutError:
                proc.kill()
                out, err = await proc.communicate()
                timed_out = True
        except NotImplementedError:  # Windows event-loop quirk fallback
            return await asyncio.get_running_loop().run_in_executor(
                None, self._sync_run, command, timeout_ms / 1000, ctx
            )

        stdout = out.decode("utf-8", "replace") if out else ""
        stderr = err.decode("utf-8", "replace") if err else ""
        code = proc.returncode if proc.returncode is not None else -1
        elapsed = time.time() - started

        parts = []
        if stdout.strip():
            parts.append(_clip(stdout))
        if stderr.strip():
            parts.append(_clip(stderr))
        body = "\n".join(parts) or "(no output)"

        if timed_out:
            return ToolResult(f"Command timed out after {timeout_ms}ms\n{body}", error=True)
        if code != 0:
            return ToolResult(f"Exit code {code}\n{body}", error=True)
        return ToolResult(body)

    def _sync_run(self, command: str, timeout_s: float, ctx: ToolContext) -> ToolResult:
        try:
            proc = subprocess.run(
                command, shell=True, capture_output=True, timeout=timeout_s,
                cwd=ctx.cwd or None,
                env={**os.environ, "KALICODE": "1"},
            )
        except subprocess.TimeoutExpired:
            return ToolResult(f"Command timed out after {int(timeout_s * 1000)}ms", error=True)
        stdout = (proc.stdout or b"").decode("utf-8", "replace")
        stderr = (proc.stderr or b"").decode("utf-8", "replace")
        parts = [p for p in (_clip(stdout), _clip(stderr)) if p.strip()]
        body = "\n".join(parts) or "(no output)"
        if proc.returncode != 0:
            return ToolResult(f"Exit code {proc.returncode}\n{body}", error=True)
        return ToolResult(body)


def _clip(text: str, limit: int = MAX_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + f"\n... [{len(text) - limit} chars truncated] ...\n" + text[-half:]


class TaskStop(Tool):
    """Verbatim description/schema from the spec (section 2.1). KillShell was
    renamed TaskStop in 2.1.x; the deprecated KillShell-era `shell_id` param is
    kept and both task_id/shell_id map to the background shell id."""
    name = "TaskStop"
    description = """- Stops a running background task by its ID
- Takes a task_id parameter identifying the task to stop
- To stop an agent-team teammate, pass its agent ID or bare teammate name as task_id
- To stop a background agent spawned with a name, pass that name as task_id
- Returns a success or failure status
- Use this tool when you need to terminate a long-running task"""
    schema = _s(
        {
            "task_id": {**STR, "description": "The ID of the background task to stop. Agent-team teammates and named background agents are also accepted by agent ID or name."},
            "shell_id": {**STR, "description": "Deprecated: use task_id instead"},
        },
    )

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        task_id = str(args.get("task_id") or args.get("shell_id") or "").strip()
        if not task_id:
            return ToolResult("TaskStop: provide task_id (or the deprecated shell_id)", error=True)
        ok, msg = ctx.agent.kill_background_shell(task_id)
        return ToolResult(msg, error=not ok)
