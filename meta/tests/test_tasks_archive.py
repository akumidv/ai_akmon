"""Tests for the tasks-archive tool (tools/tasks/archive.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_KEYSTONE = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("tasks_archive", _KEYSTONE / "tools" / "tasks" / "archive.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


archive = _load()


TASKS = """\
# TASKS

## Active

- C16 · gate-pack builder · ready · engineer · one package · [d](x)
- C21 · delegation indication · done · engineer · systemMessage per call · owner request
- C22 · corridor · active · engineer · corridor warning · [d](y)

Some trailing prose.
"""

ARCHIVE = """\
# Archive

## Done

- T0 · tooling · done · engineer · first thing
"""


# --------------------------------------------------------------------------------------
# field parsing
# --------------------------------------------------------------------------------------


def test_status_of_reads_third_dotted_field():
    assert archive._status_of("- C21 · title · done · engineer · goal") == "done"
    assert archive._status_of("- C16 · title · ready · engineer · goal") == "ready"
    assert archive._status_of("- lonely bullet") is None  # too few fields → no status


def test_entry_id_is_leading_field():
    assert archive._entry_id("- C21 · title · done · x") == "C21"


def test_multiword_status_is_not_done():
    # C22/C23 use "implemented, awaiting owner verify (D2)" — must not be swept.
    assert archive._status_of("- C22 · x · implemented, awaiting owner verify (D2) · engineer · g") != "done"


# --------------------------------------------------------------------------------------
# entry ranging (continuation lines)
# --------------------------------------------------------------------------------------


def test_parse_entries_absorbs_indented_continuation():
    lines = [
        "- C1 · a · done · e · g",
        "  a continuation note",
        "  and another",
        "- C2 · b · active · e · g",
    ]
    assert archive.parse_entries(lines) == [(0, 3), (3, 4)]


# --------------------------------------------------------------------------------------
# split_done
# --------------------------------------------------------------------------------------


def test_split_done_extracts_only_done_entries():
    remaining, blocks, ids = archive.split_done(TASKS)
    assert ids == ["C21"]
    assert blocks == [["- C21 · delegation indication · done · engineer · systemMessage per call · owner request"]]
    assert "C21" not in remaining
    assert "C16" in remaining and "C22" in remaining  # non-done entries stay


def test_split_done_moves_continuation_with_its_entry():
    text = "## Active\n\n- C1 · a · done · e · g\n  note line\n- C2 · b · active · e · g\n"
    remaining, blocks, ids = archive.split_done(text)
    assert ids == ["C1"]
    assert blocks == [["- C1 · a · done · e · g", "  note line"]]
    assert "note line" not in remaining and "C2" in remaining


def test_split_done_none_when_no_done_entries():
    text = "## Active\n\n- C1 · a · active · e · g\n"
    remaining, blocks, ids = archive.split_done(text)
    assert blocks == [] and ids == []


# --------------------------------------------------------------------------------------
# insert_into_archive
# --------------------------------------------------------------------------------------


def test_insert_into_archive_prepends_under_done_header():
    _, blocks, _ = archive.split_done(TASKS)
    out = archive.insert_into_archive(ARCHIVE, blocks)
    lines = out.splitlines()
    done_idx = lines.index("## Done")
    bullets = [ln for ln in lines[done_idx:] if ln.startswith("- ")]
    # The moved entry sits above the pre-existing T0 (newest-first); the header keeps its blank.
    assert bullets[0].startswith("- C21") and bullets[1].startswith("- T0")
    assert lines[done_idx + 1] == ""


def test_insert_into_archive_raises_without_done_section():
    try:
        archive.insert_into_archive("# Archive\n\nno done header\n", [["- C1 · a · done · e · g"]])
    except ValueError as exc:
        assert "## Done" in str(exc)
    else:
        raise AssertionError("expected ValueError")


# --------------------------------------------------------------------------------------
# main() end to end
# --------------------------------------------------------------------------------------


def _write_pair(tmp_path: Path) -> Path:
    tasks = tmp_path / "TASKS.md"
    tasks.write_text(TASKS, encoding="utf-8")
    (tmp_path / "TASKS_ARCHIVE.md").write_text(ARCHIVE, encoding="utf-8")
    return tasks


def test_main_dry_run_lists_and_exits_1_without_mutating(tmp_path, capsys):
    tasks = _write_pair(tmp_path)
    before = tasks.read_text(encoding="utf-8")
    assert archive.main(["--tasks", str(tasks)]) == 1
    assert "C21" in capsys.readouterr().out
    assert tasks.read_text(encoding="utf-8") == before  # dry-run never writes


def test_main_apply_moves_entry_and_is_idempotent(tmp_path, capsys):
    tasks = _write_pair(tmp_path)
    archive_path = tmp_path / "TASKS_ARCHIVE.md"

    assert archive.main(["--tasks", str(tasks), "--apply"]) == 0
    assert "archived 1: C21" in capsys.readouterr().out
    assert "C21" not in tasks.read_text(encoding="utf-8")
    assert "C21" in archive_path.read_text(encoding="utf-8")

    # Second run: nothing left to move.
    assert archive.main(["--tasks", str(tasks), "--apply"]) == 0
    assert "no done entries" in capsys.readouterr().out


def test_main_no_done_entries_exits_0(tmp_path, capsys):
    tasks = tmp_path / "TASKS.md"
    tasks.write_text("## Active\n\n- C1 · a · active · e · g\n", encoding="utf-8")
    (tmp_path / "TASKS_ARCHIVE.md").write_text(ARCHIVE, encoding="utf-8")
    assert archive.main(["--tasks", str(tasks)]) == 0
    assert "no done entries" in capsys.readouterr().out


def test_main_missing_tasks_file_errors(tmp_path):
    assert archive.main(["--tasks", str(tmp_path / "nope.md")]) == 2


# --------------------------------------------------------------------------------------
# _set_status / mark_done (--done flip)
# --------------------------------------------------------------------------------------


def test_set_status_replaces_only_the_status_cell_and_keeps_spacing():
    out = archive._set_status("- C16 · gate-pack builder · ready · engineer · one package", "done")
    assert out == "- C16 · gate-pack builder · done · engineer · one package"


def test_set_status_leaves_malformed_bullet_untouched():
    assert archive._set_status("- lonely bullet", "done") == "- lonely bullet"


def test_mark_done_flips_named_entries_and_reports_missing():
    text, missing = archive.mark_done(TASKS, ["C16", "C99"])
    assert missing == ["C99"]  # not a top-level entry
    # C16 flipped ready -> done; C22 (not named) untouched.
    assert "- C16 · gate-pack builder · done · engineer · one package · [d](x)" in text
    assert "- C22 · corridor · active · engineer" in text


def test_mark_done_is_idempotent_on_already_done():
    text, missing = archive.mark_done(TASKS, ["C21"])
    assert missing == []
    assert text.count("- C21 · delegation indication · done") == 1


# --------------------------------------------------------------------------------------
# malformed_entries (advisory)
# --------------------------------------------------------------------------------------


def test_malformed_entries_flags_task_shaped_bullet_without_status():
    lines = [
        "- C24 · title only",  # task id, dropped the status field -> flagged
        "- C25 · title · ready · engineer · goal",  # well-formed -> not flagged
        "- some prose bullet without an id",  # not task-shaped -> not flagged
    ]
    assert archive.malformed_entries(lines) == ["- C24 · title only"]


# --------------------------------------------------------------------------------------
# main() --done end to end
# --------------------------------------------------------------------------------------


def test_main_done_flag_flips_then_moves_on_apply(tmp_path, capsys):
    tasks = _write_pair(tmp_path)
    archive_path = tmp_path / "TASKS_ARCHIVE.md"
    # C16 starts `ready`; --done closes and archives it in one call (plus the pre-existing C21).
    assert archive.main(["--tasks", str(tasks), "--done", "C16", "--apply"]) == 0
    out = capsys.readouterr().out
    assert "C16" in out and "C21" in out
    remaining = tasks.read_text(encoding="utf-8")
    assert "C16" not in remaining and "C21" not in remaining and "C22" in remaining
    archived = archive_path.read_text(encoding="utf-8")
    assert "- C16 · gate-pack builder · done" in archived


def test_main_done_dry_run_reports_without_writing(tmp_path, capsys):
    tasks = _write_pair(tmp_path)
    before = tasks.read_text(encoding="utf-8")
    assert archive.main(["--tasks", str(tasks), "--done", "C16"]) == 1
    assert "C16" in capsys.readouterr().out
    assert tasks.read_text(encoding="utf-8") == before  # dry-run never writes


def test_main_done_unknown_id_fails_closed(tmp_path, capsys):
    tasks = _write_pair(tmp_path)
    before = tasks.read_text(encoding="utf-8")
    assert archive.main(["--tasks", str(tasks), "--done", "C99", "--apply"]) == 2
    assert "no such entry: C99" in capsys.readouterr().err
    assert tasks.read_text(encoding="utf-8") == before  # nothing written on a typo


def test_main_warns_on_malformed_entry(tmp_path, capsys):
    tasks = tmp_path / "TASKS.md"
    tasks.write_text("## Active\n\n- C24 · title only\n- C21 · x · done · e · g\n", encoding="utf-8")
    (tmp_path / "TASKS_ARCHIVE.md").write_text(ARCHIVE, encoding="utf-8")
    archive.main(["--tasks", str(tasks), "--apply"])
    assert "missing a status field" in capsys.readouterr().err
