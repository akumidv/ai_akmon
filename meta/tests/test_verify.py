"""Unit tests for the akmon layout verifier (``verify``).

A ``_make_project`` helper builds a fully compliant throwaway tree (clean strict run), and
each test mutates one thing to assert the matching finding. Nothing touches the real repo.

Run from the akmon root::

    python3 -m pytest tests
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest
import sync
import verify

from common.codex_hooks import CodexProtocolError, expected_codex_hooks
from common.findings import exit_code, render

AGENTS_MD = """# AGENTS.md

## Dev layer — akmon

Model: `_aitna/akmon/README.md`. Archetype: `ARCHETYPES.md`. Roles:
`_aitna/akmon/roles/`. Read `_aitna/memory` at session start.

Prime directives D2 and D5 are always-on. Secrets come from `.env`.
Delegation is the default.
Skills live in `_aitna/skills/` and root `skills/`; generated vendor skill stubs are pointers only.
"""

CI_YML = """name: CI
on: [push]
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - run: python3 _aitna/akmon/bin/sync.py --check
      - run: python3 _aitna/akmon/bin/verify.py --strict
"""

GITIGNORE = "*.env\n!*.env.example\n"

CHANGELOG_MD = "# Changelog\n\n## Unreleased\n\n### Added\n- fixture\n"

SKILL_MD = """---
name: demo
description: Demonstrates the akmon skill contract. Use for verifier fixture coverage.
metadata:
  owner: akmon
---

