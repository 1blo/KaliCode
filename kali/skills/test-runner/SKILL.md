---
name: test-runner
description: Run the smallest relevant test suite for a change and interpret failures. Use when verifying an edit, or when the user asks to run tests.
---

# Test runner

1. Detect the runner: pytest/vitest/jest/go test/cargo test/dotnet test/unity test-runner.
2. Run the MOST SPECIFIC scope that covers the changed files (single test file first, then module, then suite).
3. On failure: read the failure output carefully; re-run only the failing tests while iterating.
4. Classify failures: regression from the change vs. pre-existing vs. flaky (re-run flaky candidates once).
5. Report: what passed, what failed, and the exact failing assertion - no vague summaries.
