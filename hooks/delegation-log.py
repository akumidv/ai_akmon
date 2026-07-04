#!/usr/bin/env python3
"""Claude PreToolUse wrapper: log each subagent delegation at zero token cost.

Appends one TSV line (timestamp, subagent, model, description) to
``.claude/model-routing.log`` whenever the session calls the subagent tool
(``Agent``/``Task``). Nothing is injected into context and nothing is blocked — routing
switches are visible in the log, so the model never has to narrate them. A system message
is emitted to the user interface (not model context) to make delegations visible.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from claude_adapter import load_payload, print_result
from hook_core import HookResult, find_project_root

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "model_routing"))

import routing


def _format_system_message(line: str) -> str:
    """Format a delegation-log TSV line as a user-facing system message."""
    parts = [field.strip() if field.strip() != "-" else None for field in line.split("\t")]
    subagent = parts[1] if len(parts) > 1 else None
    model = parts[2] if len(parts) > 2 else None
    description = parts[3] if len(parts) > 3 else None

    msg = f"[keystone] → {subagent}"
    if model and model != "-":
        msg += f" ({model})"
    if description:
        msg += f": {description}"
    return msg


def main() -> int:
    # Never block a tool call: on any failure, log to stderr and exit cleanly.
    try:
        payload = load_payload()
        tool_input = payload.get("tool_input")
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        line = routing.delegation_log_line(
            str(payload.get("tool_name") or ""),
            tool_input if isinstance(tool_input, dict) else {},
            timestamp,
        )
        if line is not None:
            cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
            log_path = find_project_root(Path(cwd)) / routing.DELEGATION_LOG_REL
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            # Emit system message for UI visibility (zero token cost).
            system_message = _format_system_message(line)
            print_result(HookResult(event_name="PreToolUse", system_message=system_message))
    except Exception as exc:
        print(f"keystone delegation-log hook: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
