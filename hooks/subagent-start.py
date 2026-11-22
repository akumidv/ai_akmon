#!/usr/bin/env python3
"""Claude SubagentStart wrapper: the unattended layer for the delegate that is starting (A49).

A delegate is read only by the head session that launched it, so it needs the rules for working without
an owner (``rules/unattended.md``), not the owner-dialogue rules the head gets at SessionStart. The
``additionalContext`` of a ``SubagentStart`` hook reaches the subagent (M247). The text comes from
``hook_core.py``; this entrypoint only adapts Claude Code's JSON payload/output shape.
"""

from __future__ import annotations

from claude_adapter import load_payload, project_root, run_guarded
from hook_core import HookResult, subagent_start_result


def _decide() -> HookResult | None:
    return subagent_start_result(project_root(load_payload()))


def main() -> int:
    """Entry point: emit the unattended layer, never blocking the subagent's start."""
    return run_guarded("subagent-start", _decide)


if __name__ == "__main__":
    raise SystemExit(main())
