#!/usr/bin/env python3
"""Claude SessionStart wrapper for the akmon active-agent reminder and the audience's layer.

The reminder logic lives in ``hook_core.py`` and returns a vendor-neutral ``HookResult``.
This entrypoint only adapts Claude Code's JSON payload/output shape so existing
``.claude/settings.json`` wiring can keep pointing here.
"""

from __future__ import annotations

import os
from pathlib import Path

from claude_adapter import load_payload, run_guarded
from hook_core import HookResult, session_layer, session_start_result

from common import audience  # hook_core puts the tree root on sys.path


def _project_root(payload: dict) -> Path:
    cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or str(Path.cwd())
    return Path(cwd)


def _decide() -> HookResult | None:
    payload = load_payload()
    session_id = payload.get("session_id")
    root = _project_root(payload)
    # The environment is read here, once, and passed down. The audience's layer rides on every ``source``:
    # compaction drops what was given only at startup (M246).
    layer = session_layer(root, attended=audience.is_attended(os.environ))
    return session_start_result(root, session_id if isinstance(session_id, str) else None, layer)


def main() -> int:
    """Entry point: emit the active-agent reminder, never blocking session start."""
    # Never block session start: a crash is reported (stderr + the owner's notice), exit 0.
    return run_guarded("session-start-agent", _decide)


if __name__ == "__main__":
    raise SystemExit(main())
