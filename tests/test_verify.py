"""Unit tests for the keystone layout verifier (``verify``).

A ``_make_project`` helper builds a fully compliant throwaway tree (clean strict run), and
each test mutates one thing to assert the matching finding. Nothing touches the real repo.

Run from the keystone root::

    python3 -m pytest tests
"""

from __future__ import annotations

from pathlib import Path

import sync
import verify

AGENTS_MD = """# AGENTS.md

## Dev layer — keystone

Model: `_forge/keystone/README.md`. Archetype: `ARCHETYPES.md`. Roles:
`_forge/keystone/roles/`. Read `_forge/memory` at session start.

Prime directives D2 and D5 are always-on. Secrets come from `.env`.
Skills live in `_forge/skills/` and root `skills/`; generated vendor skill stubs are pointers only.
"""

CI_YML = """name: CI
on: [push]
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - run: python3 _forge/keystone/bin/sync.py --check
      - run: python3 _forge/keystone/bin/verify.py --strict
      - run: python3 _forge/keystone/bin/self_ci.py
      - run: uv run pytest _forge/keystone/tests
"""

GITIGNORE = "*.env\n!*.env.example\n"

CHANGELOG_MD = "# Changelog\n\n## Unreleased\n\n### Added\n- fixture\n"

SKILL_MD = """---
name: demo
description: Demonstrates the keystone skill contract.
when_to_use: Use for verifier fixture coverage.
owner: keystone
---

# demo
"""