# demo
"""


def _write(path: Path, text: str = "x\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_project(tmp_path: Path) -> Path:
    root = tmp_path
    _write(root / "AGENTS.md", AGENTS_MD)
    _write(root / "_aitna" / "TASKS.md")

    ks = root / "_aitna" / "akmon"
    for rel in (
        "README.md",
        "BOOTSTRAP.md",
        "ARCHETYPES.md",
        "CHANGELOG.md",
        "MODEL.md",
        "CAPABILITIES.md",
        "roles/README.md",
        "roles/review.md",
        "roles/architect.md",
        "roles/engineer.md",
        "roles/learn.md",
        "roles/release.md",
        "guardrails/_common.md",
        "pipelines/pre-commit.md",
        "pipelines/code-flow.md",
        "pipelines/design-flow.md",
        "pipelines/release.md",
        "pipelines/tasks.md",
        "bin/sync.py",
        "bin/verify.py",
        "hooks/hook_core.py",
        "hooks/claude_adapter.py",
        "hooks/codex_adapter.py",
        "hooks/codex-hook.py",
        "hooks/git-commit-guard.py",
        "hooks/session-start-agent.py",
        "hooks/role-on-code.py",
        "hooks/analysis-guard.py",
        "hooks/model-routing.py",
        "hooks/delegation-log.py",
        "tools/model_routing/routing.py",
        "tools/model_routing/init.py",
        "tools/model_routing/second_opinion.py",
    ):
        text = CHANGELOG_MD if rel == "CHANGELOG.md" else "x\n"
        _write(ks / rel, text)
    _write(
        ks / "tools" / "model_routing" / "registry.json",
        """{
  "anthropic": {
    "selection_policy": {
      "available_order": "weakest-to-strongest",
      "worker": "lowest",
      "mid": "next-after-worker",
      "reasoner": "highest",
      "orchestrator_floor": "highest"
    },
    "second_opinion": {
      "harness": "claude",
      "operation": "review",
      "report_dir": ".codex/second-opinion/"
    },
    "semantic_fallback": {
      "worker": "worker",
      "mid": "mid",
      "reasoner": "strongest",
      "orchestrator": "strongest"
    }
  },
  "openai": {
    "selection_policy": {
      "available_order": "weakest-to-strongest",
      "worker": "lowest",
      "mid": "next-after-worker",
      "reasoner": "highest",
      "orchestrator_floor": "highest"
    },
    "second_opinion": {
      "harness": "codex",
      "operation": "review",
      "report_dir": ".claude/second-opinion/"
    },
    "semantic_fallback": {
      "worker": "worker",
      "mid": "mid",
      "reasoner": "strongest",
      "orchestrator": "strongest"
    }
  }
}
""",
    )

    # an agent charter that links a akmon role
    _write(root / "_aitna" / "agents" / "engineer" / "README.md", "See `_aitna/akmon/roles/engineer.md`.\n")

    # a skill (so check_skills is ok, not warn)
    _write(ks / "skills" / "demo" / "SKILL.md", SKILL_MD)

    # memory index mentioning its one memory file
    _write(root / "_aitna" / "memory" / "note.md", "fact\n")
    _write(root / "_aitna" / "memory" / "README.md", "# Memory\n- note.md\n")

    _write(root / ".gitignore", GITIGNORE)
    _write(ks / ".gitignore", "__pycache__/\n*.env\n!*.env.example\n")
    _write(root / ".github" / "workflows" / "ci.yml", CI_YML)

    # generated pointers must match sync output
    files, _ = sync._planned_files(root)
    sync._apply(files, write=True)
    return root


def _levels(findings) -> set[str]:
    return {finding.severity for finding in findings}


def _messages(findings, level: str) -> list[str]:
    return [finding.message for finding in findings if finding.severity == level]


# --------------------------------------------------------------------------------------
# clean tree
# --------------------------------------------------------------------------------------


def test_compliant_project_has_no_errors_or_warnings(tmp_path):
    root = _make_project(tmp_path)
    verifier = verify.Verifier(root)
    verifier.run()
    assert "error" not in _levels(verifier.findings), _messages(verifier.findings, "error")
    assert "warn" not in _levels(verifier.findings), _messages(verifier.findings, "warn")


def test_main_strict_passes_on_compliant_project(tmp_path):
    root = _make_project(tmp_path)
    assert verify.main(["--project-root", str(root), "--strict"]) == 0


# --------------------------------------------------------------------------------------
# model-routing registry — reasoner policy (C26): the checker drifted from the live
# registry (asserted reasoner=="highest" only) after ADR 0005/0006 made it dynamic
# (reasoner=="orchestrator"), silently red-lining every verify-touching CI leg. Test
# against the *live* registry, not just a fixture that happens to still say "highest".
# --------------------------------------------------------------------------------------

_AKMON_ROOT = Path(__file__).resolve().parents[2]


def test_live_registry_reasoner_policy_passes_the_checker():
    import json

    registry = json.loads(
        (_AKMON_ROOT / "tools" / "model_routing" / "registry.json").read_text(encoding="utf-8")
    )
    verifier = verify.Verifier(_AKMON_ROOT)
    verifier._check_model_routing_registry(registry)
    errors = _messages(verifier.findings, "error")
    assert not errors, errors


def test_reasoner_policy_accepts_dynamic_orchestrator_value(tmp_path):
    root = _make_project(tmp_path)
    registry_path = root / "_aitna" / "akmon" / "tools" / "model_routing" / "registry.json"
    import json

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for vendor in ("anthropic", "openai"):
        registry[vendor]["selection_policy"]["reasoner"] = "orchestrator"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    verifier = verify.Verifier(root)
    verifier.run()
    assert "error" not in _levels(verifier.findings), _messages(verifier.findings, "error")


def test_reasoner_policy_rejects_unknown_value(tmp_path):
    root = _make_project(tmp_path)
    registry_path = root / "_aitna" / "akmon" / "tools" / "model_routing" / "registry.json"
    import json

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["anthropic"]["selection_policy"]["reasoner"] = "lowest"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    verifier = verify.Verifier(root)
    verifier.run()
    errors = _messages(verifier.findings, "error")
    assert any("semantic selection_policy" in message for message in errors), errors


# --------------------------------------------------------------------------------------
# USE-surface isolation (ADR 0003 §6): the surface must not name dev artifacts
# --------------------------------------------------------------------------------------


def _use_doc(root: Path) -> Path:
    return root / "_aitna" / "akmon" / "roles" / "architect.md"


def _isolation_errors(verifier) -> list[str]:
    return [m for m in _messages(verifier.findings, "error") if "development artifacts" in m]


def test_numbered_adr_citation_is_isolation_error(tmp_path):
    root = _make_project(tmp_path)
    _use_doc(root).write_text("# architect\n\nLocked in ADR 0001.\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("cites ADR 0001" in m for m in _isolation_errors(verifier))


def test_roadmap_citation_is_isolation_error(tmp_path):
    root = _make_project(tmp_path)
    _use_doc(root).write_text("# architect\n\nOut of scope (ROADMAP O1).\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("cites ROADMAP O1" in m for m in _isolation_errors(verifier))


def test_dev_path_in_inline_code_is_isolation_error(tmp_path):
    root = _make_project(tmp_path)
    _use_doc(root).write_text("# architect\n\nWritten into `meta/reviews/x.md`.\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("path meta/reviews/x.md" in m for m in _isolation_errors(verifier))


def test_dev_path_in_markdown_link_is_isolation_error(tmp_path):
    root = _make_project(tmp_path)
    _use_doc(root).write_text("# architect\n\nSee [the record](../../decisions/0001-x.md).\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("decisions/0001-x.md" in m for m in _isolation_errors(verifier))


def test_bare_prose_dev_name_is_isolation_error(tmp_path):
    """An unambiguous dev-artifact name leaks even outside a path/link (no backticks)."""
    root = _make_project(tmp_path)
    _use_doc(root).write_text("# architect\n\nVerification runs self_ci before handoff.\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("names self_ci" in m for m in _isolation_errors(verifier))


def test_generic_dev_vocabulary_is_allowed(tmp_path):
    """The bare concept words stay legal — only number-pinned citations, dev paths, and
    unambiguous dev names leak. Generic words (sync/verify/pytest/design/decisions) do not."""
    root = _make_project(tmp_path)
    _use_doc(root).write_text(
        "# architect\n\nFile an ADR; detail lives in decisions/ ADRs and design/ docs.\n"
        "Run sync and verify, then pytest. Capture the project roadmap before building.\n",
        encoding="utf-8",
    )
    verifier = verify.Verifier(root)
    verifier.run()
    assert not _isolation_errors(verifier), _isolation_errors(verifier)


def test_live_tree_use_surface_isolation_passes():
    """Regression for C35: skills/stats-digest/SKILL.md cited meta/design/model-routing.md,
    a real leak on the live tree that the fixture-only tests above could not catch."""
    verifier = verify.Verifier(_AKMON_ROOT.parent.parent)
    verifier.check_use_surface_isolation()
    assert not _isolation_errors(verifier), _isolation_errors(verifier)


def test_examples_dir_is_deliberately_not_scanned_for_use_surface(tmp_path):
    """C35: examples/ bridges to the dev tree the same way README/CHANGELOG do (worked
    examples with provenance citations for a maintainer, not operative consumer guidance) —
    confirmed deliberate, not an accidental gap in _USE_OPERATIVE_GLOBS."""
    root = _make_project(tmp_path)
    akmon = root / "_aitna" / "akmon"
    examples_dir = akmon / "examples"
    examples_dir.mkdir()
    (examples_dir / "gate-anatomy.md").write_text(
        "# example\n\nSee [the audit](../meta/reviews/review-20260705.md).\n",
        encoding="utf-8",
    )
    verifier = verify.Verifier(root)
    verifier.check_use_surface_isolation()
    assert not _isolation_errors(verifier), _isolation_errors(verifier)


# --------------------------------------------------------------------------------------
# errors
# --------------------------------------------------------------------------------------


def test_missing_agents_md_is_error(tmp_path):
    root = _make_project(tmp_path)
    (root / "AGENTS.md").unlink()
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("AGENTS.md is missing" in message for message in _messages(verifier.findings, "error"))


def test_missing_release_role_is_error(tmp_path):
    root = _make_project(tmp_path)
    (root / "_aitna" / "akmon" / "roles" / "release.md").unlink()
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("roles/release.md is missing" in message for message in _messages(verifier.findings, "error"))


def test_missing_changelog_is_error(tmp_path):
    root = _make_project(tmp_path)
    (root / "_aitna" / "akmon" / "CHANGELOG.md").unlink()
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("CHANGELOG.md is missing" in message for message in _messages(verifier.findings, "error"))


def test_agents_md_missing_anchor_is_error(tmp_path):
    root = _make_project(tmp_path)
    (root / "AGENTS.md").write_text("# AGENTS\nno anchors here\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("akmon block is missing" in message for message in _messages(verifier.findings, "error"))



def test_agents_md_generated_marker_is_error(tmp_path):
    root = _make_project(tmp_path)
    (root / "AGENTS.md").write_text(
        AGENTS_MD + f"\n<!-- {sync.GENERATED_MARKER} -->\n",
        encoding="utf-8",
    )
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("hand-reviewed source" in message for message in _messages(verifier.findings, "error"))


def test_claude_pointer_must_import_agents_md(tmp_path):
    root = _make_project(tmp_path)
    (root / "CLAUDE.md").write_text(
        "# CLAUDE.md\n\nSee [AGENTS.md](AGENTS.md).\n",
        encoding="utf-8",
    )
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("must import @AGENTS.md" in message for message in _messages(verifier.findings, "error"))


def test_vendor_pointer_without_agents_link_is_error(tmp_path):
    root = _make_project(tmp_path)
    (root / ".github" / "copilot-instructions.md").write_text(
        "# Copilot Instructions\n\nNo canonical pointer here.\n",
        encoding="utf-8",
    )
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("do not point at AGENTS.md" in message for message in _messages(verifier.findings, "error"))


def test_missing_vendor_pointers_do_not_emit_a_pointer_ok(tmp_path):
    root = tmp_path
    (root / "AGENTS.md").write_text(AGENTS_MD, encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.check_cross_agent_contract()
    assert not any(
        finding.code == "pointers.vendor-agents-link" and finding.severity == "ok"
        for finding in verifier.findings
    )


def test_a_path_with_a_line_separator_is_escaped_before_it_reaches_a_finding(tmp_path):
    root = tmp_path
    agent = root / "_aitna" / "agents" / "bad\nERROR forged.rule victim"
    agent.mkdir(parents=True)
    verifier = verify.Verifier(root)
    verifier.check_agent_charters()
    assert len(verifier.findings) == 1
    finding = verifier.findings[0]
    assert finding.severity == "error"
    assert r"\nERROR forged.rule victim" in finding.target
    assert len(render(finding).splitlines()) == 1


def test_skills_without_agents_source_root_reference_is_warning(tmp_path):
    root = _make_project(tmp_path)
    agents_without_skills = AGENTS_MD.replace(
        "Skills live in `_aitna/skills/` and root `skills/`; generated vendor skill stubs are pointers only.\n",
        "",
    )
    (root / "AGENTS.md").write_text(agents_without_skills, encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("does not mention source skill roots" in message for message in _messages(verifier.findings, "warn"))


def test_skill_missing_frontmatter_is_error(tmp_path):
    root = _make_project(tmp_path)
    (root / "_aitna" / "akmon" / "skills" / "demo" / "SKILL.md").write_text("# demo\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("missing required frontmatter" in message for message in _messages(verifier.findings, "error"))


def test_skill_missing_required_frontmatter_field_is_error(tmp_path):
    root = _make_project(tmp_path)
    (root / "_aitna" / "akmon" / "skills" / "demo" / "SKILL.md").write_text(
        SKILL_MD.replace("owner: akmon\n", ""),
        encoding="utf-8",
    )
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("frontmatter is missing: metadata.owner" in message for message in _messages(verifier.findings, "error"))


def _skill_codes(root: Path, text: str, name: str = "demo") -> set[str]:
    skill = root / "_aitna" / "akmon" / "skills" / name / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(text, encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    return {
        finding.code
        for finding in verifier.findings
        if finding.code.startswith("skills.") and finding.severity == "error"
    }


def test_skill_contract_accepts_the_fixture_without_when_to_use(tmp_path):
    assert "when_to_use" not in SKILL_MD
    assert _skill_codes(_make_project(tmp_path), SKILL_MD) == set()


def test_skill_owner_at_the_top_level_is_not_metadata_owner(tmp_path):
    root = _make_project(tmp_path)
    text = SKILL_MD.replace("metadata:\n  owner: akmon\n", "owner: akmon\n")
    assert _skill_codes(root, text) == {"skills.required-fields"}


@pytest.mark.parametrize("name", ["Demo", "-demo", "demo-", "de--mo", "de_mo", "a" * 65])
def test_skill_name_outside_the_standard_is_error(tmp_path, name):
    root = _make_project(tmp_path)
    assert "skills.name-format" in _skill_codes(root, SKILL_MD.replace("name: demo\n", f"name: {name}\n"), name)


def test_skill_name_of_64_characters_is_accepted(tmp_path):
    root = _make_project(tmp_path)
    name = "a" * 64
    assert _skill_codes(root, SKILL_MD.replace("name: demo\n", f"name: {name}\n"), name) == set()


@pytest.mark.parametrize(("length", "codes"), [(1024, set()), (1025, {"skills.description-length"})])
def test_skill_description_limit(tmp_path, length, codes):
    root = _make_project(tmp_path)
    text = SKILL_MD.replace(
        "description: Demonstrates the akmon skill contract. Use for verifier fixture coverage.\n",
        f"description: {'d' * length}\n",
    )
    assert _skill_codes(root, text) == codes


@pytest.mark.parametrize(
    ("description", "codes"),
    [
        ("Produces a report: counts per herd. Use when asked.", {"skills.frontmatter-yaml"}),
        ("Produces the okapi #1 digest. Use when asked.", {"skills.frontmatter-yaml"}),
        ("#1 digest of okapis. Use when asked.", {"skills.frontmatter-yaml"}),
        ('"Produces a report: counts, the #1 digest. Use when asked."', set()),
        ("'Produces a report: counts, the #1 digest. Use when asked.'", set()),
        ("Produces a C# report. Use when asked.", set()),
    ],
)
def test_skill_frontmatter_yaml_hazards(tmp_path, description, codes):
    root = _make_project(tmp_path)
    text = SKILL_MD.replace(
        "description: Demonstrates the akmon skill contract. Use for verifier fixture coverage.\n",
        f"description: {description}\n",
    )
    assert _skill_codes(root, text) == codes


def test_skill_frontmatter_yaml_hazard_in_a_nested_value(tmp_path):
    root = _make_project(tmp_path)
    text = SKILL_MD.replace("  owner: akmon\n", "  owner: team: akmon\n")
    assert _skill_codes(root, text) == {"skills.frontmatter-yaml"}


def test_agents_md_should_not_link_generated_agents_skill_stubs(tmp_path):
    root = _make_project(tmp_path)
    (root / "AGENTS.md").write_text(AGENTS_MD + "\nUse `.agents/skills/demo/SKILL.md`.\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any(".agents/skills stubs" in message for message in _messages(verifier.findings, "warn"))


def test_obsolete_generated_agents_skill_stub_is_error(tmp_path):
    root = _make_project(tmp_path)
    stale = root / ".agents" / "skills" / "old-skill" / "SKILL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text(f"---\n# {sync.GENERATED_MARKER}\nname: old-skill\n---\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any(".agents/skills/old-skill/SKILL.md" in message for message in _messages(verifier.findings, "error"))


def test_skill_frontmatter_name_must_match_directory(tmp_path):
    root = _make_project(tmp_path)
    (root / "_aitna" / "akmon" / "skills" / "demo" / "SKILL.md").write_text(
        SKILL_MD.replace("name: demo\n", "name: other\n"),
        encoding="utf-8",
    )
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("name must match its skill directory" in message for message in _messages(verifier.findings, "error"))


def test_agents_md_should_not_link_generated_skill_stubs(tmp_path):
    root = _make_project(tmp_path)
    (root / "AGENTS.md").write_text(
        AGENTS_MD + "\nUse `.claude/skills/demo/SKILL.md`.\n",
        encoding="utf-8",
    )
    verifier = verify.Verifier(root)
    verifier.run()
    assert any(
        "generated .claude/skills or .agents/skills stubs" in message
        for message in _messages(verifier.findings, "warn")
    )


def test_stale_generated_pointer_is_error(tmp_path):
    root = _make_project(tmp_path)
    (root / "CLAUDE.md").write_text("hand-edited, drifted\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("generated pointers are stale" in message for message in _messages(verifier.findings, "error"))


def test_obsolete_generated_skill_stub_is_error(tmp_path):
    root = _make_project(tmp_path)
    stale = root / ".claude" / "skills" / "old-skill" / "SKILL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text(f"# old-skill\n\n<!-- {sync.GENERATED_MARKER} -->\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("old-skill/SKILL.md" in message for message in _messages(verifier.findings, "error"))


def test_missing_memory_index_is_error(tmp_path):
    root = _make_project(tmp_path)
    (root / "_aitna" / "memory" / "README.md").unlink()
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("needs README.md index" in message for message in _messages(verifier.findings, "error"))


def test_main_returns_1_on_error(tmp_path):
    root = _make_project(tmp_path)
    (root / "AGENTS.md").unlink()
    assert verify.main(["--project-root", str(root)]) == 1


# --------------------------------------------------------------------------------------
# warnings
# --------------------------------------------------------------------------------------


def test_legacy_memory_index_is_warning(tmp_path):
    root = _make_project(tmp_path)
    memory = root / "_aitna" / "memory"
    (memory / "README.md").unlink()
    _write(memory / "MEMORY.md", "# Memory\n- note.md\n")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("README.md is the preferred index" in message for message in _messages(verifier.findings, "warn"))


def test_memory_file_missing_from_index_is_warning(tmp_path):
    root = _make_project(tmp_path)
    _write(root / "_aitna" / "memory" / "orphan.md", "unlisted\n")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("not mentioned in index" in message for message in _messages(verifier.findings, "warn"))


def test_gitignore_without_env_pattern_is_warning(tmp_path):
    root = _make_project(tmp_path)
    (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("*.env" in message for message in _messages(verifier.findings, "warn"))


def test_ci_missing_akmon_commands_is_warning(tmp_path):
    root = _make_project(tmp_path)
    (root / ".github" / "workflows" / "ci.yml").write_text("name: CI\non: [push]\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("CI should run" in message for message in _messages(verifier.findings, "warn"))


def _tasks(root: Path) -> Path:
    return root / "_aitna" / "TASKS.md"


def test_well_formed_index_tasks_is_ok(tmp_path):
    root = _make_project(tmp_path)
    _tasks(root).write_text(
        "# TASKS\n\n- T1 · do a thing · active · engineer · ship the thing\n",
        encoding="utf-8",
    )
    verifier = verify.Verifier(root)
    verifier.run()
    assert "warn" not in _levels(verifier.findings), _messages(verifier.findings, "warn")


def test_missing_akmon_gitignore_is_warning(tmp_path):
    root = _make_project(tmp_path)
    (root / "_aitna" / "akmon" / ".gitignore").unlink()
    verifier = verify.Verifier(root)
    verifier.run()
    assert any(
        "_aitna/akmon/.gitignore is missing" in message for message in _messages(verifier.findings, "warn")
    )


def test_akmon_gitignore_without_pycache_is_warning(tmp_path):
    root = _make_project(tmp_path)
    (root / "_aitna" / "akmon" / ".gitignore").write_text("*.env\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("should ignore __pycache__/" in message for message in _messages(verifier.findings, "warn"))


def test_done_entry_in_active_tasks_is_warning(tmp_path):
    root = _make_project(tmp_path)
    _tasks(root).write_text("- T1 · old work · done · engineer · finished\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("TASKS_ARCHIVE.md" in message for message in _messages(verifier.findings, "warn"))


def test_entry_without_status_is_warning(tmp_path):
    root = _make_project(tmp_path)
    _tasks(root).write_text("- T1 · vague · engineer · no status token here\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    warnings = _messages(verifier.findings, "warn")
    assert any("status outside" in message and "T1" in message for message in warnings), warnings


def test_free_form_status_is_warning_even_when_the_prose_says_blocked(tmp_path):
    """The defect the old whole-line search could not see: the status field is what is checked."""
    root = _make_project(tmp_path)
    _tasks(root).write_text(
        "- T1 · a thing · code-complete & D2-pending (D2-1) · engineer · nothing here is blocked\n",
        encoding="utf-8",
    )
    verifier = verify.Verifier(root)
    verifier.run()
    warnings = _messages(verifier.findings, "warn")
    assert any("status outside" in message and "T1" in message for message in warnings), warnings


def test_prose_containing_done_is_not_reported_as_a_done_entry(tmp_path):
    """The mirror defect: `done` anywhere in the line used to mean the entry was finished."""
    root = _make_project(tmp_path)
    _tasks(root).write_text(
        "- T1 · a thing · active · engineer · the previous attempt is done with; this one is not\n",
        encoding="utf-8",
    )
    verifier = verify.Verifier(root)
    verifier.run()
    assert not any("TASKS_ARCHIVE.md" in message for message in _messages(verifier.findings, "warn"))


def test_status_qualifier_and_emphasis_stay_valid(tmp_path):
    root = _make_project(tmp_path)
    _tasks(root).write_text(
        "- T1 · a thing · blocked (after T9) · engineer · waits on T9\n"
        "- T2 · another · **deferred** · engineer · parked on purpose\n",
        encoding="utf-8",
    )
    verifier = verify.Verifier(root)
    verifier.run()
    assert "warn" not in _levels(verifier.findings), _messages(verifier.findings, "warn")


def test_indented_note_under_an_entry_is_not_an_entry(tmp_path):
    """A note under an entry is not held to the entry grammar (pipelines/tasks.md)."""
    root = _make_project(tmp_path)
    _tasks(root).write_text(
        "- T1 · a thing · active · engineer · ship it\n"
        "    - **finding A · the sub-bullet that used to be read as an entry**\n",
        encoding="utf-8",
    )
    verifier = verify.Verifier(root)
    verifier.run()
    assert "warn" not in _levels(verifier.findings), _messages(verifier.findings, "warn")


def test_done_entry_is_named_in_the_archive_warning(tmp_path):
    root = _make_project(tmp_path)
    _tasks(root).write_text(
        "- T1 · old work · done · engineer · finished\n"
        "- T2 · live work · active · engineer · ongoing\n",
        encoding="utf-8",
    )
    verifier = verify.Verifier(root)
    verifier.run()
    warnings = [message for message in _messages(verifier.findings, "warn") if "TASKS_ARCHIVE.md" in message]
    assert warnings and "T1" in warnings[0] and "T2" not in warnings[0], warnings


def test_dates_in_tasks_are_warning(tmp_path):
    root = _make_project(tmp_path)
    _tasks(root).write_text(
        "- T1 · do a thing · active · engineer · landed 2026-06-21\n", encoding="utf-8"
    )
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("dates" in message for message in _messages(verifier.findings, "warn"))


def test_oversized_tasks_file_is_warning(tmp_path):
    root = _make_project(tmp_path)
    _tasks(root).write_text("\n".join(f"line {i}" for i in range(250)), encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("index" in message for message in _messages(verifier.findings, "warn"))


def test_strict_turns_warning_into_failure(tmp_path):
    root = _make_project(tmp_path)
    (root / ".gitignore").write_text("nothing useful\n", encoding="utf-8")
    assert verify.main(["--project-root", str(root)]) == 0  # warning only → ok without strict
    assert verify.main(["--project-root", str(root), "--strict"]) == 1  # strict → fail


# --------------------------------------------------------------------------------------
# changelog (ADR 0001 §9)
# --------------------------------------------------------------------------------------


def _changelog(root: Path) -> Path:
    return root / "_aitna" / "akmon" / "CHANGELOG.md"


def test_changelog_with_unreleased_is_ok(tmp_path):
    root = _make_project(tmp_path)
    _changelog(root).write_text("# Changelog\n\n## Unreleased\n\n### Added\n- x\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert not any("CHANGELOG" in message for message in _messages(verifier.findings, "warn"))
    assert any("Unreleased section" in message for message in _messages(verifier.findings, "ok"))


def test_changelog_without_unreleased_is_warning(tmp_path):
    root = _make_project(tmp_path)
    _changelog(root).write_text("# Changelog\n\n## v0.1.0\n\n### Added\n- x\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("Unreleased" in message for message in _messages(verifier.findings, "warn"))


# --------------------------------------------------------------------------------------
# integration record (_aitna/.akmon.toml) — a consumer artifact, non-gating when absent
# --------------------------------------------------------------------------------------

_VALID_ATTACH = (
    'akmon_version = "v0.3.0"\n'
    'attached_archetype = "package/python"\n'
    'last_realign = "v0.3.0"\n'
)


def _attach(root: Path) -> Path:
    return root / "_aitna" / ".akmon.toml"


def test_attach_record_missing_is_non_gating(tmp_path):
    root = _make_project(tmp_path)  # _make_project never writes .akmon.toml
    verifier = verify.Verifier(root)
    verifier.check_attach_record()
    assert "warn" not in _levels(verifier.findings)
    assert "error" not in _levels(verifier.findings)
    assert any(".akmon.toml not present" in m for m in _messages(verifier.findings, "ok"))


def test_attach_record_valid_is_ok(tmp_path):
    root = _make_project(tmp_path)
    _attach(root).write_text(_VALID_ATTACH, encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.check_attach_record()
    assert any("records akmon version v0.3.0" in m for m in _messages(verifier.findings, "ok"))


def _record(root: Path, *, pin: str, realigned: str) -> None:
    _attach(root).write_text(
        f'akmon_version = "{pin}"\nattached_archetype = "package/python"\nlast_realign = "{realigned}"\n',
        encoding="utf-8",
    )


def test_attach_realign_matching_the_pin_is_ok(tmp_path):
    root = _make_project(tmp_path)
    _record(root, pin="v0.3.0", realigned="v0.3.0")
    verifier = verify.Verifier(root)
    verifier.check_attach_record()
    assert "error" not in _levels(verifier.findings)
    assert any("realigned at v0.3.0" in m for m in _messages(verifier.findings, "ok"))


def test_attach_realign_behind_the_pin_is_error(tmp_path):
    """The state a package-mode bump leaves when `sync` ran and `init` did not."""
    root = _make_project(tmp_path)
    _record(root, pin="0.4.0.dev0", realigned="v0.2.1")
    verifier = verify.Verifier(root)
    verifier.check_attach_record()
    errors = _messages(verifier.findings, "error")
    assert any("0.4.0.dev0" in m and "v0.2.1" in m for m in errors)
    assert any(
        finding.code == "attach.realign" and "akmon init" in finding.fix
        for finding in verifier.findings
    )


def test_attach_realign_accepts_the_two_recorded_spellings(tmp_path):
    """A mounted record writes `git describe` and a package one writes PEP 440 — same version."""
    root = _make_project(tmp_path)
    _record(root, pin="0.3.0", realigned="v0.3.0")
    verifier = verify.Verifier(root)
    verifier.check_attach_record()
    assert "error" not in _levels(verifier.findings)


def test_attach_realign_ignores_a_describe_distance(tmp_path):
    """A mount past its tag is `cli._skew_notice`'s fact, not a missing realign."""
    root = _make_project(tmp_path)
    _record(root, pin="v0.3.0-5-gabc1234", realigned="v0.3.0")
    verifier = verify.Verifier(root)
    verifier.check_attach_record()
    assert "error" not in _levels(verifier.findings)


