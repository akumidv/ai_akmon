"""``common/transcripts.py``: a project's transcript directory and the sessions a learning run may read (C177)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from common import transcripts


def _touch(path: Path, text: str, when: datetime) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.utime(path, (when.timestamp(), when.timestamp()))
    return path


def _at(day: int) -> datetime:
    return datetime(2026, 10, day, 12, 0, 0, tzinfo=UTC)


def test_munged_project_dir_replaces_every_non_alphanumeric_character():
    assert transcripts.munged_project_dir(Path("/home/ai/workspace/alphavar")) == "-home-ai-workspace-alphavar"
    # read off ~/.claude/projects: `_cto` became `--cto`, `.` and `-` stay dashes
    assert transcripts.munged_project_dir(Path("/home/a/workspace/_cto")) == "-home-a-workspace--cto"
    assert transcripts.munged_project_dir(Path("/srv/my.app")) == "-srv-my-app"


def test_transcripts_dir_under_claude_home(tmp_path):
    claude_home = tmp_path / "claude-home"
    root = tmp_path / "project"
    directory = transcripts.transcripts_dir(root, claude_home=claude_home)
    assert directory == claude_home / "projects" / transcripts.munged_project_dir(root)


def test_newest_jsonl_picks_most_recently_modified(tmp_path):
    older = _touch(tmp_path / "sessions" / "aaa.jsonl", "{}\n", _at(1))
    newer = _touch(tmp_path / "sessions" / "zzz.jsonl", "{}\n", _at(2))
    assert older != newer
    assert transcripts.newest_jsonl(tmp_path / "sessions") == newer


def test_newest_jsonl_missing_directory_returns_none(tmp_path):
    assert transcripts.newest_jsonl(tmp_path / "nope") is None


def test_newest_jsonl_ignores_non_jsonl_files(tmp_path):
    _touch(tmp_path / "sessions" / "notes.txt", "hi", _at(1))
    assert transcripts.newest_jsonl(tmp_path / "sessions") is None


def test_claude_sessions_lists_only_this_projects_files_modified_after_since(tmp_path):
    root, other = tmp_path / "proj", tmp_path / "other"
    home = tmp_path / "claude"
    mine = transcripts.transcripts_dir(root, home)
    _touch(mine / "old.jsonl", "{}\n", _at(1))
    _touch(mine / "new.jsonl", "{}\n{}\n", _at(5))
    _touch(mine / "notes.txt", "x", _at(6))
    _touch(mine / "new" / "subagents" / "agent-1.jsonl", "{}\n", _at(6))
    _touch(transcripts.transcripts_dir(other, home) / "foreign.jsonl", "{}\n", _at(6))

    everything = transcripts.claude_sessions(root, home)
    assert [item.session_id for item in everything] == ["old", "new"]
    assert {item.kind for item in everything} == {transcripts.CLAUDE}
    recent = transcripts.claude_sessions(root, home, since=_at(3))
    assert [(item.session_id, item.size, item.modified) for item in recent] == [("new", 6, _at(5))]
    assert transcripts.claude_sessions(tmp_path / "unknown", home) == []


def _rollout(path: Path, when: datetime, **payload: object) -> Path:
    meta = {"timestamp": "t", "type": "session_meta", "payload": payload}
    return _touch(path, json.dumps(meta) + "\n" + '{"type":"event_msg"}\n', when)


def test_codex_sessions_keeps_only_rollouts_recorded_in_this_project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    home = tmp_path / "codex"
    day = home / "sessions" / "2026" / "10" / "28"
    _rollout(day / "rollout-a.jsonl", _at(5), id="codex-mine", cwd=str(root), source="cli")
    _rollout(day / "rollout-b.jsonl", _at(5), id="codex-foreign", cwd=str(tmp_path / "other"), source="cli")
    _rollout(day / "rollout-c.jsonl", _at(5), id="codex-child", cwd=str(root), source={"subagent": {}})
    _rollout(day / "rollout-d.jsonl", _at(1), id="codex-old", cwd=str(root), source="exec")
    _touch(day / "rollout-e.jsonl", "not json\n", _at(5))
    _touch(day / "rollout-f.jsonl", json.dumps({"type": "other"}) + "\n", _at(5))

    found = transcripts.codex_sessions(root, home, since=_at(3))
    assert [(item.kind, item.session_id) for item in found] == [(transcripts.CODEX, "codex-mine")]
    assert [item.session_id for item in transcripts.codex_sessions(root, home)] == ["codex-old", "codex-mine"]


def test_codex_sessions_is_empty_without_a_codex_home(tmp_path):
    assert transcripts.codex_sessions(tmp_path, tmp_path / "no-codex") == []


def _claude_line(cwd: Path | str) -> str:
    return json.dumps({"type": "user", "cwd": str(cwd)}) + "\n"


def test_claude_sessions_count_directories_named_by_a_path_inside_the_root(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    home = tmp_path / "claude"
    projects = home / "projects"
    name = transcripts.munged_project_dir(root)
    bookkeeping = json.dumps({"type": "file-history-snapshot"}) + "\n"
    _touch(projects / name / "own.jsonl", "{}\n", _at(5))
    _touch(projects / f"{name}-sub" / "inside.jsonl", bookkeeping + _claude_line(root / "sub"), _at(5))
    _touch(projects / f"{name}-sub--hidden" / "deep.jsonl", _claude_line(root / "sub" / ".hidden"), _at(6))
    _touch(projects / f"{name}-x" / "sibling.jsonl", _claude_line(f"{root}-x"), _at(5))
    _touch(projects / f"{name}-nocwd" / "silent.jsonl", bookkeeping, _at(5))
    _touch(projects / f"{name}x" / "no-dash.jsonl", _claude_line(root), _at(5))
    _touch(projects / f"{name}-file", "not a directory", _at(5))

    found = transcripts.claude_sessions(root, home)
    assert sorted(item.session_id for item in found) == ["deep", "inside", "own"]


def test_a_session_file_that_vanishes_before_its_stat_is_skipped(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    home = tmp_path / "claude"
    directory = transcripts.transcripts_dir(root, home)
    _touch(directory / "keep.jsonl", "{}\n", _at(5))
    gone = _touch(directory / "gone.jsonl", "{}\n", _at(5))
    assert transcripts._modified_after(tmp_path / "missing.jsonl", None) is None
    real_modified_after = transcripts._modified_after

    def racing(path, since):
        if path == gone:
            gone.unlink()  # deleted after the directory listing and its is_file() check
        return real_modified_after(path, since)

    monkeypatch.setattr(transcripts, "_modified_after", racing)
    assert [item.session_id for item in transcripts.claude_sessions(root, home)] == ["keep"]


def test_codex_sessions_count_a_rollout_started_inside_the_root(tmp_path):
    root = tmp_path / "proj"
    (root / "sub").mkdir(parents=True)
    home = tmp_path / "codex"
    day = home / "sessions" / "2026" / "10" / "28"
    _rollout(day / "rollout-a.jsonl", _at(5), id="codex-root", cwd=str(root), source="cli")
    _rollout(day / "rollout-b.jsonl", _at(6), id="codex-sub", cwd=str(root / "sub"), source="cli")
    _rollout(day / "rollout-c.jsonl", _at(7), id="codex-sibling", cwd=f"{root}-x", source="cli")
    assert [item.session_id for item in transcripts.codex_sessions(root, home)] == ["codex-root", "codex-sub"]
