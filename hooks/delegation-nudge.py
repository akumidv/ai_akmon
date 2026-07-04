#!/usr/bin/env python3
"""Claude PreToolUse wrapper for the keystone delegation nudge.

Counts consecutive orchestrator edit/shell calls since session start or the last subagent
delegation (``Task``/``Agent`` resets the counter and re-arms the reminder) and, past the
threshold, injects a soft reminder — once per drift episode — that the work may belong to
a ``k-*`` delegate (MODEL.md § Capability tiers). Advisory only — nothing is ever blocked.
The decision logic lives in ``hook_core.py``; this entrypoint only adapts Claude Code's
payload.
"""

from __future__ import annotations

import sys

from claude_adapter import load_payload, normalize_tool, print_result
from hook_core import SHELL_TOOL, SUBAGENT_TOOL, delegation_nudge_result

# Claude tool names → the neutral kinds hook_core expects (edit tools via normalize_tool).
_TOOL_KINDS = {"Bash": SHELL_TOOL, "Task": SUBAGENT_TOOL, "Agent": SUBAGENT_TOOL}


def main() -> int:
    # Never block a tool call: on any failure, log to stderr and exit cleanly.
    try:
        payload = load_payload()
        name = str(payload.get("tool_name") or "")
        kind = _TOOL_KINDS.get(name) or normalize_tool(name)
        session_id = payload.get("session_id")
        print_result(delegation_nudge_result(kind, session_id if isinstance(session_id, str) else None))
    except Exception as exc:
        print(f"keystone delegation-nudge hook: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
