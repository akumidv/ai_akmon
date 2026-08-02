"""Tests for the D2 ledger tool (tools/d2_ledger/d2_ledger.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_KEYSTONE = Path(__file__).resolve().parents[2]

# The ``.akmon.toml`` reader uses ``tomllib`` (3.11+ stdlib) and degrades to ``{}`` on
# older hosts by design (see d2_ledger's own docstring) — these tests assert the full
# behaviour.
requires_tomllib = pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="tomllib is 3.11+ stdlib; .akmon.toml reading degrades to silent on older hosts by design",
)


def _load():
    spec = importlib.util.spec_from_file_location("d2_ledger", _KEYSTONE / "tools" / "d2_ledger" / "d2_ledger.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


d2 = _load()


LEDGER = """\
# D2 ledger — owner-verification points

> One entry per owner-verify point (guardrails/_common.md "Owner-verify any change to
> math, data shape, or architecture"). Pending on top; verified below. No dates — the
> landing commit is the timeline (D5: the tool never runs git; the owner supplies the sha).

## Pending

| id | kind | what | anchor | draft | second_opinion |
|----|------|------|--------|-------|----------------|
| D2-1 | math | reprice formula | src/x.py:42 |  |  |
| D2-3 | data-shape | new column | src/y.py:10 |  |  |

## Verified

| id | kind | what | anchor | commit |
|----|------|------|--------|--------|
| D2-2 | architecture | provider split | src/z.py:1 | abc1234 |
"""


# --------------------------------------------------------------------------------------
# row parsing helpers
# --------------------------------------------------------------------------------------


def test_split_row_parses_cells():
    assert d2._split_row("| a | b | c |") == ["a", "b", "c"]


def test_split_row_none_for_non_table_line():
    assert d2._split_row("## Pending") is None
    assert d2._split_row("") is None


def test_is_separator_row_detects_dashes():
    assert d2._is_separator_row(["----", "------", ":---:"])
    assert not d2._is_separator_row(["a", "b"])


def test_format_row_round_trips_through_split():
    row = ["D2-1", "math", "x", "y:1", "", ""]
    assert d2._split_row(d2._format_row(row)) == row


# --------------------------------------------------------------------------------------
# table_bounds / parse_table / parse_ledger
# --------------------------------------------------------------------------------------


def test_table_bounds_finds_pending_data_rows():
    lines = LEDGER.splitlines()
    start, end = d2.table_bounds(lines, d2.PENDING_HEADER)
    assert [d2._split_row(line)[0] for line in lines[start:end]] == ["D2-1", "D2-3"]


def test_table_bounds_empty_table_has_no_rows():
    start, end = d2.table_bounds(d2.SKELETON.splitlines(), d2.PENDING_HEADER)
    assert start == end


LEDGER_WITH_BLANK_ROW_GAP = """\
# D2 ledger — owner-verification points

## Pending

| id | kind | what | anchor | draft | second_opinion |
|----|------|------|--------|-------|----------------|
| D2-1 | math | reprice formula | src/x.py:42 |  |  |

| D2-3 | data-shape | new column | src/y.py:10 |  |  |

## Verified

| id | kind | what | anchor | commit |
|----|------|------|--------|--------|
"""


def test_table_bounds_tolerates_blank_line_within_pending_table():
    # A blank line used as a visual break between rows must not truncate the data range —
    # regression for the duplicate-id bug (D2-14's own ledger entry).
    lines = LEDGER_WITH_BLANK_ROW_GAP.splitlines()
    start, end = d2.table_bounds(lines, d2.PENDING_HEADER)
    ids = [row[0] for line in lines[start:end] if (row := d2._split_row(line)) is not None]
    assert ids == ["D2-1", "D2-3"]


def test_next_id_sees_rows_past_a_blank_line_gap():
    pending, verified = d2.parse_ledger(LEDGER_WITH_BLANK_ROW_GAP)
    assert [r[0] for r in pending] == ["D2-1", "D2-3"]
    assert d2.next_id(pending, verified) == "D2-4"


def test_add_entry_increments_past_a_blank_line_gap():
    new_text, new_id = d2.add_entry(LEDGER_WITH_BLANK_ROW_GAP, kind="architecture", what="x", anchor="z.py:1")
    assert new_id == "D2-4"
    pending, _ = d2.parse_ledger(new_text)
    assert [r[0] for r in pending] == ["D2-1", "D2-3", "D2-4"]


def test_table_bounds_missing_section_raises():
    try:
        d2.table_bounds(["# nope"], d2.PENDING_HEADER)
    except ValueError as exc:
        assert "Pending" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_parse_table_returns_cell_lists():
    rows = d2.parse_table(LEDGER, d2.PENDING_HEADER)
    assert rows == [
        ["D2-1", "math", "reprice formula", "src/x.py:42", "", ""],
        ["D2-3", "data-shape", "new column", "src/y.py:10", "", ""],
    ]


def test_parse_ledger_splits_pending_and_verified():
    pending, verified = d2.parse_ledger(LEDGER)
    assert [r[0] for r in pending] == ["D2-1", "D2-3"]
    assert [r[0] for r in verified] == ["D2-2"]


# --------------------------------------------------------------------------------------
# next_id
# --------------------------------------------------------------------------------------


def test_next_id_is_one_past_max_across_both_tables():
    pending, verified = d2.parse_ledger(LEDGER)
    assert d2.next_id(pending, verified) == "D2-4"


def test_next_id_starts_at_one_on_empty_ledger():
    pending, verified = d2.parse_ledger(d2.SKELETON)
    assert d2.next_id(pending, verified) == "D2-1"


# --------------------------------------------------------------------------------------
# add_entry / verify_entry
# --------------------------------------------------------------------------------------


def test_add_entry_appends_pending_row_with_new_id():
    new_text, new_id = d2.add_entry(d2.SKELETON, kind="math", what="thing", anchor="a.py:1")
    assert new_id == "D2-1"
    pending, verified = d2.parse_ledger(new_text)
    assert pending == [["D2-1", "math", "thing", "a.py:1", "", ""]]
    assert verified == []


def test_add_entry_increments_across_existing_entries():
    new_text, new_id = d2.add_entry(LEDGER, kind="architecture", what="split", anchor="b.py:9")
    assert new_id == "D2-4"
    pending, _ = d2.parse_ledger(new_text)
    assert pending[-1] == ["D2-4", "architecture", "split", "b.py:9", "", ""]


def test_verify_entry_moves_row_to_top_of_verified():
    new_text = d2.verify_entry(LEDGER, "D2-1", commit="deadbee")
    pending, verified = d2.parse_ledger(new_text)
    assert [r[0] for r in pending] == ["D2-3"]
    assert verified[0] == ["D2-1", "math", "reprice formula", "src/x.py:42", "deadbee"]
    assert verified[1][0] == "D2-2"  # pre-existing verified entry stays, pushed down


def test_verify_entry_missing_id_raises():
    try:
        d2.verify_entry(LEDGER, "D2-99", commit="x")
    except ValueError as exc:
        assert "D2-99" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_add_then_verify_round_trip_removes_from_pending():
    added_text, new_id = d2.add_entry(d2.SKELETON, kind="math", what="t", anchor="a.py:1")
    verified_text = d2.verify_entry(added_text, new_id, commit="c0ffee")
    pending, verified = d2.parse_ledger(verified_text)
    assert pending == []
    assert [r[0] for r in verified] == [new_id]


# --------------------------------------------------------------------------------------
# config: sensitive_paths / glob matching
# --------------------------------------------------------------------------------------


def test_matches_any_supports_double_star():
    assert d2._matches_any("src/alphavar/options/lib/x.py", ["src/**/lib/**"])
    assert not d2._matches_any("README.md", ["src/**/lib/**"])


def test_matches_any_double_star_spans_zero_segments():
    # ** matches zero or more whole segments (mirrors PurePath.full_match), so a direct child matches.
    assert d2._matches_any("a/b.py", ["a/**/b.py"])  # zero middle segments
    assert d2._matches_any("a/x/y/b.py", ["a/**/b.py"])  # several middle segments
    assert d2._matches_any("a/b.py", ["a/**/*.py"])  # * globs within the final segment
    assert not d2._matches_any("a/b.txt", ["a/**/*.py"])  # extension differs → no match


@requires_tomllib
def test_sensitive_paths_for_reads_akmon_toml(tmp_path):
    (tmp_path / ".akmon.toml").write_text('[d2_ledger]\nsensitive_paths = ["src/**/lib/**"]\n', encoding="utf-8")
    ledger = tmp_path / "sub" / "D2_LEDGER.md"
    ledger.parent.mkdir()
    ledger.write_text(d2.SKELETON, encoding="utf-8")
    assert d2.sensitive_paths_for(ledger) == ["src/**/lib/**"]


def test_sensitive_paths_for_absent_config_is_empty(tmp_path):
    ledger = tmp_path / "D2_LEDGER.md"
    ledger.write_text(d2.SKELETON, encoding="utf-8")
    assert d2.sensitive_paths_for(ledger) == []


def test_sensitive_paths_for_degrades_gracefully_without_tomllib(tmp_path, monkeypatch):
    # Host Python < 3.11 has no tomllib: skip config gracefully (no dependency added).
    import builtins

    (tmp_path / ".akmon.toml").write_text('[d2_ledger]\nsensitive_paths = ["src/**/lib/**"]\n', encoding="utf-8")
    ledger = tmp_path / "D2_LEDGER.md"
    ledger.write_text(d2.SKELETON, encoding="utf-8")

    real_import = builtins.__import__

    def no_tomllib(name, *args, **kwargs):
        if name == "tomllib":
            raise ImportError("simulated: no tomllib on this host")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_tomllib)
    assert d2.sensitive_paths_for(ledger) == []


# --------------------------------------------------------------------------------------
# main() end to end
# --------------------------------------------------------------------------------------


def test_main_add_creates_ledger_and_prints_id(tmp_path, capsys):
    ledger = tmp_path / "D2_LEDGER.md"
    assert not ledger.exists()
    rc = d2.main(["add", "--ledger", str(ledger), "--kind", "math", "--what", "thing", "--anchor", "a.py:1"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "D2-1"
    assert ledger.is_file()


def test_main_list_reports_no_pending_on_fresh_ledger(tmp_path, capsys):
    ledger = tmp_path / "D2_LEDGER.md"
    rc = d2.main(["list", "--ledger", str(ledger)])
    assert rc == 0
    assert "no pending D2 entries" in capsys.readouterr().out


def test_main_add_list_verify_round_trip(tmp_path, capsys):
    ledger = tmp_path / "D2_LEDGER.md"
    d2.main(["add", "--ledger", str(ledger), "--kind", "data-shape", "--what", "new col", "--anchor", "y.py:5"])
    capsys.readouterr()

    rc = d2.main(["list", "--ledger", str(ledger)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "D2-1" in out and "new col" in out and "y.py:5" in out

    rc = d2.main(["verify", "D2-1", "--ledger", str(ledger), "--commit", "abc1234"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "verified D2-1 (commit abc1234)" in out

    rc = d2.main(["list", "--ledger", str(ledger)])
    assert rc == 0
    assert "no pending D2 entries" in capsys.readouterr().out


def test_main_verify_missing_id_errors(tmp_path, capsys):
    ledger = tmp_path / "D2_LEDGER.md"
    d2.main(["add", "--ledger", str(ledger), "--kind", "math", "--what", "t", "--anchor", "a.py:1"])
    capsys.readouterr()
    rc = d2.main(["verify", "D2-99", "--ledger", str(ledger), "--commit", "x"])
    assert rc == 2
    assert "D2-99" in capsys.readouterr().err


def test_main_check_clean_when_no_pending(tmp_path, capsys):
    ledger = tmp_path / "D2_LEDGER.md"
    rc = d2.main(["check", "--ledger", str(ledger)])
    assert rc == 0
    assert "D2 ledger clean" in capsys.readouterr().out


def test_main_check_warns_when_pending_and_no_changed_filter(tmp_path, capsys):
    ledger = tmp_path / "D2_LEDGER.md"
    d2.main(["add", "--ledger", str(ledger), "--kind", "math", "--what", "t", "--anchor", "a.py:1"])
    capsys.readouterr()
    rc = d2.main(["check", "--ledger", str(ledger)])
    assert rc == 0  # warn-first: still exits 0 without --strict
    assert "D2-1" in capsys.readouterr().err


def test_main_check_strict_exits_1_on_would_warn(tmp_path, capsys):
    ledger = tmp_path / "D2_LEDGER.md"
    d2.main(["add", "--ledger", str(ledger), "--kind", "math", "--what", "t", "--anchor", "a.py:1"])
    capsys.readouterr()
    rc = d2.main(["check", "--ledger", str(ledger), "--strict"])
    assert rc == 1
    assert "D2-1" in capsys.readouterr().err


@requires_tomllib
def test_main_check_changed_paths_filtered_by_sensitive_globs(tmp_path, capsys):
    (tmp_path / ".akmon.toml").write_text('[d2_ledger]\nsensitive_paths = ["src/**/lib/**"]\n', encoding="utf-8")
    ledger = tmp_path / "D2_LEDGER.md"
    d2.main(["add", "--ledger", str(ledger), "--kind", "math", "--what", "t", "--anchor", "a.py:1"])
    capsys.readouterr()

    # Changed path does not match a sensitive glob -> clean, even with pending entries.
    rc = d2.main(["check", "--ledger", str(ledger), "--strict", "--changed", "README.md"])
    assert rc == 0
    assert "D2 ledger clean" in capsys.readouterr().out

    # Changed path matches -> would warn, --strict exits 1.
    rc = d2.main(["check", "--ledger", str(ledger), "--strict", "--changed", "src/pkg/lib/x.py"])
    assert rc == 1
    assert "D2-1" in capsys.readouterr().err


def test_main_check_changed_unconfigured_warns(tmp_path, capsys):
    # No [d2_ledger] sensitive_paths configured -> can't tell what's sensitive, so warn (owner decision).
    ledger = tmp_path / "D2_LEDGER.md"
    d2.main(["add", "--ledger", str(ledger), "--kind", "math", "--what", "t", "--anchor", "a.py:1"])
    capsys.readouterr()
    rc = d2.main(["check", "--ledger", str(ledger), "--strict", "--changed", "README.md"])
    assert rc == 1
    assert "D2-1" in capsys.readouterr().err


def test_main_missing_ledger_check_is_clean(tmp_path, capsys):
    rc = d2.main(["check", "--ledger", str(tmp_path / "nope.md")])
    assert rc == 0
    assert "D2 ledger clean" in capsys.readouterr().out
