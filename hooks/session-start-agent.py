#!/usr/bin/env python3
"""Claude SessionStart wrapper for the akmon active-agent reminder.

The reminder logic lives in ``hook_core.py`` and returns a vendor-neutral ``HookResult``.
This entrypoint only adapts Claude Code's JSON payload/output shape so existing
``.claude/settings.json`` wiring can keep pointing here.
"""

from __future__ import annotations

import os
from pathlib import Path

from claude_adapter import load_payload, run_guarded
from hook_core import HookResult, session_start_result


def _project_root(payload: dict) -> Path:
    cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return Path(cwd)


def _decide() -> HookResult | None:
    return session_start_result(_project_root(load_payload()))


def main() -> int:
    # Never block session start: a crash is reported (stderr + the owner's notice), exit 0.
    return run_guarded("session-start-agent", _decide)


if __name__ == "__main__":
    raise SystemExit(main())
