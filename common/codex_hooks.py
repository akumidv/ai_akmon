#!/usr/bin/env python3
"""C70 — bounded live query of Codex host-side hook delivery (D2-27, design §7).

Generated wiring is structural proof only (N7 — meta/reviews/n7-codex-hook-delivery-20260825.md):
a discovered hook entry can be reported ``enabled: true`` while its persisted trust is absent or
stale, and the handler simply never fires. This module derives the expected hook population from
generated wiring and compares it against the authoritative ``codex app-server`` ``hooks/list``
result — the only oracle for project discovery and per-entry trust — rather than reconstruct
``~/.codex/config.toml`` parsing or hashing, which N7 also measured to be keyed per *group*, not
per command, making a reimplementation a standing bug source.

Wire protocol, measured live against codex-cli 0.154.0: newline-delimited JSON-RPC 2.0 over
stdio, no Content-Length framing. An ``initialize`` request naming ``clientInfo`` is answered
almost immediately; ``hooks/list`` needs no further handshake and can be written right behind it
without waiting — an unrelated server notification (``remoteControl/status/changed`` was observed)
may arrive interleaved and is skipped by matching on the request ``id``, which this module also
requires the response to echo before trusting it. The response shape is ``{"id": <matching id>,
"result": {"data": [{"cwd", "hooks", "warnings", "errors"}]}}``; each ``hooks`` entry
(``HookMetadata`` in the vendor's own schema — ``codex app-server generate-json-schema``) carries
``key``, ``enabled``, ``eventName`` (camelCase), ``matcher``, ``command`` (present when
``handlerType == "command"``), and ``trustStatus`` — one of ``managed|untrusted|trusted|modified``
— among other fields this module does not read.

Every field this module reads off the wire is untrusted vendor input and is validated structurally
before use; anything short of that measured shape raises :class:`CodexProtocolError`. Every
diagnostic this module produces is one of the fixed texts in :data:`_PROTOCOL_FAILURES`:
:class:`CodexProtocolError` is built from a failure *kind*, not from a message, so whoever raises
it — this module or an injected runner — can only select one of those texts, never supply one.
Nothing taken from the response reaches it: not the body, not the echoed id, not a JSON-RPC error
code or message, not an unrecognized ``trustStatus``, not the text of an exception raised while
reading it. That is design §7's "no raw hash/config/vendor-output leak" boundary, held by
construction rather than by redaction.
"""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

#: The bounded wait for a ``hooks/list`` answer. A pinned implementation constant (design §7:
#: "the bounded timeout literal" is C70's own, not a reopened architecture fork) — local
#: app-server startup plus one query answered in well under a second when measured live.
DEFAULT_TIMEOUT_SECONDS = 5.0

#: How long cleanup waits for the app-server to exit, once after ``terminate()`` and once more
#: after ``kill()``. A child still alive after both (uninterruptible sleep) is abandoned rather
#: than waited on without bound: the query's answer, or its failure, is already decided by then.
_EXIT_GRACE_SECONDS = 2.0

#: PascalCase keys generated wiring uses (``sync._codex_hooks``) -> the app-server's camelCase
#: ``HookEventName`` enum. Only the events akmon's own generator wires today; a key with no entry
#: here is a :class:`CodexWiringError`, and ``test_codex_hooks.py`` pins that every event the
#: generator emits has one, so the two cannot drift apart without a red test.
_EVENT_NAMES = {
    "PreToolUse": "preToolUse",
    "SessionStart": "sessionStart",
}

#: Every ``trustStatus`` the vendor schema defines. A value outside it is not a new kind of
#: problem to report by name — echoing it would put a vendor-chosen string into the diagnostic —
#: but a protocol akmon has not measured, so :func:`query_hooks_list` rejects it.
_TRUST_STATUSES = frozenset({"managed", "untrusted", "trusted", "modified"})

