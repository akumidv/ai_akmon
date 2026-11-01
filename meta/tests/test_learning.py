"""The learning run's record, reminder, hooks and CLI (C177, ADR 0026/D07).

The JavaScript twin pins the same cases in ``js/common/learning.test.mjs``,
``js/hooks/learning-reminder.test.mjs`` and ``js/akmon/_learn.test.mjs``.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import hook_core
import pytest

from akmon import _learn
from common import learning
from common.transcripts import transcripts_dir

NOW = datetime(2026, 10, 28, 9, 30, 0, tzinfo=UTC)
DATA = learning.read_data()


@pytest.fixture(autouse=True)
def _hermetic_environment(monkeypatch):
    monkeypatch.delenv(DATA["second_opinion_variable"], raising=False)
    monkeypatch.delenv(DATA["attended_variable"], raising=False)


def _project(tmp_path: Path, record: str | None = None) -> Path:
    root = tmp_path / "proj"
    (root / "_aitna").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (root / "_aitna" / ".akmon.toml").write_text(record or 'mount = "package"\n', encoding="utf-8")
    return root


def _ago(days: float) -> str:
    return learning.format_utc(NOW - timedelta(days=days))


def _seed(path: Path, *, last_run: str | None, since: str | None, sessions: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"last_run": last_run, "since": since, "sessions": sessions}), encoding="utf-8")


# --- state -----------------------------------------------------------------------------


def test_state_lives_in_the_local_layer_of_the_dev_root(tmp_path):
    root = _project(tmp_path)
    assert learning.state_path(root, DATA) == root / "_aitna" / ".local" / "learning.json"
    (root / ".aitna-root").write_text("meta\n", encoding="utf-8")
    assert learning.state_path(root, DATA) == root / "meta" / ".local" / "learning.json"


def test_recording_dedupes_a_known_session_and_starts_the_count_once(tmp_path):
    path = tmp_path / "learning.json"
    first = learning.record_session(path, "s1", NOW, DATA)
    assert (first.last_run, first.since, first.sessions) == (None, learning.format_utc(NOW), ("s1",))
    later = learning.record_session(path, "s2", NOW + timedelta(days=1), DATA)
    assert later.since == first.since
    again = learning.record_session(path, "s1", NOW + timedelta(days=2), DATA)  # resumed or compacted
    assert again.sessions == ("s1", "s2")
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "last_run": None,
        "since": "2026-10-28T09:30:00Z",
        "sessions": ["s1", "s2"],
    }


def test_a_known_session_writes_nothing(tmp_path):
    path = tmp_path / "learning.json"
    learning.record_session(path, "s1", NOW, DATA)
    before = path.stat().st_mtime_ns
    learning.record_session(path, "s1", NOW + timedelta(days=1), DATA)
    assert path.stat().st_mtime_ns == before


def test_writes_are_atomic_and_leave_no_temporary_file(tmp_path, monkeypatch):
    path = tmp_path / ".local" / "learning.json"
    learning.record_session(path, "s1", NOW, DATA)
    assert sorted(item.name for item in path.parent.iterdir()) == ["learning.json"]

    def refuse(self, target):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(OSError, match="disk full"):
        learning.record_session(path, "s2", NOW, DATA)
    assert sorted(item.name for item in path.parent.iterdir()) == ["learning.json"]
    assert learning.read_state(path).sessions == ("s1",)  # the old file survived whole


@pytest.mark.parametrize(
    "text",
    ["", "{not json", "[]", '{"sessions": "s1"}', '{"sessions": [1]}', '{"last_run": "yesterday", "sessions": []}'],
)
def test_a_missing_or_corrupt_file_is_empty_state_and_is_rewritten(tmp_path, text):
    path = tmp_path / "learning.json"
    assert learning.read_state(path) == learning.LearningState()
    path.write_text(text, encoding="utf-8")
    assert learning.read_state(path) == learning.LearningState()
    assert learning.record_session(path, "s1", NOW, DATA).sessions == ("s1",)
    assert learning.read_state(path).sessions == ("s1",)


def test_mark_run_records_the_end_and_clears_the_sessions(tmp_path):
    path = tmp_path / "learning.json"
    learning.record_session(path, "s1", NOW - timedelta(days=3), DATA)
    marked = learning.mark_run(path, NOW, DATA)
    assert marked == learning.LearningState("2026-10-28T09:30:00Z", None, ())
    assert learning.read_state(path) == marked
    assert (
        learning.record_session(path, "s2", NOW + timedelta(days=1), DATA).since is None
    )  # a run exists: days count from it


@pytest.mark.parametrize(
    "text", ["2026-1-5T1:2:3Z", "2026-02-30T00:00:00Z", "2026-10-28T09:30:00", "٢٠٢٦-10-28T09:30:00Z"]
)
def test_parse_utc_refuses_anything_but_the_recorded_shape(text):
    with pytest.raises(ValueError, match=r"UTC|day is out of range|does not match"):
        learning.parse_utc(text)


# --- thresholds ------------------------------------------------------------------------


def test_thresholds_default_to_ten_sessions_and_seven_days(tmp_path):
    assert learning.read_thresholds(_project(tmp_path), DATA) == learning.Thresholds(10, 7)


def test_thresholds_are_overridden_by_the_learning_table(tmp_path):
    record = 'mount = "package"\n[learning]\nreminder_sessions = 3\nreminder_days = 2\n'
    assert learning.read_thresholds(_project(tmp_path, record), DATA) == learning.Thresholds(3, 2)


@pytest.mark.parametrize("value", ['"many"', "0", "-4", "true", "2.5"])
def test_an_invalid_threshold_falls_back_to_the_default(tmp_path, value):
    record = f'mount = "package"\n[learning]\nreminder_sessions = {value}\nreminder_days = {value}\n'
    assert learning.read_thresholds(_project(tmp_path, record), DATA) == learning.Thresholds(10, 7)


def test_reminder_needs_a_session_and_then_either_threshold():
    thresholds = learning.Thresholds(3, 7)
    state = learning.LearningState
    assert learning.reminder_due(state(), thresholds, NOW) is None
    assert learning.reminder_due(state(_ago(30), None, ()), thresholds, NOW) is None  # days alone never
    assert learning.reminder_due(state(_ago(1), _ago(1), ("a", "b")), thresholds, NOW) is None
    assert learning.reminder_due(state(_ago(1), _ago(1), ("a", "b", "c")), thresholds, NOW) == learning.Due(
        3, 1, since_run=True
    )
    assert learning.reminder_due(state(_ago(7), None, ("a",)), thresholds, NOW) == learning.Due(1, 7, since_run=True)
    assert learning.reminder_due(state(_ago(6.9), None, ("a",)), thresholds, NOW) is None
    assert learning.reminder_due(state(None, _ago(8), ("a",)), thresholds, NOW) == learning.Due(1, 8, since_run=False)


def _remind(path: Path, session_id: str, now: datetime, thresholds: learning.Thresholds, *, attended: bool = True):
    event = learning.SessionEvent(session_id, "startup", attended)
    return learning.record_and_remind(path, event, thresholds, now, DATA)


def test_a_session_counts_only_once_it_has_passed(tmp_path):
    path = tmp_path / "learning.json"
    thresholds = learning.Thresholds(3, 7)
    # two sessions have passed: the third starting is not yet a third that "has passed"
    assert _remind(path, "s1", NOW, thresholds) is None
    assert _remind(path, "s2", NOW, thresholds) is None
    assert _remind(path, "s3", NOW, thresholds) is None
    assert _remind(path, "s4", NOW, thresholds) is not None  # three have passed
    assert learning.read_state(path).sessions == ("s1", "s2", "s3", "s4")


def test_after_a_run_the_days_threshold_waits_for_a_session_that_has_passed(tmp_path):
    path = tmp_path / "learning.json"
    thresholds = learning.Thresholds(10, 7)
    learning.mark_run(path, NOW, DATA)
    later = NOW + timedelta(days=14)
    assert _remind(path, "s1", later, thresholds) is None  # 14 days, but no session has passed yet
    reminder = _remind(path, "s2", later, thresholds)  # s1 has passed
    assert reminder is not None
    assert "1 session and 14 days" in reminder[1]


def test_an_unattended_run_is_recorded_but_never_reminded(tmp_path):
    path = tmp_path / "learning.json"
    thresholds = learning.Thresholds(1, 7)
    assert _remind(path, "s1", NOW, thresholds) is None
    assert _remind(path, "s2", NOW, thresholds, attended=False) is None
    assert learning.read_state(path).sessions == ("s1", "s2")
    assert _remind(path, "s3", NOW, thresholds) is not None


def test_the_session_event_reads_the_environment_it_is_handed():
    attended, variable = DATA["attended_variable"], DATA["second_opinion_variable"]
    assert learning.session_event("s", "startup", {}, DATA) == learning.SessionEvent("s", "startup", attended=True)
    assert learning.session_event("s", "startup", {attended: "1"}, DATA).attended is True
    assert learning.session_event("s", "startup", {attended: "0"}, DATA).attended is False
    assert learning.session_event("s", "startup", {variable: "1"}, DATA) is None


def test_a_held_lock_makes_the_hook_give_up_silently_and_mark_fail(tmp_path):
    path = tmp_path / "learning.json"
    lock = tmp_path / "learning.json.lock"
    lock.write_text("1\n", encoding="utf-8")
    assert _remind(path, "s1", NOW, learning.Thresholds(1, 1)) is None
    assert not path.exists()
    with pytest.raises(learning.StateLockedError, match="held by another process"):
        learning.mark_run(path, NOW, DATA)
    assert lock.exists()  # a lock we did not take is never ours to remove


def test_a_stale_lock_is_taken_over_and_a_finished_write_leaves_none(tmp_path):
    path = tmp_path / "learning.json"
    lock = tmp_path / "learning.json.lock"
    lock.write_text("1\n", encoding="utf-8")
    old = (NOW - timedelta(days=1)).timestamp()
    os.utime(lock, (old, old))
    assert learning.record_session(path, "s1", NOW, DATA).sessions == ("s1",)
    assert not lock.exists()


def test_concurrent_recording_and_marking_lose_no_update(tmp_path):
    path = tmp_path / "learning.json"
    errors: list[BaseException] = []

    def record(session_id: str) -> None:
        try:
            learning.record_session(path, session_id, NOW, DATA)
        except BaseException as exc:  # noqa: BLE001 - reported to the test thread below
            errors.append(exc)

    workers = [threading.Thread(target=record, args=(f"s{index}",)) for index in range(6)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert errors == []
    assert sorted(learning.read_state(path).sessions) == [f"s{index}" for index in range(6)]


def test_reminder_texts_name_both_counts_with_singular_and_plural():
    model, owner = learning.reminder_texts(learning.Due(12, 3, since_run=True), DATA)
    assert owner == (
        "[akmon] learning: 12 sessions and 3 days since the last learning run — "
        "run the `learning` skill to review them."
    )
    assert "tell them once" in model and "`learning` skill" in model
    assert learning.reminder_texts(learning.Due(1, 1, since_run=True), DATA)[1].startswith(
        "[akmon] learning: 1 session and 1 day since"
    )
    assert "since akmon began counting" in learning.reminder_texts(learning.Due(1, 0, since_run=False), DATA)[1]


def test_a_compaction_is_silent_even_when_due():
    state = learning.LearningState(_ago(9), None, ("a",))
    thresholds = learning.Thresholds(10, 7)
    assert learning.session_reminder(state, "compact", thresholds, NOW, DATA) is None
    assert learning.session_reminder(state, "resume", thresholds, NOW, DATA) is not None


# --- hooks -----------------------------------------------------------------------------

_HOOKS = Path(learning.__file__).resolve().parent.parent / "hooks"


def _load_claude_hook():
    spec = importlib.util.spec_from_file_location("learning_reminder", _HOOKS / "learning-reminder.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_hook(root: Path, payload: dict, monkeypatch, capsys) -> str:
    hook = _load_claude_hook()
    monkeypatch.setattr(hook, "load_payload", lambda: {"cwd": str(root), **payload})
    assert hook.main() == 0
    return capsys.readouterr().out


def test_the_claude_hook_records_the_session_and_stays_silent_until_due(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, 'mount = "package"\n[learning]\nreminder_sessions = 2\n')
    assert _run_hook(root, {"session_id": "s1", "source": "startup"}, monkeypatch, capsys) == ""
    assert _run_hook(root, {"session_id": "s1", "source": "resume"}, monkeypatch, capsys) == ""  # known id: not counted
    assert _run_hook(root, {"session_id": "s2", "source": "startup"}, monkeypatch, capsys) == ""  # s1 only has passed
    out = _run_hook(root, {"session_id": "s3", "source": "startup"}, monkeypatch, capsys)
    document = json.loads(out)
    assert document["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "`learning` skill" in document["hookSpecificOutput"]["additionalContext"]
    assert document["systemMessage"].startswith("[akmon] learning: 2 sessions and 0 days since akmon began counting")
    assert learning.read_state(root / "_aitna" / ".local" / "learning.json").sessions == ("s1", "s2", "s3")


def test_the_claude_hook_does_not_remind_on_a_compaction_and_never_without_an_id_counts(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, 'mount = "package"\n[learning]\nreminder_sessions = 1\n')
    assert _run_hook(root, {"session_id": "s1", "source": "compact"}, monkeypatch, capsys) == ""
    assert (
        _run_hook(root, {"source": "startup"}, monkeypatch, capsys) != ""
    )  # reads state, s1 counts, id-less is not added
    assert learning.read_state(root / "_aitna" / ".local" / "learning.json").sessions == ("s1",)


def test_the_claude_hook_neither_records_nor_reminds_a_second_opinion_run(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, 'mount = "package"\n[learning]\nreminder_sessions = 1\n')
    path = root / "_aitna" / ".local" / "learning.json"
    _seed(path, last_run=None, since=_ago(1), sessions=["s0"])
    monkeypatch.setenv(DATA["second_opinion_variable"], "1")
    assert _run_hook(root, {"session_id": "so1", "source": "startup"}, monkeypatch, capsys) == ""
    assert learning.read_state(path).sessions == ("s0",)


def test_the_claude_hook_records_an_unattended_run_without_a_reminder(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, 'mount = "package"\n[learning]\nreminder_sessions = 1\n')
    path = root / "_aitna" / ".local" / "learning.json"
    _seed(path, last_run=None, since=_ago(1), sessions=["s0"])
    monkeypatch.setenv(DATA["attended_variable"], "0")
    assert _run_hook(root, {"session_id": "p1", "source": "startup"}, monkeypatch, capsys) == ""
    assert learning.read_state(path).sessions == ("s0", "p1")
    monkeypatch.setenv(DATA["attended_variable"], "1")
    assert _run_hook(root, {"session_id": "s1", "source": "startup"}, monkeypatch, capsys) != ""


def test_the_claude_hook_with_no_project_root_stays_silent_and_writes_no_file(tmp_path, monkeypatch, capsys):
    bare = tmp_path / "bare"
    bare.mkdir()
    assert _run_hook(bare, {"session_id": "s1", "source": "startup"}, monkeypatch, capsys) == ""
    assert list(bare.iterdir()) == []
    assert sorted(path.name for path in tmp_path.iterdir()) == ["bare"]


def test_the_claude_hook_survives_a_corrupt_state_file(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    path = root / "_aitna" / ".local" / "learning.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    assert _run_hook(root, {"session_id": "s1"}, monkeypatch, capsys) == ""
    assert learning.read_state(path).sessions == ("s1",)


def test_the_claude_hook_is_crash_open_when_the_state_cannot_be_written(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    (root / "_aitna" / ".local").write_text("a file where the local layer should be", encoding="utf-8")
    out = _run_hook(root, {"session_id": "s1"}, monkeypatch, capsys)
    assert json.loads(out) == {"systemMessage": hook_core.hook_failure_notice("learning-reminder", FileExistsError())}


def _codex_hook():
    spec = importlib.util.spec_from_file_location("codex_hook", _HOOKS / "codex-hook.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_codex_route_prints_only_the_model_half(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, 'mount = "package"\n[learning]\nreminder_sessions = 1\n')
    _seed(root / "_aitna" / ".local" / "learning.json", last_run=None, since=_ago(0), sessions=["c0"])
    hook = _codex_hook()
    monkeypatch.setattr(hook, "load_payload", lambda: {"cwd": str(root), "session_id": "c1", "source": "startup"})
    assert hook.main(["learning-reminder"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert set(document) == {"hookSpecificOutput"}
    assert "`learning` skill" in document["hookSpecificOutput"]["additionalContext"]


def test_the_codex_route_neither_records_nor_reminds_a_second_opinion_run(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, 'mount = "package"\n[learning]\nreminder_sessions = 1\n')
    path = root / "_aitna" / ".local" / "learning.json"
    _seed(path, last_run=None, since=_ago(1), sessions=["c0"])
    monkeypatch.setenv(DATA["second_opinion_variable"], "1")
    hook = _codex_hook()
    monkeypatch.setattr(hook, "load_payload", lambda: {"cwd": str(root), "session_id": "so", "source": "startup"})
    assert hook.main(["learning-reminder"]) == 0
    assert capsys.readouterr().out == ""
    assert learning.read_state(path).sessions == ("c0",)


def test_the_codex_route_skips_recording_an_unidentified_session(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    hook = _codex_hook()
    monkeypatch.setattr(hook, "load_payload", lambda: {"cwd": str(root)})
    assert hook.main(["learning-reminder"]) == 0
    assert capsys.readouterr().out == ""
    assert not (root / "_aitna" / ".local" / "learning.json").exists()


# --- CLI -------------------------------------------------------------------------------


class _Cli:
    def __init__(self, tmp_path: Path, record: str | None = None) -> None:
        self.root = _project(tmp_path, record)
        self.claude = tmp_path / "claude"
        self.codex = tmp_path / "codex"
        self.state = self.root / "_aitna" / ".local" / "learning.json"
        self.out, self.err = io.StringIO(), io.StringIO()

    def run(self, *argv: str, now: datetime = NOW) -> int:
        self.out.seek(0)
        self.out.truncate()
        self.err.seek(0)
        self.err.truncate()
        environ = {"CLAUDE_CONFIG_DIR": str(self.claude), "CODEX_HOME": str(self.codex)}
        return _learn.main(argv, _learn.LearnIO(environ, self.root, self.out, self.err, lambda: now))

    def transcript(self, name: str, project: Path, when: datetime) -> Path:
        path = transcripts_dir(project, self.claude) / f"{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
        os.utime(path, (when.timestamp(), when.timestamp()))
        return path


def test_status_without_a_record_says_nothing_has_run_or_been_counted(tmp_path):
    cli = _Cli(tmp_path)
    assert cli.run("status") == 0
    assert cli.out.getvalue() == (
        "last run: never\n"
        "counting since: no session recorded yet\n"
        "sessions since the last run: 0\n"
        "days since the last run (or since counting began): -\n"
        "reminder at 10 sessions or 7 days (from <dev root>/.akmon.toml [learning])\n"
        "state: _aitna/.local/learning.json\n"
    )


def test_status_reports_sessions_days_and_the_configured_thresholds(tmp_path):
    cli = _Cli(tmp_path, 'mount = "package"\n[learning]\nreminder_days = 3\n')
    _seed(cli.state, last_run=_ago(5), since=None, sessions=["a", "b"])
    assert cli.run("status") == 0
    assert cli.out.getvalue() == (
        "last run: 2026-10-23T09:30:00Z\n"
        "counting since: no session recorded yet\n"
        "sessions since the last run: 2\n"
        "days since the last run (or since counting began): 5\n"
        "reminder at 10 sessions or 3 days (from <dev root>/.akmon.toml [learning])\n"
        "state: _aitna/.local/learning.json\n"
    )


def test_sessions_lists_this_projects_files_since_the_last_run_and_never_other_projects(tmp_path):
    cli = _Cli(tmp_path)
    other = tmp_path / "other-project"
    cli.transcript("before", cli.root, NOW - timedelta(days=9))
    mine = cli.transcript("after", cli.root, NOW - timedelta(days=1))
    cli.transcript("foreign", other, NOW - timedelta(days=1))
    rollouts = cli.codex / "sessions" / "2026" / "10" / "27"
    rollouts.mkdir(parents=True)
    for name, cwd in (("mine", cli.root), ("foreign", other)):
        meta = {"type": "session_meta", "payload": {"id": f"codex-{name}", "cwd": str(cwd), "source": "cli"}}
        (rollouts / f"rollout-{name}.jsonl").write_text(json.dumps(meta) + "\n", encoding="utf-8")
        stamp = (NOW - timedelta(days=1)).timestamp()
        os.utime(rollouts / f"rollout-{name}.jsonl", (stamp, stamp))
    _seed(cli.state, last_run=_ago(4), since=None, sessions=[])

    assert cli.run("sessions") == 0
    lines = cli.out.getvalue().splitlines()
    assert lines[0].startswith("akmon learn: listed at 2026-10-28T09:30:00Z")
    assert lines[1] == "kind\tsession\tmodified\tbytes\tpath"
    rows = [line.split("\t") for line in lines[2:]]
    assert sorted((row[0], row[1]) for row in rows) == [("claude", "after"), ("codex", "codex-mine")]
    assert [row[4] for row in rows if row[0] == "claude"] == [str(mine)]
    assert {row[2] for row in rows} == {"2026-10-27T09:30:00Z"}
    assert "foreign" not in cli.out.getvalue() and "before" not in cli.out.getvalue()


def test_sessions_with_no_run_lists_everything_and_says_so_when_there_is_nothing(tmp_path):
    cli = _Cli(tmp_path)
    assert cli.run("sessions") == 0
    assert cli.out.getvalue().splitlines()[1:] == ["akmon learn: no sessions of this project found"]
    cli.transcript("only", cli.root, NOW - timedelta(days=40))
    assert cli.run("sessions") == 0
    assert "\tonly\t" in cli.out.getvalue()
    _seed(cli.state, last_run=_ago(1), since=None, sessions=[])
    assert cli.run("sessions") == 0
    assert cli.out.getvalue().splitlines()[1:] == [
        "akmon learn: no sessions of this project since 2026-10-27T09:30:00Z"
    ]


def test_sessions_prints_the_listing_time_first_and_mark_at_stamps_it(tmp_path):
    cli = _Cli(tmp_path)
    _seed(cli.state, last_run=None, since=_ago(9), sessions=["a"])
    assert cli.run("sessions") == 0
    assert cli.out.getvalue().splitlines()[0] == (
        "akmon learn: listed at 2026-10-28T09:30:00Z (pass it as `akmon learn mark --at 2026-10-28T09:30:00Z`)"
    )
    assert cli.run("mark", "--at", "2026-10-28T09:29:00Z", now=NOW + timedelta(minutes=5)) == 0
    assert json.loads(cli.state.read_text(encoding="utf-8"))["last_run"] == "2026-10-28T09:29:00Z"
    assert cli.run("mark", "--at", "2999-01-01T00:00:00Z") == 2
    assert "is after the current time 2026-10-28T09:30:00Z" in cli.err.getvalue()
    assert cli.run("mark", "--at", "yesterday") == 2
    assert cli.err.getvalue().startswith("akmon learn: ")


def test_sessions_before_the_first_run_are_bounded_by_since_and_all_lists_everything(tmp_path):
    cli = _Cli(tmp_path)
    cli.transcript("old", cli.root, NOW - timedelta(days=40))
    cli.transcript("new", cli.root, NOW - timedelta(days=1))
    _seed(cli.state, last_run=None, since=_ago(3), sessions=["new"])
    assert cli.run("sessions") == 0
    listing = cli.out.getvalue()
    assert "\tnew\t" in listing and "\told\t" not in listing
    assert cli.run("sessions", "--all") == 0
    listing = cli.out.getvalue()
    assert "\tnew\t" in listing and "\told\t" in listing
    cli.transcript("new", cli.root, NOW - timedelta(days=5))
    assert cli.run("sessions") == 0
    assert cli.out.getvalue().splitlines()[1] == "akmon learn: no sessions of this project since 2026-10-25T09:30:00Z"


def test_a_held_lock_is_one_line_and_exit_2_for_mark(tmp_path):
    cli = _Cli(tmp_path)
    cli.state.parent.mkdir(parents=True)
    (cli.state.parent / "learning.json.lock").write_text("1\n", encoding="utf-8")
    assert cli.run("mark") == 2
    assert "held by another process" in cli.err.getvalue()
    assert cli.err.getvalue().count("\n") == 1


def test_mark_records_the_run_clears_the_sessions_and_status_follows(tmp_path):
    cli = _Cli(tmp_path)
    _seed(cli.state, last_run=None, since=_ago(9), sessions=["a", "b", "c"])
    assert cli.run("mark") == 0
    assert cli.out.getvalue() == (
        "akmon learn: learning run recorded at 2026-10-28T09:30:00Z; the counted sessions are cleared\n"
    )
    assert json.loads(cli.state.read_text(encoding="utf-8")) == {
        "last_run": "2026-10-28T09:30:00Z",
        "since": None,
        "sessions": [],
    }
    assert cli.run("status", now=NOW + timedelta(days=2)) == 0
    assert "sessions since the last run: 0" in cli.out.getvalue()
    assert "days since the last run (or since counting began): 2" in cli.out.getvalue()


@pytest.mark.parametrize(
    "argv", [[], ["bogus"], ["status", "extra"], ["mark", "--now"], ["mark", "--at"], ["sessions", "--none"]]
)
def test_usage_errors_exit_2_with_the_usage_on_stderr(tmp_path, argv):
    cli = _Cli(tmp_path)
    assert cli.run(*argv) == 2
    assert "usage: akmon learn status | sessions [--all] | mark [--at TIME]" in cli.err.getvalue()
    assert cli.out.getvalue() == ""


def test_help_prints_the_usage_and_exits_0(tmp_path):
    cli = _Cli(tmp_path)
    assert cli.run("--help") == 0
    assert cli.out.getvalue().startswith("usage: akmon learn status | sessions [--all] | mark [--at TIME]")
    assert "[--project-root PATH]" in cli.out.getvalue().splitlines()[0]


def test_status_with_project_root_reads_that_project_from_any_directory(tmp_path):
    cli = _Cli(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    environ = {"CLAUDE_CONFIG_DIR": str(cli.claude), "CODEX_HOME": str(cli.codex)}
    io_ = _learn.LearnIO(environ, elsewhere, cli.out, cli.err, lambda: NOW)
    assert _learn.main(["status", "--project-root", str(cli.root)], io_) == 0
    assert "_aitna/.local/learning.json" in cli.out.getvalue()
    assert cli.err.getvalue() == ""


def test_mark_with_no_project_root_refuses_and_writes_nothing(tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    out, err = io.StringIO(), io.StringIO()
    environ = {"CLAUDE_CONFIG_DIR": str(tmp_path / "claude"), "CODEX_HOME": str(tmp_path / "codex")}
    assert _learn.main(["mark"], _learn.LearnIO(environ, bare, out, err, lambda: NOW)) == 2
    assert "no project root at or above" in err.getvalue()
    assert out.getvalue() == ""
    assert sorted(path.name for path in tmp_path.iterdir()) == ["bare"]
    assert list(bare.iterdir()) == []


def test_an_unwritable_local_layer_is_one_line_and_exit_2(tmp_path):
    cli = _Cli(tmp_path)
    (cli.root / "_aitna" / ".local").write_text("a file", encoding="utf-8")
    assert cli.run("mark") == 2
    assert cli.err.getvalue().startswith("akmon learn: ")
    assert cli.err.getvalue().count("\n") == 1
