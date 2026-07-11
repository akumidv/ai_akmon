"""Unit tests for mount mode ``package`` (ADR 0009 §4, C37 slice B): mount-decoupled tree
resolution, ``.akmon/`` materialization, mount-aware hook-entry recognition, and the
``.akmon.toml`` version stamp — all in ``bin/sync.py``.

These build throwaway project trees under ``tmp_path``; nothing touches the real repo. A
package-mode fixture has no mounted tree at all, so ``sync``'s own "embedded tree" fallback
(``_TREE_ROOT``, this checkout's own akmon root) supplies real hook/guardrail content to
materialize from — the same dev-bench property the CLI's tests rely on.

Run from the akmon root::

    python3 -m pytest tests
"""

from __future__ import annotations

from pathlib import Path

import sync

# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def _make_mounted_root(tmp_path: Path) -> Path:
    """A minimal mounted-mode project (no .akmon.toml): AGENTS.md + an empty mount dir."""
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (tmp_path / "_aitna" / "akmon").mkdir(parents=True)
    return tmp_path


def _make_package_root(tmp_path: Path, *, extra_toml: str = "") -> Path:
    """A minimal package-mode project: AGENTS.md + _aitna/.akmon.toml, no mounted tree."""
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (tmp_path / "_aitna").mkdir(parents=True)
    (tmp_path / "_aitna" / ".akmon.toml").write_text(f'mount = "package"\n{extra_toml}', encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------------------
# _find_project_root — .akmon.toml as an alternate marker
# --------------------------------------------------------------------------------------


def test_find_project_root_accepts_akmon_toml_without_mount(tmp_path):
    root = _make_package_root(tmp_path)
    nested = root / "src" / "pkg"
    nested.mkdir(parents=True)
    assert sync._find_project_root(nested) == root


def test_find_project_root_still_requires_agents_md(tmp_path):
    (tmp_path / "_aitna").mkdir()
    (tmp_path / "_aitna" / ".akmon.toml").write_text('mount = "package"\n', encoding="utf-8")
    assert sync._find_project_root(tmp_path) == tmp_path  # no AGENTS.md -> falls back to start


# --------------------------------------------------------------------------------------
# read_mount_mode / is_package_mode
# --------------------------------------------------------------------------------------


def test_is_package_mode_true_with_recorded_mount(tmp_path):
    root = _make_package_root(tmp_path)
    assert sync.is_package_mode(root) is True
    assert sync.read_mount_mode(root) == "package"


def test_is_package_mode_false_by_default(tmp_path):
    root = _make_mounted_root(tmp_path)
    assert sync.is_package_mode(root) is False
    assert sync.read_mount_mode(root) == "submodule"


def test_is_package_mode_false_when_toml_absent_and_no_mount(tmp_path):
    # backward compatibility: no record at all must not be misread as package mode.
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    assert sync.is_package_mode(tmp_path) is False


# --------------------------------------------------------------------------------------
# standard_tree_root — mount-decoupled resolution
# --------------------------------------------------------------------------------------


def test_standard_tree_root_is_the_mount_when_mounted(tmp_path):
    root = _make_mounted_root(tmp_path)
    assert sync.standard_tree_root(root) == sync.akmon_root(root)


def test_standard_tree_root_is_own_tree_in_package_mode(tmp_path):
    root = _make_package_root(tmp_path)
    assert sync.standard_tree_root(root) == sync._TREE_ROOT


def test_standard_tree_root_ignores_stale_mount_dir_in_package_mode(tmp_path):
    root = _make_package_root(tmp_path)
    (root / "_aitna" / "akmon").mkdir(parents=True)  # stale leftover from a prior mode
    assert sync.standard_tree_root(root) == sync._TREE_ROOT


# --------------------------------------------------------------------------------------
# materialization
# --------------------------------------------------------------------------------------


def test_materialized_files_empty_outside_package_mode(tmp_path):
    root = _make_mounted_root(tmp_path)
    assert sync._materialized_files(root) == []


def test_materialized_files_copies_hooks_and_guardrails_with_banner(tmp_path):
    root = _make_package_root(tmp_path)
    files = sync._materialized_files(root)
    paths = {f.path.relative_to(root).as_posix() for f in files}

    assert "_aitna/.akmon/hooks/hook_core.py" in paths
    assert "_aitna/.akmon/hooks/git-commit-guard.py" in paths
    assert "_aitna/.akmon/guardrails/_common.md" in paths
    assert "_aitna/.akmon/guardrails/python.md" in paths
    # hooks/*.py only — hooks/README.md is not a hook script and must not be materialized.
    assert not any(p.endswith("hooks/README.md") for p in paths)

    # git-commit-guard.py is a directly-invoked hook and carries a shebang; the banner must
    # land right after it so the materialized copy stays directly runnable with no venv.
    commit_guard = next(f for f in files if f.path.name == "git-commit-guard.py")
    assert commit_guard.content.startswith("#!")
    assert sync.GENERATED_MARKER in commit_guard.content.splitlines()[1]

    # hook_core.py is a support module with no shebang; the banner leads the file instead.
    hook_core = next(f for f in files if f.path.name == "hook_core.py")
    assert sync.GENERATED_MARKER in hook_core.content
    assert hook_core.content.splitlines()[0].startswith("#")

    guardrail = next(f for f in files if f.path.name == "_common.md")
    assert sync.GENERATED_MARKER in guardrail.content
    assert guardrail.content.startswith("#")  # heading preserved as the first line


def test_materialized_python_content_no_shebang_gets_leading_banner():
    content = sync._materialized_python_content("import os\n")
    lines = content.splitlines()
    assert lines[0].startswith("#") and sync.GENERATED_MARKER in lines[0]
    assert "import os" in content


def test_materialized_markdown_content_no_heading_gets_leading_banner():
    content = sync._materialized_markdown_content("some prose\n")
    assert content.startswith("<!--")
    assert sync.GENERATED_MARKER in content


def test_sync_check_detects_drift_in_materialized_hook(tmp_path):
    root = _make_package_root(tmp_path)
    files, errors = sync._planned_files(root)
    assert errors == []
    result = sync._apply(files, write=True, root=root)
    assert not result.errors

    hook_path = root / "_aitna" / ".akmon" / "hooks" / "hook_core.py"
    assert hook_path.is_file()
    hand_edited = hook_path.read_text(encoding="utf-8") + "\n# hand edit\n"
    hook_path.write_text(hand_edited, encoding="utf-8")

    files2, errors2 = sync._planned_files(root)
    assert errors2 == []
    check_result = sync._apply(files2, write=False, root=root)
    changed_rel = {p.relative_to(root).as_posix() for p in check_result.changed}
    assert "_aitna/.akmon/hooks/hook_core.py" in changed_rel
    assert hook_path.read_text(encoding="utf-8") == hand_edited  # --check must not rewrite

    # a real (write=True) sync run then clears the drift.
    result2 = sync._apply(files2, write=True, root=root)
    assert hook_path in result2.changed
    assert "hand edit" not in hook_path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------
# mount-aware hook templating + entry recognition
# --------------------------------------------------------------------------------------


def test_hooks_dir_mount_aware(tmp_path):
    mounted_dir = tmp_path / "mounted"
    mounted_dir.mkdir()
    mounted = _make_mounted_root(mounted_dir)
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    package = _make_package_root(package_dir)
    assert sync._hooks_dir(mounted) == "_aitna/akmon/hooks"
    assert sync._hooks_dir(package) == "_aitna/.akmon/hooks"


def test_claude_settings_uses_package_hooks_dir_in_package_mode(tmp_path):
    root = _make_package_root(tmp_path)
    settings = sync._claude_settings(root).content
    assert "_aitna/.akmon/hooks/git-commit-guard.py" in settings
    assert "_aitna/akmon/hooks" not in settings


def test_codex_hooks_uses_package_hooks_dir_in_package_mode(tmp_path):
    root = _make_package_root(tmp_path)
    files, errors = sync._planned_files(root)
    assert errors == []
    codex = next(f for f in files if f.path.name == "hooks.json").content
    assert "_aitna/.akmon/hooks/codex-hook.py" in codex
    assert "_aitna/akmon/hooks" not in codex


def _akmon_entry(path: str) -> dict:
    return {"matcher": "Bash", "hooks": [{"type": "command", "command": f'python3 "{path}"'}]}


def test_is_akmon_entry_recognises_both_mounted_and_package_markers(monkeypatch):
    monkeypatch.delenv("AITNA_ROOT", raising=False)
    assert sync._is_akmon_entry(_akmon_entry("_aitna/akmon/hooks/git-commit-guard.py"))
    assert sync._is_akmon_entry(_akmon_entry("_aitna/.akmon/hooks/git-commit-guard.py"))


def test_merge_drops_mounted_entry_when_switching_to_package_mode(monkeypatch):
    monkeypatch.delenv("AITNA_ROOT", raising=False)
    stale = _akmon_entry("_aitna/akmon/hooks/git-commit-guard.py")
    wanted = [_akmon_entry("_aitna/.akmon/hooks/git-commit-guard.py")]
    merged = sync._merge_hook_entries([stale], wanted)
    assert stale not in merged
    assert merged == wanted


def test_merge_drops_package_entry_when_switching_to_mounted_mode(monkeypatch):
    monkeypatch.delenv("AITNA_ROOT", raising=False)
    stale = _akmon_entry("_aitna/.akmon/hooks/git-commit-guard.py")
    wanted = [_akmon_entry("_aitna/akmon/hooks/git-commit-guard.py")]
    merged = sync._merge_hook_entries([stale], wanted)
    assert stale not in merged
    assert merged == wanted


# --------------------------------------------------------------------------------------
# _upsert_toml_key
# --------------------------------------------------------------------------------------


def test_upsert_toml_key_updates_existing_top_level_key():
    text = 'a = "1"\nb = "2"\n'
    assert sync._upsert_toml_key(text, "a", "9") == 'a = "9"\nb = "2"\n'


def test_upsert_toml_key_inserts_before_first_section():
    text = 'a = "1"\n\n[test]\nrunner = "pytest"\n'
    result = sync._upsert_toml_key(text, "b", "2")
    lines = result.splitlines()
    assert lines.index('b = "2"') < lines.index("[test]")
    assert 'a = "1"' in result
    assert 'runner = "pytest"' in result


def test_upsert_toml_key_appends_when_no_section_present():
    text = 'a = "1"\n'
    assert sync._upsert_toml_key(text, "b", "2") == 'a = "1"\nb = "2"\n'


def test_upsert_toml_key_ignores_commented_lines():
    text = '# a = "old"\na = "1"\n'
    assert sync._upsert_toml_key(text, "a", "9") == '# a = "old"\na = "9"\n'


# --------------------------------------------------------------------------------------
# .akmon.toml version stamping
# --------------------------------------------------------------------------------------


def test_package_mode_akmon_toml_none_outside_package_mode(tmp_path, monkeypatch):
    root = _make_mounted_root(tmp_path)
    monkeypatch.setattr(sync, "_installed_akmon_version", lambda: "0.4.0")
    assert sync._package_mode_akmon_toml(root) is None


def test_package_mode_akmon_toml_none_when_version_unknown(tmp_path, monkeypatch):
    root = _make_package_root(tmp_path)
    monkeypatch.setattr(sync, "_installed_akmon_version", lambda: None)
    assert sync._package_mode_akmon_toml(root) is None


def test_package_mode_akmon_toml_stamps_version_and_preserves_other_fields(tmp_path, monkeypatch):
    root = _make_package_root(
        tmp_path,
        extra_toml='attached_archetype = "package"\nlast_realign = "2026-01-01"\n\n[test]\nrunner = "pytest"\n',
    )
    monkeypatch.setattr(sync, "_installed_akmon_version", lambda: "0.4.0")
    planned = sync._package_mode_akmon_toml(root)
    assert planned is not None
    assert planned.path == root / "_aitna" / ".akmon.toml"
    assert 'akmon_version = "0.4.0"' in planned.content
    assert 'mount = "package"' in planned.content
    assert 'attached_archetype = "package"' in planned.content
    assert 'last_realign = "2026-01-01"' in planned.content
    assert 'runner = "pytest"' in planned.content


def test_planned_files_include_akmon_toml_stamp_in_package_mode(tmp_path, monkeypatch):
    root = _make_package_root(tmp_path)
    monkeypatch.setattr(sync, "_installed_akmon_version", lambda: "0.4.0")
    files, errors = sync._planned_files(root)
    assert errors == []
    toml_plan = next((f for f in files if f.path.name == ".akmon.toml"), None)
    assert toml_plan is not None
    assert 'akmon_version = "0.4.0"' in toml_plan.content