#: `trustStatus` values that mean an entry actually runs. `managed` is the vendor's own
#: system/MDM-delivered case, trusted the ordinary owner-approved one; everything else
#: (`untrusted`, `modified`) is exactly what N7 measured as reported `enabled: true` and inert.
_LIVE_TRUST_STATUSES = frozenset({"trusted", "managed"})

#: Fixed JSON-RPC request ids this module sends: 1 for the handshake, 2 for the query it actually
#: reads. Any response not echoing 2 is rejected rather than trusted, matching-notification
#: filtering aside — a stray or reordered message answering the wrong request must not be read as
#: this one's.
_INITIALIZE_ID = 1
_HOOKS_LIST_ID = 2


#: Failure kind -> the only text a :class:`CodexProtocolError` can carry. A closed table rather
#: than messages written at each raise site: an injected runner that raised
#: ``CodexProtocolError(<vendor text>)`` had that text printed verbatim (fourth C70 review).
#: ``test_codex_hooks.py`` pins that every raise site names a kind here and every kind is raised.
_UNCLASSIFIED = "unclassified"
_PROTOCOL_FAILURES = {
    "unstartable": "codex app-server could not be started",
    "stdin-closed": "codex app-server exited before accepting the hooks/list request",
    "timeout": "no hooks/list response within the query timeout",
    "stdout-closed": "codex app-server closed its output before answering hooks/list",
    "runner-failed": "the hooks/list runner failed",
    "not-json": "hooks/list response is not valid JSON",
    "not-object": "hooks/list response is not a JSON object",
    "id-mismatch": "hooks/list response does not answer this request (id mismatch)",
    "jsonrpc-error": "hooks/list returned a JSON-RPC error",
    "no-data": "hooks/list response has no result.data list",
    "no-project": "hooks/list answered no entry for this project",
    "duplicate-project": "hooks/list answered this project more than once",
    "project-shape": "hooks/list entry for this project lacks a hooks, warnings or errors list",
    "discovery-errors": "hooks/list reported discovery errors for this project",
    "hook-not-object": "hooks/list returned a hook entry that is not an object",
    "hook-handler": "hooks/list returned a hook entry without a string handlerType",
    "hook-enabled": "hooks/list returned a hook entry whose enabled is not a boolean",
    "hook-trust": "hooks/list returned a hook entry with an unrecognized trustStatus",
    "hook-identity": "hooks/list returned a command hook without a string eventName/command",
    "hook-matcher": "hooks/list returned a command hook with a non-string matcher",
    _UNCLASSIFIED: "the hooks/list exchange failed for an unclassified reason",
}


class CodexProtocolError(Exception):
    """codex app-server resolved but its hooks/list exchange could not be trusted.

    Built from a failure ``kind`` — a key of :data:`_PROTOCOL_FAILURES` — and never from text:
    ``str()`` is always that key's fixed message, and any other value (arbitrary text, a
    non-string) becomes :data:`_UNCLASSIFIED`. ``kind`` is kept for callers and carriers.
    """

    def __init__(self, kind: object) -> None:
        self.kind = kind if isinstance(kind, str) and kind in _PROTOCOL_FAILURES else _UNCLASSIFIED
        super().__init__(_PROTOCOL_FAILURES[self.kind])


class CodexWiringError(ValueError):
    """Wiring handed to :func:`expected_codex_hooks` is not the shape akmon's generator emits."""


