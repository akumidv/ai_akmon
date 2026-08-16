"""Claude Code adapter for neutral akmon hook results."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from hook_core import EDIT_TOOL, READ_TOOL, HookResult, find_project_root

# Claude Code's file-editing tool names → akmon's neutral edit-tool kind.
EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})
# Claude Code's read/sweep tool names → akmon's neutral read-tool kind.
READ_TOOLS = frozenset({"Read", "Grep", "Glob"})


def normalize_tool(name: str) -> str:
    """Map a Claude tool name to the neutral kind hook_core expects; pass others through."""
    if name in EDIT_TOOLS:
        return EDIT_TOOL
    if name in READ_TOOLS:
        return READ_TOOL
    return name


def load_payload() -> dict[str, Any]:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def project_root(payload: dict[str, Any]) -> Path:
    """The project root the payload's paths belong to — from its ``cwd``, not the process's.

    Mirrors ``codex-hook``'s ``_payload_root``. The path predicates normalize against this
    root (C47), so it has to describe the session's project rather than wherever the hook
    process happens to have been started.
    """
    cwd = payload.get("cwd")
    return find_project_root(Path(cwd) if isinstance(cwd, str) and cwd else None)


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

    top_level: dict[str, Any] = {"hookSpecificOutput": output}
    if result.system_message is not None:
        top_level["systemMessage"] = result.system_message

    print(json.dumps(top_level))
