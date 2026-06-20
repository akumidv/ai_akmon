#!/usr/bin/env python3
"""SessionStart hook — prompt the agent to declare which keystone agent it operates as.

Vendor-neutral, stdlib-only, no project imports — runs unchanged in any repo. It injects a
short reminder at session start: the active agent is chosen per task, so the model must
declare its role before doing work and restate it on every switch. It also surfaces the
project's actual agent roster (scanned, not hardcoded) and the "read _forge/memory/ at
session start" rule.

This is the executable side of the "Role declaration" convention in
``_forge/keystone/roles/README.md``. Wired for Claude Code as a SessionStart hook in
``.claude/settings.json``; see ``hooks/README.md``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _project_root() -> Path:
    """Best-effort project root: hook stdin ``cwd`` → ``CLAUDE_PROJECT_DIR`` → process cwd."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}
    cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return Path(cwd)


def _agent_names(directory: Path) -> list[str]:
    """Sorted sub-directory names that look like agents (have a README.md)."""
    if not directory.is_dir():
        return []
    return sorted(
        d.name
        for d in directory.iterdir()
        if d.is_dir() and not d.name.startswith(".") and (d / "README.md").is_file()
    )


def _build_message(root: Path) -> str | None:
    dev = _agent_names(root / "_forge" / "agents")
    desk = _agent_names(root / "agents")
    if not dev and not desk:
        return None  # not a keystone project — stay silent

    lines = [
        "[keystone] Active-agent declaration",
        "Before doing project work, state which agent you are operating as, and restate it "
        "whenever you switch. Format: `\U0001f9ed agent: <name> — <focus>`.",
    ]
    if dev:
        lines.append(f"- DEVELOP (build the project): {', '.join(dev)}")
    if desk:
        lines.append(f"- OPERATE (run on the market): {', '.join(desk)}")
    lines.append("No agent is active yet — pick the one the task calls for; if unclear, ask.")
    lines.append("Also: read `_forge/memory/` at session start (project memory).")
    return "\n".join(lines)


def main() -> int:
    try:
        message = _build_message(_project_root())
    except Exception:
        return 0  # never break a session over the reminder
    if not message:
        return 0
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": message,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
