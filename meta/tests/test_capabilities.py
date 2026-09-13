"""Contract suite for the capability-matrix vocabulary (C57, design §7).

Every rule carries an isolated seeded violation: one mutation per fixture, one expected code,
and an exact count — so a fixture that happens to break two rules cannot be mistaken for
evidence about either. The negative fixtures matter as much: akmon-owned checker prose and
guardrail prose must produce **no** C57 finding, because a scan that swallows them would make
this checker a second owner of C53's surface.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from checks import capabilities
from checks.capabilities import (
    CRASH_POSTURES,
    EFFECTS,
    MATRIX_FILE,
    REGION_BEGIN,
    REGION_END,
    UNMEASURED,
)

# A clean non-enforcement claim: every axis present, delivery settled, nothing enforced.
PLAIN_ROW = """### Demo capability — Claude Code

- documented: yes
- delivered: yes
- route: vendor=claude-code; version=2.1.221; event=SessionStart; matcher=n/a
- effect: none
- crash-posture: unmeasured
- evidence: demo probe
"""

# A clean enforcement claim: an `ask`/`deny` effect with every coordinate measured.
GUARD_ROW = """### Demo guard — Claude Code

- documented: yes
- delivered: yes
- route: vendor=claude-code; version=2.1.221; event=PreToolUse; matcher=Bash
- effect: deny
- crash-posture: fail-closed
- evidence: demo probe
"""


def _matrix(*rows: str) -> str:
    body = "\n".join(rows)
    return f"# Capability matrix\n\n{REGION_BEGIN}\n\n{body}\n{REGION_END}\n"


def _tree(tmp_path: Path, *rows: str, docs: dict | None = None) -> Path:
    (tmp_path / MATRIX_FILE).write_text(_matrix(*(rows or (PLAIN_ROW,))), encoding="utf-8")
    for relative, text in (docs or {}).items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def _codes(findings) -> list[str]:
    return [finding.code for finding in findings]


def _only(findings, code: str, severity: str = "error"):
    """Exactly one finding, carrying ``code`` at ``severity``.

    Severity is pinned, not just the code: a warn and an error of one code are different verdicts
    — the crash-posture branch of ``matrix.unqualified-effect`` was a warn on two named claims
    until C90/D2-47 — and a code-only assertion could not tell the two apart.
    """
    assert [(f.severity, f.code) for f in findings] == [(severity, code)], _codes(findings)
    return findings[0]


# --------------------------------------------------------------------------------------
# the baseline is clean — without this, every "exactly one" below proves nothing
# --------------------------------------------------------------------------------------


def test_a_clean_non_enforcement_tree_has_no_findings(tmp_path):
    assert capabilities.check_capabilities(_tree(tmp_path)) == []


def test_a_clean_enforcement_tree_has_no_findings(tmp_path):
    assert capabilities.check_capabilities(_tree(tmp_path, GUARD_ROW)) == []


# --------------------------------------------------------------------------------------
# matrix.missing-file — the file, the region, and the absence of any fallback
# --------------------------------------------------------------------------------------


def test_absent_matrix_file_is_one_missing_file(tmp_path):
    _only(capabilities.check_capabilities(tmp_path), "matrix.missing-file")


def test_absent_marked_region_is_the_same_finding(tmp_path):
    (tmp_path / MATRIX_FILE).write_text(f"# Capability matrix\n\n{PLAIN_ROW}", encoding="utf-8")
    _only(capabilities.check_capabilities(tmp_path), "matrix.missing-file")


def test_a_complete_matrix_under_meta_is_not_a_fallback(tmp_path):
    """No alternate location is accepted: the top-level file is the sole home."""
    nested = tmp_path / "meta" / MATRIX_FILE
    nested.parent.mkdir(parents=True)
    nested.write_text(_matrix(PLAIN_ROW), encoding="utf-8")
    _only(capabilities.check_capabilities(tmp_path), "matrix.missing-file")


# --------------------------------------------------------------------------------------
# matrix.missing-axis — six axes and four route coordinates, one fixture each
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("axis", ["documented", "delivered", "route", "effect", "crash-posture", "evidence"])
def test_deleting_one_axis_is_one_missing_axis(tmp_path, axis):
    row = "\n".join(line for line in PLAIN_ROW.splitlines() if not line.startswith(f"- {axis}:"))
    finding = _only(capabilities.check_capabilities(_tree(tmp_path, row)), "matrix.missing-axis")
    assert axis in finding.message


@pytest.mark.parametrize("coordinate", ["vendor", "version", "event", "matcher"])
def test_deleting_one_route_coordinate_is_one_missing_axis(tmp_path, coordinate):
    route = "; ".join(
        part.strip()
        for part in ["vendor=claude-code", " version=2.1.221", " event=SessionStart", " matcher=n/a"]
        if not part.strip().startswith(f"{coordinate}=")
    )
    row = PLAIN_ROW.replace(
        "- route: vendor=claude-code; version=2.1.221; event=SessionStart; matcher=n/a",
        f"- route: {route}",
    )
    finding = _only(capabilities.check_capabilities(_tree(tmp_path, row)), "matrix.missing-axis")
    assert coordinate in finding.message


# --------------------------------------------------------------------------------------
# matrix.invalid-value — the two closed vocabularies, every accepted value plus one outside
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("effect", EFFECTS)
def test_every_accepted_effect_is_valid(tmp_path, effect):
    row = GUARD_ROW.replace("- effect: deny", f"- effect: {effect}")
    assert "matrix.invalid-value" not in _codes(capabilities.check_capabilities(_tree(tmp_path, row)))


@pytest.mark.parametrize("posture", CRASH_POSTURES)
def test_every_accepted_crash_posture_is_valid(tmp_path, posture):
    row = PLAIN_ROW.replace("- crash-posture: unmeasured", f"- crash-posture: {posture}")
    if posture in ("fail-open", "fail-closed"):
        pass  # still measured, evidence already present
    assert "matrix.invalid-value" not in _codes(capabilities.check_capabilities(_tree(tmp_path, row)))


def test_an_effect_outside_the_vocabulary_is_one_invalid_value(tmp_path):
    row = PLAIN_ROW.replace("- effect: none", "- effect: blocks")
    _only(capabilities.check_capabilities(_tree(tmp_path, row)), "matrix.invalid-value")


def test_a_crash_posture_outside_the_vocabulary_is_one_invalid_value(tmp_path):
    row = PLAIN_ROW.replace("- crash-posture: unmeasured", "- crash-posture: probably-fine")
    _only(capabilities.check_capabilities(_tree(tmp_path, row)), "matrix.invalid-value")


# --------------------------------------------------------------------------------------
# matrix.unqualified-effect — an enforcement claim over something unmeasured
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("effect", ["ask", "deny"])
@pytest.mark.parametrize("coordinate", ["vendor", "version", "event", "matcher"])
def test_an_unmeasured_route_coordinate_under_enforcement_is_unqualified(tmp_path, effect, coordinate):
    row = GUARD_ROW.replace("- effect: deny", f"- effect: {effect}")
    for name, value in (
        ("vendor", "claude-code"),
        ("version", "2.1.221"),
        ("event", "PreToolUse"),
        ("matcher", "Bash"),
    ):
        if name == coordinate:
            row = row.replace(f"{name}={value}", f"{name}=unmeasured")
    finding = _only(capabilities.check_capabilities(_tree(tmp_path, row)), "matrix.unqualified-effect")
    assert coordinate in finding.message


def _guard(effect: str, *, title: str | None = None, posture: str = "unmeasured") -> str:
    row = GUARD_ROW.replace("- effect: deny", f"- effect: {effect}")
    row = row.replace("- crash-posture: fail-closed", f"- crash-posture: {posture}")
    return row.replace("### Demo guard — Claude Code", f"### {title}") if title else row


@pytest.mark.parametrize("effect", ["ask", "deny"])
def test_an_unmeasured_crash_posture_under_enforcement_is_unqualified(tmp_path, effect):
    """An error on every claim — none is exempt by name since D2-29 expired (C90/D2-47)."""
    finding = _only(capabilities.check_capabilities(_tree(tmp_path, _guard(effect))), "matrix.unqualified-effect")
    assert "crash-posture" in finding.message


@pytest.mark.parametrize("effect", ["ask", "deny"])
def test_an_unmeasured_crash_posture_fails_a_non_strict_run(tmp_path, effect):
    from common.findings import exit_code

    assert exit_code(capabilities.check_capabilities(_tree(tmp_path, _guard(effect))), strict=False) == 1


# The two claims D2-29 carried as a warn until C90/D2-47 measured them. Their titles now get the
# rule every claim gets: a warn coming back for them is the exemption coming back.
_FORMERLY_EXEMPT = (
    "Commit guard — owner-owned commits at the tool boundary — Claude Code",
    "Delegation log and drift nudge — Claude Code",
)


@pytest.mark.parametrize("title", _FORMERLY_EXEMPT)
@pytest.mark.parametrize("effect", ["ask", "deny"])
def test_a_formerly_exempt_claim_is_an_error_like_any_other(tmp_path, effect, title):
    from common.findings import exit_code

    found = capabilities.check_capabilities(_tree(tmp_path, _guard(effect, title=title)))
    _only(found, "matrix.unqualified-effect")
    assert exit_code(found, strict=False) == 1


def _live_claims() -> dict[str, dict]:
    text = (Path(__file__).resolve().parents[2] / MATRIX_FILE).read_text(encoding="utf-8")
    begin, end = capabilities._region_span(text)
    rows, _ = capabilities._parse_rows(text[begin:end], line_offset=1)
    return {row["title"]: row["axes"] for row in rows}


def test_every_shipped_enforcement_claim_records_a_measured_crash_posture():
    """The shipped matrix, not a fixture: nothing in the checker excuses an ``ask``/``deny`` claim
    over an unmeasured crash posture any more (C90/D2-47), so none may stand in the tree."""
    enforcing = {title: axes for title, axes in _live_claims().items() if axes.get("effect") in ("ask", "deny")}
    assert enforcing, "the shipped matrix carries no ask/deny claim — this carrier would prove nothing"
    assert [title for title, axes in enforcing.items() if axes.get("crash-posture") == UNMEASURED] == []


@pytest.mark.parametrize("effect", ["none", "advisory"])
def test_a_non_enforcement_effect_may_leave_a_coordinate_unmeasured(tmp_path, effect):
    """The rule is about enforcement claims; an advisory over an unprobed route is honest."""
    row = GUARD_ROW.replace("- effect: deny", f"- effect: {effect}")
    row = row.replace("version=2.1.221", "version=unmeasured")
    assert "matrix.unqualified-effect" not in _codes(capabilities.check_capabilities(_tree(tmp_path, row)))


def test_deleting_a_coordinate_is_never_unqualified_effect(tmp_path):
    """Deletion is `missing-axis`; only an explicit `unmeasured` is `unqualified-effect`."""
    row = GUARD_ROW.replace("; matcher=Bash", "")
    _only(capabilities.check_capabilities(_tree(tmp_path, row)), "matrix.missing-axis")


# --------------------------------------------------------------------------------------
# matrix.uncited-claim — the evidence relation, both directions
# --------------------------------------------------------------------------------------


def test_a_measured_claim_without_evidence_is_uncited(tmp_path):
    row = PLAIN_ROW.replace("- evidence: demo probe", "- evidence:")
    _only(capabilities.check_capabilities(_tree(tmp_path, row)), "matrix.uncited-claim")


def test_an_unmeasured_claim_with_evidence_is_uncited(tmp_path):
    row = PLAIN_ROW.replace("- delivered: yes", "- delivered: unmeasured")
    _only(capabilities.check_capabilities(_tree(tmp_path, row)), "matrix.uncited-claim")


def test_an_unmeasured_claim_without_evidence_is_clean(tmp_path):
    row = PLAIN_ROW.replace("- delivered: yes", "- delivered: unmeasured")
    row = row.replace("- evidence: demo probe", "- evidence:")
    assert capabilities.check_capabilities(_tree(tmp_path, row)) == []


# --------------------------------------------------------------------------------------
# matrix.bare-claim — forbidden claims outside the marked region
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("token", ["enforced", "enforces", "✅", "⚠️"])
@pytest.mark.parametrize("nearby", ["Claude Code", "Codex CLI", "Gemini", "Copilot", "SessionStart", "PreToolUse"])
def test_a_forbidden_claim_beside_a_vendor_or_event_is_one_bare_claim(tmp_path, token, nearby):
    docs = {"MODEL.md": f"# Model\n\nThe guard {token} the boundary on {nearby}.\n"}
    findings = capabilities.check_capabilities(_tree(tmp_path, docs=docs))
    _only(findings, "matrix.bare-claim")


@pytest.mark.parametrize("token", ["enforced", "enforces", "✅", "⚠️"])
def test_a_forbidden_claim_with_no_vendor_or_event_nearby_is_clean(tmp_path, token):
    docs = {"MODEL.md": f"# Model\n\nThe threshold is {token} for every project.\n"}
    assert capabilities.check_capabilities(_tree(tmp_path, docs=docs)) == []


def test_akmon_own_checker_prose_is_not_a_bare_claim(tmp_path):
    """The lock's named allowance: a threshold attributed to akmon's in-process checker."""
    docs = {
        "pipelines/tasks.md": "# Tasks\n\n## Thresholds (enforced by `verify.py`)\n\n"
        "Claude Code and Codex CLI read the same index.\n"
    }
    assert capabilities.check_capabilities(_tree(tmp_path, docs=docs)) == []


def test_guardrail_prose_is_not_scanned_here(tmp_path):
    """Guardrail runtime prose is C53's F7/F8 surface; two owners for one rule is the defect."""
    docs = {"guardrails/_common.md": "# Common\n\nD5 is enforced on Claude Code by the guard.\n"}
    assert capabilities.check_capabilities(_tree(tmp_path, docs=docs)) == []


