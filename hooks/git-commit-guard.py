#!/usr/bin/env python3
"""Claude PreToolUse wrapper for the keystone commit guard.

The guardrail logic lives in ``hook_core.py`` and returns a vendor-neutral ``HookResult``.
This entrypoint only adapts Claude Code's JSON payload/output shape so existing
``.claude/settings.json`` wiring can keep pointing here.
"""

from __future__ import annotations

from claude_adapter import load_payload, print_result
from hook_core import git_commit_guard_result


def main() -> int:
    payload = load_payload()
    if payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command", "") or ""
    print_result(git_commit_guard_result(command))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