def _write(path: Path, text: str = "x\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_project(tmp_path: Path) -> Path:
    root = tmp_path
    _write(root / "AGENTS.md", AGENTS_MD)
    _write(root / "_forge" / "TASKS.md")

    ks = root / "_forge" / "keystone"
    for rel in (
        "README.md",
        "BOOTSTRAP.md",
        "ARCHETYPES.md",
        "ROADMAP.md",
        "CHANGELOG.md",
        "decisions/README.md",
        "roles/README.md",
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
        "bin/self_ci.py",
        "hooks/hook_core.py",
        "hooks/claude_adapter.py",
        "hooks/codex_adapter.py",
        "hooks/codex-hook.py",
        "hooks/git-commit-guard.py",
        "hooks/session-start-agent.py",
        "hooks/role-on-code.py",
        "hooks/analysis-guard.py",
    ):
        text = CHANGELOG_MD if rel == "CHANGELOG.md" else "x\n"
        _write(ks / rel, text)

    # an agent charter that links a keystone role
    _write(root / "_forge" / "agents" / "engineer" / "README.md", "See `_forge/keystone/roles/engineer.md`.\n")

    # a skill (so check_skills is ok, not warn)
    _write(ks / "skills" / "demo" / "SKILL.md", SKILL_MD)

    # memory index mentioning its one memory file
    _write(root / "_forge" / "memory" / "note.md", "fact\n")
    _write(root / "_forge" / "memory" / "README.md", "# Memory\n- note.md\n")

    _write(root / ".gitignore", GITIGNORE)
    _write(ks / ".gitignore", "__pycache__/\n*.env\n!*.env.example\n")
    _write(root / ".github" / "workflows" / "ci.yml", CI_YML)

    # generated pointers must match sync output
    files, _ = sync._planned_files(root)
    sync._apply(files, write=True)
    return root


def _levels(findings) -> set[str]:
    return {finding.level for finding in findings}


def _messages(findings, level: str) -> list[str]:
    return [finding.message for finding in findings if finding.level == level]


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
    (root / "_forge" / "keystone" / "roles" / "release.md").unlink()
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("roles/release.md is missing" in message for message in _messages(verifier.findings, "error"))


def test_missing_changelog_is_error(tmp_path):
    root = _make_project(tmp_path)
    (root / "_forge" / "keystone" / "CHANGELOG.md").unlink()
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("CHANGELOG.md is missing" in message for message in _messages(verifier.findings, "error"))


def test_agents_md_missing_anchor_is_error(tmp_path):
    root = _make_project(tmp_path)
    (root / "AGENTS.md").write_text("# AGENTS\nno anchors here\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("keystone block is missing" in message for message in _messages(verifier.findings, "error"))



def test_agents_md_generated_marker_is_error(tmp_path):
    root = _make_project(tmp_path)
    (root / "AGENTS.md").write_text(
        AGENTS_MD + f"\n<!-- {sync.GENERATED} -->\n",
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


def test_skills_without_agents_source_root_reference_is_warning(tmp_path):
    root = _make_project(tmp_path)
    agents_without_skills = AGENTS_MD.replace(
        "Skills live in `_forge/skills/` and root `skills/`; generated vendor skill stubs are pointers only.\n",
        "",
    )
    (root / "AGENTS.md").write_text(agents_without_skills, encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("does not mention source skill roots" in message for message in _messages(verifier.findings, "warn"))


def test_skill_missing_frontmatter_is_error(tmp_path):
    root = _make_project(tmp_path)
    (root / "_forge" / "keystone" / "skills" / "demo" / "SKILL.md").write_text("# demo\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("missing required frontmatter" in message for message in _messages(verifier.findings, "error"))


def test_skill_missing_required_frontmatter_field_is_error(tmp_path):
    root = _make_project(tmp_path)
    (root / "_forge" / "keystone" / "skills" / "demo" / "SKILL.md").write_text(
        SKILL_MD.replace("owner: keystone\n", ""),
        encoding="utf-8",
    )
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("frontmatter is missing: owner" in message for message in _messages(verifier.findings, "error"))


def test_skill_frontmatter_name_must_match_directory(tmp_path):
    root = _make_project(tmp_path)
    (root / "_forge" / "keystone" / "skills" / "demo" / "SKILL.md").write_text(
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
    assert any("generated .claude/skills stubs" in message for message in _messages(verifier.findings, "warn"))


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
    stale.write_text(f"# old-skill\n\n<!-- {sync.GENERATED} -->\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("old-skill/SKILL.md" in message for message in _messages(verifier.findings, "error"))


def test_missing_memory_index_is_error(tmp_path):
    root = _make_project(tmp_path)
    (root / "_forge" / "memory" / "README.md").unlink()
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
    memory = root / "_forge" / "memory"
    (memory / "README.md").unlink()
    _write(memory / "MEMORY.md", "# Memory\n- note.md\n")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("README.md is the preferred index" in message for message in _messages(verifier.findings, "warn"))


def test_memory_file_missing_from_index_is_warning(tmp_path):
    root = _make_project(tmp_path)
    _write(root / "_forge" / "memory" / "orphan.md", "unlisted\n")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("not mentioned in index" in message for message in _messages(verifier.findings, "warn"))


def test_gitignore_without_env_pattern_is_warning(tmp_path):
    root = _make_project(tmp_path)
    (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("*.env" in message for message in _messages(verifier.findings, "warn"))


def test_ci_missing_keystone_commands_is_warning(tmp_path):
    root = _make_project(tmp_path)
    (root / ".github" / "workflows" / "ci.yml").write_text("name: CI\non: [push]\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.run()
    assert any("CI should run" in message for message in _messages(verifier.findings, "warn"))


def _tasks(root: Path) -> Path:
    return root / "_forge" / "TASKS.md"


def test_well_formed_index_tasks_is_ok(tmp_path):
    root = _make_project(tmp_path)
    _tasks(root).write_text(
        "# TASKS\n\n- T1 · do a thing · active · engineer · ship the thing\n",
        encoding="utf-8",
    )
    verifier = verify.Verifier(root)
    verifier.run()
    assert "warn" not in _levels(verifier.findings), _messages(verifier.findings, "warn")


def test_missing_keystone_gitignore_is_warning(tmp_path):
    root = _make_project(tmp_path)
    (root / "_forge" / "keystone" / ".gitignore").unlink()
    verifier = verify.Verifier(root)
    verifier.run()
    assert any(
        "_forge/keystone/.gitignore is missing" in message for message in _messages(verifier.findings, "warn")
    )


def test_keystone_gitignore_without_pycache_is_warning(tmp_path):
    root = _make_project(tmp_path)
    (root / "_forge" / "keystone" / ".gitignore").write_text("*.env\n", encoding="utf-8")
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
    assert any("lack a status token" in message for message in _messages(verifier.findings, "warn"))


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
    return root / "_forge" / "keystone" / "CHANGELOG.md"


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