def test_attach_realign_silent_when_the_record_is_malformed(tmp_path):
    """One finding per defect: a record missing keys cannot also be judged for freshness."""
    root = _make_project(tmp_path)
    _write(_attach(root), 'akmon_version = "v0.3.0"\n')
    verifier = verify.Verifier(root)
    verifier.check_attach_record()
    assert not any(finding.code == "attach.realign" for finding in verifier.findings)


def test_attach_record_malformed_is_error(tmp_path):
    root = _make_project(tmp_path)
    _attach(root).write_text('akmon_version = "v0.3.0"\n', encoding="utf-8")  # missing the other keys
    verifier = verify.Verifier(root)
    verifier.check_attach_record()
    errors = _messages(verifier.findings, "error")
    assert any("missing required key" in m for m in errors)


@pytest.mark.parametrize(
    ("version_key", "toml_value"),
    [
        ("akmon_version", "42"),
        ("last_realign", '{ version = "v0.3.0" }'),
    ],
)
def test_attach_record_rejects_non_string_versions(tmp_path, version_key, toml_value):
    root = _make_project(tmp_path)
    values = {
        "akmon_version": '"v0.3.0"',
        "attached_archetype": '"package/python"',
        "last_realign": '"v0.3.0"',
    }
    values[version_key] = toml_value
    _attach(root).write_text(
        "".join(f"{key} = {value}\n" for key, value in values.items()),
        encoding="utf-8",
    )

    verifier = verify.Verifier(root)
    verifier.check_attach_record()

    errors = [finding for finding in verifier.findings if finding.severity == "error"]
    assert len(errors) == 1
    assert errors[0].code == "attach.record"
    assert version_key in errors[0].message
    assert "expected non-empty strings" in errors[0].message
    assert not any(finding.code == "attach.realign" for finding in verifier.findings)


