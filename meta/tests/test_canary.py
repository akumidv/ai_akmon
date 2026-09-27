"""Contract tests for the invariant canary: the policy-ID join and D07's population rule.

Two layers, deliberately different. The seeded mutations run against a synthetic tree, so each
one breaks exactly one relation and the assertion names the code and the diagnostic coordinates
(F13). The shipped-contract tests run against akmon's own tree and pin what the current release
classifies — a coordinated rename on both structural sides keeps the join balanced and must still
fail here (F15).
"""

from __future__ import annotations

from pathlib import Path

from checks import canary

_AKMON = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)

_PROSE = """# Guardrails

## The example rule

- Never do the thing.

Runtime check: example.no-thing — subset: the first attempt in a session is denied.
"""

_HOOK_CORE = '''"""Fixture hook core."""


def example_guard_result(command):
    """Deny the thing.

    Policy ID: example.no-thing
    """
    return command


def helper_message():
    """Text reached only through the result above, so it is outside the population."""
    return "text"


def failure_notice(name):
    """What the owner is told when a hook crashed.

    Runtime classification: operational
    Rationale: it authors no rule of its own.
    """
    return name
'''

_ADAPTER = '''"""Fixture adapter — the vendor channel itself."""

from hook_core import failure_notice


def print_result(result):
    """Render the result, and the crash notice, into the vendor's channel."""
    print(failure_notice(result))
'''


def _tree(tmp_path: Path) -> Path:
    (tmp_path / "guardrails").mkdir()
    (tmp_path / "hooks").mkdir()
    (tmp_path / "guardrails" / "_common.md").write_text(_PROSE, encoding="utf-8")
    (tmp_path / "hooks" / "hook_core.py").write_text(_HOOK_CORE, encoding="utf-8")
    (tmp_path / "hooks" / "claude_adapter.py").write_text(_ADAPTER, encoding="utf-8")
    return tmp_path


def _errors(root: Path) -> list:
    return [finding for finding in canary.check_canary(root) if finding.severity == "error"]


def _codes(root: Path) -> list[str]:
    return [finding.code for finding in _errors(root)]


def _rewrite(root: Path, relative: str, old: str, new: str) -> None:
    path = root / relative
    text = path.read_text(encoding="utf-8")
    assert old in text, f"fixture no longer contains {old!r}"
    path.write_text(text.replace(old, new), encoding="utf-8")


# --- the join, one relation per mutation ---------------------------------------------------


def test_balanced_join_is_clean(tmp_path):
    assert _codes(_tree(tmp_path)) == []


def test_policy_id_with_no_prose_is_rejected(tmp_path):
    root = _tree(tmp_path)
    _rewrite(root, "guardrails/_common.md", "Runtime check: example.no-thing", "Nothing claims it")
    (finding,) = _errors(root)
    assert finding.code == "canary.docstring-orphan"
    assert "policy ID example.no-thing" in finding.message
    assert "callable hooks/hook_core.py:4" in finding.message
    assert "prose absent" in finding.message


def test_prose_marker_with_no_callable_is_rejected(tmp_path):
    root = _tree(tmp_path)
    _rewrite(root, "hooks/hook_core.py", "    Policy ID: example.no-thing\n", "")
    codes = _codes(root)
    assert "canary.prose-orphan" in codes
    orphan = next(finding for finding in _errors(root) if finding.code == "canary.prose-orphan")
    assert "policy ID example.no-thing" in orphan.message
    assert "callable absent" in orphan.message
    assert "prose guardrails/_common.md:7" in orphan.message


def test_deleting_the_docstring_annotation_also_reports_the_unclassified_result(tmp_path):
    root = _tree(tmp_path)
    _rewrite(root, "hooks/hook_core.py", "    Policy ID: example.no-thing\n", "")
    assert "canary.unclassified" in _codes(root)


def test_duplicate_prose_marker_is_rejected(tmp_path):
    root = _tree(tmp_path)
    _rewrite(
        root,
        "guardrails/_common.md",
        "Runtime check: example.no-thing — subset: the first attempt in a session is denied.\n",
        "Runtime check: example.no-thing — subset: one.\n\nRuntime check: example.no-thing — subset: two.\n",
    )
    assert _codes(root) == ["canary.duplicate-id"]


def test_one_policy_id_claimed_by_two_callables_is_rejected(tmp_path):
    root = _tree(tmp_path)
    _rewrite(
        root,
        "hooks/hook_core.py",
        '    """Text reached only through the result above, so it is outside the population."""',
        '    """Text.\n\n    Policy ID: example.no-thing\n    """',
    )
    codes = _codes(root)
    assert "canary.duplicate-id" in codes


def test_malformed_policy_id_is_rejected(tmp_path):
    root = _tree(tmp_path)
    _rewrite(root, "guardrails/_common.md", "example.no-thing —", "ExampleNoThing —")
    assert "canary.malformed-id" in _codes(root)


def test_public_result_without_classification_is_rejected(tmp_path):
    root = _tree(tmp_path)
    _rewrite(
        root,
        "hooks/hook_core.py",
        '    """Deny the thing.\n\n    Policy ID: example.no-thing\n    """',
        '    """Deny the thing."""',
    )
    unclassified = next(finding for finding in _errors(root) if finding.code == "canary.unclassified")
    assert "example_guard_result" in unclassified.message
    assert "policy ID absent" in unclassified.message