def test_meta_material_is_not_scanned_here(tmp_path):
    docs = {"meta/design/notes.md": "# Notes\n\nPreToolUse enforces the deny on Claude Code.\n"}
    assert capabilities.check_capabilities(_tree(tmp_path, docs=docs)) == []


def test_claims_inside_the_marked_region_are_not_bare_claims(tmp_path):
    """The region is where qualified claims belong; scanning it would forbid the matrix itself."""
    row = PLAIN_ROW.replace("### Demo capability — Claude Code", "### Demo capability ✅ enforced — Claude Code")
    assert capabilities.check_capabilities(_tree(tmp_path, row)) == []


def test_a_retained_legacy_table_beside_a_valid_matrix_is_one_bare_claim(tmp_path):
    """The transition fixture: a second authority fails, and is never parsed as matrix rows."""
    legacy = (
        "# akmon\n\n"
        "| Capability | Claude Code | Codex CLI |\n"
        "|---|---|---|\n"
        "| Commit guard | ✅ PreToolUse hook | ❌ not wired |\n"
    )
    findings = capabilities.check_capabilities(_tree(tmp_path, docs={"README.md": legacy}))
    _only(findings, "matrix.bare-claim")
    assert "matrix.missing-axis" not in _codes(findings)


# --- region integrity (N-review finding 4) --------------------------------------------------
#
# The six-axis rules only run over rows the parser recognises, so every shape that yields zero
# recognised rows used to pass silently: the matrix could be gutted down to a marker pair and
# `self_ci` stayed green. A checked region must therefore prove it still holds claims.