def test_attach_record_skipped_without_akmon_submodule(tmp_path):
    # No _aitna/akmon/ mounted (e.g. verify run against the akmon repo itself): skip entirely.
    root = tmp_path
    _write(root / "_aitna" / "TASKS.md")
    verifier = verify.Verifier(root)
    verifier.check_attach_record()
    assert verifier.findings == []


def test_attach_record_fires_for_package_mode_without_mount_dir(tmp_path):
    # No mount at all, but .akmon.toml exists (the only trace a package-mode consumer
    # leaves) — the gate must fire, not skip (ADR 0009 §4).
    root = tmp_path
    _write(_attach(root), 'akmon_version = "v0.3.0"\n')  # missing attached_archetype/last_realign
    verifier = verify.Verifier(root)
    verifier.check_attach_record()
    assert any("missing required key" in m for m in _messages(verifier.findings, "error"))


def test_attach_record_valid_for_package_mode_without_mount_dir(tmp_path):
    root = tmp_path
    _write(_attach(root), 'mount = "package"\n' + _VALID_ATTACH)
    verifier = verify.Verifier(root)
    verifier.check_attach_record()
    assert "error" not in _levels(verifier.findings)
    assert any("records akmon version v0.3.0" in m for m in _messages(verifier.findings, "ok"))


# --------------------------------------------------------------------------------------
# mount mode "package" (ADR 0009 §4, C37 slice B): a synthetic package-mode project that
# goes end-to-end green after a real sync run, plus the individual re-pointed/re-rooted/
# skipped checks. Mounted-mode fixtures/tests above are untouched and must still pass
# unchanged — that is the byte-identical regression guard for existing consumers.
# --------------------------------------------------------------------------------------

PACKAGE_AGENTS_MD = """# AGENTS.md

## Dev layer — akmon

Read `akmon path` to find the standard tree locally (roles, MODEL.md). Archetype:
`ARCHETYPES.md`. Read `_aitna/memory` at session start.

@_aitna/.akmon/guardrails/_common.md

Prime directives D2 and D5 are always-on. Secrets come from `.env`.
Delegation is the default.
Skills live in `_aitna/skills/` and root `skills/`; generated vendor skill stubs are pointers only.
"""

PACKAGE_CI_YML = """name: CI
on: [push]
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - run: uv run akmon sync --check
      - run: uv run akmon verify --strict
"""

