"""Unit tests for the coverage-map assembler (``tools/model_routing/coverage_map.py``).

Covers ``parse_zone_plan`` and the pure ``build_coverage_map`` (design §9.4 + §10.3 —
map assembled from the delegation log by code) plus a CLI smoke test with scoping.
"""

from __future__ import annotations

import sys
from pathlib import Path

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


def _entry(zone, subagent="k-explorer", model="small", ts="T0", session="sess-1", desc="d"):
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
        _entry("auth", "k-explorer", "small"),
        _entry("auth", "k-reasoner", "big"),
        _entry("auth", "k-explorer", "small"),  # duplicate worker -> count 3, one entry
        _entry("pricing", "k-explorer", "small"),
    ]
    out = coverage_map.build_coverage_map(entries)
    assert "| auth | k-explorer/small, k-reasoner/big | 3 |" in out
    assert "| pricing | k-explorer/small | 1 |" in out


def test_unlabelled_zone_when_no_marker():
    out = coverage_map.build_coverage_map([_entry(None)])
    assert "| (unlabelled) |" in out


def test_worker_without_model():
    out = coverage_map.build_coverage_map([_entry("auth", model=None)])
    assert "| auth | k-explorer | 1 |" in out


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
        "T0\tsess-1\tk-explorer\tsmall\tauth\tcheck tokens\n"
        "T1\tsess-2\tk-explorer\tsmall\tpricing\tother session\n",
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
