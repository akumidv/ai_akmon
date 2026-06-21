#!/usr/bin/env python3
"""Codex command-hook entrypoint for keystone guardrail reminders.

Usage from .codex/hooks.json::

    python3 "$(git rev-parse --show-toplevel)/_forge/keystone/hooks/codex-hook.py" analysis-guard

The guardrail decisions live in ``hook_core.py``. This wrapper only maps Codex hook
payloads into those neutral functions and prints plain-text reminders for Codex to ingest.
"""

from __future__ import annotations

import argparse

from codex_adapter import (
    command,
    file_paths,
    load_payload,
    normalize_tool,
    print_result,
    session_id,
    tool_name,
)
from hook_core import analysis_write_result, find_project_root, role_on_code_result, session_start_result


def _analysis_guard(payload: dict) -> None:
    name = normalize_tool(tool_name(payload) or "apply_patch")
    sid = session_id(payload)
    for path in file_paths(payload):
        result = analysis_write_result(name, path, sid)
        if result is not None:
            print_result(result)
            return


def _role_on_code(payload: dict) -> None:
    name = normalize_tool(tool_name(payload) or "apply_patch")
    sid = session_id(payload)
    for path in file_paths(payload):
        result = role_on_code_result(name, path, sid)
        if result is not None:
            print_result(result)
            return


def _session_start() -> None:
    print_result(session_start_result(find_project_root()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "hook",
        choices=("analysis-guard", "role-on-code", "session-start", "git-commit-guard"),
    )
    args = parser.parse_args(argv)

    payload = load_payload()
    if args.hook == "analysis-guard":
        _analysis_guard(payload)
    elif args.hook == "role-on-code":
        _role_on_code(payload)
    elif args.hook == "session-start":
        _session_start()
    elif args.hook == "git-commit-guard":
        # Intentionally not wired by sync.py yet: Codex hard allow/deny output must be verified
        # before keystone claims enforcement. Keep the mode available for protocol spikes.
        from hook_core import git_commit_guard_result

        print_result(git_commit_guard_result(command(payload)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
