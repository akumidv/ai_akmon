#!/usr/bin/env python3
"""Claude SessionStart hook for the learning-run reminder (C177, ADR 0026/D07).

Records the session in the project's learning record (``<dev root>/.local/learning.json``) and,
once enough sessions or days have passed since the learning agent's last run, tells the model (to
say so once, in its first reply) and the owner to run the ``learning`` skill. Silent when nothing is
due, and never blocking: a failure goes through the shared crash guard, which exits 0.

The record, the thresholds and the texts live in ``common/learning.py`` and its data file; this
entry point reads the clock, the payload, the thresholds and the record once, and adapts the
result. The Codex route (``codex-hook.py learning-reminder``) calls the same functions.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from claude_adapter import load_payload, located_project_root, run_guarded
from hook_core import HookResult

from common import learning  # hook_core puts the tree root on sys.path


def payload_event(payload: dict, environ: Mapping[str, str], data: dict) -> learning.SessionEvent | None:
    """The session start this payload names, as the learning record sees it, or ``None`` for a second opinion.

    ``environ`` is the hook process's environment, read once at the entry point: a second-opinion run
    is neither recorded nor reminded, an unattended session (``claude -p``) is recorded but not reminded.
    """
    session_id, source = payload.get("session_id"), payload.get("source")
    return learning.session_event(
        session_id if isinstance(session_id, str) else None,
        source if isinstance(source, str) else None,
        environ,
        data,
    )


def learning_reminder_result(
    event: learning.SessionEvent | None, root: Path, data: dict, thresholds: learning.Thresholds, now: datetime
) -> HookResult | None:
    """The SessionStart result for this session: the learning reminder, or ``None`` when nothing is due.

    ``event`` is :func:`payload_event`'s answer; ``None`` (a second-opinion run) records and says nothing.

    Runtime classification: operational
    Rationale: it authors no guardrail rule. It records that a session happened and delivers a
    reminder the learning agent's charter (ADR 0026/D07) already states, on the two channels an
    owner-addressed notice uses: ``additionalContext`` for the model, ``systemMessage`` for the
    owner. It is a public ``*_result`` outside ``hook_core``, so ADR-0012/D07's join covers neither
    it nor the thresholds it applies (same standing as ``model_routing_result``).
    """
    if event is None:
        return None
    reminder = learning.record_and_remind(learning.state_path(root, data), event, thresholds, now, data)
    if reminder is None:
        return None
    for_model, for_owner = reminder
    return HookResult(event_name="SessionStart", additional_context=for_model, system_message=for_owner)


def _decide() -> HookResult | None:
    payload = load_payload()
    root = located_project_root(payload)
    if root is None:
        # No project root: the record has no local layer to live in, so nothing is written (ADR 0022 D09).
        return None
    data = learning.read_data()
    event = payload_event(payload, os.environ, data)
    return learning_reminder_result(event, root, data, learning.read_thresholds(root, data), datetime.now(UTC))


def main() -> int:
    """Entry point: record the session and emit the learning reminder when one is due."""
    # Never block session start: a crash is reported (stderr + the owner's notice), exit 0.
    return run_guarded("learning-reminder", _decide)


if __name__ == "__main__":
    raise SystemExit(main())
