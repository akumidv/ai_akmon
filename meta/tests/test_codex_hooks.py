"""Unit tests for common/codex_hooks.py — C70's pure population/diff/protocol logic.

bin/verify.py::check_codex_host_trust is exercised end to end in test_verify.py; these tests
pin the library functions it calls directly, including the wire-protocol parsing with an
injected runner (no real `codex app-server` subprocess).
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest
import sync

from common import codex_hooks
from common.codex_hooks import (
    CodexProtocolError,
    CodexWiringError,
    default_runner,
    expected_codex_hooks,
    hook_trust_problems,
    query_hooks_list,
)

_WIRING = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Bash|apply_patch",
                "hooks": [
                    {"type": "command", "command": "akmon role-on-code"},
                    {"type": "command", "command": "akmon analysis-guard"},
                ],
            }
        ],
        "SessionStart": [
            {
                "matcher": "startup|resume|clear|compact",
                "hooks": [{"type": "command", "command": "akmon session-start"}],
            }
        ],
    }
}

#: A value only a hostile or broken host would put on the wire; no diagnostic may contain it.
_CANARY = "VENDOR_CANARY_7f3a"


def test_expected_codex_hooks_derives_every_command_entry():
    expected = expected_codex_hooks(_WIRING)
    assert expected == [
        ("preToolUse", "Bash|apply_patch", "akmon role-on-code"),
        ("preToolUse", "Bash|apply_patch", "akmon analysis-guard"),
        ("sessionStart", "startup|resume|clear|compact", "akmon session-start"),
    ]


def test_expected_codex_hooks_is_empty_for_empty_wiring():
    assert expected_codex_hooks({"hooks": {}}) == []
    assert expected_codex_hooks({}) == []


def test_expected_codex_hooks_ignores_non_command_hooks():
    wiring = {"hooks": {"PreToolUse": [{"matcher": "x", "hooks": [{"type": "prompt"}]}]}}
    assert expected_codex_hooks(wiring) == []


def test_expected_codex_hooks_maps_every_event_the_real_generator_wires(tmp_path):
    """The generator and `_EVENT_NAMES` must not drift: an event it starts wiring with no
    hooks/list mapping would otherwise only surface as a CodexWiringError inside `verify`."""
    expected = expected_codex_hooks(sync._codex_hooks(tmp_path))
    assert len(expected) == 4
    assert {event for event, _, _ in expected} == {"preToolUse", "sessionStart"}


@pytest.mark.parametrize(
    "wiring",
    [
        [],
        "hooks",
        {"hooks": []},
        {"hooks": {"UnknownEvent": [{"hooks": [{"type": "command", "command": "x"}]}]}},
        {"hooks": {"PreToolUse": {"matcher": "x"}}},
        {"hooks": {"PreToolUse": [1]}},
        {"hooks": {"PreToolUse": [{"matcher": 1, "hooks": []}]}},
        {"hooks": {"PreToolUse": [{"matcher": "x", "hooks": {"type": "command"}}]}},
        {"hooks": {"PreToolUse": [{"matcher": "x", "hooks": ["command"]}]}},
        {"hooks": {"PreToolUse": [{"matcher": "x", "hooks": [{"type": "command"}]}]}},
    ],
    ids=[
        "list",
        "string",
        "hooks-list",
        "unknown-event",
        "groups-object",
        "group-scalar",
        "matcher-int",
        "hooks-object",
        "hook-scalar",
        "command-absent",
    ],
)
def test_expected_codex_hooks_rejects_a_shape_the_generator_never_emits(wiring):
    with pytest.raises(CodexWiringError):
        expected_codex_hooks(wiring)


def _entry(event, matcher, command, *, enabled=True, trust="trusted"):
    return {
        "handlerType": "command",
        "eventName": event,
        "matcher": matcher,
        "command": command,
        "enabled": enabled,
        "trustStatus": trust,
    }


def test_hook_trust_problems_empty_when_everything_matches():
    expected = [("preToolUse", "m", "c1")]
    entries = [_entry("preToolUse", "m", "c1")]
    assert hook_trust_problems(expected, entries) == {}


def test_hook_trust_problems_reports_missing_entirely_absent_entry():
    expected = [("preToolUse", "m", "c1")]
    assert hook_trust_problems(expected, []) == {"missing": ["c1"]}


def test_hook_trust_problems_reports_disabled():
    expected = [("preToolUse", "m", "c1")]
    entries = [_entry("preToolUse", "m", "c1", enabled=False)]
    assert hook_trust_problems(expected, entries) == {"disabled": ["c1"]}


@pytest.mark.parametrize("enabled", ["false", "true", 1, None])
def test_hook_trust_problems_counts_only_the_boolean_true_as_enabled(enabled):
    """`bool("false")` is True: a non-boolean `enabled` must never read as a live entry."""
    expected = [("preToolUse", "m", "c1")]
    entries = [_entry("preToolUse", "m", "c1", enabled=enabled)]
    assert hook_trust_problems(expected, entries) == {"disabled": ["c1"]}


@pytest.mark.parametrize("trust", ["untrusted", "modified"])
def test_hook_trust_problems_reports_untrusted_and_modified_by_name(trust):
    expected = [("preToolUse", "m", "c1")]
    entries = [_entry("preToolUse", "m", "c1", trust=trust)]
    assert hook_trust_problems(expected, entries) == {trust: ["c1"]}


@pytest.mark.parametrize("trust", [_CANARY, 7, None, ["trusted"]])
def test_hook_trust_problems_names_an_unknown_trust_status_by_a_fixed_word(trust):
    """The problem name is akmon's vocabulary, never the vendor's value — and an unhashable
    value must not reach the frozenset membership test as a TypeError."""
    expected = [("preToolUse", "m", "c1")]
    entries = [_entry("preToolUse", "m", "c1", trust=trust)]
    assert hook_trust_problems(expected, entries) == {"unrecognized": ["c1"]}


def test_hook_trust_problems_accepts_managed_as_live():
    expected = [("preToolUse", "m", "c1")]
    entries = [_entry("preToolUse", "m", "c1", trust="managed")]
    assert hook_trust_problems(expected, entries) == {}


def test_hook_trust_problems_ignores_non_command_entries_as_missing():
    expected = [("preToolUse", "m", "c1")]
    entries = [{"handlerType": "mcpTool", "eventName": "preToolUse", "matcher": "m", "command": "c1"}]
    assert hook_trust_problems(expected, entries) == {"missing": ["c1"]}


def test_hook_trust_problems_skips_an_entry_with_an_unhashable_identity():
    expected = [("preToolUse", "m", "c1")]
    entries = [_entry("preToolUse", ["m"], "c1"), 1, None]
    assert hook_trust_problems(expected, entries) == {"missing": ["c1"]}


def test_hook_trust_problems_aggregates_multiple_commands_per_problem():
    expected = [("preToolUse", "m", "c1"), ("preToolUse", "m", "c2")]
    entries = []
    assert hook_trust_problems(expected, entries) == {"missing": ["c1", "c2"]}


def test_hook_trust_problems_flags_disagreeing_duplicate_identities_as_ambiguous():
    """Two entries for the same identity that disagree on enabled/trust must not silently pick
    whichever came last — the contract rejects the ambiguity instead."""
    expected = [("preToolUse", "m", "c1")]
    trusted = _entry("preToolUse", "m", "c1", trust="trusted")
    untrusted = _entry("preToolUse", "m", "c1", trust="untrusted")
    assert hook_trust_problems(expected, [trusted, untrusted]) == {"ambiguous": ["c1"]}
    assert hook_trust_problems(expected, [untrusted, trusted]) == {"ambiguous": ["c1"]}


def test_hook_trust_problems_agreeing_duplicate_identities_are_not_ambiguous():
    expected = [("preToolUse", "m", "c1")]
    entries = [_entry("preToolUse", "m", "c1"), _entry("preToolUse", "m", "c1")]
    assert hook_trust_problems(expected, entries) == {}
    # Two live states are one delivery answer, not a disagreement.
    entries = [_entry("preToolUse", "m", "c1", trust="managed"), _entry("preToolUse", "m", "c1")]
    assert hook_trust_problems(expected, entries) == {}


# --------------------------------------------------------------------------------------
# query_hooks_list — the wire-protocol parsing, with an injected runner (no subprocess)
# --------------------------------------------------------------------------------------


def _raw(result=None, error=None, id_=2):
    message = {"id": id_}
    if error is not None:
        message["error"] = error
    else:
        message["result"] = result
    return json.dumps(message)


def _query(raw):
    return query_hooks_list(["codex", "app-server"], "/proj", runner=lambda c, cwd, t: raw)


def _project(**fields):
    entry = {"cwd": "/proj", "hooks": [], "warnings": [], "errors": []}
    entry.update(fields)
    return _raw({"data": [{k: v for k, v in entry.items() if v is not _ABSENT}]})


_ABSENT = object()


def test_query_hooks_list_returns_the_matching_cwds_hooks():
    hooks = [_entry("preToolUse", "m", "c1")]
    assert _query(_project(hooks=hooks)) == hooks


def test_query_hooks_list_ignores_other_roots_even_when_they_are_malformed():
    raw = _raw(
        {
            "data": [
                {"cwd": "/elsewhere", "hooks": [1], "warnings": None, "errors": ["x"]},
                {"cwd": "/proj", "hooks": [], "warnings": [], "errors": []},
            ]
        }
    )
    assert _query(raw) == []


def test_query_hooks_list_accepts_a_non_command_handler_without_a_command():
    hook = {"handlerType": "prompt", "enabled": True, "trustStatus": "trusted"}
    assert _query(_project(hooks=[hook])) == [hook]


def test_query_hooks_list_raises_on_malformed_json():
    with pytest.raises(CodexProtocolError, match="not valid JSON"):
        _query("not json")


def test_query_hooks_list_raises_on_jsonrpc_error_object_without_echoing_it():
    """Neither the vendor's error message nor its code reaches the diagnostic (design §7): a
    fixed category is all ``verify`` may print."""
    with pytest.raises(CodexProtocolError, match="JSON-RPC error") as excinfo:
        _query(_raw(error={"code": _CANARY, "message": _CANARY}))
    assert _CANARY not in str(excinfo.value)


def test_query_hooks_list_raises_when_result_data_is_missing():
    with pytest.raises(CodexProtocolError, match=r"result\.data"):
        _query(json.dumps({"id": 2, "result": {}}))


def test_query_hooks_list_raises_when_no_entry_matches_the_cwd():
    raw = _raw({"data": [{"cwd": "/somewhere-else", "hooks": [], "warnings": [], "errors": []}]})
    with pytest.raises(CodexProtocolError, match="no entry for this project"):
        _query(raw)


@pytest.mark.parametrize("data", [None, _CANARY, {"cwd": "/proj"}])
def test_query_hooks_list_raises_when_data_is_not_a_list(data):
    with pytest.raises(CodexProtocolError) as excinfo:
        _query(_raw({"data": data}))
    assert _CANARY not in str(excinfo.value)


def test_query_hooks_list_raises_when_data_entries_are_not_objects():
    """A non-dict entry (e.g. `data: [1]`) must not reach `.get("cwd")` as a bare AttributeError."""
    with pytest.raises(CodexProtocolError, match="no entry for this project"):
        _query(_raw({"data": [1, 2, 3]}))


@pytest.mark.parametrize("order", ["answer-first", "empty-first", "identical"])
def test_query_hooks_list_rejects_a_second_answer_for_the_same_cwd(order):
    """Fourth C70 review: the first matching entry won, so `[trusted, empty]` read green and the
    reverse read every entry missing. Two answers for the one cwd asked about are uninspectable
    in any order, identical ones included — never a pick, never a merge."""
    answer = {"cwd": "/proj", "hooks": [_entry("preToolUse", "m", "c1")], "warnings": [], "errors": []}
    empty = {**answer, "hooks": []}
    data = {"answer-first": [answer, empty], "empty-first": [empty, answer], "identical": [answer, answer]}[order]
    with pytest.raises(CodexProtocolError) as excinfo:
        _query(_raw({"data": data}))
    assert excinfo.value.kind == "duplicate-project"


@pytest.mark.parametrize(
    "fields",
    [
        {"hooks": None},
        {"hooks": _ABSENT},
        {"hooks": {}},
        {"warnings": _ABSENT},
        {"warnings": 5},
        {"warnings": _CANARY},
        {"errors": _ABSENT},
        {"errors": {}},
        {"errors": 0},
        {"errors": _CANARY},
    ],
    ids=[
        "hooks-null",
        "hooks-absent",
        "hooks-object",
        "warnings-absent",
        "warnings-int",
        "warnings-string",
        "errors-absent",
        "errors-object",
        "errors-zero",
        "errors-string",
    ],
)
def test_query_hooks_list_rejects_a_misshapen_project_entry(fields):
    """Every list the entry carries is checked for being one: a falsy non-list `errors` (`0`,
    `{}`) would otherwise read as "no errors", and `hooks: null` as an empty discovery."""
    with pytest.raises(CodexProtocolError) as excinfo:
        _query(_project(**fields))
    assert _CANARY not in str(excinfo.value)


def test_query_hooks_list_raises_on_non_empty_per_entry_errors_without_echoing_them():
    """A non-empty per-cwd ``errors`` array means this project's discovery was itself
    uninspectable — the ``hooks`` list beside it must not be trusted and returned anyway."""
    with pytest.raises(CodexProtocolError, match="discovery errors") as excinfo:
        _query(_project(errors=[_CANARY]))
    assert _CANARY not in str(excinfo.value)


@pytest.mark.parametrize(
    "change",
    [
        {"enabled": "false"},
        {"enabled": _ABSENT},
        {"enabled": 0},
        {"trustStatus": _CANARY},
        {"trustStatus": 7},
        {"trustStatus": ["trusted"]},
        {"trustStatus": _ABSENT},
        {"handlerType": _ABSENT},
        {"handlerType": 1},
        {"command": ["c1"]},
        {"command": _ABSENT},
        {"eventName": _ABSENT},
        {"matcher": {"m": 1}},
    ],
    ids=[
        "enabled-string",
        "enabled-absent",
        "enabled-int",
        "trust-unknown",
        "trust-int",
        "trust-list",
        "trust-absent",
        "handler-absent",
        "handler-int",
        "command-list",
        "command-absent",
        "event-absent",
        "matcher-object",
    ],
)
def test_query_hooks_list_rejects_malformed_hook_metadata(change):
    """One malformed element means the answer is not the protocol akmon measured; skipping it,
    or coercing it (`bool("false")`), is exactly how a broken answer becomes a green result."""
    hook = {k: v for k, v in {**_entry("preToolUse", "m", "c1"), **change}.items() if v is not _ABSENT}
    with pytest.raises(CodexProtocolError) as excinfo:
        _query(_project(hooks=[_entry("preToolUse", "m", "c0"), hook]))
    assert _CANARY not in str(excinfo.value)


@pytest.mark.parametrize("hook", [1, _CANARY, None, ["c1"]])
def test_query_hooks_list_rejects_a_scalar_hook_element(hook):
    with pytest.raises(CodexProtocolError, match="not an object") as excinfo:
        _query(_project(hooks=[hook]))
    assert _CANARY not in str(excinfo.value)


@pytest.mark.parametrize("id_", [999, _CANARY, None, "2"])
def test_query_hooks_list_rejects_a_response_whose_id_does_not_match_without_echoing_it(id_):
    with pytest.raises(CodexProtocolError, match="id mismatch") as excinfo:
        _query(_raw({"data": []}, id_=id_))
    assert str(id_) not in str(excinfo.value).replace("hooks/list", "")


def test_query_hooks_list_raises_when_response_is_not_a_json_object():
    """A well-formed JSON value that is not an object (e.g. a bare string) must not leak into
    the diagnostic verbatim."""
    with pytest.raises(CodexProtocolError) as excinfo:
        _query(json.dumps(_CANARY))
    assert _CANARY not in str(excinfo.value)


def test_query_hooks_list_converts_an_arbitrary_runner_exception_without_its_message():
    """Any exception the runner raises other than CodexProtocolError — a write/flush failure, an
    exec race, a bug in an injected test runner — must become a Finding-shaped error, not a
    bare traceback that verify's narrow `except CodexProtocolError` would miss; and its text,
    which may be host or vendor output, is not carried over."""

    def flaky(command, cwd, timeout):
        raise BrokenPipeError(_CANARY)

    with pytest.raises(CodexProtocolError, match="runner failed") as excinfo:
        query_hooks_list(["codex", "app-server"], "/proj", runner=flaky)
    assert excinfo.value.kind == "runner-failed"
    assert _CANARY not in str(excinfo.value)
    assert excinfo.value.__cause__ is None


def test_query_hooks_list_propagates_a_runner_timeout():
    def timing_out(command, cwd, timeout):
        raise CodexProtocolError("timeout")

    with pytest.raises(CodexProtocolError, match="within the query timeout") as excinfo:
        query_hooks_list(["codex", "app-server"], "/proj", runner=timing_out)
    assert excinfo.value.kind == "timeout"


@pytest.mark.parametrize("kind", [_CANARY, "no hooks/list response within 5.0s", None, 7, ["timeout"]])
def test_a_protocol_error_can_only_carry_a_fixed_text(kind):
    """Fourth C70 review: `CodexProtocolError("<vendor text>")` printed its text. The error is
    built from a kind, so anything outside the fixed table — text, a non-string, an unhashable
    value — is `unclassified`, never echoed."""
    error = CodexProtocolError(kind)
    assert error.kind == "unclassified"
    assert str(error) == codex_hooks._PROTOCOL_FAILURES["unclassified"]


class _VendorTextError(CodexProtocolError):
    def __str__(self):
        return _CANARY


class _UninitializedError(CodexProtocolError):
    def __init__(self):
        Exception.__init__(self, _CANARY)


@pytest.mark.parametrize(
    ("raised", "kind"),
    [
        (CodexProtocolError(_CANARY), "unclassified"),
        (CodexProtocolError("timeout"), "timeout"),
        (_VendorTextError("timeout"), "timeout"),
        (_UninitializedError(), "unclassified"),
    ],
    ids=["free-text", "known-kind", "subclass-str", "subclass-without-kind"],
)
def test_query_hooks_list_rebuilds_a_runner_protocol_error_from_its_kind(raised, kind):
    """The review's probe: a runner raising `CodexProtocolError("SECRET_CANARY")` put the canary in
    the Finding. What leaves this seam is a fresh base-class error rebuilt from `kind` alone, so
    neither free text nor a subclass's own `__str__`/args survive it."""

    def runner(command, cwd, timeout):
        raise raised

    with pytest.raises(CodexProtocolError) as excinfo:
        query_hooks_list(["codex", "app-server"], "/proj", runner=runner)
    assert type(excinfo.value) is CodexProtocolError
    assert excinfo.value.kind == kind
    assert str(excinfo.value) == codex_hooks._PROTOCOL_FAILURES[kind]
    assert excinfo.value.__cause__ is None


