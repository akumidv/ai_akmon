#!/usr/bin/env python3
"""Codex command-hook entrypoint for akmon guardrail reminders.

Usage from .codex/hooks.json (``_aitna`` is the default dev-layer root; a project that sets
``AITNA_ROOT`` gets the matching path written by ``sync.py``)::

    python3 "$(git rev-parse --show-toplevel)/_aitna/akmon/hooks/codex-hook.py" analysis-guard

The guardrail decisions live in ``hook_core.py``. This wrapper only maps Codex hook
payloads into those neutral functions and prints plain-text reminders for Codex to ingest.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

from codex_adapter import (
    command,
    cwd,
    file_paths,
    load_payload,
    payload_shape,
    print_result,
    report_failure,
    session_id,
    tool_kind,
    tool_name,
    tool_use_id,
    unmeasured_path_source,
)
from hook_core import (
    EDIT_TOOL,
    SHELL_TOOL,
    HookResult,
    analysis_write_result,
    claim_diagnostic_marker,
    d2_ledger_reminder_result,
    find_project_root,
    report_unclassified_shell_route,
    role_on_code_result,
    session_start_result,
)


def _payload_root(payload: dict) -> Path:
    """The project root the payload's paths are relative to.

    Codex patch bodies carry repo-relative paths (``*** Add File: note.txt``), so every
    path predicate needs the root to normalize against — not only the D2 one (C47).
    """
    return find_project_root(Path(cwd(payload)) if cwd(payload) else None)


def _report_unreadable_target(payload: dict, name: str) -> None:
    """Report an edit call whose target could not be read out of the payload.

    The matcher fired, so Codex did route a file-touching call here; extracting no path
    from it means akmon is reading the wrong key, not that there was nothing to say. C48
    was exactly that — three advisory hooks inert from the day they were wired, invisible
    because a hook with a broken payload reader and a hook with nothing to report both
    print nothing. Stderr only: the model never sees this, and the call is never blocked.
    """
    if name != EDIT_TOOL:
        return
    sid = session_id(payload)
    event_id = tool_use_id(payload)
    # Codex launches this wrapper once for each path-keyed advisory. Treat the
    # session/tool-use pair as the event identity so one malformed edit produces one
    # diagnostic, while a later malformed edit remains visible. A missing component
    # repeats fail-visible instead of creating a global marker that can hide drift.
    if sid != "nosession" and event_id and not claim_diagnostic_marker("codex-unreadable-target", f"{sid}\0{event_id}"):
        return
    print(
        f"akmon codex-hook: '{tool_name(payload) or 'apply_patch'}' matched but no file path could "
        f"be read from the payload — the advisory hooks are inert for this call ({payload_shape(payload)})",
        file=sys.stderr,
    )


def _report_unmeasured_path_source(payload: dict) -> None:
    """Report an edit whose paths came only from keys no measured Codex version sends.

    C48 deleted the invented ``patch`` keys but left the guessed *path* keys in place, and a
    guess that happens to match is worse than one that misses: an empty list raises the
    no-path signal, while a wrong path is classified in silence. So the advisories still run
    on it — a probable target beats no target — and the provenance is stated instead of being
    presented as measured fact (D2-18 a, owner choice iii).
    """
    sid = session_id(payload)
    event_id = tool_use_id(payload)
    if sid != "nosession" and event_id and not claim_diagnostic_marker("codex-unmeasured-path", f"{sid}\0{event_id}"):
        return
    print(
        f"akmon codex-hook: '{tool_name(payload) or 'apply_patch'}' named a file only through an "
        f"unmeasured payload key — the advisories ran on a path no measured Codex version is "
        f"known to send, so the classification may be wrong ({payload_shape(payload)})",
        file=sys.stderr,
    )


Advisory = Callable[[str, str, str, Path], HookResult | None]


def _advisory(payload: dict, decide: Advisory) -> None:
    """Run one path-keyed advisory over the paths the payload names, first result wins.

    One body for all three wired advisories: they differed only in the decision function,
    and a payload-reading defect in a copy is a defect the other copies hide (C48).
    """
    kind = tool_kind(payload)
    sid = session_id(payload)
    if kind == SHELL_TOOL:
        report_unclassified_shell_route(sid)
        return
    paths = file_paths(payload)
    if not paths:
        _report_unreadable_target(payload, kind)
        return
    if kind == EDIT_TOOL and unmeasured_path_source(payload):
        _report_unmeasured_path_source(payload)
    root = _payload_root(payload)
    for path in paths:
        result = decide(kind, path, sid, root)
        if result is not None:
            print_result(result)
            return


def _session_start(payload: dict) -> None:
    start = Path(cwd(payload)) if cwd(payload) else None
    print_result(session_start_result(find_project_root(start)))


_ROUTES = ("analysis-guard", "role-on-code", "d2-ledger-reminder", "session-start", "git-commit-guard")


class UsageError(Exception):
    """A bad route argument, raised where argparse would print usage and exit on its own."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse's own exit is a SystemExit, which passes an `except Exception` guard, and it
        # prints a usage block first — two lines where the crash contract allows one (ADR 0013).
        raise UsageError(message)


def _dispatch(route: str, payload: dict) -> None:
    if route == "analysis-guard":
        _advisory(payload, analysis_write_result)
    elif route == "role-on-code":
        _advisory(payload, role_on_code_result)
    elif route == "d2-ledger-reminder":
        _advisory(payload, d2_ledger_reminder_result)
    elif route == "session-start":
        _session_start(payload)
    elif route == "git-commit-guard":
        # Intentionally not wired by sync.py yet; C28(b) owns the exact live-probe,
        # owner/D2-verification, then generated-wiring sequence for Bash+git behavior.
        from hook_core import (  # noqa: PLC0415 — unwired route (C28(b))
            git_commit_guard_result,
            privilege_escalation_guard_result,
        )

        cmd = command(payload)
        print_result(privilege_escalation_guard_result(cmd) or git_commit_guard_result(cmd))


def main(argv: list[str] | None = None) -> int:
    """Run one route under the crash guard: a crash exits 1 so Codex shows the hook ``Failed``.

    Every route writes at most one document, as its last step, so a crash cannot leave a
    partial one behind it (ADR 0013 F3 as amended by C87/D2-45).
    """
    hook = "codex-hook"
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument("hook", choices=_ROUTES)
        route = parser.parse_args(argv).hook
        hook = f"codex-hook {route}"
        _dispatch(route, load_payload())
    except Exception as exc:  # noqa: BLE001 — crash-open: every failure is reported, none blocks
        return report_failure(hook, exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
