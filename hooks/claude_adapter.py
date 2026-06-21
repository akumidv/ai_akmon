"""Claude Code adapter for neutral keystone hook results."""

from __future__ import annotations

import json
import sys
from typing import Any

from hook_core import EDIT_TOOL, HookResult

# Claude Code's file-editing tool names → keystone's neutral edit-tool kind.
EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})


def normalize_tool(name: str) -> str:
    """Map a Claude tool name to the neutral kind hook_core expects; pass others through."""
    return EDIT_TOOL if name in EDIT_TOOLS else name


def load_payload() -> dict[str, Any]:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def print_result(result: HookResult | None) -> None:
    if result is None:
        return

    output: dict[str, Any] = {"hookEventName": result.event_name}
    if result.additional_context is not None:
        output["additionalContext"] = result.additional_context
    if result.permission_decision is not None:
        output["permissionDecision"] = result.permission_decision
    if result.permission_reason is not None:
        output["permissionDecisionReason"] = result.permission_reason

    print(json.dumps({"hookSpecificOutput": output}))