def _protocol_error_arguments():
    tree = ast.parse(Path(codex_hooks.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "CodexProtocolError":
            yield node.args[0]


def test_every_raise_site_names_a_fixed_kind_and_every_kind_is_raised():
    """A misspelt kind would silently degrade to `unclassified`, and a kind nothing raises is dead
    text. The one non-literal argument is `query_hooks_list`'s rebuild of a runner's own error."""
    arguments = list(_protocol_error_arguments())
    literals = [arg.value for arg in arguments if isinstance(arg, ast.Constant)]
    assert all(isinstance(kind, str) for kind in literals)
    assert set(literals) == set(codex_hooks._PROTOCOL_FAILURES) - {"unclassified"}
    assert len(arguments) - len(literals) == 1


# --------------------------------------------------------------------------------------
# default_runner — the real subprocess/JSON-RPC implementation
# --------------------------------------------------------------------------------------


def _fake_codex_script(tmp_path, body: str):
    script = tmp_path / "fake_codex.py"
    script.write_text(body, encoding="utf-8")
    return [sys.executable, str(script)]


def test_default_runner_does_not_time_out_when_both_responses_arrive_in_one_flush(tmp_path):
    """Both the `initialize` ack and the `hooks/list` answer land in a single OS-level read.
    A `select()`-then-`readline()` implementation can see the fd as not-readable for the second
    line once both are already sitting in Python's own buffered reader; a thread that only ever
    blocks on `readline()` does not have that gap."""
    command = _fake_codex_script(
        tmp_path,
        "import sys, json\n"
        "sys.stdin.readline(); sys.stdin.readline()\n"
        "sys.stdout.write(json.dumps({'id': 1, 'result': {}}) + chr(10))\n"
        "sys.stdout.write(json.dumps({'id': 2, 'result': {'data': []}}) + chr(10))\n"
        "sys.stdout.flush()\n"
        "sys.stdin.readline()\n",
    )
    raw = default_runner(command, tmp_path, timeout=5.0)
    assert json.loads(raw) == {"id": 2, "result": {"data": []}}


def test_default_runner_reports_a_protocol_error_when_the_process_exits_immediately(tmp_path):
    """An exec race — the process is gone before (or right as) this module writes to its
    stdin — must surface as CodexProtocolError, never a bare BrokenPipeError/OSError traceback."""
    command = _fake_codex_script(tmp_path, "import sys\nsys.exit(1)\n")
    with pytest.raises(CodexProtocolError):
        default_runner(command, tmp_path, timeout=2.0)


def test_default_runner_reports_an_unstartable_binary_by_type_not_os_text(tmp_path):
    with pytest.raises(CodexProtocolError, match="could not be started") as excinfo:
        default_runner([str(tmp_path / "no-such-codex")], tmp_path, timeout=1.0)
    assert excinfo.value.kind == "unstartable"
    assert "No such file" not in str(excinfo.value)


def test_default_runner_times_out_on_a_silent_process(tmp_path):
    command = _fake_codex_script(tmp_path, "import time\ntime.sleep(30)\n")
    with pytest.raises(CodexProtocolError, match="within"):
        default_runner(command, tmp_path, timeout=0.2)


def test_default_runner_never_waits_without_bound_during_cleanup(tmp_path, monkeypatch):
    """A child that survives both terminate() and kill() (uninterruptible sleep) is abandoned
    after two bounded waits, not waited on forever — the answer is already in hand. The exact
    sequence pins D2-40 (6): terminate, 2.0 s, kill, 2.0 s (fourth C70 review: only
    "bounded" was checked, so changing either literal stayed green)."""
    events = []

    class _Stdin:
        def write(self, text):
            pass

        def flush(self):
            pass

        def close(self):
            pass

    class _Unkillable:
        def __init__(self, *args, **kwargs):
            self.stdin = _Stdin()
            self.stdout = iter([json.dumps({"id": 2, "result": {"data": []}}) + "\n"])

        def terminate(self):
            events.append("terminate")

        def kill(self):
            events.append("kill")

        def wait(self, timeout=None):
            events.append(("wait", timeout))
            if timeout is None:
                raise AssertionError("unbounded wait")
            raise subprocess.TimeoutExpired("codex", timeout)

    monkeypatch.setattr(codex_hooks.subprocess, "Popen", _Unkillable)
    raw = default_runner(["codex", "app-server"], tmp_path, timeout=1.0)
    assert json.loads(raw)["id"] == 2
    assert events == ["terminate", ("wait", 2.0), "kill", ("wait", 2.0)]


# --------------------------------------------------------------------------------------
# One command owner, one caller (TASKS.md C70: "no second command owner and no C59-side
# query"). `akmon status` (C59) receives this finding through verify's stream; if it — or
# anything else akmon ships — starts speaking to the route itself, this goes red.
# --------------------------------------------------------------------------------------

_ROUTE_TOKENS = ("common.codex_hooks", "query_hooks_list", "codex_hooks_list_command", "hooks/list", "app-server")
_ROUTE_FILES = {"bin/verify.py", "common/codex_hooks.py", "common/runtime.py"}


def _shipped_python(root: Path):
    for top in ("bin", "common", "hooks", "src", "tools"):
        for path in sorted((root / top).rglob("*.py")):
            yield path.relative_to(root).as_posix(), path.read_text(encoding="utf-8")


def test_the_hooks_list_route_is_reached_only_through_verify():
    root = Path(__file__).resolve().parents[2]
    speakers = {name for name, text in _shipped_python(root) if any(token in text for token in _ROUTE_TOKENS)}
    assert speakers == _ROUTE_FILES


def test_the_app_server_argv_is_spelled_only_by_the_runtime_owner():
    root = Path(__file__).resolve().parents[2]
    spellers = {name for name, text in _shipped_python(root) if '"app-server"' in text or "'app-server'" in text}
    assert spellers == {"common/runtime.py"}