def test_dual_classification_is_rejected(tmp_path):
    root = _tree(tmp_path)
    _rewrite(
        root,
        "hooks/hook_core.py",
        "    Policy ID: example.no-thing\n    \"\"\"",
        "    Policy ID: example.no-thing\n    Runtime classification: operational\n    \"\"\"",
    )
    assert "canary.dual-classification" in _codes(root)


def test_operational_without_rationale_is_rejected(tmp_path):
    root = _tree(tmp_path)
    _rewrite(root, "hooks/hook_core.py", "    Rationale: it authors no rule of its own.\n", "")
    assert _codes(root) == ["canary.empty-rationale"]


def test_unknown_classification_value_is_rejected(tmp_path):
    root = _tree(tmp_path)
    _rewrite(root, "hooks/hook_core.py", "Runtime classification: operational", "Runtime classification: exempt")
    assert _codes(root) == ["canary.malformed-classification"]


def test_legacy_enforcement_claim_in_live_prose_is_rejected(tmp_path):
    root = _tree(tmp_path)
    _rewrite(
        root,
        "guardrails/_common.md",
        "- Never do the thing.",
        "- Never do the thing.\n\n> **Enforced** (not just documented) by the hook.",
    )
    assert _codes(root) == ["canary.legacy-marker"]


# --- D07: the population outside the join ---------------------------------------------------


def test_owner_visible_callable_outside_the_join_may_not_stay_silent(tmp_path):
    root = _tree(tmp_path)
    _rewrite(
        root,
        "hooks/hook_core.py",
        '''def helper_message():
    """Text reached only through the result above, so it is outside the population."""
    return "text"''',
        '''def report_gap():
    """Say once that something cannot be classified."""
    print("gap")''',
    )
    (finding,) = _errors(root)
    assert finding.code == "canary.silent-callable"
    assert "report_gap" in finding.message


def test_text_builder_behind_a_classified_result_is_not_in_the_population(tmp_path):
    """Classifying it would let one policy ID be claimed from two places (ADR-0012/D07)."""
    assert _codes(_tree(tmp_path)) == []


def test_adapter_callable_is_the_rendering_seam_not_a_member(tmp_path):
    root = _tree(tmp_path)
    assert "print" in (root / "hooks" / "claude_adapter.py").read_text(encoding="utf-8")
    assert _codes(root) == []


def test_policy_id_outside_the_join_is_rejected(tmp_path):
    root = _tree(tmp_path)
    _rewrite(
        root,
        "hooks/hook_core.py",
        "    Runtime classification: operational\n    Rationale: it authors no rule of its own.\n",
        "    Policy ID: example.no-thing\n",
    )
    assert "canary.policy-id-outside-join" in _codes(root)


# --- F15: what this release ships -----------------------------------------------------------


def _shipped() -> list[canary.CallableClassification]:
    return canary._collect_callables(_AKMON)


def test_shipped_tree_is_clean():
    assert _codes(_AKMON) == []


def test_shipped_policy_id_pairs_are_pinned():
    pairs = {entry.name: entry.policy_id for entry in _shipped() if entry.policy_id}
    assert pairs == {
        "privilege_escalation_guard_result": "privilege.no-escalation",
        "git_commit_guard_result": "commits.owner-owned",
        "analysis_write_result": "analysis.before-mutation",
        "delegation_nudge_result": "delegation.tier-floor",
        "role_on_code_result": "role.declaration",
    }


def test_session_start_stays_operational_with_its_required_rationale():
    entry = next(entry for entry in _shipped() if entry.name == "session_start_result")
    assert entry.classification == "operational"
    assert "Delivery is not ownership" in entry.rationale
    assert "only delivery channel for the delegation rule" in entry.rationale
    assert "Codex" in entry.rationale


def test_owner_visible_population_outside_the_join_is_pinned():
    outside = {entry.name for entry in _shipped() if entry.owner_visible}
    assert outside == {
        "report_unclassified_shell_route",
        "hook_failure_diagnostic",
        "hook_failure_notice",
        "model_routing_result",
        # The neutral tool-kind tokens the adapters import (C102: hooks/vocabulary.json).
        "edit_tool",
        "shell_tool",
        "read_tool",
    }
    for entry in _shipped():
        if entry.owner_visible:
            assert entry.classification == "operational" and entry.rationale
            assert not entry.policy_id


def _tail(policy_id: str) -> str:
    markers, _ = canary._read_prose(_AKMON)
    return next(marker.tail for marker in markers if marker.policy_id == policy_id)


def test_marker_tails_state_the_subset_each_callable_actually_covers():
    assert "the whole rule" in _tail("privilege.no-escalation")
    commits = _tail("commits.owner-owned")
    assert "detached/unresolved HEAD" in commits
    assert "not machine-checked" in commits
    assert "not decidable by a hook" in _tail("analysis.before-mutation")
    delegation = _tail("delegation.tier-floor")
    assert "escalates that ask to a deny" in delegation
    assert "first edit to a code file" in _tail("role.declaration")