def test_an_empty_marked_region_is_not_a_matrix(tmp_path):
    (tmp_path / MATRIX_FILE).write_text(f"# Capability matrix\n\n{REGION_BEGIN}\n\n{REGION_END}\n", encoding="utf-8")
    _only(capabilities.check_matrix(tmp_path), "matrix.missing-file")


def test_a_region_holding_only_prose_is_not_a_matrix(tmp_path):
    (tmp_path / MATRIX_FILE).write_text(
        f"{REGION_BEGIN}\nEvery capability is covered, trust us.\n{REGION_END}\n",
        encoding="utf-8",
    )
    _only(capabilities.check_matrix(tmp_path), "matrix.missing-file")


def test_a_second_marker_pair_leaves_no_single_region(tmp_path):
    text = _matrix(PLAIN_ROW) + f"\n{REGION_BEGIN}\n{GUARD_ROW}\n{REGION_END}\n"
    (tmp_path / MATRIX_FILE).write_text(text, encoding="utf-8")
    _only(capabilities.check_matrix(tmp_path), "matrix.missing-file")


def test_a_repeated_begin_marker_leaves_no_single_region(tmp_path):
    text = _matrix(PLAIN_ROW).replace(REGION_BEGIN, f"{REGION_BEGIN}\n{REGION_BEGIN}", 1)
    (tmp_path / MATRIX_FILE).write_text(text, encoding="utf-8")
    _only(capabilities.check_matrix(tmp_path), "matrix.missing-file")


