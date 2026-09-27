#!/usr/bin/env python3
"""Claude PreToolUse wrapper: log each subagent delegation outside model context.

Appends one TSV line (timestamp, session_id, subagent, model, zone, description) to
``.claude/model-routing.log`` whenever the session calls the subagent tool
(``Agent``/``Task``). Nothing is injected into context and nothing is blocked — declared
routing selections are visible in the log, so the model never has to narrate them. A system message
is emitted to the user interface (not model context) to make each delegation — and its
declared model selection, when present — visible in the console. When the routed agent has
no kind overlapping the active role's effective allowed set (§10.2, C20), an advisory line
is appended; likewise when the agent is bound below the rung floor of one of its task kinds
and the call does not override the model to meet it (C32); and when a fan-out delegation
carries no zone label while earlier delegations of the session did (C33).
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

from claude_adapter import load_payload, run_guarded
from hook_core import HookResult, akmon_runtime_root, find_project_root

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "model_routing"))

import routing

from common import jsondata  # hook_core put the tree root on sys.path


def _load_config(root: Path) -> dict:
    """This project's recorded binding (one reader, ``routing.read_local_config``)."""
    return routing.read_local_config(root)


def _log_data() -> dict[str, Any]:
    """The delegation-log data file beside this module (C102).

    The system-message fragments and the advisory warning prefix.
    """
    return jsondata.read(Path(__file__).parent / "delegation_log.json")


def _format_system_message(line: str) -> str:
    """Format a delegation-log TSV line as a user-facing system message."""
    parts = [field.strip() if field.strip() != "-" else None for field in line.split("\t")]
    padded = (parts + [None] * 6)[:6]
    _timestamp, _session_id, subagent, model, zone, description = padded

    # The fragment texts are owned by hooks/delegation_log.json (C102); the assembly order and
    # the empty-part rules stay here.
    data = _log_data()
    msg = jsondata.fill(data["subagent_prefix"], {"subagent": subagent})
    if model:
        msg += jsondata.fill(data["model_suffix"], {"model": model})
    if zone:
        msg += jsondata.fill(data["zone_suffix"], {"zone": zone})
    if description:
        msg += jsondata.fill(data["description_suffix"], {"description": description})
    return msg


def _decide() -> HookResult | None:
    payload = load_payload()
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    session_id = payload.get("session_id")
    cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or str(Path.cwd())
    root = find_project_root(Path(cwd))

    # Derive the recorded generated-agent pin (its frontmatter `model:` is not echoed in
    # the call). An explicit call override still wins in `delegation_log_line`; neither
    # value is an independent observation of the model the harness actually launched.
    config = _load_config(root)
    subagent_type = str(tool_input.get("subagent_type") or "")
    bound_model = routing.bound_model_for(config, subagent_type)

    line = routing.delegation_log_line(
        str(payload.get("tool_name") or ""),
        tool_input,
        timestamp,
        session_id if isinstance(session_id, str) else None,
        bound_model,
    )
    if line is None:
        return None
    log_path = root / routing.delegation_log_rel()
    # C33 — read this session's earlier delegations before the new line joins them.
    earlier = (
        routing.parse_delegation_entries(log_path.read_text(encoding="utf-8").splitlines())
        if log_path.is_file()
        else []
    )
    this_call = routing.parse_delegation_entries([line])[0]
    zone_warning = routing.unlabelled_fanout_warning(earlier, this_call.session_id, subagent_type, this_call.zone)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    # Emit a UI-visible system message without injecting it into model context.
    messages = [_format_system_message(line)]
    # C20 — advise when the agent has no overlap with the role's effective allowed set.
    registry = routing.load_registry(akmon_runtime_root(root), root)
    role = routing.active_role(payload.get("transcript_path"))
    warning = routing.role_matrix_warning(registry, subagent_type, role)
    warn_prefix = _log_data()["warning_prefix"]
    if warning:
        messages.append(jsondata.fill(warn_prefix, {"warning": warning}))
    # C32 — the recorded task-kind floors are otherwise read by nothing at delegation time.
    floor_warning = routing.delegation_floor_warning(config, subagent_type, tool_input.get("model"))
    if floor_warning:
        messages.append(jsondata.fill(warn_prefix, {"warning": floor_warning}))
    if zone_warning:
        messages.append(jsondata.fill(warn_prefix, {"warning": zone_warning}))
    return HookResult(event_name="PreToolUse", system_message="\n".join(messages))


def main() -> int:
    """Entry point: log the delegation, advisory only."""
    # Advisory only: a crash is reported (stderr + the owner's notice) and never blocks the call.
    return run_guarded("delegation-log", _decide)


if __name__ == "__main__":
    raise SystemExit(main())