def _package_akmon_toml() -> str:
    """A package-mode record of a project that *is* realigned to what is installed.

    Both version keys carry the installed version, because these fixtures run a real ``sync``,
    and ``sync`` restamps ``akmon_version`` with it (``sync._package_mode_akmon_toml``). A
    literal here would make every whole-verifier package-mode test assert the one state
    ``attach.realign`` exists to reject — an unrealigned project — instead of the green path.
    """
    version = sync._installed_akmon_version() or "0.3.0.dev0"
    return (
        'mount = "package"\n'
        f'akmon_version = "{version}"\n'
        'attached_archetype = "package"\n'
        f'last_realign = "{version}"\n'
    )


def _make_package_mode_project(tmp_path: Path) -> Path:
    """A minimal package-mode project: no mounted tree at all. ``standard_tree_root``
    resolves to this checkout's own akmon tree (the dev-bench "embedded tree" fallback —
    the same property slice A's/B's sync.py tests already rely on), so the standard-tree
    content checks (basic layout, USE-surface isolation, model-routing, skills) validate
    against real, already-compliant content with no extra fixture setup needed.
    """
    root = tmp_path
    _write(root / "AGENTS.md", PACKAGE_AGENTS_MD)
    _write(root / "_aitna" / "TASKS.md")
    _write(root / "_aitna" / ".akmon.toml", _package_akmon_toml())

    _write(root / "_aitna" / "agents" / "engineer" / "README.md", "See `_aitna/akmon/roles/engineer.md`.\n")
    _write(root / "_aitna" / "memory" / "note.md", "fact\n")
    _write(root / "_aitna" / "memory" / "README.md", "# Memory\n- note.md\n")

    _write(root / ".gitignore", GITIGNORE)
    _write(root / ".github" / "workflows" / "ci.yml", PACKAGE_CI_YML)
    # The console script the generated wiring names. A real consumer has it by construction —
    # the dev-group pin puts it in the project venv on install — and since C77 the hook
    # commands reference it, so a fixture without it is not a package-mode project.
    launcher = root / ".venv" / "bin" / "akmon"
    _write(launcher, "#!/bin/sh\n")
    launcher.chmod(0o755)

    # a real sync run: materializes the imported .akmon/guardrails and writes the vendor
    # pointers, exactly as attaching for real would.
    files, errors = sync._planned_files(root)
    assert errors == []
    result = sync._apply(files, write=True, root=root)
    assert not result.errors
    return root


def test_package_mode_project_verifies_green_after_real_sync(tmp_path):
    root = _make_package_mode_project(tmp_path)
    verifier = verify.Verifier(root)
    verifier.run()
    assert "error" not in _levels(verifier.findings), _messages(verifier.findings, "error")
    assert "warn" not in _levels(verifier.findings), _messages(verifier.findings, "warn")


def test_main_strict_passes_on_package_mode_project(tmp_path):
    root = _make_package_mode_project(tmp_path)
    assert verify.main(["--project-root", str(root), "--strict"]) == 0


def test_check_hooks_checks_the_wheels_scripts_in_package_mode(tmp_path):
    """It used to short-circuit here, on the grounds that the generated-pointers check already
    covered the materialized copies. There are no copies since C77: the wiring calls
    ``akmon hook``, so these files' existence in the tree *is* what it rests on."""
    root = tmp_path
    _write(root / "_aitna" / ".akmon.toml", 'mount = "package"\n')
    verifier = verify.Verifier(root)
    verifier.check_hooks()
    assert _levels(verifier.findings) == {"ok"}
    assert any("hooks/codex-hook.py" in finding.message for finding in verifier.findings)


def test_check_hook_launcher_passes_when_the_project_venv_has_the_script(tmp_path):
    root = tmp_path
    _write(root / "_aitna" / ".akmon.toml", 'mount = "package"\n')
    launcher = root / ".venv" / "bin" / "akmon"
    _write(launcher, "#!/bin/sh\n")
    launcher.chmod(0o755)
    verifier = verify.Verifier(root)
    verifier.check_hook_launcher()
    assert _levels(verifier.findings) == {"ok"}


def test_check_hook_launcher_errors_and_names_the_silence(tmp_path):
    """The finding has to say *how* it fails: a hook command whose executable is missing
    produces no session-visible error at all, so "the guardrails are off" is not deducible
    from anything the developer would otherwise see."""
    root = tmp_path
    _write(root / "_aitna" / ".akmon.toml", 'mount = "package"\n')
    verifier = verify.Verifier(root)
    verifier.check_hook_launcher()
    assert _levels(verifier.findings) == {"error"}
    message = verifier.findings[0].message
    assert ".venv/bin/akmon" in message
    assert "silently" in message


def test_check_hook_launcher_errors_when_the_script_is_not_executable(tmp_path):
    root = tmp_path
    _write(root / "_aitna" / ".akmon.toml", 'mount = "package"\n')
    launcher = root / ".venv" / "bin" / "akmon"
    _write(launcher, "#!/bin/sh\n")
    launcher.chmod(0o644)

    verifier = verify.Verifier(root)
    verifier.check_hook_launcher()

    assert _levels(verifier.findings) == {"error"}
    assert "not executable" in verifier.findings[0].message


# --------------------------------------------------------------------------------------
# C70 — codex host-trust (D2-27, design §7). conftest.py hides the real `codex` from PATH for
# every test; these carriers inject a hooks/list runner (and let `which` resolve codex), or,
# for the one end-to-end read-only carrier, put a stand-in `codex` executable first on PATH.
# Every fixture is the real generator's population for its root, never a hand-kept copy.
# --------------------------------------------------------------------------------------

_CANARY = "VENDOR_CANARY_7f3a"
_ABSENT = object()


def _write_codex_wiring(root: Path, text: str | None = None) -> None:
    """The real generator's `.codex/hooks.json` for ``root`` — or ``text`` in its place."""
    _write(root / ".codex" / "hooks.json", sync._codex_hooks_text(root) if text is None else text)


def _hook_entry(*, event: str, matcher: str, command: str, enabled=True, trust="trusted") -> dict:
    return {
        "handlerType": "command",
        "eventName": event,
        "matcher": matcher,
        "command": command,
        "enabled": enabled,
        "trustStatus": trust,
    }


def _generated_entries(root: Path) -> list[dict]:
    """One live, trusted hooks/list entry per entry the real generator wires for ``root``."""
    return [
        _hook_entry(event=event, matcher=matcher, command=command)
        for event, matcher, command in expected_codex_hooks(sync._codex_hooks(root))
    ]


def _hooks_list_runner(entries, calls=None):
    def runner(command, cwd, timeout):
        if calls is not None:
            calls.append((cwd, timeout))
        data = [{"cwd": str(cwd), "hooks": entries, "warnings": [], "errors": []}]
        return json.dumps({"id": 2, "result": {"data": data}})

    return runner


def _live_query_verifier(root: Path, monkeypatch, runner) -> verify.Verifier:
    """A Verifier on which `codex` resolves and whose hooks/list answer is ``runner``'s."""
    real_which = shutil.which
    monkeypatch.setattr(
        verify.shutil,
        "which",
        lambda name, *args, **kwargs: "/usr/bin/codex" if name == "codex" else real_which(name, *args, **kwargs),
    )
    return verify.Verifier(root, codex_hooks_runner=runner)


def _host_trust(verifier: verify.Verifier) -> list:
    return [finding for finding in verifier.findings if finding.code == "codex.host-trust"]


def _only_host_trust_message(verifier: verify.Verifier) -> str:
    (finding,) = _host_trust(verifier)
    return finding.message


# Wiring the gate has to stop at *before* parsing: the first four would raise in the parse.
_UNUSABLE_WIRING = ["not-json", "not-an-object", "hooks-not-an-object", "unknown-event", "stale", "reformatted"]


def _unusable_wiring(root: Path, kind: str) -> str:
    wiring = sync._codex_hooks(root)
    if kind == "stale":
        wiring["hooks"]["PreToolUse"][0]["hooks"].pop()
        return json.dumps(wiring, indent=2) + "\n"
    if kind == "reformatted":  # the same object, not the same text — stale to `sync --check`
        return json.dumps(wiring)
    return {
        "not-json": "{not json",
        "not-an-object": "[]",
        "hooks-not-an-object": json.dumps({"hooks": []}),
        "unknown-event": json.dumps({"hooks": {"UnknownEvent": [{"hooks": [{"type": "command", "command": "x"}]}]}}),
    }[kind]


def test_the_generated_population_is_four_command_entries(tmp_path):
    """The carriers below derive their fixture from the real generator; pin its size so a
    shrinking population cannot quietly thin the corpus."""
    assert len(_generated_entries(tmp_path)) == 4


def test_check_codex_host_trust_is_silent_without_generated_wiring(tmp_path, monkeypatch):
    calls = []
    verifier = _live_query_verifier(tmp_path, monkeypatch, _hooks_list_runner([], calls))
    verifier.check_codex_host_trust()
    assert verifier.findings == []
    assert calls == []