def test_a_glyph_table_smuggled_into_the_region_is_one_invalid_value(tmp_path):
    # The exact regression the matrix replaced: a legacy grid re-entering through the one
    # location the bare-claim scan deliberately does not read.
    (tmp_path / MATRIX_FILE).write_text(
        _matrix(PLAIN_ROW + "\n| Commit guard | Claude Code | ✅ |\n"), encoding="utf-8"
    )
    _only(capabilities.check_matrix(tmp_path), "matrix.invalid-value")


def test_an_axis_line_above_every_heading_is_one_invalid_value(tmp_path):
    (tmp_path / MATRIX_FILE).write_text(_matrix("- documented: yes\n", PLAIN_ROW), encoding="utf-8")
    _only(capabilities.check_matrix(tmp_path), "matrix.invalid-value")


def test_a_blank_line_inside_a_claim_is_not_a_stray_line(tmp_path):
    # Claims are separated by blank lines in the shipped file; blanks must stay free.
    (tmp_path / MATRIX_FILE).write_text(_matrix(PLAIN_ROW, GUARD_ROW), encoding="utf-8")
    assert capabilities.check_matrix(tmp_path) == []


# --- the shipped population (N-review finding 4) --------------------------------------------


def test_the_shipped_matrix_population_is_pinned():
    """The exact claims the shipped matrix carries.

    Without this, deleting a claim is invisible: the remaining rows stay well-formed and every
    per-row rule still passes. Removing coverage must be a deliberate edit to this list.
    """
    root = Path(__file__).resolve().parents[2]
    text = (root / MATRIX_FILE).read_text(encoding="utf-8")
    region = text[text.index(REGION_BEGIN) : text.index(REGION_END)]
    titles = [line[4:].strip() for line in region.splitlines() if line.startswith("### ")]
    assert len(titles) == 19
    assert len(set(titles)) == len(titles), "one claim per capability-and-vendor pair"
    vendors = [title.rsplit("—", 1)[-1].strip() for title in titles]
    assert {vendor: vendors.count(vendor) for vendor in set(vendors)} == {
        "Claude Code": 9,
        "Codex CLI": 9,
        "Gemini CLI": 1,
    }


