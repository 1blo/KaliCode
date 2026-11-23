"""Smoke test: agent loop + tools + skills, no network needed for registry checks."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kali.agent import Agent
from kali.config import AgentConfig


def make_agent(**kw) -> Agent:
    kwargs = {"model": "stepfun-ai/step-5-preview",
              "permission_mode": "bypassPermissions", "settings": {}}
    kwargs.update(kw)
    cfg = AgentConfig(**kwargs)
    return Agent(cfg, ui=None)


async def main() -> int:
    failures = []

    # 1. registry
    a = make_agent()
    expected_core = {"Bash", "Read", "Edit", "Write", "Glob", "Grep", "NotebookEdit",
                     "WebFetch", "WebSearch", "TaskCreate", "TaskGet", "TaskList",
                     "TaskUpdate", "Agent", "AskUserQuestion", "EnterPlanMode",
                     "ExitPlanMode", "Skill", "ToolSearch", "TaskStop"}
    missing = expected_core - set(a.tools)
    if missing:
        failures.append(f"registry missing: {missing}")
    print(f"[registry] {len(a.tools)} tools: {', '.join(sorted(a.tools))}")

    # 2. skills loaded
    if not a.skills.skills:
        failures.append("no skills loaded")
    else:
        print(f"[skills] {sorted(a.skills.skills)}")

    # 3. file tools round-trip (uses real tools, no LLM)
    from kali.tools import ToolContext
    ctx = ToolContext(agent=a, cwd=os.getcwd())
    tmp = os.path.join(os.environ.get("TEMP", "."), "kali_smoke.txt")
    write = a.tools["Write"]
    a.read_files.add(tmp)
    r = await write.run({"file_path": tmp, "content": "hello\nworld\n"}, ctx)
    print(f"[write] {r.output} err={r.error}")
    if r.error:
        failures.append("write failed")

    edit = a.tools["Edit"]
    r = await edit.run({"file_path": tmp, "old_string": "world", "new_string": "kali"}, ctx)
    if r.error:
        failures.append(f"edit failed: {r.output}")
    print(f"[edit] {r.output}")

    read = a.tools["Read"]
    r = await read.run({"file_path": tmp}, ctx)
    if "kali" not in r.output:
        failures.append("read content mismatch")
    print(f"[read] {r.output.strip()!r}")

    glob = a.tools["Glob"]
    r = await glob.run({"pattern": "kali/*.py"}, ctx)
    if r.error or "agent.py" not in r.output:
        failures.append(f"glob failed: {r.output[:100]}")
    print(f"[glob] {r.output.splitlines()[0]}")

    grep = a.tools["Grep"]
    r = await grep.run({"pattern": "class Agent", "path": "kali", "output_mode": "content"}, ctx)
    if r.error or "class Agent" not in r.output:
        failures.append(f"grep failed: {r.output[:200]}")
    print(f"[grep] {r.output.splitlines()[0]}")

    bash = a.tools["Bash"]
    r = await bash.run({"command": "echo KALI_BASH_OK"}, ctx)
    if "KALI_BASH_OK" not in r.output:
        failures.append(f"bash failed: {r.output}")
    print(f"[bash] {r.output.strip()}")

    # 4. Task* tools
    tc = a.tools["TaskCreate"]
    r = await tc.run({"subject": "write tests", "description": "unit tests"}, ctx)
    print(f"[taskcreate] {r.output[:120]}")
    r = await a.tools["TaskList"].run({}, ctx)
    print(f"[tasklist] {r.output[:200]}")

    # 5. plan mode gating
    a2 = make_agent(permission_mode="plan")
    ctx2 = ToolContext(agent=a2, cwd=os.getcwd())
    d = a2.permissions.check("Write", {"file_path": "x"}, a2.tools["Write"])
    if d.behavior != "deny":
        failures.append(f"plan mode allowed Write: {d}")
    d2 = a2.permissions.check("Bash", {"command": "git status"}, a2.tools["Bash"])
    if d2.behavior != "allow":
        failures.append(f"plan mode blocked read-only bash: {d2}")
    d3 = a2.permissions.check("Bash", {"command": "rm -rf /"}, a2.tools["Bash"])
    if d3.behavior != "deny":
        failures.append(f"plan mode allowed destructive bash: {d3}")
    print(f"[plan mode] write={d.behavior} git-status={d2.behavior} rm={d3.behavior}")

    # 6. system prompt builds
    sp = a.build_system()
    for token in ("Kali Code", "ToolSearch", "# Tools"):
        if token not in sp:
            failures.append(f"system prompt missing {token!r}")
    print(f"[system prompt] {len(sp):,} chars")

    os.unlink(tmp)
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nALL SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
