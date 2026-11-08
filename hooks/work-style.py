#!/usr/bin/env python3
"""Claude UserPromptSubmit hook for the work style (ADR 0031/D03).

When the owner types ``/style delegating`` or ``/style controlling`` it records that style for the
session in ``<dev root>/.local/work-sessions.json`` and tells the model — and the owner — what was
recorded and that a switch inside an athlos takes effect at the next park boundary. A value that
names no style returns the allowed values and records nothing. Any other prompt: silent, no write.
The agent cannot produce a user prompt, so only the owner can switch (a style never widens a
permission, D01).

The record, the styles and the texts live in ``common/work_style.py`` and its data file; this entry
point reads the payload and the data once and adapts the result. The Codex route
(``codex-hook.py work-style``) calls the same function. Never blocking: a failure goes through the
shared crash guard, which exits 0.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from claude_adapter import load_payload, located_project_root, run_guarded
from hook_core import HookResult

from common import work_style  # hook_core puts the tree root on sys.path


def work_style_result(root: Path, session_id: str | None, prompt: str, data: Mapping[str, Any]) -> HookResult | None:
    """The UserPromptSubmit result for a typed ``prompt``, or ``None`` when it is not a ``/style`` command.

    Both channels carry the reply (requirement 11): the model acts on it and the owner who typed
    the command sees what was recorded.

    Runtime classification: operational
    Rationale: it authors no guardrail rule. It captures the owner's typed style switch (ADR
    0031/D03) and confirms it; a style never widens a permission (D01), so nothing a hook enforces
    depends on it. It is a public ``*_result`` outside ``hook_core``, so ADR-0012/D07's join covers
    neither it nor the values it records (same standing as ``model_routing_result``).
    """
    reply = work_style.record_and_reply(root, session_id, prompt, data)
    if reply is None:
        return None
    return HookResult(event_name="UserPromptSubmit", additional_context=reply, system_message=reply)


def _decide() -> HookResult | None:
    payload = load_payload()
    prompt = payload.get("prompt")
    if not isinstance(prompt, str):
        return None
    root = located_project_root(payload)
    if root is None:
        # No project root: the record has no local layer to live in, so nothing is written (ADR 0022 D09).
        return None
    session_id = payload.get("session_id")
    return work_style_result(
        root, session_id if isinstance(session_id, str) and session_id else None, prompt, work_style.read_data()
    )


def main() -> int:
    """Entry point: record a typed ``/style`` switch for the session, silent on every other prompt."""
    # Never block a turn: a crash is reported (stderr + the owner's notice), exit 0.
    return run_guarded("work-style", _decide)


if __name__ == "__main__":
    raise SystemExit(main())