# --- the axis list is closed in both directions (N-review finding 5) -------------------------


def test_a_repeated_axis_is_one_invalid_value(tmp_path):
    """Two readings of one axis silently collapsed to whichever line came last."""
    row = PLAIN_ROW.replace("- documented: yes", "- documented: yes\n- documented: no", 1)
    (tmp_path / MATRIX_FILE).write_text(_matrix(row), encoding="utf-8")
    _only(capabilities.check_matrix(tmp_path), "matrix.invalid-value")


def test_an_unknown_axis_is_one_invalid_value(tmp_path):
    """A seventh key is either a typo for a real axis or an answer nothing reads."""
    (tmp_path / MATRIX_FILE).write_text(_matrix(PLAIN_ROW + "- mystery: yes\n"), encoding="utf-8")
    _only(capabilities.check_matrix(tmp_path), "matrix.invalid-value")


def test_a_misspelled_axis_reports_the_stray_key_and_the_absent_one(tmp_path):
    row = PLAIN_ROW.replace("- delivered: yes", "- delivred: yes", 1)
    (tmp_path / MATRIX_FILE).write_text(_matrix(row), encoding="utf-8")
    assert _codes(capabilities.check_matrix(tmp_path)) == [
        "matrix.invalid-value",
        "matrix.missing-axis",
    ]
