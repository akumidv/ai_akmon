#!/usr/bin/env python3
"""Claude PreToolUse wrapper for the akmon commit guard, the browser class and the shell-route diagnostic.

The guardrail logic lives in ``hook_core.py`` and returns a vendor-neutral ``HookResult``.
This entrypoint only adapts Claude Code's JSON payload/output shape so existing
``.claude/settings.json`` wiring can keep pointing here.

It also carries the browser class of the access matrix (ADR 0032/D07): a ``Bash`` call that runs
``akmon tool browser`` and an MCP call of the ``akmon-browser`` server are denied to a delegated agent (its
payload carries ``agent_id``, M189) and to an autonomous run, for the matrix's ``browser_*`` rows.

It also carries the unclassified-shell-route diagnostic (C49, ADR-0012/D02).
The blind spot it reports is not Codex-specific — Claude's advisories sit on the edit tools,
so a write that reaches the filesystem through ``Bash`` was unreported here while Codex at
least said the route may mutate files unseen. This is the hook Claude already runs on every
``Bash`` call, so the diagnostic costs no additional process on the hottest tool.
"""

from __future__ import annotations

import functools
import os
from typing import Any

from claude_adapter import attended_from_environment, load_payload, run_guarded
from hook_core import (
    HookResult,
    browser_guard_result,
    git_commit_guard_result,
    guard_crash_deny_document,
    privilege_escalation_guard_result,
    report_unclassified_shell_route,
    strictest_result,
)

from common import access_matrix  # hook_core put the tree root on sys.path


def _decide(actor: access_matrix.Actor) -> HookResult | None:
    payload = load_payload()
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str):
        return None
    permission_mode = payload.get("permission_mode")
    mode = permission_mode if isinstance(permission_mode, str) else None
    attended = attended_from_environment(os.environ)
    cwd = payload.get("cwd")
    directory = cwd if isinstance(cwd, str) and cwd else None
    browser = functools.partial(
        browser_guard_result,
        tool_name,
        actor=actor,
        delegated=_is_delegated(payload),
        permission_mode=mode,
        attended=attended,
        directory=directory,
    )
    if tool_name != "Bash":
        # An MCP call of the browser server: the only non-shell call this entry is wired for.
        return browser()
    session_id = payload.get("session_id")
    report_unclassified_shell_route(session_id if isinstance(session_id, str) else None)
    command = (payload.get("tool_input") or {}).get("command", "") or ""
    escalation = privilege_escalation_guard_result(command, directory)
    if escalation is not None:
        return escalation
    # Every guard reads the command and the strictest decision wins: a git ask must not hide a browser deny.
    return strictest_result(
        [
            git_commit_guard_result(
                command,
                permission_mode=mode,
                directory=directory,
                attended=attended,
                actor=actor,
                run_branch=access_matrix.run_branch_from_environment(os.environ),
            ),
            browser(command),
        ]
    )


def _is_delegated(payload: dict[str, Any]) -> bool:
    """Whether the call is a delegated agent's: a Claude subagent's every tool event carries ``agent_id`` (M189)."""
    agent_id = payload.get("agent_id")
    return isinstance(agent_id, str) and agent_id != ""


def main() -> int:
    """Entry point: guard privilege-escalation, commit-shaped and browser-driving calls."""
    # Deny-class, and crash-open for a developer (ADR 0013 F3): a crash lets the command through and says so. An
    # autonomous run is denied instead (ADR 0031/D07, D-C203-GUARD-CRASH); the actor is read here, before the
    # matrix or anything else that can crash.
    actor = access_matrix.actor_from_environment(os.environ)
    autonomous = actor is access_matrix.Actor.AUTONOMOUS
    return run_guarded(
        "git-commit-guard",
        lambda: _decide(actor),
        closed_document=guard_crash_deny_document if autonomous else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