def expected_codex_hooks(wiring: object) -> list[tuple[str, str | None, str]]:
    """``(eventName, matcher, command)`` triples generated Codex wiring expects to be live.

    Reads the nested shape ``sync._codex_hooks`` emits and ``.codex/hooks.json`` carries, and
    raises :class:`CodexWiringError` for anything else — a non-object, an unmapped event, a
    group or hook list that is not a list, a command that is not a string — rather than let a
    ``KeyError``/``AttributeError`` escape. ``verify`` only calls this on text byte-identical to
    what the current generator writes (its freshness gate runs first), so there the error means
    the generator and :data:`_EVENT_NAMES` disagree, which a test pins; the validation is for any
    other caller.
    """
    if not isinstance(wiring, dict):
        raise CodexWiringError("Codex wiring is not a JSON object")
    events = wiring.get("hooks", {})
    if not isinstance(events, dict):
        raise CodexWiringError("Codex wiring `hooks` is not an object")
    expected: list[tuple[str, str | None, str]] = []
    for event, groups in events.items():
        if event not in _EVENT_NAMES:
            raise CodexWiringError(f"Codex wiring names event {event!r}, which has no hooks/list mapping")
        if not isinstance(groups, list):
            raise CodexWiringError(f"Codex wiring event {event!r} is not a list of groups")
        for group in groups:
            if not isinstance(group, dict):
                raise CodexWiringError(f"Codex wiring event {event!r} has a group that is not an object")
            matcher = group.get("matcher")
            if matcher is not None and not isinstance(matcher, str):
                raise CodexWiringError(f"Codex wiring event {event!r} has a non-string matcher")
            hooks = group.get("hooks", [])
            if not isinstance(hooks, list):
                raise CodexWiringError(f"Codex wiring event {event!r} has a group whose hooks is not a list")
            for hook in hooks:
                if not isinstance(hook, dict):
                    raise CodexWiringError(f"Codex wiring event {event!r} has a hook that is not an object")
                if hook.get("type") != "command":
                    continue
                command = hook.get("command")
                if not isinstance(command, str):
                    raise CodexWiringError(f"Codex wiring event {event!r} has a command hook without a command")
                expected.append((_EVENT_NAMES[event], matcher, command))
    return expected


def _delivery_state(hook: dict) -> str | None:
    """``None`` when the entry runs, else its problem category — always a fixed word.

    ``enabled`` counts only as the boolean ``true``: a string ``"false"`` is truthy to ``bool()``
    and would have read as enabled. An unrecognized ``trustStatus`` is ``"unrecognized"`` rather
    than its own value, so no vendor-chosen string becomes a problem name.
    """
    if hook.get("enabled") is not True:
        return "disabled"
    trust = hook.get("trustStatus")
    if not isinstance(trust, str) or trust not in _TRUST_STATUSES:
        return "unrecognized"
    return None if trust in _LIVE_TRUST_STATUSES else trust


def hook_trust_problems(
    expected: Sequence[tuple[str, str | None, str]], entries: Sequence[object]
) -> dict[str, list[str]]:
    """``problem -> [command, ...]`` for every expected entry that is not live and trusted.

    ``problem`` is one of a fixed vocabulary: ``"missing"`` (not discovered at all),
    ``"disabled"`` (discovered, not ``enabled: true``), ``"untrusted"``/``"modified"`` (the
    states N7 measured as silently inert despite generated wiring validating clean),
    ``"unrecognized"`` (a ``trustStatus`` outside the vendor schema), or ``"ambiguous"`` (the host
    reported the same identity more than once and the copies disagree). The commands listed are
    akmon's own, taken from ``expected``, never from ``entries``. An expected identity absent
    from ``entries`` and one present only as a non-command handler are both "missing": akmon only
    ever generates command hooks, so a same-identity non-command entry is not this one.

    Every expected identity is resolved from the *full* set of matching entries, not the last one
    seen: a host that reports the same identity twice with conflicting state must not produce an
    outcome that depends on iteration order. Copies that land in the same category (exact
    duplicates, or ``trusted`` beside ``managed``) resolve normally; copies that do not are
    ``"ambiguous"`` regardless of order.
    """
    by_identity: dict[tuple[str | None, str | None, str | None], list[dict]] = {}
    for hook in entries:
        if not isinstance(hook, dict) or hook.get("handlerType") != "command":
            continue
        identity = (hook.get("eventName"), hook.get("matcher"), hook.get("command"))
        if not all(part is None or isinstance(part, str) for part in identity):
            continue  # an unhashable/misshapen identity cannot be an expected one
        by_identity.setdefault(identity, []).append(hook)

    problems: dict[str, list[str]] = {}
    for identity in expected:
        command = identity[2]
        hooks = by_identity.get(identity)
        if not hooks:
            problems.setdefault("missing", []).append(command)
            continue
        states = {_delivery_state(hook) for hook in hooks}
        state = "ambiguous" if len(states) > 1 else next(iter(states))
        if state is not None:
            problems.setdefault(state, []).append(command)
    return problems