@pytest.mark.parametrize("kind", _UNUSABLE_WIRING)
def test_check_codex_host_trust_neither_parses_nor_queries_unusable_wiring(tmp_path, monkeypatch, kind):
    """TASKS.md C70: "no call after missing/invalid/stale wiring" — and no traceback from
    parsing it first (third C70 review: `[]` and an unknown event raised)."""
    _write_codex_wiring(tmp_path, _unusable_wiring(tmp_path, kind))
    calls = []
    verifier = _live_query_verifier(tmp_path, monkeypatch, _hooks_list_runner(_generated_entries(tmp_path), calls))
    verifier.check_codex_host_trust()
    assert verifier.findings == []
    assert calls == []


@pytest.mark.parametrize("kind", _UNUSABLE_WIRING)
def test_run_reports_unusable_wiring_once_and_never_queries(tmp_path, monkeypatch, kind):
    """Through `run()`: the drift is exactly the one `pointers.generated-freshness` error, the
    host is never asked, and C70 adds nothing of its own."""
    root = _make_project(tmp_path)
    _write_codex_wiring(root, _unusable_wiring(root, kind))
    calls = []
    verifier = _live_query_verifier(root, monkeypatch, _hooks_list_runner(_generated_entries(root), calls))
    verifier.run()
    assert calls == []
    assert _host_trust(verifier) == []
    freshness = [f for f in verifier.findings if f.code == "pointers.generated-freshness"]
    assert [f.severity for f in freshness] == ["error"]
    assert ".codex/hooks.json" in freshness[0].message


def test_check_codex_host_trust_is_silent_when_the_generator_wires_nothing(tmp_path, monkeypatch):
    text = json.dumps({"hooks": {}}, indent=2) + "\n"
    monkeypatch.setattr(verify.sync_tool, "_codex_hooks_text", lambda root: text)
    _write_codex_wiring(tmp_path, text)
    calls = []
    verifier = _live_query_verifier(tmp_path, monkeypatch, _hooks_list_runner([], calls))
    verifier.check_codex_host_trust()
    assert verifier.findings == []
    assert calls == []


def test_check_codex_host_trust_skips_neutrally_when_codex_is_not_installed(tmp_path):
    """No `which` patch: conftest's codex-free PATH is the absent installation, the same
    mechanism self-CI's fixture legs use in place of a switch in verify."""
    _write_codex_wiring(tmp_path)
    calls = []
    verifier = verify.Verifier(tmp_path, codex_hooks_runner=_hooks_list_runner([], calls))
    verifier.check_codex_host_trust()
    assert _levels(verifier.findings) == {"ok"}
    assert "not installed" in verifier.findings[0].message
    assert calls == []


def test_check_codex_host_trust_ok_when_every_generated_entry_is_trusted(tmp_path, monkeypatch):
    _write_codex_wiring(tmp_path)
    verifier = _live_query_verifier(tmp_path, monkeypatch, _hooks_list_runner(_generated_entries(tmp_path)))
    verifier.check_codex_host_trust()
    assert _levels(verifier.findings) == {"ok"}


def test_check_codex_host_trust_ignores_extras_other_roots_and_order(tmp_path, monkeypatch):
    _write_codex_wiring(tmp_path)
    entries = [
        *reversed(_generated_entries(tmp_path)),
        _hook_entry(event="preToolUse", matcher="Bash", command="owner-hook", trust="untrusted"),
    ]

    def runner(command, cwd, timeout):
        data = [
            {"cwd": "/elsewhere", "hooks": [], "warnings": [], "errors": ["not this project"]},
            {"cwd": str(cwd), "hooks": entries, "warnings": [], "errors": []},
        ]
        return json.dumps({"id": 2, "result": {"data": data}})

    verifier = _live_query_verifier(tmp_path, monkeypatch, runner)
    verifier.check_codex_host_trust()
    assert _levels(verifier.findings) == {"ok"}


def test_check_codex_host_trust_zero_discovered_entries_is_every_one_missing(tmp_path, monkeypatch):
    _write_codex_wiring(tmp_path)
    verifier = _live_query_verifier(tmp_path, monkeypatch, _hooks_list_runner([]))
    verifier.check_codex_host_trust()
    assert _levels(verifier.findings) == {"warn"}
    assert _only_host_trust_message(verifier) == "Codex hook delivery is incomplete: missing (4)"


@pytest.mark.parametrize("index", range(4))
def test_check_codex_host_trust_warns_when_any_one_generated_entry_is_missing(tmp_path, monkeypatch, index):
    _write_codex_wiring(tmp_path)
    entries = _generated_entries(tmp_path)
    del entries[index]
    verifier = _live_query_verifier(tmp_path, monkeypatch, _hooks_list_runner(entries))
    verifier.check_codex_host_trust()
    assert _levels(verifier.findings) == {"warn"}
    assert _only_host_trust_message(verifier) == "Codex hook delivery is incomplete: missing (1)"
    assert exit_code(verifier.findings, strict=True) == 1


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"enabled": False}, "disabled"),
        ({"trustStatus": "untrusted"}, "untrusted"),
        ({"trustStatus": "modified"}, "modified"),
    ],
)
@pytest.mark.parametrize("index", range(4))
def test_check_codex_host_trust_names_each_inert_state_of_each_entry(tmp_path, monkeypatch, index, change, problem):
    _write_codex_wiring(tmp_path)
    entries = _generated_entries(tmp_path)
    entries[index] = {**entries[index], **change}
    verifier = _live_query_verifier(tmp_path, monkeypatch, _hooks_list_runner(entries))
    verifier.check_codex_host_trust()
    assert _levels(verifier.findings) == {"warn"}
    assert _only_host_trust_message(verifier) == f"Codex hook delivery is incomplete: {problem} (1)"


def test_check_codex_host_trust_aggregates_mixed_problems_into_one_warning(tmp_path, monkeypatch):
    _write_codex_wiring(tmp_path)
    entries = _generated_entries(tmp_path)
    entries[0] = {**entries[0], "trustStatus": "untrusted"}
    entries[1] = {**entries[1], "enabled": False}
    del entries[3]
    verifier = _live_query_verifier(tmp_path, monkeypatch, _hooks_list_runner(entries))
    verifier.check_codex_host_trust()
    assert _levels(verifier.findings) == {"warn"}
    assert _only_host_trust_message(verifier) == (
        "Codex hook delivery is incomplete: disabled (1); missing (1); untrusted (1)"
    )
    # The message carries categories and counts only, so the remediation cannot point at a list.
    assert _host_trust(verifier)[0].fix == "Open `/hooks` in Codex and re-approve the affected generated entries."
    assert exit_code(verifier.findings, strict=True) == 1
    assert exit_code(verifier.findings, strict=False) == 0


@pytest.mark.parametrize(
    "change",
    [
        {"enabled": "false"},
        {"enabled": _ABSENT},
        {"trustStatus": 7},
        {"trustStatus": _CANARY},
        {"command": ["x"]},
        {"matcher": {"x": 1}},
        {"handlerType": _ABSENT},
    ],
    ids=[
        "enabled-string-false",
        "enabled-absent",
        "trust-int",
        "trust-unknown",
        "command-list",
        "matcher-object",
        "handler-absent",
    ],
)
def test_check_codex_host_trust_malformed_hook_metadata_is_a_warning_never_green(tmp_path, monkeypatch, change):
    """Third C70 review: `enabled: "false"` read as enabled and a scalar hook was skipped, so a
    broken answer came out ok. Any malformed field is an uninspectable answer: warn, strict 1."""
    _write_codex_wiring(tmp_path)
    entries = _generated_entries(tmp_path)
    entries[0] = {k: v for k, v in {**entries[0], **change}.items() if v is not _ABSENT}
    verifier = _live_query_verifier(tmp_path, monkeypatch, _hooks_list_runner(entries))
    verifier.check_codex_host_trust()
    assert _levels(verifier.findings) == {"warn"}
    assert "could not be inspected" in _only_host_trust_message(verifier)
    assert _CANARY not in repr(verifier.findings)


@pytest.mark.parametrize("extra", [1, _CANARY, None])
def test_check_codex_host_trust_a_scalar_hook_element_is_a_warning(tmp_path, monkeypatch, extra):
    _write_codex_wiring(tmp_path)
    verifier = _live_query_verifier(tmp_path, monkeypatch, _hooks_list_runner([*_generated_entries(tmp_path), extra]))
    verifier.check_codex_host_trust()
    assert _levels(verifier.findings) == {"warn"}
    assert _CANARY not in repr(verifier.findings)


def test_check_codex_host_trust_warns_when_the_protocol_cannot_be_trusted(tmp_path, monkeypatch):
    _write_codex_wiring(tmp_path)
    verifier = _live_query_verifier(tmp_path, monkeypatch, lambda command, cwd, timeout: "not json")
    verifier.check_codex_host_trust()
    assert _levels(verifier.findings) == {"warn"}
    assert "hooks/list" in verifier.findings[0].message
    assert exit_code(verifier.findings, strict=True) == 1


