#!/usr/bin/env python3
"""Run keystone's self-checks against a synthetic consuming-project fixture."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

AGENTS_MD = """# AGENTS.md

## Dev layer — keystone

Model: `_forge/keystone/README.md`. Archetype: `ARCHETYPES.md`. Roles:
`_forge/keystone/roles/`. Read `_forge/memory` at session start.

Prime directives D2 and D5 are always-on. Secrets come from `.env`.
Skills live in `_forge/skills/` and root `skills/`; generated vendor skill stubs are pointers only.
"""


CI_YML = """name: CI
on: [push]
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - run: python3 _forge/keystone/bin/sync.py --check
      - run: python3 _forge/keystone/bin/verify.py --strict
"""


SKILL_MD = """---
name: demo
description: Demonstrates the keystone skill contract.
when_to_use: Use for keystone self-CI fixture coverage.
owner: keystone
---

# demo
"""


def _write(path: Path, text: str = "x\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_fixture(root: Path, keystone_root: Path) -> None:
    _write(root / "AGENTS.md", AGENTS_MD)
    _write(root / "_forge" / "TASKS.md", "# Tasks\n\n- T1 · demo · active · engineer · keep fixture valid\n")
    _write(root / "_forge" / "agents" / "engineer" / "README.md", "See `_forge/keystone/roles/engineer.md`.\n")
    _write(root / "_forge" / "keystone" / "skills" / "demo" / "SKILL.md", SKILL_MD)
    _write(root / "_forge" / "memory" / "note.md", "fact\n")
    _write(root / "_forge" / "memory" / "README.md", "# Memory\n- note.md\n")
    _write(root / ".gitignore", "*.env\n!*.env.example\n")
    _write(root / "_forge" / "keystone" / ".gitignore", "__pycache__/\n*.env\n!*.env.example\n")
    _write(root / ".github" / "workflows" / "ci.yml", CI_YML)

    for relative in (
        "README.md",
        "BOOTSTRAP.md",
        "ARCHETYPES.md",
        "CHANGELOG.md",
        "MODEL.md",
        "roles/README.md",
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
    ):
        source = keystone_root / relative
        text = source.read_text(encoding="utf-8") if source.is_file() else "fixture placeholder\n"
        _write(root / "_forge" / "keystone" / relative, text)


def main() -> int:
    keystone_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="keystone-self-ci-") as tmp:
        fixture = Path(tmp)
        _make_fixture(fixture, keystone_root)
        commands = (
            [sys.executable, str(keystone_root / "bin" / "sync.py"), "--project-root", str(fixture)],
            [
                sys.executable,
                str(keystone_root / "bin" / "sync.py"),
                "--project-root",
                str(fixture),
                "--check",
            ],
            [
                sys.executable,
                str(keystone_root / "bin" / "verify.py"),
                "--project-root",
                str(fixture),
                "--strict",
                "--quiet",
            ],
        )
        for command in commands:
            subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
