#!/usr/bin/env python3
"""Codex command-hook entrypoint for akmon guardrail reminders.

Usage from .codex/hooks.json (``_aitna`` is the default dev-layer root; a project that declares
another root in ``.aitna-root`` gets the matching path written by ``sync.py``)::

    python3 "$(git rev-parse --show-toplevel)/_aitna/akmon/hooks/codex-hook.py" analysis-guard

The guardrail decisions live in ``hook_core.py``. This wrapper only maps Codex hook
payloads into those neutral functions and prints plain-text reminders for Codex to ingest.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

from codex_adapter import (
    command,
    cwd,
    file_paths,
    load_payload,
    payload_shape,
    print_result,
    prompt,
    report_closed_failure,
    report_failure,
    session_id,
    tool_kind,
    tool_name,
    tool_use_id,
    unmeasured_path_source,
)
from hook_core import (
    HookResult,
    analysis_write_result,
    edit_tool,
    find_project_root,
    guard_crash_deny_document,
    locate_project_root,
    report_unclassified_shell_route,
    role_on_code_result,
    session_start_result,
    shell_tool,
)

from common import access_matrix, jsondata, learning, work_style  # hook_core put the tree root on sys.path
from common.markers import (
    claim_diagnostic_marker,
    marker_kind,
    unidentified_identity,
)


def _codex_hook_data() -> dict[str, Any]:
    """The codex-hook data file beside this module (C102).

    The route list and the two payload-defect diagnostic templates.
    """
    return jsondata.read(Path(__file__).parent / "codex_hook.json")


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
    if name != edit_tool():
        return
    sid = session_id(payload)
    event_id = tool_use_id(payload)
    # Codex launches this wrapper once for each path-keyed advisory. Treat the
    # session/tool-use pair as the event identity so one malformed edit produces one
    # diagnostic, while a later malformed edit remains visible. A missing component
    # repeats fail-visible instead of creating a global marker that can hide drift.
    if (
        sid != unidentified_identity()
        and event_id
        and not claim_diagnostic_marker(marker_kind("codex_unreadable_target"), f"{sid}\0{event_id}")
    ):
        return
    print(
        jsondata.fill(
            _codex_hook_data()["unreadable_target"],
            {"tool_name": tool_name(payload) or "apply_patch", "payload_shape": payload_shape(payload)},
        ),
        file=sys.stderr,
    )


def _report_unmeasured_path_source(payload: dict) -> None:
    """Report an edit whose paths came only from keys no measured Codex version sends.

    C48 deleted the invented ``patch`` keys but left the guessed *path* keys in place, and a
    guess that happens to match is worse than one that misses: an empty list raises the
    no-path signal, while a wrong path is classified in silence. So the advisories still run
    on it — a probable target beats no target — and the provenance is stated instead of being
    presented as measured fact (ADR-0012/D01, owner choice iii).
    """
    sid = session_id(payload)
    event_id = tool_use_id(payload)
    if (
        sid != unidentified_identity()
        and event_id
        and not claim_diagnostic_marker(marker_kind("codex_unmeasured_path"), f"{sid}\0{event_id}")
    ):
        return
    print(
        jsondata.fill(
            _codex_hook_data()["unmeasured_path_source"],
            {"tool_name": tool_name(payload) or "apply_patch", "payload_shape": payload_shape(payload)},
        ),
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
    if kind == shell_tool():
        report_unclassified_shell_route(sid)
        return
    paths = file_paths(payload)
    if not paths:
        _report_unreadable_target(payload, kind)
        return
    if kind == edit_tool() and unmeasured_path_source(payload):
        _report_unmeasured_path_source(payload)
    root = _payload_root(payload)
    for path in paths:
        result = decide(kind, path, sid, root)
        if result is not None:
            print_result(result)
            return


def _session_start(payload: dict) -> None:
    start = Path(cwd(payload)) if cwd(payload) else None
    sid = session_id(payload)
    print_result(session_start_result(find_project_root(start), None if sid == unidentified_identity() else sid))


def _learning_reminder(payload: dict) -> None:
    """The learning-run reminder (C177): record the session, remind once a run is due.

    Codex reads ``additionalContext`` on ``SessionStart`` (M65) and has no owner channel, so only
    the model half of the reminder is printed — the adapter drops ``system_message``.
    """
    start = Path(cwd(payload)) if cwd(payload) else None
    root = locate_project_root(start)
    if root is None:
        # No project root: the record has no local layer to live in, so nothing is written (ADR 0022 D09).
        return
    data = learning.read_data()
    sid = session_id(payload)
    source = payload.get("source")
    event = learning.session_event(
        None if sid == unidentified_identity() else sid,
        source if isinstance(source, str) else None,
        os.environ,
        data,
    )
    if event is None:
        return
    reminder = learning.record_and_remind(
        learning.state_path(root, data), event, learning.read_thresholds(root, data), datetime.now(UTC), data
    )
    if reminder is not None:
        print_result(HookResult(event_name="SessionStart", additional_context=reminder[0]))


def _work_style(payload: dict) -> None:
    """The work-style capture (ADR 0031/D03): record a typed ``/style`` switch for the session.

    Codex's ``UserPromptSubmit`` carries the typed ``prompt`` and ``session_id`` (M65) and reads
    ``additionalContext`` into the model request; it has no owner channel, so only the model half
    of the reply is printed. Any other prompt: silent, no write.
    """
    start = Path(cwd(payload)) if cwd(payload) else None
    root = locate_project_root(start)
    if root is None:
        # No project root: the record has no local layer to live in, so nothing is written (ADR 0022 D09).
        return
    sid = session_id(payload)
    reply = work_style.record_and_reply(
        root, None if sid == unidentified_identity() else sid, prompt(payload), work_style.read_data()
    )
    if reply is not None:
        print_result(HookResult(event_name="UserPromptSubmit", additional_context=reply))


# The route whose crash an autonomous run answers with a deny (ADR 0031/D07, D-C203-GUARD-CRASH).
_COMMIT_GUARD_ROUTE = "git-commit-guard"


def _routes() -> tuple[str, ...]:
    """The hook routes this wrapper dispatches (hooks/codex_hook.json, C102)."""
    return tuple(_codex_hook_data()["routes"])


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
    elif route == "session-start":
        _session_start(payload)
    elif route == "learning-reminder":
        _learning_reminder(payload)
    elif route == "work-style":
        _work_style(payload)
    elif route == _COMMIT_GUARD_ROUTE:
        # Intentionally not wired by sync.py yet; C28(b) owns the exact live-probe,
        # owner verification, then generated-wiring sequence for Bash+git behavior.
        from hook_core import (  # noqa: PLC0415 — unwired route (C28(b))
            git_commit_guard_result,
            privilege_escalation_guard_result,
        )

        cmd = command(payload)
        start = cwd(payload) or None
        print_result(
            privilege_escalation_guard_result(cmd, start)
            or git_commit_guard_result(
                cmd,
                actor=access_matrix.actor_from_environment(os.environ),
                run_branch=access_matrix.run_branch_from_environment(os.environ),
            )
        )


def main(argv: list[str] | None = None) -> int:
    """Run one route under the crash guard: a crash exits 1 so Codex shows the hook ``Failed``.

    Every route writes at most one document, as its last step, so a crash cannot leave a
    partial one behind it (ADR-0013/D01).
    """
    hook = "codex-hook"
    # The actor is read before anything that can crash: an autonomous run's commit guard fails closed.
    autonomous = access_matrix.actor_from_environment(os.environ) is access_matrix.Actor.AUTONOMOUS
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument("hook", choices=_routes())
        route = parser.parse_args(argv).hook
        hook = f"codex-hook {route}"
        _dispatch(route, load_payload())
    except Exception as exc:  # noqa: BLE001 — crash-open: every failure is reported, none blocks
        if autonomous and hook == f"codex-hook {_COMMIT_GUARD_ROUTE}":
            return report_closed_failure(hook, exc, guard_crash_deny_document())
        return report_failure(hook, exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
