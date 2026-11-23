---
name: commit
description: Create a clean git commit from staged/unstaged changes with a convention-following message. Use when the user asks to commit.
allowed-tools: Bash, Read, Grep, Glob, TaskCreate, TaskUpdate
---

# Git commit workflow

1. Run `git status` and `git diff` (staged + unstaged) and recent `git log` for message style.
2. Analyze ALL changes (staged, unstaged, untracked). Draft a message:
   - Conventional Commits if history shows them (`feat:`, `fix:`, ...), else match repo style.
   - Subject <= 72 chars, imperative mood, no "generated" or "AI" mentions.
   - Body bullet points explaining the WHY when non-obvious.
3. Stage ONLY the files relevant to the logical change (never `git add -A` blindly; never commit .env or secrets).
4. Commit with a heredoc for the message.
5. NEVER push, never amend history, never change git config.

If the user asks to push, confirm the remote first with `git remote -v`.
