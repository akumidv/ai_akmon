#!/usr/bin/env python3
"""Claude Stop wrapper for the akmon gate-audit forcing function (C25).

`gate_triggers` in the registry carries two count floors — `review_min_findings` and
`architect_min_options` — and until now nothing read them: the flows named the gate, and a
role that produced ten findings could hand off without the audit ever being mentioned. This
entrypoint is the observation point that was missing. It runs on **Stop**, where the turn's
own text is already in the payload (`last_assistant_message`, M87), counts the structural
items under the role's Findings/Options sections, and — at or above the floor — holds the turn
once with the one request the flows make there: run the `audit` pass, or say the skip out loud.

Three properties keep it from becoming noise:

- **it holds the turn once per gate** — the C36 marker is keyed by role and count, so the same
  material never blocks twice while a later turn carrying a different count is a new gate;
- **it never holds a turn it already held** — `stop_hook_active` is true on the turn that runs
  *because* a Stop hook blocked (M87), and that turn is the audit itself;
- **it stays advisory in substance** — the floor is advisory in review-flow and design-flow, so
  the request names both moves the flows allow; what it removes is the silent pass.

Codex has no main-agent stop event on 0.155.1 (M88), so this gate is Claude-only for now; the
logic it calls lives in `tools/model_routing/routing.py` and is vendor-neutral when one appears.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from claude_adapter import load_payload, run_guarded
from hook_core import HookResult, akmon_runtime_root, find_project_root

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "model_routing"))

import routing


def gate_audit_result(root: Path, payload: dict) -> HookResult | None:
    """The Stop decision for this turn: hold it for the gate audit, or ``None`` to let it end.

    Runtime classification: operational
    Rationale: it authors no guardrail rule of its own. The count floors are registry data and
    the gate is written in review-flow and design-flow; this delivers them at the moment the
    role hands off. It is a public ``*_result`` outside ``hook_core``, so ADR-0012/D07's join
    covers neither it nor the floors it restates (same standing as ``model_routing_result``).
    """
    if payload.get("stop_hook_active"):
        return None  # this turn is already the answer to a held turn — never hold it again
    message = payload.get("last_assistant_message")
    if not isinstance(message, str) or not message.strip():
        return None
    akmon = akmon_runtime_root(root)
    if not routing.registry_path(akmon).is_file():
        return None  # a tree from before model routing has no floors to enforce
    registry = routing.load_registry(akmon, root)
    role = routing.active_role(payload.get("transcript_path"))
    request = routing.gate_audit_request(registry, routing.read_local_config(root), role, message)
    if request is None:
        return None
    if not routing.gate_audit_once(role, message, payload.get("session_id")):
        return None  # this gate was already asked about; a second hold would be a loop
    return HookResult(event_name="Stop", decision="block", reason=request)


def _project_root(payload: dict) -> Path:
    cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or str(Path.cwd())
    return find_project_root(Path(cwd))


def _decide() -> HookResult | None:
    payload = load_payload()
    return gate_audit_result(_project_root(payload), payload)


def main() -> int:
    """Entry point: hold the turn once when a role passed its gate's count floor."""
    # Crash-open through the shared guard: a failure here must never wedge a session's turn.
    return run_guarded("gate-audit", _decide)


if __name__ == "__main__":
    raise SystemExit(main())