def test_run_queries_the_host_exactly_once_after_valid_wiring(tmp_path, monkeypatch):
    """Driven through `Verifier.run()` only, never the method directly: deleting C70's call from
    `run()`, or calling it twice, fails here — the one-call carrier TASKS.md C70 names. The one
    call asks about the consumer root with the pinned 5.0 s query timeout (D2-40 (6))."""
    root = _make_project(tmp_path)
    calls = []
    verifier = _live_query_verifier(root, monkeypatch, _hooks_list_runner(_generated_entries(root), calls))
    verifier.run()
    assert calls == [(root, 5.0)]
    assert [finding.severity for finding in _host_trust(verifier)] == ["ok"]


@pytest.mark.parametrize("order", ["trusted-first", "untrusted-first"])
def test_check_codex_host_trust_ambiguous_duplicate_entries_warn(tmp_path, monkeypatch, order):
    _write_codex_wiring(tmp_path)
    entries = _generated_entries(tmp_path)
    duplicate = {**entries[0], "trustStatus": "untrusted"}
    entries = [entries[0], duplicate, *entries[1:]] if order == "trusted-first" else [duplicate, *entries]
    verifier = _live_query_verifier(tmp_path, monkeypatch, _hooks_list_runner(entries))
    verifier.check_codex_host_trust()
    assert _levels(verifier.findings) == {"warn"}
    assert _only_host_trust_message(verifier) == "Codex hook delivery is incomplete: ambiguous (1)"


@pytest.mark.parametrize("order", ["trusted-first", "empty-first"])
def test_check_codex_host_trust_a_second_answer_for_the_project_is_uninspectable(tmp_path, monkeypatch, order):
    """Fourth C70 review: `[trusted, empty]` for the same cwd read green and the reverse read
    `missing (4)`. Either order is now the same uninspectable warning, strict exit 1."""
    _write_codex_wiring(tmp_path)

    def runner(command, cwd, timeout):
        trusted = {"cwd": str(cwd), "hooks": _generated_entries(tmp_path), "warnings": [], "errors": []}
        empty = {**trusted, "hooks": []}
        data = [trusted, empty] if order == "trusted-first" else [empty, trusted]
        return json.dumps({"id": 2, "result": {"data": data}})

    verifier = _live_query_verifier(tmp_path, monkeypatch, runner)
    verifier.check_codex_host_trust()
    assert _only_host_trust_message(verifier) == (
        "codex app-server hooks/list could not be inspected: hooks/list answered this project more than once"
    )
    assert exit_code(verifier.findings, strict=True) == 1


def test_check_codex_host_trust_runner_failure_becomes_a_warn_not_a_crash(tmp_path, monkeypatch):
    """A runner that raises an exception other than CodexProtocolError (a write/flush failure, an
    exec race) must still produce a Finding, never propagate past check_codex_host_trust."""
    _write_codex_wiring(tmp_path)

    def flaky_runner(command, cwd, timeout):
        raise BrokenPipeError("exec race")

    verifier = _live_query_verifier(tmp_path, monkeypatch, flaky_runner)
    verifier.check_codex_host_trust()  # must not raise
    assert _levels(verifier.findings) == {"warn"}


def _raising(exc):
    def runner(command, cwd, timeout):
        raise exc

    return runner


def _answering(message):
    return lambda command, cwd, timeout: message if isinstance(message, str) else json.dumps(message)


def _project_answer(**fields):
    def runner(command, cwd, timeout):
        entry = {"cwd": str(cwd), "hooks": [], "warnings": [], "errors": [], **fields}
        return json.dumps({"id": 2, "result": {"data": [entry]}})

    return runner


class _VendorTextProtocolError(CodexProtocolError):
    def __str__(self):
        return _CANARY


@pytest.mark.parametrize(
    "runner",
    [
        _raising(RuntimeError(_CANARY)),
        _raising(OSError(5, _CANARY)),
        _raising(CodexProtocolError(_CANARY)),
        _raising(_VendorTextProtocolError("timeout")),
        _answering(_CANARY),
        _answering(json.dumps(_CANARY)),
        _answering({"id": _CANARY, "result": {"data": []}}),
        _answering({"id": 2, "error": {"code": _CANARY, "message": _CANARY}}),
        _answering({"id": 2, "error": {"code": -32000, "message": _CANARY}}),
        _answering({"id": 2, "result": {"data": _CANARY}}),
        _project_answer(errors=[_CANARY]),
        _project_answer(warnings=_CANARY),
        _project_answer(hooks=[_CANARY]),
    ],
    ids=[
        "exception-text",
        "os-error-text",
        "protocol-error-text",
        "protocol-error-str",
        "raw-body",
        "json-string-body",
        "response-id",
        "error-code-and-message",
        "error-message",
        "data-value",
        "project-errors",
        "project-warnings",
        "hook-element",
    ],
)
def test_check_codex_host_trust_never_prints_a_value_from_the_host(tmp_path, monkeypatch, runner):
    """design §7's no-vendor-output-leak boundary, per place a host value could ride in: the
    finding is a warning built from fixed categories, and the canary appears nowhere in it."""
    _write_codex_wiring(tmp_path)
    verifier = _live_query_verifier(tmp_path, monkeypatch, runner)
    verifier.check_codex_host_trust()
    assert _levels(verifier.findings) == {"warn"}
    assert _CANARY not in repr(verifier.findings)


def test_check_codex_host_trust_an_unknown_trust_status_is_not_echoed_as_a_problem_name(tmp_path, monkeypatch):
    """hook_trust_problems names an unknown trustStatus `unrecognized` rather than by value; the
    query layer rejects it first, so either way the vendor's word never reaches the summary."""
    _write_codex_wiring(tmp_path)
    entries = _generated_entries(tmp_path)
    entries[2] = {**entries[2], "trustStatus": _CANARY}
    verifier = _live_query_verifier(tmp_path, monkeypatch, _hooks_list_runner(entries))
    verifier.check_codex_host_trust()
    assert _CANARY not in repr(verifier.findings)


def test_no_environment_variable_turns_the_check_off(tmp_path, monkeypatch):
    """The retired AKMON_SKIP_CODEX_HOST_TRUST (third C70 review, no contract allows a bypass):
    setting it must change nothing — the host is still asked and its answer still reported."""
    monkeypatch.setenv("AKMON_SKIP_CODEX_HOST_TRUST", "1")
    _write_codex_wiring(tmp_path)
    entries = _generated_entries(tmp_path)
    entries[0] = {**entries[0], "trustStatus": "untrusted"}
    calls = []
    verifier = _live_query_verifier(tmp_path, monkeypatch, _hooks_list_runner(entries, calls))
    verifier.check_codex_host_trust()
    assert len(calls) == 1
    assert _levels(verifier.findings) == {"warn"}


_FAKE_CODEX_BODY = """import json, os, sys
with open(os.environ["FAKE_CODEX_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({"argv": sys.argv[1:]}) + "\\n")
    log.flush()
    for line in sys.stdin:
        message = json.loads(line)
        log.write(json.dumps({"method": message.get("method"), "id": message.get("id")}) + "\\n")
        log.flush()
        if message.get("method") == "initialize":
            reply = {"id": message["id"], "result": {}}
        elif message.get("method") == "hooks/list":
            with open(os.environ["FAKE_CODEX_HOOKS"], encoding="utf-8") as state:
                hooks = json.load(state)
            project = {"cwd": message["params"]["cwds"][0], "hooks": hooks, "warnings": [], "errors": []}
            reply = {"id": message["id"], "result": {"data": [project]}}
        else:
            continue
        sys.stdout.write(json.dumps(reply) + "\\n")
        sys.stdout.flush()
"""


def _tree_snapshot(*roots: Path) -> dict:
    return {path: path.read_bytes() for root in roots for path in root.rglob("*") if path.is_file()}


def _fake_codex_host(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path, Path]:
    """A consumer with generated wiring, an isolated host home, and a stand-in `codex` first on
    PATH that answers hooks/list from a state file it re-reads on every query — so a carrier can
    change the host's trust between runs. Returns ``(root, home, state, log)``; the state starts
    as every generated entry live and trusted."""
    root = tmp_path / "consumer"
    root.mkdir()
    _write_codex_wiring(root)
    home = tmp_path / "home"
    _write(home / ".codex" / "config.toml", '[projects."/somewhere"]\ntrust_level = "trusted"\n')
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake = fake_bin / "codex"
    fake.write_text(f"#!{sys.executable}\n{_FAKE_CODEX_BODY}", encoding="utf-8")
    fake.chmod(0o755)
    state = tmp_path / "hooks-list.json"
    state.write_text(json.dumps(_generated_entries(root)), encoding="utf-8")
    log = tmp_path / "codex.log"
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEX_HOME", str(home / ".codex"))
    monkeypatch.setenv("FAKE_CODEX_LOG", str(log))
    monkeypatch.setenv("FAKE_CODEX_HOOKS", str(state))
    return root, home, state, log


