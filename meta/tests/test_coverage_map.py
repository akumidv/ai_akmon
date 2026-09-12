"""Unit tests for the coverage-map assembler (``tools/model_routing/coverage_map.py``).

Covers ``parse_zone_plan`` and the pure ``build_coverage_map`` (design §9.4 + §10.3 —
map assembled from the delegation log by code) plus a CLI smoke test with scoping.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

_KEYSTONE = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_ROUTING_DIR = _KEYSTONE / "tools" / "model_routing"
if str(_ROUTING_DIR) not in sys.path:
    sys.path.insert(0, str(_ROUTING_DIR))

import coverage_map  # noqa: E402
import routing  # noqa: E402


def _entry(zone, subagent="k_explorer", model="small", ts="T0", session="sess-1", desc="d"):
    return routing.DelegationEntry(ts, session, subagent, model, zone, desc)


# --------------------------------------------------------------------------------------
# parse_zone_plan
# --------------------------------------------------------------------------------------


def test_parse_zone_plan_bullets_comments_and_dedup():
    text = "# plan\n- auth\n* pricing\nio\n\nauth\n"
    assert coverage_map.parse_zone_plan(text) == ["auth", "pricing", "io"]


# --------------------------------------------------------------------------------------
# build_coverage_map
# --------------------------------------------------------------------------------------


def test_empty_scope():
    assert coverage_map.build_coverage_map([]) == "_No delegations in scope._"


def test_groups_by_zone_distinct_workers_and_count():
    entries = [
        _entry("auth", "k_explorer", "small"),
        _entry("auth", "k_reasoner", "big"),
        _entry("auth", "k_explorer", "small"),  # duplicate worker -> count 3, one entry
        _entry("pricing", "k_explorer", "small"),
    ]
    out = coverage_map.build_coverage_map(entries)
    assert "| auth | k_explorer/small, k_reasoner/big | 3 |" in out
    assert "| pricing | k_explorer/small | 1 |" in out


def test_unlabelled_zone_when_no_marker():
    out = coverage_map.build_coverage_map([_entry(None)])
    assert "| (unlabelled) |" in out


def test_worker_without_model():
    out = coverage_map.build_coverage_map([_entry("auth", model=None)])
    assert "| auth | k_explorer | 1 |" in out


def test_zone_plan_flags_uncovered_and_off_plan():
    entries = [_entry("auth"), _entry("extra")]
    out = coverage_map.build_coverage_map(entries, zone_plan=["auth", "pricing", "io"])
    assert "### Uncovered zones (planned, no worker)" in out
    assert "- pricing" in out
    assert "- io" in out
    assert "### Off-plan zones (worked, not in the zone plan)" in out
    assert "- extra" in out


def test_zone_plan_all_covered():
    out = coverage_map.build_coverage_map([_entry("auth")], zone_plan=["auth"])
    assert "_All planned zones have at least one worker._" in out


def test_zone_plan_notes_unlabelled_delegations():
    out = coverage_map.build_coverage_map([_entry(None), _entry(None)], zone_plan=["auth"])
    assert "2 delegation(s) carried no" in out


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def test_cli_scopes_by_session_and_writes(tmp_path, capsys):
    root = tmp_path
    (root / "AGENTS.md").write_text("x", encoding="utf-8")
    (root / "_aitna" / "akmon").mkdir(parents=True)
    log = root / routing.DELEGATION_LOG_REL
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        "T0\tsess-1\tk_explorer\tsmall\tauth\tcheck tokens\n"
        "T1\tsess-2\tk_explorer\tsmall\tpricing\tother session\n",
        encoding="utf-8",
    )
    out = root / "cov.md"

    rc = coverage_map.main(
        ["--project-root", str(root), "--session", "sess-1", "--out", str(out), "--stdout"]
    )
    assert rc == 0
    written = out.read_text(encoding="utf-8")
    assert "| auth |" in written
    assert "pricing" not in written  # other session filtered out
    captured = capsys.readouterr().out
    assert "entries=1" in captured


def test_the_default_map_path_follows_the_configured_dev_layer_root(tmp_path, monkeypatch, capsys):
    """No ``--out`` must land under the *configured* dev layer, not the default literal.

    The sibling of the gate-pack carrier, and the same defect: this path was spelled
    ``_aitna`` directly, so a project that relocated its dev layer got its coverage map
    written into a directory it does not read — silently, with a success line printed.
    """
    monkeypatch.setenv("AITNA_ROOT", "tools/ai")
    root = tmp_path
    (root / "AGENTS.md").write_text("x", encoding="utf-8")
    (root / "tools" / "ai" / "akmon").mkdir(parents=True)
    log = root / routing.DELEGATION_LOG_REL
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("T0\tsess-1\tk_explorer\tsmall\tauth\tcheck tokens\n", encoding="utf-8")

    assert coverage_map.main(["--project-root", str(root), "--all-sessions"]) == 0
    capsys.readouterr()

    written = sorted((root / "tools" / "ai" / "artifacts" / "gates").glob("coverage-*.md"))
    assert len(written) == 1
    assert not (root / "_aitna").exists()


# --------------------------------------------------------------------------------------
# CLI scope edges (C76): the map must not quietly widen or truncate its own scope
# --------------------------------------------------------------------------------------


def _log_project(tmp_path, rows):
    root = tmp_path
    (root / "AGENTS.md").write_text("x", encoding="utf-8")
    (root / "_aitna" / "akmon").mkdir(parents=True)
    log = root / routing.DELEGATION_LOG_REL
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("".join(f"{row}\n" for row in rows), encoding="utf-8")
    return root


@pytest.fixture
def utc_local(monkeypatch):
    """Pin local time to UTC: a bare-date or offset-less bound is read in local time."""
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


_TWO_ROUNDS = [
    "2026-09-01T10:00:00+0000\tsess-1\tk_explorer\tsmall\tauth\tround one",
    "2026-09-01T11:00:00+0000\tsess-2\tk_explorer\tsmall\tpricing\tround two",
]


def test_cli_refuses_a_run_that_names_no_scope(tmp_path, capsys):
    """Unscoped, the map unioned every session and a zone one round missed read as covered."""
    root = _log_project(tmp_path, _TWO_ROUNDS)
    with pytest.raises(SystemExit) as exc:
        coverage_map.main(["--project-root", str(root), "--zone-plan", str(root / "AGENTS.md")])
    assert exc.value.code == 2
    assert "--session" in capsys.readouterr().err
    assert not (root / "_aitna" / "artifacts").exists()


def test_session_scope_keeps_the_other_rounds_zone_uncovered(tmp_path, capsys):
    root = _log_project(tmp_path, _TWO_ROUNDS)
    plan = root / "plan.txt"
    plan.write_text("auth\npricing\nio\n", encoding="utf-8")
    args = ["--project-root", str(root), "--session", "sess-1", "--zone-plan", str(plan), "--stdout"]
    assert coverage_map.main(args) == 0
    out = capsys.readouterr().out
    assert "scope: session sess-1" in out
    assert "- pricing" in out and "- io" in out


def test_all_sessions_is_explicit_and_names_the_session_set(tmp_path, capsys):
    root = _log_project(tmp_path, [*_TWO_ROUNDS, "T9\tk_explorer\tsmall\tlegacy row"])
    assert coverage_map.main(["--project-root", str(root), "--all-sessions", "--out", str(root / "m.md")]) == 0
    out = capsys.readouterr().out
    assert "entries=3" in out
    assert "scope: all sessions (3: -, sess-1, sess-2)" in out


def test_a_bare_date_until_keeps_that_whole_day(tmp_path, capsys, utc_local):
    """Compared as strings, `--until 2026-09-02` sorted before every stamp of that day."""
    root = _log_project(
        tmp_path,
        [
            "2026-09-01T10:00:00+0000\tsess-1\tk_explorer\tsmall\tauth\tday one",
            "2026-09-02T00:00:00+0000\tsess-1\tk_explorer\tsmall\tpricing\tday two, first second",
            "2026-09-02T23:59:59+0000\tsess-1\tk_explorer\tsmall\tio\tday two, last second",
            "2026-09-03T00:00:00+0000\tsess-1\tk_explorer\tsmall\tdb\tday three",
        ],
    )
    args = ["--project-root", str(root), "--session", "sess-1", "--out", str(root / "m.md")]
    assert coverage_map.main([*args, "--until", "2026-09-02"]) == 0
    assert "entries=3" in capsys.readouterr().out
    assert coverage_map.main([*args, "--since", "2026-09-02"]) == 0
    assert "entries=3" in capsys.readouterr().out
    assert coverage_map.main([*args, "--since", "2026-09-02", "--until", "2026-09-02"]) == 0
    assert "entries=2" in capsys.readouterr().out


def test_bounds_compare_instants_across_offsets(tmp_path, capsys):
    """01:00 at +0300 is 22:00 UTC the day before — inside a bound a string compare puts it past."""
    root = _log_project(tmp_path, ["2026-09-02T01:00:00+0300\tsess-1\tk_explorer\tsmall\tauth\tlate"])
    args = ["--project-root", str(root), "--session", "sess-1", "--out", str(root / "m.md")]
    assert coverage_map.main([*args, "--until", "2026-09-01T23:00:00+00:00"]) == 0
    assert "entries=1" in capsys.readouterr().out


def test_an_unparseable_bound_is_refused(tmp_path, capsys):
    root = _log_project(tmp_path, _TWO_ROUNDS)
    with pytest.raises(SystemExit) as exc:
        coverage_map.main(["--project-root", str(root), "--all-sessions", "--until", "yesterday"])
    assert exc.value.code == 2
    assert "--until 'yesterday' is not an ISO date" in capsys.readouterr().err


def test_a_row_without_an_iso_stamp_fails_a_time_scoped_run(tmp_path, capsys):
    """Kept or dropped, such a row would be a guess about the scope — neither is silent."""
    root = _log_project(tmp_path, ["T0\tsess-1\tk_explorer\tsmall\tauth\tno stamp"])
    out = root / "m.md"
    with pytest.raises(SystemExit) as exc:
        coverage_map.main(
            ["--project-root", str(root), "--session", "sess-1", "--since", "2026-09-01", "--out", str(out)]
        )
    assert exc.value.code == 2
    assert "cannot be placed inside --since/--until" in capsys.readouterr().err
    assert not out.exists()
