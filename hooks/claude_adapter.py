"""Claude Code adapter for neutral akmon hook results."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hook_core import (
    EDIT_TOOL,
    READ_TOOL,
    HookResult,
    find_project_root,
    hook_failure_diagnostic,
    hook_failure_notice,
)

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
    """Parse the hook payload from stdin as a JSON object; ``{}`` on any parse failure."""
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


def render_result(result: HookResult | None) -> str | None:
    """The one JSON document Claude Code reads for ``result``, or ``None`` when there is none."""
    if result is None:
        return None

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

    return json.dumps(top_level)


def print_result(result: HookResult | None) -> None:
    """Print the rendered ``result`` document, or nothing when there is none."""
    document = render_result(result)
    if document is not None:
        print(document)


def run_guarded(hook_name: str, decide: Callable[[], HookResult | None]) -> int:
    """Run one Claude entry point under the crash guard every spawned entry carries.

    ADR 0013 F3 as amended by C87/D2-45. ``decide`` computes the entry's whole result and writes
    nothing to stdout; the one document is rendered first and written after, so a crash can only
    land before the write — the single-write property the guard rests on, and the reason a render
    failure is caught here too. A crash is reported to two readers: one stderr line naming the
    hook and the exception class, never its message, which routinely carries a path, a key or a
    payload fragment; and one ``systemMessage`` for the owner. On 2.1.270 Claude Code shows that
    message as a notice on ``PreToolUse`` and ``UserPromptSubmit`` and never passes it to the
    model (M69); on ``SessionStart`` it is recorded with the hook's response, and whether the
    terminal shows it there is unmeasured. The exit stays 0 — Claude Code shows nothing at all for
    a hook that exits 1 on ``PreToolUse`` or ``UserPromptSubmit`` (M70), so a non-zero exit would
    only hide the failure. The action goes ahead either way: crash-open, including the deny-class
    commit guard.
    """
    try:
        document = render_result(decide())
    except Exception as exc:  # noqa: BLE001 — crash-open: every failure is reported, none blocks
        print(hook_failure_diagnostic(hook_name, exc), file=sys.stderr)
        document = json.dumps({"systemMessage": hook_failure_notice(hook_name, exc)})
    if document is not None:
        print(document)
    return 0
