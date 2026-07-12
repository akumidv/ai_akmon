#!/usr/bin/env python3
"""Run akmon's self-checks against a synthetic consuming-project fixture."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

AGENTS_MD = """# AGENTS.md

## Dev layer — akmon

Model: `_aitna/akmon/README.md`. Archetype: `ARCHETYPES.md`. Roles:
`_aitna/akmon/roles/`. Read `_aitna/memory` at session start.

Prime directives D2 and D5 are always-on. Secrets come from `.env`.
Skills live in `_aitna/skills/` and root `skills/`; generated vendor skill stubs are pointers only.

**Delegation is the default.** For every non-trivial task, delegate independent mechanical
substeps without waiting for an owner prompt; the orchestrator keeps decomposition, routing,
synthesis, and owner dialogue.
"""


CI_YML = """name: CI
on: [push]
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - run: python3 _aitna/akmon/bin/sync.py --check
      - run: python3 _aitna/akmon/bin/verify.py --strict
"""


SKILL_MD = """---
name: demo
description: Demonstrates the akmon skill contract.
when_to_use: Use for akmon self-CI fixture coverage.
owner: akmon
---

# demo
"""


def _write(path: Path, text: str = "x\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_fixture(root: Path, akmon_root: Path) -> None:
    _write(root / "AGENTS.md", AGENTS_MD)
    _write(root / "_aitna" / "TASKS.md", "# Tasks\n\n- T1 · demo · active · engineer · keep fixture valid\n")
    _write(root / "_aitna" / "agents" / "engineer" / "README.md", "See `_aitna/akmon/roles/engineer.md`.\n")
    _write(root / "_aitna" / "akmon" / "skills" / "demo" / "SKILL.md", SKILL_MD)
    _write(root / "_aitna" / "memory" / "note.md", "fact\n")
    _write(root / "_aitna" / "memory" / "README.md", "# Memory\n- note.md\n")
    _write(root / ".gitignore", "*.env\n!*.env.example\n")
    _write(root / "_aitna" / "akmon" / ".gitignore", "__pycache__/\n*.env\n!*.env.example\n")
    _write(root / ".github" / "workflows" / "ci.yml", CI_YML)

    for relative in (
        "README.md",
        "BOOTSTRAP.md",
        "ARCHETYPES.md",
        "CHANGELOG.md",
        "MODEL.md",
        "roles/README.md",
        "roles/review.md",
        "roles/architect.md",
        "roles/engineer.md",
        "roles/learn.md",
        "roles/release.md",
        "guardrails/_common.md",
        "pipelines/pre-commit.md",
        "pipelines/code-flow.md",
        "pipelines/design-flow.md",
        "pipelines/release.md",
        "pipelines/tasks.md",
        "bin/sync.py",
        "bin/verify.py",
        "hooks/hook_core.py",
        "hooks/claude_adapter.py",
        "hooks/codex_adapter.py",
        "hooks/codex-hook.py",
        "hooks/git-commit-guard.py",
        "hooks/session-start-agent.py",
        "hooks/role-on-code.py",
        "hooks/analysis-guard.py",
        "hooks/model-routing.py",
        "hooks/delegation-log.py",
        "tools/model_routing/registry.json",
        "tools/model_routing/routing.py",
        "tools/model_routing/init.py",
        "tools/model_routing/second_opinion.py",
    ):
        source = akmon_root / relative
        text = source.read_text(encoding="utf-8") if source.is_file() else "fixture placeholder\n"
        _write(root / "_aitna" / "akmon" / relative, text)


def _installed_wheel_smoke(akmon_root: Path, tmp_root: Path) -> None:
    dist = tmp_root / "dist"
    venv = tmp_root / "venv"
    fixture = tmp_root / "package-consumer"
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(dist)], cwd=akmon_root, check=True)
    wheel = next(dist.glob("akmon-*.whl"))
    subprocess.run(["uv", "venv", str(venv)], check=True)
    python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    akmon = venv / ("Scripts/akmon.exe" if sys.platform == "win32" else "bin/akmon")
    subprocess.run(["uv", "pip", "install", "--python", str(python), str(wheel)], check=True)

    _write(
        fixture / "AGENTS.md",
        "# AGENTS.md\n\n## Dev layer — akmon\n\n"
        "Read `akmon path`. Archetype: `ARCHETYPES.md`. Read `_aitna/memory` at session start.\n\n"
        "@_aitna/.akmon/guardrails/_common.md\n\n"
        "Prime directives D2 and D5 are always-on. Secrets come from `.env`.\n"
        "Delegation is the default.\n",
    )
    _write(fixture / "_aitna" / ".akmon.toml", 'mount = "package"\n')
    _write(fixture / "_aitna" / "agents" / "review" / "README.md", "# Review\n")
    subprocess.run([str(akmon), "sync"], cwd=fixture, check=True, capture_output=True, text=True)

    nested = fixture / "src" / "package"
    nested.mkdir(parents=True)
    completed = subprocess.run(
        [str(python), str(fixture / "_aitna" / ".akmon" / "hooks" / "codex-hook.py"), "session-start"],
        input=json.dumps({"cwd": str(nested)}),
        check=True,
        capture_output=True,
        text=True,
    )
    output = json.loads(completed.stdout)
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "DEVELOP (build the project): review" in context
    assert "Delegation is the default for non-atomic work" in context


def main() -> int:
    akmon_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="akmon-self-ci-") as tmp:
        fixture = Path(tmp)
        _make_fixture(fixture, akmon_root)
        commands = (
            [sys.executable, str(akmon_root / "bin" / "sync.py"), "--project-root", str(fixture)],
            [
                sys.executable,
                str(akmon_root / "bin" / "sync.py"),
                "--project-root",
                str(fixture),
                "--check",
            ],
            [
                sys.executable,
                str(akmon_root / "bin" / "verify.py"),
                "--project-root",
                str(fixture),
                "--strict",
                "--quiet",
            ],
        )
        for command in commands:
            subprocess.run(command, check=True)
        _installed_wheel_smoke(akmon_root, fixture / "wheel-smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
