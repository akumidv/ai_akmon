#!/usr/bin/env python3
"""Claude PreToolUse wrapper for the akmon D2 ledger reminder.

Reminds once per session when an edit lands on a project-declared D2-sensitive path
(``[d2_ledger] sensitive_paths`` in ``<aitna>/.akmon.toml``) so the change gets logged in the
ledger for owner verification (design meta/design/d2-ledger.md §2.2, phase 2 of C11). The decision
logic lives in ``hook_core.py``; this entrypoint only adapts Claude Code's payload. Advisory only —
a failure is reported (stderr + the owner's notice) and never blocks the edit.
"""

from __future__ import annotations

from claude_adapter import load_payload, normalize_tool, project_root, run_guarded
from hook_core import HookResult, d2_ledger_reminder_result


def _decide() -> HookResult | None:
    payload = load_payload()
    tool_input = payload.get("tool_input") or {}
    session_id = payload.get("session_id")
    return d2_ledger_reminder_result(
        normalize_tool(str(payload.get("tool_name") or "")),
        tool_input.get("file_path"),
        session_id if isinstance(session_id, str) else None,
        project_root(payload),
    )


def main() -> int:
    """Entry point: emit the D2 ledger reminder."""
    return run_guarded("d2-ledger-reminder", _decide)


if __name__ == "__main__":
    raise SystemExit(main())