def _codex_log(log: Path) -> list[dict]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_check_codex_host_trust_end_to_end_is_read_only(tmp_path, monkeypatch):
    """The whole route through the default runner and a real subprocess — a stand-in `codex`
    first on PATH: the only requests sent are the handshake and hooks/list, with the pinned
    JSON-RPC ids 1 and 2 (D2-40 (6)) — nothing that grants trust or writes config — and neither
    the consumer tree nor the host's Codex home changes."""
    root, home, _, log = _fake_codex_host(tmp_path, monkeypatch)
    before = _tree_snapshot(root, home)

    verifier = verify.Verifier(root)
    verifier.check_codex_host_trust()

    assert [finding.severity for finding in _host_trust(verifier)] == ["ok"]
    records = _codex_log(log)
    assert records[0] == {"argv": ["app-server"]}
    assert records[1:] == [{"method": "initialize", "id": 1}, {"method": "hooks/list", "id": 2}]
    assert _tree_snapshot(root, home) == before


@pytest.mark.parametrize("reuse", [False, True], ids=["fresh-verifier", "same-verifier"])
def test_check_codex_host_trust_reports_the_host_state_current_at_each_run(tmp_path, monkeypatch, reuse):
    """TASKS.md C70 "current-state freshness" (fourth C70 review: every other carrier answers from
    a fixed runner, so a cached result would pass). The host's trust flips green -> inert -> green
    -> inert between runs; each run must report the state current at that run, through the real
    runner and one fresh `codex` process per run, as a new Verifier or the same one run again —
    so neither a module-level nor a per-instance cached answer survives."""
    root, _, state, log = _fake_codex_host(tmp_path, monkeypatch)
    live = _generated_entries(root)
    inert = [{**live[0], "trustStatus": "untrusted"}, *live[1:]]
    shared = verify.Verifier(root)
    seen = []
    for hooks in (live, inert, live, inert):
        state.write_text(json.dumps(hooks), encoding="utf-8")
        verifier = shared if reuse else verify.Verifier(root)
        already = len(_host_trust(verifier))
        verifier.check_codex_host_trust()
        (finding,) = _host_trust(verifier)[already:]
        seen.append((finding.severity, finding.message))

    green = ("ok", "every generated Codex hook entry is discovered, enabled, and trusted")
    inert_warning = ("warn", "Codex hook delivery is incomplete: untrusted (1)")
    assert seen == [green, inert_warning, green, inert_warning]
    assert [record for record in _codex_log(log) if "argv" in record] == [{"argv": ["app-server"]}] * 4


def test_check_hook_launcher_is_a_package_mode_check_only(tmp_path):
    root = tmp_path
    (root / "_aitna" / "akmon").mkdir(parents=True)
    verifier = verify.Verifier(root)
    verifier.check_hook_launcher()
    assert verifier.findings == []


def test_check_hooks_still_checks_mounted_paths_when_not_package_mode(tmp_path):
    root = tmp_path
    (root / "_aitna" / "akmon" / "hooks").mkdir(parents=True)
    verifier = verify.Verifier(root)
    verifier.check_hooks()
    assert _levels(verifier.findings) == {"error"}  # hook scripts missing -> errors, not skipped


def test_check_changelog_skips_in_package_mode_with_note(tmp_path):
    root = tmp_path
    _write(root / "_aitna" / ".akmon.toml", 'mount = "package"\n')
    verifier = verify.Verifier(root)
    verifier.check_changelog()
    assert len(verifier.findings) == 1
    assert verifier.findings[0].severity == "ok"
    assert verifier.findings[0].message == "package mode: changelog discipline is owned by the akmon repository"
    assert "generated-pointers" not in verifier.findings[0].message


def test_check_ci_package_mode_accepts_cli_invocation(tmp_path):
    root = tmp_path
    _write(root / "_aitna" / ".akmon.toml", 'mount = "package"\n')
    _write(
        root / ".github" / "workflows" / "ci.yml",
        "steps:\n  - run: uv run akmon sync --check\n  - run: uv run akmon verify --strict\n",
    )
    verifier = verify.Verifier(root)
    verifier.check_ci()
    assert _levels(verifier.findings) == {"ok"}


def test_check_ci_package_mode_rejects_mounted_style_command(tmp_path):
    root = tmp_path
    _write(root / "_aitna" / ".akmon.toml", 'mount = "package"\n')
    _write(root / ".github" / "workflows" / "ci.yml", "steps:\n  - run: python3 _aitna/akmon/bin/sync.py --check\n")
    verifier = verify.Verifier(root)
    verifier.check_ci()
    assert _levels(verifier.findings) == {"warn"}


def test_check_agents_md_package_mode_contract(tmp_path):
    root = tmp_path
    _write(root / "_aitna" / ".akmon.toml", 'mount = "package"\n')
    _write(
        root / "AGENTS.md",
        "## Dev layer — akmon\n\n"
        "@_aitna/.akmon/guardrails/_common.md\n\n"
        "Read `akmon path`. Archetype: ARCHETYPES.md. Memory: _aitna/memory.\n"
        "D2 and D5 always-on. Secrets from .env. Delegation is the default.\n",
    )
    verifier = verify.Verifier(root)
    verifier.check_agents_md()
    assert _levels(verifier.findings) == {"ok"}


def test_check_agents_md_requires_direct_delegation_rule(tmp_path):
    root = tmp_path
    _write(root / "_aitna" / ".akmon.toml", 'mount = "package"\n')
    _write(
        root / "AGENTS.md",
        "## Dev layer — akmon\n\n"
        "@_aitna/.akmon/guardrails/_common.md\n\n"
        "Read `akmon path`. Archetype: ARCHETYPES.md. Memory: _aitna/memory.\n"
        "D2 and D5 always-on. Secrets from .env.\n",
    )
    verifier = verify.Verifier(root)
    verifier.check_agents_md()
    assert _levels(verifier.findings) == {"error"}
    assert any("direct delegation-default rule" in message for message in _messages(verifier.findings, "error"))


def test_check_agents_md_package_mode_does_not_accept_mounted_snippets_alone(tmp_path):
    # A mounted-style AGENTS.md (no guardrails @-import, no "akmon path" mention) must still
    # fail the package-mode contract even though it satisfies the mounted one.
    root = tmp_path
    _write(root / "_aitna" / ".akmon.toml", 'mount = "package"\n')
    _write(
        root / "AGENTS.md",
        "## Dev layer — akmon\n\n"
        "Model: `_aitna/akmon/README.md`. Roles: `_aitna/akmon/roles/`.\n"
        "Archetype: ARCHETYPES.md. Memory: _aitna/memory.\n"
        "D2 and D5 always-on. Secrets from .env.\n",
    )
    verifier = verify.Verifier(root)
    verifier.check_agents_md()
    assert _levels(verifier.findings) == {"error"}


def test_mounted_mode_standard_root_matches_akmon_mount(tmp_path):
    # The invariant that keeps mounted-mode verify output byte-identical: re-rooting onto
    # standard_root must resolve to exactly the same directory the old hardcoded path used.
    root = _make_project(tmp_path)
    verifier = verify.Verifier(root)
    assert verifier.standard_root == sync.akmon_root(root)


def test_check_standard_path_message_matches_check_path_wording_in_mounted_mode(tmp_path):
    root = _make_project(tmp_path)
    verifier = verify.Verifier(root)
    verifier.findings.clear()
    verifier.check_standard_path("README.md")
    assert verifier.findings[-1].message == f"{verifier.akmon}/README.md exists"


def test_check_standard_path_falls_back_to_standard_tree_label_in_package_mode(tmp_path):
    root = _make_package_mode_project(tmp_path)
    verifier = verify.Verifier(root)
    verifier.findings.clear()
    verifier.check_standard_path("README.md")
    assert verifier.findings[-1].message.startswith("standard tree:")
    assert verifier.findings[-1].message.endswith("README.md exists")


# --------------------------------------------------------------------------------------
# retired second-opinion keys in the project overlay (N-review of C57). The overlay is
# deep-merged *over* the shipped registry, so `cli`/`invoke` never displace the new
# `harness`/`operation` — they ride along beside them, and every presence check still
# passes. The stale pair therefore has to be caught at the file it is written in.
# --------------------------------------------------------------------------------------


def _overlay_second_opinion_errors(root: Path) -> list[str]:
    verifier = verify.Verifier(root)
    verifier.run()
    return [
        f.target
        for f in verifier.findings
        if f.severity == "error" and f.code == "routing.second-opinion"
    ]


@pytest.mark.parametrize("retired", [{"cli": "claude"}, {"invoke": "claude -p"},
                                     {"cli": "claude", "invoke": "claude -p"}])
def test_a_stale_overlay_second_opinion_is_one_error(tmp_path, retired):
    root = _make_project(tmp_path)
    _write(
        root / "_aitna" / "model-routing.json",
        json.dumps({"anthropic": {"second_opinion": dict(retired)}}),
    )
    assert _overlay_second_opinion_errors(root) == ["_aitna/model-routing.json#anthropic"]


def test_an_overlay_overriding_only_policy_stays_clean(tmp_path):
    root = _make_project(tmp_path)
    _write(
        root / "_aitna" / "model-routing.json",
        json.dumps({"anthropic": {"second_opinion": {"report_dir": ".local/so/"}}}),
    )
    assert _overlay_second_opinion_errors(root) == []
