"""The work style: its resolver, the session store, the capture hook and the SessionStart line (ADR 0031/D03).

The JavaScript twin pins the same cases in ``js/common/work_style.test.mjs`` and
``js/hooks/work-style.test.mjs``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import hook_core
import pytest

from common import work_style

DATA = work_style.read_data()
_HOOKS = Path(work_style.__file__).resolve().parent.parent / "hooks"


def _project(tmp_path: Path, record: str = 'mount = "package"\n') -> Path:
    root = tmp_path / "proj"
    (root / "_aitna").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (root / "_aitna" / ".akmon.toml").write_text(record, encoding="utf-8")
    return root


def _local(root: Path, name: str) -> Path:
    return root / "_aitna" / ".local" / name


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- the data -----------------------------------------------------------------------------


def test_the_data_file_names_the_two_styles_and_their_locations():
    assert DATA["styles"] == ["delegating", "controlling"]
    assert DATA["default"] == "delegating"
    assert DATA["developer_rel"] == ".local/work.json"
    assert DATA["sessions_rel"] == ".local/work-sessions.json"
    assert DATA["sessions_keep"] == 50
    assert (DATA["record_section"], DATA["record_key"]) == ("work", "style")


# --- the resolver ---------------------------------------------------------------------------


def test_with_nothing_set_the_default_decides(tmp_path):
    assert work_style.resolve(_project(tmp_path), "s1", DATA) == work_style.WorkStyle("delegating", "default")


def test_a_project_style_decides_over_the_default(tmp_path):
    root = _project(tmp_path, 'mount = "package"\n[work]\nstyle = "controlling"\n')
    assert work_style.resolve(root, None, DATA) == work_style.WorkStyle("controlling", "project")


def test_a_developer_style_decides_over_the_project(tmp_path):
    root = _project(tmp_path, 'mount = "package"\n[work]\nstyle = "controlling"\n')
    _write(_local(root, "work.json"), '{"style": "delegating"}')
    assert work_style.resolve(root, None, DATA) == work_style.WorkStyle("delegating", "developer")


def test_a_session_style_decides_over_every_other_level(tmp_path):
    root = _project(tmp_path, 'mount = "package"\n[work]\nstyle = "delegating"\n')
    _write(_local(root, "work.json"), '{"style": "delegating"}')
    _write(_local(root, "work-sessions.json"), '{"sessions": {"s1": "controlling"}}')
    assert work_style.resolve(root, "s1", DATA) == work_style.WorkStyle("controlling", "session")
    assert work_style.resolve(root, "other", DATA).source == "developer"  # another session sees the next level
    assert work_style.resolve(root, None, DATA).source == "developer"


@pytest.mark.parametrize(
    "bad", ['{"style": "chaotic"}', '{"style": 3}', '{"style": null}', "{broken", "[]", '{"other": "controlling"}', ""]
)
def test_an_invalid_developer_file_falls_through_to_the_project(tmp_path, bad):
    root = _project(tmp_path, 'mount = "package"\n[work]\nstyle = "controlling"\n')
    _write(_local(root, "work.json"), bad)
    assert work_style.resolve(root, None, DATA) == work_style.WorkStyle("controlling", "project")


@pytest.mark.parametrize("record", ['[work]\nstyle = "chaotic"\n', "[work]\nstyle = 3\n", "work = 1\n", "[work]\n"])
def test_an_invalid_project_value_falls_through_to_the_default(tmp_path, record):
    root = _project(tmp_path, record)
    assert work_style.resolve(root, None, DATA) == work_style.WorkStyle("delegating", "default")


@pytest.mark.parametrize(
    "bad",
    [
        '{"sessions": {"s1": "chaotic"}}',
        '{"sessions": {"s1": 1}}',
        '{"sessions": []}',
        "{broken",
        '{"sessions": {"": "controlling"}}',
    ],
)
def test_an_invalid_session_entry_falls_through_to_the_developer(tmp_path, bad):
    root = _project(tmp_path)
    _write(_local(root, "work.json"), '{"style": "controlling"}')
    _write(_local(root, "work-sessions.json"), bad)
    assert work_style.resolve(root, "s1", DATA) == work_style.WorkStyle("controlling", "developer")


def test_a_valid_entry_survives_beside_an_invalid_one(tmp_path):
    root = _project(tmp_path)
    _write(_local(root, "work-sessions.json"), '{"sessions": {"a": "chaotic", "b": "controlling"}}')
    assert work_style.resolve(root, "a", DATA).source == "default"
    assert work_style.resolve(root, "b", DATA) == work_style.WorkStyle("controlling", "session")


def test_the_dev_root_is_the_one_the_project_declares(tmp_path):
    root = tmp_path / "proj"
    (root / "meta").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (root / ".aitna-root").write_text("meta\n", encoding="utf-8")
    (root / "meta" / ".akmon.toml").write_text('[work]\nstyle = "controlling"\n', encoding="utf-8")
    assert work_style.resolve(root, None, DATA) == work_style.WorkStyle("controlling", "project")
    _write(root / "meta" / ".local" / "work.json", '{"style": "delegating"}')
    assert work_style.resolve(root, None, DATA) == work_style.WorkStyle("delegating", "developer")


# --- the typed command --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("prompt", "typed"),
    [
        ("/style controlling", "controlling"),
        ("  /style   Delegating \n", "Delegating"),
        ("/style\tCONTROLLING", "CONTROLLING"),
        ("/style", ""),
        ("/style nonsense", "nonsense"),
        ("/style controlling now", "controlling now"),
        ("/style\ncontrolling", "controlling"),
    ],
)
def test_a_style_prompt_yields_the_text_after_the_command(prompt, typed):
    assert work_style.typed_style(prompt, DATA) == typed


@pytest.mark.parametrize(
    "prompt", ["", "hello", "/styles controlling", "please /style controlling", "/Style controlling", "/ style x"]
)
def test_any_other_prompt_is_not_the_command(prompt):
    assert work_style.typed_style(prompt, DATA) is None


def test_the_value_is_case_insensitive_and_exact_otherwise():
    assert work_style.known_style("CONTROLLING", DATA) == "controlling"
    assert work_style.known_style("Delegating", DATA) == "delegating"
    assert work_style.known_style("control", DATA) is None
    assert work_style.known_style("", DATA) is None


# --- the session store ----------------------------------------------------------------------------


def test_recording_writes_the_documented_shape_atomically(tmp_path):
    path = tmp_path / ".local" / "work-sessions.json"
    work_style.record_session_style(path, "s1", "controlling", DATA)
    assert path.read_text(encoding="utf-8") == '{\n  "sessions": {\n    "s1": "controlling"\n  }\n}\n'
    assert [item.name for item in path.parent.iterdir()] == ["work-sessions.json"]


def test_the_store_keeps_only_the_fifty_most_recent_sessions(tmp_path):
    path = tmp_path / "work-sessions.json"
    for number in range(60):
        work_style.record_session_style(path, f"s{number}", "controlling", DATA)
    kept = list(work_style.read_sessions(path, DATA))
    assert kept == [f"s{number}" for number in range(10, 60)]


def test_a_repeated_switch_moves_the_session_to_the_newest_place_and_replaces_its_style(tmp_path):
    path = tmp_path / "work-sessions.json"
    work_style.record_session_style(path, "a", "controlling", DATA)
    work_style.record_session_style(path, "b", "controlling", DATA)
    work_style.record_session_style(path, "a", "delegating", DATA)
    assert work_style.read_sessions(path, DATA) == {"b": "controlling", "a": "delegating"}
    assert list(work_style.read_sessions(path, DATA)) == ["b", "a"]


def test_recording_over_a_corrupt_store_replaces_it(tmp_path):
    path = tmp_path / "work-sessions.json"
    path.write_text("{broken", encoding="utf-8")
    work_style.record_session_style(path, "s1", "delegating", DATA)
    assert work_style.read_sessions(path, DATA) == {"s1": "delegating"}


def test_a_failed_write_leaves_no_temp_file(tmp_path, monkeypatch):
    path = tmp_path / "work-sessions.json"
    work_style.record_session_style(path, "s1", "delegating", DATA)

    def refuse(self, target):
        raise OSError("refused")

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(OSError, match="refused"):
        work_style.record_session_style(path, "s2", "controlling", DATA)
    assert [item.name for item in tmp_path.iterdir()] == ["work-sessions.json"]
    assert work_style.read_sessions(path, DATA) == {"s1": "delegating"}


# --- record_and_reply -------------------------------------------------------------------------------


def test_a_valid_command_records_and_confirms(tmp_path):
    root = _project(tmp_path)
    reply = work_style.record_and_reply(root, "s1", "/style Controlling", DATA)
    assert reply is not None
    assert "controlling" in reply
    assert "next park boundary" in reply
    assert work_style.resolve(root, "s1", DATA) == work_style.WorkStyle("controlling", "session")


def test_an_invalid_value_names_the_allowed_values_and_records_nothing(tmp_path):
    root = _project(tmp_path)
    reply = work_style.record_and_reply(root, "s1", "/style chaotic", DATA)
    assert reply is not None
    assert "'chaotic'" in reply
    assert "delegating, controlling" in reply
    assert not _local(root, "work-sessions.json").exists()


def test_a_bare_command_is_an_invalid_value(tmp_path):
    reply = work_style.record_and_reply(_project(tmp_path), "s1", "/style", DATA)
    assert reply is not None
    assert "delegating, controlling" in reply


def test_a_command_with_no_session_id_records_nothing_and_says_so(tmp_path):
    root = _project(tmp_path)
    reply = work_style.record_and_reply(root, None, "/style controlling", DATA)
    assert reply is not None
    assert "no session id" in reply
    assert ".local/work.json" in reply
    assert not _local(root, "work-sessions.json").exists()


def test_any_other_prompt_is_silent_and_writes_nothing(tmp_path):
    root = _project(tmp_path)
    assert work_style.record_and_reply(root, "s1", "refactor the parser", DATA) is None
    assert not (root / "_aitna" / ".local").exists()


# --- the Claude hook ---------------------------------------------------------------------------------


def _load(filename: str):
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py").replace("-", "_"), _HOOKS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_hook(root: Path, payload: dict, monkeypatch, capsys) -> str:
    hook = _load("work-style.py")
    monkeypatch.setattr(hook, "load_payload", lambda: {"cwd": str(root), **payload})
    assert hook.main() == 0
    return capsys.readouterr().out


def test_the_claude_hook_records_a_typed_switch_on_both_channels(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    out = _run_hook(
        root,
        {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "/style controlling"},
        monkeypatch,
        capsys,
    )
    document = json.loads(out)
    output = document["hookSpecificOutput"]
    assert output["hookEventName"] == "UserPromptSubmit"
    assert output["additionalContext"] == document["systemMessage"]
    assert "Work style recorded for this session: controlling" in output["additionalContext"]
    assert work_style.resolve(root, "s1", DATA).style == "controlling"


def test_the_claude_hook_names_the_allowed_values_for_an_invalid_one(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    out = _run_hook(root, {"session_id": "s1", "prompt": "/style fast"}, monkeypatch, capsys)
    assert "delegating, controlling" in json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert not _local(root, "work-sessions.json").exists()


@pytest.mark.parametrize(
    "payload",
    [{"session_id": "s1", "prompt": "write the tests"}, {"session_id": "s1"}, {"session_id": "s1", "prompt": 3}, {}],
)
def test_the_claude_hook_is_silent_on_any_other_prompt_and_writes_nothing(tmp_path, monkeypatch, capsys, payload):
    root = _project(tmp_path)
    assert _run_hook(root, payload, monkeypatch, capsys) == ""
    assert not (root / "_aitna" / ".local").exists()


def test_the_claude_hook_with_no_project_root_is_silent_and_writes_no_file(tmp_path, monkeypatch, capsys):
    bare = tmp_path / "bare"
    bare.mkdir()
    assert _run_hook(bare, {"session_id": "s1", "prompt": "/style controlling"}, monkeypatch, capsys) == ""
    assert list(bare.iterdir()) == []


def test_the_claude_hook_is_crash_open_when_the_store_cannot_be_written(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    (root / "_aitna" / ".local").write_text("a file where the local layer should be", encoding="utf-8")
    out = _run_hook(root, {"session_id": "s1", "prompt": "/style controlling"}, monkeypatch, capsys)
    assert json.loads(out) == {"systemMessage": hook_core.hook_failure_notice("work-style", FileExistsError())}


# --- the Codex route (M65) -----------------------------------------------------------------------------


def _codex_payload(root: Path, prompt: str) -> dict:
    """The ``UserPromptSubmit`` payload codex-cli 0.153.4 sends (M65): the exact key set, nothing more."""
    return {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "019e0000-aaaa-7000-8000-000000000001",
        "turn_id": "019e0000-bbbb-7000-8000-000000000002",
        "prompt": prompt,
        "cwd": str(root),
        "transcript_path": str(root / "rollout.jsonl"),
        "model": "gpt-5.5",
        "permission_mode": "default",
    }


def test_the_codex_route_records_the_style_from_the_m65_payload(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    payload = _codex_payload(root, "/style controlling")
    hook = _load("codex-hook.py")
    monkeypatch.setattr(hook, "load_payload", lambda: payload)
    assert hook.main(["work-style"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert set(document) == {"hookSpecificOutput"}  # no owner channel on Codex
    assert document["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "controlling" in document["hookSpecificOutput"]["additionalContext"]
    stored = json.loads(_local(root, "work-sessions.json").read_text(encoding="utf-8"))
    assert stored == {"sessions": {payload["session_id"]: "controlling"}}
    assert work_style.resolve(root, payload["session_id"], DATA) == work_style.WorkStyle("controlling", "session")


def test_the_codex_route_is_silent_on_any_other_prompt(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    hook = _load("codex-hook.py")
    monkeypatch.setattr(hook, "load_payload", lambda: _codex_payload(root, "fix the failing test"))
    assert hook.main(["work-style"]) == 0
    assert capsys.readouterr().out == ""
    assert not (root / "_aitna" / ".local").exists()


def test_the_codex_route_skips_an_unidentified_session_and_says_so(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    payload = {k: v for k, v in _codex_payload(root, "/style controlling").items() if k != "session_id"}
    hook = _load("codex-hook.py")
    monkeypatch.setattr(hook, "load_payload", lambda: payload)
    assert hook.main(["work-style"]) == 0
    assert "no session id" in json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    assert not _local(root, "work-sessions.json").exists()


# --- the SessionStart line ----------------------------------------------------------------------------------


def _with_agent(root: Path) -> Path:
    """A project with one dev agent charter, so ``session_start_result`` builds its full context."""
    (root / "_aitna" / "agents" / "development").mkdir(parents=True)
    (root / "_aitna" / "agents" / "development" / "README.md").write_text("# development\n", encoding="utf-8")
    return root


def _style_line(result) -> str:
    [line] = [line for line in result.additional_context.splitlines() if line.startswith("work style: ")]
    return line


def test_session_start_states_the_default_when_nothing_is_set(tmp_path):
    result = hook_core.session_start_result(_with_agent(_project(tmp_path)), "s1")
    assert _style_line(result) == "work style: delegating (default)"


def test_session_start_names_the_level_that_decided(tmp_path):
    root = _with_agent(_project(tmp_path, 'mount = "package"\n[work]\nstyle = "controlling"\n'))
    assert _style_line(hook_core.session_start_result(root)) == (
        "work style: controlling (from _aitna/.akmon.toml [work])"
    )
    _write(_local(root, "work.json"), '{"style": "delegating"}')
    assert _style_line(hook_core.session_start_result(root)) == "work style: delegating (from _aitna/.local/work.json)"
    _write(_local(root, "work-sessions.json"), '{"sessions": {"s1": "controlling"}}')
    assert _style_line(hook_core.session_start_result(root, "s1")) == (
        "work style: controlling (set in this session with /style)"
    )
    assert (
        _style_line(hook_core.session_start_result(root, "s2"))
        == "work style: delegating (from _aitna/.local/work.json)"
    )
