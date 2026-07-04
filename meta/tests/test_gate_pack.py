"""Unit tests for the gate-pack builder (``tools/model_routing/gate_pack.py``).

Covers the pure builders ``build_full_pack`` / ``build_plan_check_pack`` (design §9.4 —
one packaging, N executors) plus a CLI smoke test. Inputs are plain strings, independent
of the filesystem, except for the CLI test which needs files to read.
"""

from __future__ import annotations

import sys
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

import gate_pack  # noqa: E402

# --------------------------------------------------------------------------------------
# build_full_pack
# --------------------------------------------------------------------------------------


def test_full_pack_review_header_and_sections():
    pack = gate_pack.build_full_pack(
        "code-verify",
        "review",
        "Acceptance: the endpoint returns 200 for valid input.",
        [("worker-a.md", "Finding A: seam X is uncovered."), ("worker-b.md", "Finding B: no issue.")],
        coverage_map="zone A: checked by worker-a\nzone B: not checked",
    )

    assert "# Gate-pack — code-verify" in pack
    assert "role: review" in pack
    assert "kind: full" in pack
    assert f"Question: {gate_pack.ROLE_QUESTION['review']}" in pack
    assert "## Yardstick (acceptance condition)" in pack
    assert "Acceptance: the endpoint returns 200 for valid input." in pack
    assert "## Artifacts" in pack
    assert "### worker-a.md" in pack
    assert "Finding A: seam X is uncovered." in pack
    assert "### worker-b.md" in pack
    assert "Finding B: no issue." in pack
    assert "## Coverage map" in pack
    assert "zone A: checked by worker-a" in pack

    # k-auditor output contract footer (design §9.3 item 4).
    assert "## What to return" in pack
    assert "Contradictions between independently-correct findings/options" in pack
    assert "Uncovered seams" in pack
    assert "Re-ranking / recommendation deltas" in pack
    assert "Level verdict" in pack
    assert "session's level hypothesis" in pack
    assert '"could not verify" list' in pack
    assert (
        "If this pack lacks what the audit needs (no coverage map, no yardstick), "
        "return the precise gap instead of a diluted verdict." in pack
    )

    # No decisions register or dep-graph section for a review gate that didn't ask for them.
    assert "## Decisions register" not in pack
    assert "## Dependency-graph excerpt" not in pack


def test_full_pack_architect_optional_sections_present_and_absent():
    with_extras = gate_pack.build_full_pack(
        "design-align",
        "architect",
        "Goal: the two options must not assume incompatible storage backends.",
        [("options.md", "Option 1 vs option 2.")],
        decisions="Decision: use option 1 for storage.",
        dep_graph="a.py -> b.py -> c.py",
    )
    assert f"Question: {gate_pack.ROLE_QUESTION['architect']}" in with_extras
    assert "## Decisions register" in with_extras
    assert "Decision: use option 1 for storage." in with_extras
    assert "## Dependency-graph excerpt" in with_extras
    assert "a.py -> b.py -> c.py" in with_extras

    without_extras = gate_pack.build_full_pack(
        "design-align",
        "architect",
        "Goal: the two options must not assume incompatible storage backends.",
        [("options.md", "Option 1 vs option 2.")],
    )
    assert "## Decisions register" not in without_extras
    assert "## Dependency-graph excerpt" not in without_extras


def test_full_pack_empty_artifacts_and_missing_coverage_map_sentinels():
    pack = gate_pack.build_full_pack("code-verify", "review", "Goal text.", [])
    assert "## Artifacts" in pack
    assert "_No artifacts supplied._" in pack
    assert "## Coverage map" in pack
    assert "_Coverage map not provided (assemble via coverage_map.py)._" in pack


def test_full_pack_unknown_role_raises():
    with pytest.raises(ValueError):
        gate_pack.build_full_pack("gate", "unknown-role", "yardstick", [])


# --------------------------------------------------------------------------------------
# build_plan_check_pack
# --------------------------------------------------------------------------------------


def test_plan_check_pack_contents():
    pack = gate_pack.build_plan_check_pack(
        "design-align",
        "architect",
        "Goal: ship the gate-pack builder.",
        "Zone plan: (1) pure builders, (2) CLI, (3) tests.",
    )
    assert "kind: plan-check" in pack
    assert "Does the plan cover the stated goal? Which zones or seams are obviously missing?" in pack
    assert "## Yardstick (goal)" in pack
    assert "Goal: ship the gate-pack builder." in pack
    assert "## Zone plan" in pack
    assert "Zone plan: (1) pure builders, (2) CLI, (3) tests." in pack
    assert "Check the plan against the goal, not against its own coverage map." in pack

    # No Artifacts / Coverage map sections in a plan-check pack.
    assert "## Artifacts" not in pack
    assert "## Coverage map" not in pack


def test_plan_check_pack_unknown_role_raises():
    with pytest.raises(ValueError):
        gate_pack.build_plan_check_pack("gate", "unknown-role", "yardstick", "zone plan")


# --------------------------------------------------------------------------------------
# CLI smoke test
# --------------------------------------------------------------------------------------


def test_cli_writes_full_pack(tmp_path):
    yardstick = tmp_path / "yardstick.md"
    yardstick.write_text("Acceptance: green tests.", encoding="utf-8")
    artifact = tmp_path / "finding.md"
    artifact.write_text("Finding: all clear.", encoding="utf-8")
    out = tmp_path / "pack.md"

    exit_code = gate_pack.main(
        [
            "--project-root",
            str(tmp_path),
            "--gate",
            "code-verify",
            "--role",
            "review",
            "--yardstick",
            str(yardstick),
            "--artifact",
            str(artifact),
            "--out",
            str(out),
        ]
    )

    assert exit_code == 0
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "# Gate-pack — code-verify" in text
    assert "### finding.md" in text
    assert "Finding: all clear." in text