def default_runner(command: Sequence[str], cwd: Path, timeout: float) -> str:
    """Spawn ``command`` (``codex app-server``), negotiate the minimal handshake, and return the
    raw ``hooks/list`` response line. See the module docstring for the measured wire shape.

    This is the seam :func:`query_hooks_list` calls by default; a caller (a test, or a future
    caller that already has a running app-server) may pass its own ``runner`` instead — carriers
    inject the command runner and a canned protocol result rather than spawn a real subprocess.

    Reads happen on a dedicated daemon thread that only ever blocks on ``readline()`` and posts
    decoded lines to a queue; the timeout is enforced on ``queue.get`` in this thread instead of
    ``select()`` on the raw file descriptor. ``select()`` reports OS-level readability only — once
    ``TextIOWrapper``/``BufferedReader`` has pulled two already-sent lines into its own userspace
    buffer in a single read, a second ``select()`` call sees no *new* bytes at the fd and times out
    even though the second line is already fully available to ``readline()``; the reader thread
    never has that ambiguity because it always calls the blocking read directly.

    Every wait is bounded, cleanup included: ``terminate()`` then at most
    :data:`_EXIT_GRACE_SECONDS`, ``kill()`` then at most that again, and a child that survives
    both is abandoned (the daemon reader never blocks interpreter exit).
    """
    try:
        proc = subprocess.Popen(
            list(command),
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
    except OSError:
        raise CodexProtocolError("unstartable") from None

    lines: queue.Queue[str | None] = queue.Queue()

    def _pump() -> None:
        try:
            for text_line in proc.stdout:
                lines.put(text_line)
        except (OSError, ValueError):
            pass
        finally:
            lines.put(None)

    reader = threading.Thread(target=_pump, daemon=True)
    reader.start()

    try:
        try:
            proc.stdin.write(
                json.dumps(
                    {
                        "id": _INITIALIZE_ID,
                        "method": "initialize",
                        "params": {
                            "clientInfo": {"name": "akmon", "title": "akmon verify", "version": "1"}
                        },
                    }
                )
                + "\n"
            )
            proc.stdin.write(
                json.dumps(
                    {"id": _HOOKS_LIST_ID, "method": "hooks/list", "params": {"cwds": [str(cwd)]}}
                )
                + "\n"
            )
            proc.stdin.flush()
        except OSError:
            raise CodexProtocolError("stdin-closed") from None

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CodexProtocolError("timeout")
            try:
                line = lines.get(timeout=remaining)
            except queue.Empty:
                raise CodexProtocolError("timeout") from None
            if line is None:
                raise CodexProtocolError("stdout-closed")
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict) and message.get("id") == _HOOKS_LIST_ID:
                return line
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass
        for stop in (proc.terminate, proc.kill):
            try:
                stop()
            except OSError:
                pass
            try:
                proc.wait(timeout=_EXIT_GRACE_SECONDS)
                break
            except subprocess.TimeoutExpired:
                continue


