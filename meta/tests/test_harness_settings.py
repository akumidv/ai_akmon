"""An agent never writes the ``env`` of a harness settings file (ADR 0031/D07, D-C203-ACTOR-WRITE).

Both routes of the guard (policy ``privilege.no-escalation``, every actor) are pinned by the shared table
``meta/conformance/units/harness_settings_cases.json``, which the JavaScript twin
(``js/common/harness_settings.test.mjs``, ``js/hooks/hook_core.test.mjs``) runs as well:

- the shell route: :func:`hook_core.privilege_escalation_guard_result` reads the command's words;
- the edit route: :func:`harness_settings.edit_reason`, which the ``settings-env-guard`` hook calls.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import hook_core
import pytest

from common import harness_settings, jsondata

_AKMON = Path(hook_core.__file__).resolve().parent.parent
_CASES = json.loads((_AKMON / "meta" / "conformance" / "units" / "harness_settings_cases.json").read_text("utf-8"))
_DATA = harness_settings.read_data()


def _label(case):
    return f"{case['start']}: {case['command']!r}"


@pytest.mark.parametrize("case", _CASES["bash"], ids=_label)
def test_the_shell_route_decides_as_the_shared_table_says(monkeypatch, case):
    monkeypatch.setattr(hook_core, "_home_directory", lambda: "/home/u")
    result = hook_core.privilege_escalation_guard_result(case["command"], case["start"])
    if case["decision"] == "pass":
        assert result is None
        return
    assert result is not None
    assert (result.event_name, result.permission_decision) == ("PreToolUse", "deny")
    for text in case.get("contains", []):
        assert text in result.permission_reason


def test_the_shell_route_reads_the_process_directory_when_none_is_given(monkeypatch, tmp_path):
    (tmp_path / ".claude").mkdir()
    monkeypatch.chdir(tmp_path / ".claude")
    assert hook_core.privilege_escalation_guard_result("echo x > settings.json") is not None
    assert hook_core.privilege_escalation_guard_result("echo x > notes.md") is None


def test_a_command_that_names_no_settings_directory_is_not_parsed(monkeypatch):
    # The directories come from the data file; a command that mentions none is passed without a parse.
    def parsed(*_args, **_keywords):
        raise AssertionError("parsed")

    monkeypatch.setattr(hook_core, "_Parser", parsed)
    assert hook_core.privilege_escalation_guard_result("echo x > notes.md", "/p") is None


def test_the_shell_route_denies_the_same_for_every_actor(monkeypatch):
    # the rule takes no actor: nothing in the call or the environment moves it
    for actor in ("developer", "autonomous", "guided", ""):
        monkeypatch.setenv("AKMON_ACTOR", actor)
        assert hook_core.privilege_escalation_guard_result("echo x > .claude/settings.json", "/p") is not None


def test_the_settings_reason_is_its_own_text_and_the_elevation_deny_comes_first():
    elevated = hook_core.privilege_escalation_guard_result("sudo tee .claude/settings.json", "/p")
    settings = hook_core.privilege_escalation_guard_result("echo x > .claude/settings.json", "/p")
    assert elevated.permission_reason == hook_core._hook_core_data()["privilege_escalation_reason"]
    assert settings.permission_reason != elevated.permission_reason


def test_a_redirection_is_read_as_a_write_only_for_an_output_operator():
    [command] = hook_core._Parser("cat < a > b >> c 2>&1 <<< d <> e").script(nested=False)
    assert [(word.value, word.operand, word.write) for word in command.words] == [
        ("cat", True, False),
        ("a", False, False),
        ("b", False, True),
        ("c", False, True),
        ("1", False, True),
        ("d", False, False),
        ("e", False, True),
    ]


def _read_current(case):
    return lambda _path: case["current"]


@pytest.mark.parametrize("case", _CASES["edit"], ids=lambda case: case["name"])
def test_the_edit_route_decides_as_the_shared_table_says(case):
    reason = harness_settings.edit_reason(case["tool_input"], _read_current(case), _DATA)
    if case["decision"] == "pass":
        assert reason is None
        return
    assert reason is not None
    assert case["file"] in reason
    assert "harness settings file" in reason
    assert "AKMON_ACTOR" in reason


def test_the_edit_route_reads_the_file_only_for_a_settings_file():
    def reader(path):
        raise AssertionError(f"read {path}")

    assert harness_settings.edit_reason({"file_path": "/p/src/x.py", "content": "x"}, reader, _DATA) is None


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/p/.claude/settings.json", "json"),
        ("/p/.claude/settings.local.json", "json"),
        ("/p/.claude/settingsX.json", "json"),
        ("/p/.claude/settings.jsonl", None),
        ("/p/.codex/config.toml", "toml"),
        ("~/.codex/config.toml", "toml"),
        ("/p/.codex/config.toml.bak", None),
        ("/p/.claude/settings", None),
        ("settings.json", None),
        ("", None),
        ("/", None),
    ],
)
def test_a_settings_file_is_named_by_its_last_two_segments(path, expected):
    assert harness_settings.file_format(path, _DATA) == expected


def test_the_shipped_data_lists_the_files_and_the_texts():
    assert [(entry["directory"], entry["pattern"], entry["format"]) for entry in _DATA["files"]] == [
        (".claude", "settings*.json", "json"),
        (".codex", "config.toml", "toml"),
    ]
    assert _DATA["toml_env_names"] == ["env", "shell_environment_policy"]
    assert set(_DATA["texts"]) == {"edit", "bash"}
    assert harness_settings.write_reason("x/.claude/settings.json", _DATA).count("x/.claude/settings.json") == 1


def test_the_data_is_the_one_owner_of_the_shell_programs(monkeypatch):
    changed = json.loads(json.dumps(_DATA))
    changed["shell"]["write_all_operands"] = []
    changed["shell"]["write_last_operand"] = ["ln"]
    monkeypatch.setattr(harness_settings, "read_data", lambda: changed)
    assert hook_core.privilege_escalation_guard_result("tee .claude/settings.json", "/p") is None
    assert hook_core.privilege_escalation_guard_result("ln -s x .claude/settings.json", "/p") is not None
    assert hook_core.privilege_escalation_guard_result("cp x .claude/settings.json", "/p") is None


def test_a_broken_data_file_is_a_data_file_error(monkeypatch):
    def broken(_path):
        raise jsondata.DataFileError("harness_settings.json is gone")

    monkeypatch.setattr(harness_settings.jsondata, "read", broken)
    with pytest.raises(jsondata.DataFileError, match="gone"):
        hook_core.privilege_escalation_guard_result("echo x > .claude/settings.json", "/p")


# --- the hook script -----------------------------------------------------------------------------------------


def _hook():
    path = Path(hook_core.__file__).parent / "settings-env-guard.py"
    spec = importlib.util.spec_from_file_location("settings_env_guard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(monkeypatch, capsys, payload):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert _hook().main() == 0
    return capsys.readouterr()


def _settings(tmp_path, text):
    path = tmp_path / ".claude" / "settings.json"
    path.parent.mkdir()
    if text is not None:
        path.write_text(text, encoding="utf-8")
    return path


def test_the_hook_denies_a_write_that_changes_the_env_of_the_file_on_disk(monkeypatch, capsys, tmp_path):
    path = _settings(tmp_path, '{"hooks": {}}')
    tool_input = {"file_path": str(path), "content": '{"env": {"AKMON_ACTOR": "autonomous"}}'}
    captured = _run(monkeypatch, capsys, {"tool_name": "Write", "tool_input": tool_input})
    output = json.loads(captured.out)["hookSpecificOutput"]
    assert (output["hookEventName"], output["permissionDecision"]) == ("PreToolUse", "deny")
    assert str(path) in output["permissionDecisionReason"]
    assert captured.err == ""


def test_the_hook_denies_an_edit_and_a_multiedit_the_same_way(monkeypatch, capsys, tmp_path):
    path = _settings(tmp_path, '{"env": {"A": "1"}, "x": 1}')
    change = {"old_string": '"A": "1"', "new_string": '"A": "2"'}
    other = {"old_string": '"x": 1', "new_string": '"x": 2'}
    edit = {"tool_name": "Edit", "tool_input": {"file_path": str(path), **change}}
    multi = {"tool_name": "MultiEdit", "tool_input": {"file_path": str(path), "edits": [other, change]}}
    for payload in (edit, multi):
        output = json.loads(_run(monkeypatch, capsys, payload).out)["hookSpecificOutput"]
        assert output["permissionDecision"] == "deny", payload["tool_name"]


def test_the_hook_passes_an_edit_that_leaves_the_env_identical(monkeypatch, capsys, tmp_path):
    path = _settings(tmp_path, '{"env": {"A": "1"}, "x": 1}')
    tool_input = {"file_path": str(path), "old_string": '"x": 1', "new_string": '"x": 2'}
    assert _run(monkeypatch, capsys, {"tool_name": "Edit", "tool_input": tool_input}).out == ""


def test_the_hook_creates_a_settings_file_without_an_env_and_denies_one_with(monkeypatch, capsys, tmp_path):
    path = _settings(tmp_path, None)
    ok = {"tool_name": "Write", "tool_input": {"file_path": str(path), "content": '{"permissions": {}}'}}
    assert _run(monkeypatch, capsys, ok).out == ""
    bad = {"tool_name": "Write", "tool_input": {"file_path": str(path), "content": '{"env": {"A": "1"}}'}}
    assert json.loads(_run(monkeypatch, capsys, bad).out)["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize(
    "payload",
    [
        {"tool_name": "Bash", "tool_input": {"command": "echo x > .claude/settings.json"}},
        {"tool_name": "Read", "tool_input": {"file_path": ".claude/settings.json"}},
        {"tool_name": "Write", "tool_input": "not an object"},
        {"tool_name": "Write", "tool_input": {"file_path": "/p/src/x.py", "content": "x"}},
        {"tool_name": "Write"},
        {},
    ],
)
def test_the_hook_ignores_what_is_no_edit_of_a_settings_file(monkeypatch, capsys, payload):
    assert _run(monkeypatch, capsys, payload).out == ""


def test_the_hook_treats_an_unreadable_file_as_absent(monkeypatch, capsys, tmp_path):
    path = _settings(tmp_path, None)
    path.write_bytes(b"\xff\xfe\x00 not utf-8")
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(path), "content": '{"permissions": {}}'}}
    assert _run(monkeypatch, capsys, payload).out == ""


def test_the_hook_is_crash_open_with_the_ordinary_notice(monkeypatch, capsys):
    hook = _hook()

    def crash():
        raise RuntimeError("seeded")

    monkeypatch.setattr(hook, "load_payload", crash)
    assert hook.main() == 0
    captured = capsys.readouterr()
    assert captured.err.splitlines() == ["akmon settings-env-guard hook: RuntimeError"]
    assert list(json.loads(captured.out)) == ["systemMessage"]


def test_the_claude_wiring_runs_the_hook_on_the_edit_tools_first():
    sync_data = json.loads((_AKMON / "bin" / "sync.json").read_text("utf-8"))
    blocks = {block["matcher"]: block["commands"] for block in sync_data["claude_hooks"]["PreToolUse"]}
    assert blocks["Edit|Write|MultiEdit"][0] == "settings-env-guard"
    assert sum(commands.count("settings-env-guard") for commands in blocks.values()) == 1
