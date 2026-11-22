"""A49 — the starting context by audience: the selector, the layer, the SubagentStart hook, the delegate exemption."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import hook_core
import pytest
import sync

from common import audience, jsondata

_TREE = Path(hook_core.__file__).resolve().parent.parent
_ATTENDED_TEXT = (
    (_TREE / "rules" / "collaboration.md").read_text(encoding="utf-8").rstrip("\n")
    + "\n\n"
    + (_TREE / "rules" / "templates.md").read_text(encoding="utf-8").rstrip("\n")
)
_UNATTENDED_TEXT = (_TREE / "rules" / "unattended.md").read_text(encoding="utf-8").rstrip("\n")


def _entry(filename: str):
    path = _TREE / "hooks" / filename
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py").replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(monkeypatch, capsys, entry, payload: dict, *argv: str) -> dict | None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert entry.main(list(argv)) == 0 if argv else entry.main() == 0
    out = capsys.readouterr().out
    return json.loads(out) if out else None


@pytest.fixture(autouse=True)
def _no_audience_signals(monkeypatch):
    for name in ("AKMON_ACTOR", "AKMON_SECOND_OPINION", "CLAUDE_CODE_SESSION_ATTENDED"):
        monkeypatch.delenv(name, raising=False)


# --- the selector (D-A49-SELECTOR) ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("environ", "attended"),
    [
        ({}, True),
        ({"AKMON_ACTOR": "developer"}, True),
        ({"AKMON_ACTOR": "nonsense"}, True),  # an unknown actor reads as developer
        ({"CLAUDE_CODE_SESSION_ATTENDED": "1"}, True),
        ({"CLAUDE_CODE_SESSION_ATTENDED": "unset"}, True),  # only `0` states that nobody attends
        ({"AKMON_ACTOR": "autonomous"}, False),
        ({"CLAUDE_CODE_SESSION_ATTENDED": "0"}, False),
        ({"AKMON_SECOND_OPINION": "1"}, False),
        ({"AKMON_ACTOR": "autonomous", "CLAUDE_CODE_SESSION_ATTENDED": "0", "AKMON_SECOND_OPINION": "1"}, False),
        ({"AKMON_ACTOR": "developer", "CLAUDE_CODE_SESSION_ATTENDED": "1", "AKMON_SECOND_OPINION": ""}, True),
    ],
)
def test_a_session_is_attended_only_when_all_three_signals_allow_it(environ, attended):
    assert audience.is_attended(environ) is attended


def test_the_layers_are_the_files_the_design_names():
    data = audience.read_data()
    assert audience.layer_files(data, attended=True) == ("rules/collaboration.md", "rules/templates.md")
    assert audience.layer_files(data, attended=False) == ("rules/unattended.md",)
    assert audience.layer_text(_TREE, attended=True) == _ATTENDED_TEXT
    assert audience.layer_text(_TREE, attended=False) == _UNATTENDED_TEXT


def test_a_layer_file_missing_from_the_tree_is_raised_not_skipped(tmp_path):
    with pytest.raises(OSError):
        audience.layer_text(tmp_path, attended=False)


def test_sync_materializes_exactly_the_files_a_hook_delivers():
    data = audience.read_data()
    delivered = {*data["attended_files"], *data["unattended_files"]}
    assert set(sync.hook_delivered()) == delivered
    assert not delivered & set(sync.always_imported())  # delivered by a hook, never imported


# --- the SessionStart layer, on every source ------------------------------------------------------


def _project(tmp_path: Path, *, roster: bool) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    if roster:
        charter = root / "_aitna" / "agents" / "development"
        charter.mkdir(parents=True)
        (charter / "README.md").write_text("# development\n", encoding="utf-8")
    return root


@pytest.mark.parametrize("source", ["startup", "resume", "clear", "compact"])
@pytest.mark.parametrize("roster", [True, False])
def test_claude_session_start_carries_the_head_layer_on_every_source(monkeypatch, capsys, tmp_path, source, roster):
    payload = {
        "hook_event_name": "SessionStart",
        "source": source,
        "session_id": "s",
        "cwd": str(_project(tmp_path, roster=roster)),
    }
    document = _run(monkeypatch, capsys, _entry("session-start-agent.py"), payload)
    context = document["hookSpecificOutput"]["additionalContext"]
    assert context.endswith(_ATTENDED_TEXT)
    assert ("agents and the roles they work in" in context) is roster  # without a roster the layer stands alone
    assert _UNATTENDED_TEXT not in context


@pytest.mark.parametrize(
    "signal",
    [{"AKMON_ACTOR": "autonomous"}, {"CLAUDE_CODE_SESSION_ATTENDED": "0"}, {"AKMON_SECOND_OPINION": "1"}],
)
@pytest.mark.parametrize("source", ["startup", "compact"])
def test_an_unattended_session_gets_the_unattended_layer_instead(monkeypatch, capsys, tmp_path, signal, source):
    for name, value in signal.items():
        monkeypatch.setenv(name, value)
    payload = {
        "hook_event_name": "SessionStart",
        "source": source,
        "session_id": "s",
        "cwd": str(_project(tmp_path, roster=False)),
    }
    document = _run(monkeypatch, capsys, _entry("session-start-agent.py"), payload)
    context = document["hookSpecificOutput"]["additionalContext"]
    assert context == _UNATTENDED_TEXT
    assert _ATTENDED_TEXT not in context


@pytest.mark.parametrize("source", ["startup", "resume", "clear", "compact"])
def test_codex_session_start_carries_the_layer_on_every_source(monkeypatch, capsys, tmp_path, source):
    root = _project(tmp_path, roster=False)
    codex = _entry("codex-hook.py")
    document = _run(
        monkeypatch, capsys, codex, {"cwd": str(root), "source": source, "session_id": "s"}, "session-start"
    )
    assert document["hookSpecificOutput"]["additionalContext"] == _ATTENDED_TEXT
    monkeypatch.setenv("AKMON_ACTOR", "autonomous")
    document = _run(
        monkeypatch, capsys, codex, {"cwd": str(root), "source": source, "session_id": "s"}, "session-start"
    )
    assert document["hookSpecificOutput"]["additionalContext"] == _UNATTENDED_TEXT


def test_the_layer_does_not_change_a_project_that_passes_none():
    # The decision functions take the layer as a value: a caller that passes none gets today's text.
    assert hook_core.session_start_context(Path("/nonexistent-project"), None, None) is None
    assert hook_core.session_start_context(Path("/nonexistent-project"), None, "stale") == "stale"
    assert hook_core.session_start_context(Path("/nonexistent-project"), None, None, "layer") == "layer"
    assert hook_core.session_start_context(Path("/nonexistent-project"), None, "stale", "layer") == "stale\nlayer"


# --- SubagentStart --------------------------------------------------------------------------------


def test_subagent_start_hands_the_unattended_layer_to_the_child(monkeypatch, capsys, tmp_path):
    payload = {
        "hook_event_name": "SubagentStart",
        "agent_id": "a1",
        "agent_type": "k_explorer",
        "cwd": str(_project(tmp_path, roster=True)),
    }
    document = _run(monkeypatch, capsys, _entry("subagent-start.py"), payload)
    assert document == {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": _UNATTENDED_TEXT}}


def test_subagent_start_does_not_depend_on_the_environment(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "1")  # a delegate of an attended head is still a delegate
    payload = {"hook_event_name": "SubagentStart", "agent_id": "a1", "cwd": str(_project(tmp_path, roster=False))}
    document = _run(monkeypatch, capsys, _entry("subagent-start.py"), payload)
    assert document["hookSpecificOutput"]["additionalContext"] == _UNATTENDED_TEXT


def test_codex_subagent_start_route_hands_the_unattended_layer_to_the_child(monkeypatch, capsys, tmp_path):
    root = _project(tmp_path, roster=False)
    document = _run(
        monkeypatch, capsys, _entry("codex-hook.py"), {"cwd": str(root), "agent_id": "a1"}, "subagent-start"
    )
    assert document == {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": _UNATTENDED_TEXT}}


def test_the_subagent_start_wiring_is_shipped_for_both_harnesses():
    data = jsondata.read(_TREE / "bin" / "sync.json")
    assert data["claude_hooks"]["SubagentStart"] == [{"matcher": None, "commands": ["subagent-start"]}]
    assert [command for command, _status in data["codex_hooks"]["SubagentStart"][0]["commands"]] == ["subagent-start"]
    assert data["codex_hooks"]["SubagentStart"][0]["matcher"] is None
    assert "subagent-start" in jsondata.read(_TREE / "hooks" / "codex_hook.json")["routes"]
    assert jsondata.read(_TREE / "common" / "codex_hooks.json")["event_names"]["SubagentStart"] == "subagentStart"


# --- a delegate is exempt from the head's two reminders (C28d) ------------------------------------


_REMINDERS = {
    "role-on-code": ("src/x.py", "Role check"),
    "analysis-guard": ("_aitna/design/probe.md", "Analysis-before-mutation"),
}


@pytest.mark.parametrize("hook", sorted(_REMINDERS))
def test_claude_entries_are_silent_for_a_payload_carrying_agent_id(monkeypatch, capsys, tmp_path, hook):
    path, reminder = _REMINDERS[hook]
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    payload = {"tool_name": "Edit", "tool_input": {"file_path": path}, "session_id": "s1", "cwd": str(tmp_path)}
    entry = _entry(f"{hook}.py")
    assert _run(monkeypatch, capsys, entry, dict(payload, agent_id="a1", agent_type="k_implementer")) is None
    head = _run(monkeypatch, capsys, entry, payload)  # the delegate did not spend the head's once-per-session marker
    assert reminder in head["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("route", sorted(_REMINDERS))
def test_codex_routes_are_silent_for_a_payload_carrying_agent_id(monkeypatch, capsys, tmp_path, route):
    path, reminder = _REMINDERS[route]
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    body = f"*** Begin Patch\n*** Add File: {path}\n+x\n*** End Patch"
    payload = {"tool_name": "apply_patch", "tool_input": {"command": body}, "cwd": str(tmp_path), "session_id": "s1"}
    codex = _entry("codex-hook.py")
    assert _run(monkeypatch, capsys, codex, dict(payload, agent_id="a1"), route) is None
    head = _run(monkeypatch, capsys, codex, payload, route)
    assert reminder in head["hookSpecificOutput"]["additionalContext"]


def test_the_reminders_cite_the_head_layer_not_the_floor():
    core = jsondata.read(_TREE / "hooks" / "hook_core.json")
    assert "rules/collaboration.md" in core["analysis_before_mutation_message"]
    assert "guardrails/_common.md § Analysis before mutation" not in core["analysis_before_mutation_message"]


# --- the Codex spawn guard: a child never inherits the head's history (M256, M257) ----------------


def _spawn(monkeypatch, capsys, tool_input: dict | None) -> dict | None:
    payload = {"tool_name": "collaborationspawn_agent", "session_id": "s", "cwd": str(_TREE)}
    if tool_input is not None:
        payload["tool_input"] = tool_input
    return _run(monkeypatch, capsys, _entry("codex-hook.py"), payload, "spawn-guard")


def _allow(updated: dict) -> dict:
    return {
        "hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow", "updatedInput": updated}
    }


@pytest.mark.parametrize("fork_turns", ["all", "1", "", None, 3])
def test_a_spawn_that_would_fork_the_history_is_rewritten_to_none(monkeypatch, capsys, fork_turns):
    original = {"task_name": "explore", "message": "find it — «ünï»\n", "extra": {"a": [1, 2.5, None, True]}}
    if fork_turns is not None:
        original["fork_turns"] = fork_turns
    document = _spawn(monkeypatch, capsys, dict(original))
    updated = document["hookSpecificOutput"]["updatedInput"]
    assert updated["fork_turns"] == "none"
    # updatedInput replaces the whole input: every other received field, the opaque message included, survives
    assert {key: value for key, value in updated.items() if key != "fork_turns"} == {
        key: value for key, value in original.items() if key != "fork_turns"
    }
    assert document == _allow(updated)


def test_a_missing_fork_turns_is_added_after_the_received_fields(monkeypatch, capsys):
    document = _spawn(monkeypatch, capsys, {"task_name": "t", "message": "m"})
    assert list(document["hookSpecificOutput"]["updatedInput"]) == ["task_name", "message", "fork_turns"]


def test_a_rewritten_fork_turns_keeps_its_place(monkeypatch, capsys):
    document = _spawn(monkeypatch, capsys, {"task_name": "t", "fork_turns": "all", "message": "m"})
    assert list(document["hookSpecificOutput"]["updatedInput"]) == ["task_name", "fork_turns", "message"]


def test_a_spawn_that_already_says_none_passes_untouched(monkeypatch, capsys):
    assert _spawn(monkeypatch, capsys, {"task_name": "t", "fork_turns": "none", "message": "m"}) is None


@pytest.mark.parametrize("tool_input", [None, [], "text", 7])
def test_an_input_that_is_not_an_object_is_left_alone(monkeypatch, capsys, tool_input):
    payload = {"tool_name": "collaborationspawn_agent", "session_id": "s", "cwd": str(_TREE)}
    payload["tool_input"] = tool_input
    assert _run(monkeypatch, capsys, _entry("codex-hook.py"), payload, "spawn-guard") is None
    assert hook_core.spawn_fork_result(tool_input) is None


def test_the_spawn_guard_decision_is_pure_and_does_not_edit_its_input():
    received = {"task_name": "t", "fork_turns": "all", "message": "m"}
    result = hook_core.spawn_fork_result(received)
    assert received == {"task_name": "t", "fork_turns": "all", "message": "m"}
    assert result.permission_decision == "allow"
    assert result.updated_input == {"task_name": "t", "fork_turns": "none", "message": "m"}


def test_a_crash_of_the_spawn_guard_is_reported_failed_and_never_blocks(monkeypatch, capsys):
    # exit 1 reads `Failed` on Codex and the call runs unchanged (M257): the spawn proceeds
    codex = _entry("codex-hook.py")
    monkeypatch.setattr(codex, "spawn_fork_result", lambda _tool_input: 1 / 0)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"message": "m"}})))
    assert codex.main(["spawn-guard"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == ["akmon codex-hook spawn-guard hook: ZeroDivisionError"]


def test_the_spawn_guard_is_wired_on_the_whole_spawn_tool_name():
    data = jsondata.read(_TREE / "bin" / "sync.json")
    groups = {group["matcher"]: group["commands"] for group in data["codex_hooks"]["PreToolUse"]}
    assert [command for command, _status in groups["collaborationspawn_agent"]] == ["spawn-guard"]
    assert "spawn-guard" in jsondata.read(_TREE / "hooks" / "codex_hook.json")["routes"]