def _check_hook_metadata(hook: object) -> None:
    """Reject a ``hooks`` element that is not the measured ``HookMetadata`` shape.

    Checked for every element, not only the expected ones: one malformed entry means the answer
    is not the protocol this module measured, and a checker that skipped what it could not read
    would turn exactly that into a clean result.
    """
    if not isinstance(hook, dict):
        raise CodexProtocolError("hook-not-object")
    if not isinstance(hook.get("handlerType"), str):
        raise CodexProtocolError("hook-handler")
    if not isinstance(hook.get("enabled"), bool):
        raise CodexProtocolError("hook-enabled")
    trust = hook.get("trustStatus")
    if not isinstance(trust, str) or trust not in _TRUST_STATUSES:
        raise CodexProtocolError("hook-trust")
    if hook["handlerType"] != "command":
        return
    if not isinstance(hook.get("eventName"), str) or not isinstance(hook.get("command"), str):
        raise CodexProtocolError("hook-identity")
    matcher = hook.get("matcher")
    if matcher is not None and not isinstance(matcher, str):
        raise CodexProtocolError("hook-matcher")


def query_hooks_list(
    command: Sequence[str],
    cwd: Path,
    *,
    runner: Callable[[Sequence[str], Path, float], str] = default_runner,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[dict]:
    """The ``hooks`` entries ``hooks/list`` reports for ``cwd`` — the live oracle N7 measured.

    Raises :class:`CodexProtocolError` for anything short of a clean, well-shaped answer: a
    timeout, a closed pipe, a JSON-RPC error object, a response id that does not echo this
    request's, no entry or more than one entry for ``cwd``, a per-project ``errors`` entry, or a
    response missing or misshaping any field this module reads (``result.data`` not a list, the
    entry's ``hooks``/``warnings``/``errors`` not a list, a hook element failing
    :func:`_check_hook_metadata`). A caller must not read a caught exception as "no hooks" — that
    is a distinct, positively reported state (an empty ``data[].hooks`` list, not an exception).

    Exactly one entry may answer ``cwd``: only that one cwd was asked about, and choosing between
    two answers for it — first, last, or a merge — would make the result depend on their order
    (fourth C70 review: ``[trusted, empty]`` read green and the reverse read missing). Merging is a
    delivery-semantics choice this module does not make, so a second answer is uninspectable.

    Every message is one of :data:`_PROTOCOL_FAILURES` (see the module docstring). A
    :class:`CodexProtocolError` the ``runner`` raises is rebuilt here from its ``kind`` alone, so a
    subclass with its own ``__str__`` cannot carry text past this seam either. Any other exception
    the ``runner`` raises — a write or flush failure, an exec race, a bug in an injected test
    runner — becomes ``runner-failed`` rather than escape as a bare traceback: this function is the
    one seam ``verify`` trusts to turn "codex resolved but is uninspectable" into a `Finding`,
    never a crash.
    """
    try:
        raw = runner(command, cwd, timeout)
    except CodexProtocolError as exc:
        raise CodexProtocolError(getattr(exc, "kind", None)) from None
    except Exception:
        raise CodexProtocolError("runner-failed") from None

    try:
        message = json.loads(raw)
    except (TypeError, ValueError):
        raise CodexProtocolError("not-json") from None
    if not isinstance(message, dict):
        raise CodexProtocolError("not-object")
    if message.get("id") != _HOOKS_LIST_ID:
        raise CodexProtocolError("id-mismatch")
    if "error" in message:
        raise CodexProtocolError("jsonrpc-error")
    result = message.get("result")
    data = result.get("data") if isinstance(result, dict) else None
    if not isinstance(data, list):
        raise CodexProtocolError("no-data")

    cwd_str = str(cwd)
    answers = [entry for entry in data if isinstance(entry, dict) and entry.get("cwd") == cwd_str]
    if not answers:
        raise CodexProtocolError("no-project")
    if len(answers) > 1:
        raise CodexProtocolError("duplicate-project")
    (entry,) = answers
    if not all(isinstance(entry.get(field), list) for field in ("hooks", "warnings", "errors")):
        raise CodexProtocolError("project-shape")
    if entry["errors"]:
        raise CodexProtocolError("discovery-errors")
    for hook in entry["hooks"]:
        _check_hook_metadata(hook)
    return entry["hooks"]
