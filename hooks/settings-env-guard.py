#!/usr/bin/env python3
"""Claude PreToolUse hook: an agent never writes the ``env`` of a harness settings file (ADR 0031/D07).

A harness settings file's ``env`` block reaches the hook process (M239), and the launcher sets the run's
actor there (``AKMON_ACTOR``), so the guard denies an ``Edit``, ``Write`` or ``MultiEdit`` that changes the
parsed ``env`` of ``.claude/settings.json`` or ``.claude/settings.local.json`` (the project's at any depth
and the user's) or any ``env``/``shell_environment_policy`` text of a Codex ``.codex/config.toml`` — for every
actor, D-C203-ACTOR-WRITE. It computes the content after the edit from the file as it is now; an edit that
leaves ``env`` identical passes. The shell half of the rule is in ``privilege_escalation_guard_result``
(``hook_core.py``), on the ``Bash`` hook.

Both halves are ``privilege.no-escalation``. The file list, the texts and the comparison are
``common/harness_settings.py``'s; this entry point reads the payload and the file and adapts the result.
Deny-class, and crash-open like every other Claude entry point (ADR 0013 F3).
"""

from __future__ import annotations

from pathlib import Path

from claude_adapter import load_payload, normalize_tool, run_guarded
from hook_core import HookResult, edit_tool

from common import harness_settings  # hook_core put the tree root on sys.path


def _read_current(path: str) -> str | None:
    """The file's text now, ``None`` where there is no file to read (the edit tool fails on one that cannot be read)."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _decide() -> HookResult | None:
    payload = load_payload()
    if normalize_tool(str(payload.get("tool_name") or "")) != edit_tool():
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    reason = harness_settings.edit_reason(tool_input, _read_current, harness_settings.read_data())
    if reason is None:
        return None
    return HookResult(event_name="PreToolUse", permission_decision="deny", permission_reason=reason)


def main() -> int:
    """Entry point: deny an edit that changes the ``env`` of a harness settings file."""
    return run_guarded("settings-env-guard", _decide)


if __name__ == "__main__":
    raise SystemExit(main())
