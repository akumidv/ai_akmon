#!/usr/bin/env python3
"""Claude PreToolUse wrapper for the akmon commit guard and the shell-route diagnostic.

The guardrail logic lives in ``hook_core.py`` and returns a vendor-neutral ``HookResult``.
This entrypoint only adapts Claude Code's JSON payload/output shape so existing
``.claude/settings.json`` wiring can keep pointing here.

It also carries the unclassified-shell-route diagnostic (C49, owner decision at D2-19 e).
The blind spot it reports is not Codex-specific — Claude's advisories sit on the edit tools,
so a write that reaches the filesystem through ``Bash`` was unreported here while Codex at
least said the route may mutate files unseen. This is the hook Claude already runs on every
``Bash`` call, so the diagnostic costs no additional process on the hottest tool.
"""

from __future__ import annotations

from claude_adapter import load_payload, run_guarded
from hook_core import (
    HookResult,
    git_commit_guard_result,
    privilege_escalation_guard_result,
    report_unclassified_shell_route,
)


def _decide() -> HookResult | None:
    payload = load_payload()
    if payload.get("tool_name") != "Bash":
        return None
    session_id = payload.get("session_id")
    report_unclassified_shell_route(session_id if isinstance(session_id, str) else None)
    command = (payload.get("tool_input") or {}).get("command", "") or ""
    permission_mode = payload.get("permission_mode")
    return privilege_escalation_guard_result(command) or git_commit_guard_result(
        command, permission_mode=permission_mode if isinstance(permission_mode, str) else None
    )


def main() -> int:
    # Deny-class, and still crash-open (ADR 0013 F3): a crash lets the command through and says so.
    return run_guarded("git-commit-guard", _decide)


if __name__ == "__main__":
    raise SystemExit(main())
