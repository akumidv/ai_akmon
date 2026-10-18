"""The task-and-ordinal report names (C114): ``common/report_path.py``, twin of ``js/common/report_path.test.mjs``."""

from __future__ import annotations

from pathlib import Path

import pytest

from common import report_path
from common.report_path import create_report, next_report_path, report_prefix, safe_name, task_error


def test_safe_name_and_prefix_sanitise_like_a_gate_and_keep_the_task_case():
    assert safe_name("a b/ü") == "a-b-ü"
    assert safe_name("///") == ""
    assert report_prefix("stats", None) == "stats"
    assert report_prefix("stats", "C7") == "C7-stats"
    assert report_prefix("stats", "c7/x") == "c7-x-stats"


@pytest.mark.parametrize("task", ["///", "", "..."])
def test_a_task_with_no_usable_characters_is_an_error_not_no_task(task: str):
    """Owner decision (C114): a named task never silently vanishes from the report's name."""
    message = f"--task {task!r} has no usable characters (letters, digits, '_' or '-')"
    assert task_error(task) == message
    with pytest.raises(ValueError, match=r"has no usable characters") as caught:
        report_prefix("stats", task)
    assert str(caught.value) == message
    assert task_error(None) is None
    assert task_error("C7") is None


def test_no_task_and_a_missing_directory_give_base_1(tmp_path: Path):
    target = tmp_path / "absent"
    assert next_report_path(target, "coverage") == target / "coverage-1.md"
    made = create_report(target, "coverage", "x\n")
    assert made == target / "coverage-1.md"
    assert made.read_text(encoding="utf-8") == "x\n"


def test_with_a_task_one_past_the_largest_ordinal_of_exactly_that_prefix(tmp_path: Path):
    for name in ("C7-stats-1.md", "C7-stats-x.md", "stats-9.md", "C7-stats-full-5.md", "C7-stats-3.md.bak"):
        (tmp_path / name).write_text("", encoding="utf-8")
    prefix = report_prefix("stats", "C7")
    assert next_report_path(tmp_path, prefix) == tmp_path / "C7-stats-2.md"
    assert create_report(tmp_path, prefix, "y") == tmp_path / "C7-stats-2.md"


def test_non_matching_neighbours_are_ignored(tmp_path: Path):
    (tmp_path / "design-align-full-3.md").write_text("", encoding="utf-8")
    assert next_report_path(tmp_path, "design-align") == tmp_path / "design-align-1.md"
    assert next_report_path(tmp_path, "design-align-full") == tmp_path / "design-align-full-4.md"


def test_a_name_taken_between_scan_and_create_moves_on_never_overwrites(tmp_path: Path):
    (tmp_path / "stats-1.md").write_text("kept", encoding="utf-8")
    (tmp_path / "stats-2.md").write_text("kept", encoding="utf-8")
    assert create_report(tmp_path, "stats", "new", start=1) == tmp_path / "stats-3.md"
    assert (tmp_path / "stats-1.md").read_text(encoding="utf-8") == "kept"
    assert (tmp_path / "stats-3.md").read_text(encoding="utf-8") == "new"


def test_the_race_loser_takes_the_next_ordinal(monkeypatch, tmp_path: Path):
    """A concurrent run creates the scanned ordinal first: the exclusive create sees it and moves on."""
    real_open = Path.open

    def racing_open(self: Path, mode: str = "r", *args, **kwargs):
        if mode == "x" and self.name == "stats-1.md" and not self.exists():
            self.write_text("other run", encoding="utf-8")
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", racing_open)
    assert report_path.create_report(tmp_path, "stats", "mine") == tmp_path / "stats-2.md"
    assert (tmp_path / "stats-1.md").read_text(encoding="utf-8") == "other run"
