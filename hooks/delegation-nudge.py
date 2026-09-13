#!/usr/bin/env python3
"""Claude PreToolUse wrapper for the akmon delegation nudge.

Scores orchestrator edit/shell/read calls since session start or the last subagent delegation
(``Task``/``Agent`` resets the score and re-arms the reminder) — an edit or shell call counts
1, a read ½, the first calls of a stretch nothing (C88/D2-46) — and, past the threshold,
injects a soft reminder — once per drift episode — that the work may belong to a ``k_*``
delegate (MODEL.md § Capability tiers). Below the ask threshold, advisory only — nothing is
blocked; past it, the next edit or shell call (never a read) carries a hard ``ask``, which
escalates to ``deny`` outside the interactive default permission mode (C31/D2-10 — an
unattended ``ask`` was observed to be a silent no-op). This fires only for main-chain calls: a
subagent call (detected via the payload's ``agent_id``, present only inside a subagent) is
exempt, since Claude Code shares the ``session_id`` between the main chain and its subagents
and a k_* delegate has no ``Task`` tool to act on the nudge anyway. The decision logic lives
in ``hook_core.py``; this entrypoint only adapts Claude Code's payload.
"""

from __future__ import annotations

from claude_adapter import load_payload, normalize_tool, run_guarded
from hook_core import SHELL_TOOL, SUBAGENT_TOOL, HookResult, delegation_nudge_result

# Claude tool names → the neutral kinds hook_core expects (edit tools via normalize_tool).
_TOOL_KINDS = {"Bash": SHELL_TOOL, "Task": SUBAGENT_TOOL, "Agent": SUBAGENT_TOOL}


def _decide() -> HookResult | None:
    payload = load_payload()
    name = str(payload.get("tool_name") or "")
    kind = _TOOL_KINDS.get(name) or normalize_tool(name)
    session_id = payload.get("session_id")
    is_subagent = bool(payload.get("agent_id"))
    sid = session_id if isinstance(session_id, str) else None
    permission_mode = payload.get("permission_mode")
    return delegation_nudge_result(
        kind,
        sid,
        is_subagent=is_subagent,
        permission_mode=permission_mode if isinstance(permission_mode, str) else None,
    )


def main() -> int:
    """Entry point: score delegation drift and nudge or ask, never blocking outright."""
    # Never block a tool call: a crash is reported (stderr + the owner's notice), exit 0.
    return run_guarded("delegation-nudge", _decide)


if __name__ == "__main__":
    raise SystemExit(main())
