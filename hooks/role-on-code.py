#!/usr/bin/env python3
"""Claude PreToolUse wrapper for the akmon design-to-code role reminder.

The role-switch logic lives in ``hook_core.py`` and returns a vendor-neutral ``HookResult``.
This entrypoint only adapts Claude Code's JSON payload/output shape so existing
``.claude/settings.json`` wiring can keep pointing here.
"""

from __future__ import annotations

from claude_adapter import load_payload, normalize_tool, project_root, run_guarded
from hook_core import HookResult, role_on_code_result


def _decide() -> HookResult | None:
    payload = load_payload()
    tool_input = payload.get("tool_input") or {}
    return role_on_code_result(
        tool_name=normalize_tool(str(payload.get("tool_name") or "")),
        file_path=tool_input.get("file_path"),
        session_id=str(payload.get("session_id") or "nosession"),
        project_root=project_root(payload),
    )


def main() -> int:
    """Entry point: emit the design-to-code role reminder."""
    return run_guarded("role-on-code", _decide)


if __name__ == "__main__":
    raise SystemExit(main())
