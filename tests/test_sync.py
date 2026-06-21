"""Unit tests for the keystone pointer/hook-wiring generator (``sync``).

These build throwaway project trees under ``tmp_path``; nothing touches the real repo.

Run from the keystone root::

    python3 -m pytest tests
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import sync

# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def _make_root(tmp_path: Path) -> Path:
    """A minimal tree that _find_project_root accepts."""
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (tmp_path / "_forge" / "keystone").mkdir(parents=True)
    return tmp_path


# --------------------------------------------------------------------------------------
# _find_project_root
# --------------------------------------------------------------------------------------


def test_find_project_root_walks_up_from_nested_cwd(tmp_path):
    root = _make_root(tmp_path)
    nested = root / "src" / "pkg"
    nested.mkdir(parents=True)
    assert sync._find_project_root(nested) == root


def test_find_project_root_falls_back_to_start_when_no_marker(tmp_path):
    assert sync._find_project_root(tmp_path) == tmp_path


# --------------------------------------------------------------------------------------
# _read_json
# --------------------------------------------------------------------------------------


def test_read_json_missing_file_returns_empty(tmp_path):
    assert sync._read_json(tmp_path / "nope.json") == {}


def test_read_json_invalid_raises_value_error(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        sync._read_json(path)


def test_read_json_non_object_raises_value_error(tmp_path):
    path = tmp_path / "arr.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="expected a JSON object"):
        sync._read_json(path)


# --------------------------------------------------------------------------------------
# hook-entry merge (incl. the keystone-managed rewrite fix)
# --------------------------------------------------------------------------------------


def _keystone_entry(path: str, matcher: str = "Bash") -> dict:
    return {"matcher": matcher, "hooks": [{"type": "command", "command": f'python3 "{path}"'}]}


def test_merge_replaces_non_list_existing_with_wanted():
    wanted = [_keystone_entry("_forge/keystone/hooks/git-commit-guard.py")]
    assert sync._merge_hook_entries("garbage", wanted) == wanted


def test_merge_preserves_user_hooks_and_adds_wanted():
    user = {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-hook.sh"}]}
    wanted = [_keystone_entry("_forge/keystone/hooks/git-commit-guard.py")]
    merged = sync._merge_hook_entries([user], wanted)
    assert user in merged
    assert wanted[0] in merged


def test_merge_is_idempotent():
    wanted = [_keystone_entry("_forge/keystone/hooks/git-commit-guard.py")]
    once = sync._merge_hook_entries([], wanted)
    twice = sync._merge_hook_entries(once, wanted)
    assert once == twice


def test_merge_drops_stale_keystone_entry_on_rename():
    # A previous sync wrote the hook at an old path; the wanted set now uses a new path.
    stale = _keystone_entry("_forge/keystone/hooks/old-name.py")
    wanted = [_keystone_entry("_forge/keystone/hooks/git-commit-guard.py")]
    merged = sync._merge_hook_entries([stale], wanted)
    assert stale not in merged  # stale keystone entry removed, not duplicated
    assert merged == wanted


def test_merge_keeps_mixed_entry_that_is_not_purely_keystone():
    # An entry combining a keystone command with a user command is not "keystone-owned".
    mixed = {
        "matcher": "Bash",
        "hooks": [
            {"type": "command", "command": 'python3 "_forge/keystone/hooks/git-commit-guard.py"'},
            {"type": "command", "command": "user-extra.sh"},
        ],
    }
    merged = sync._merge_hook_entries([mixed], [])
    assert mixed in merged


def test_is_keystone_entry_recognises_marker():
    assert sync._is_keystone_entry(_keystone_entry("x/_forge/keystone/hooks/h.py"))
    assert not sync._is_keystone_entry({"matcher": "Bash", "hooks": [{"command": "other.sh"}]})
    assert not sync._is_keystone_entry({"matcher": "Bash", "hooks": []})


# --------------------------------------------------------------------------------------
# _skill_sources
# --------------------------------------------------------------------------------------


def _make_skill(base: Path, root_rel: str, name: str) -> None:
    skill = base / root_rel / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")


def test_skill_sources_finds_skills_across_roots(tmp_path):
    _make_skill(tmp_path, "_forge/keystone/skills", "alpha")
    _make_skill(tmp_path, "skills", "beta")
    sources, errors = sync._skill_sources(tmp_path)
    names = sorted(source.parent.name for source in sources)
    assert names == ["alpha", "beta"]
    assert errors == []


def test_skill_sources_reports_duplicate_names(tmp_path):
    _make_skill(tmp_path, "_forge/keystone/skills", "dup")
    _make_skill(tmp_path, "skills", "dup")
    _, errors = sync._skill_sources(tmp_path)
    assert any("duplicate skill name" in error for error in errors)


# --------------------------------------------------------------------------------------
# _claude_settings / _planned_files / _apply
# --------------------------------------------------------------------------------------


def test_claude_settings_wires_hooks_into_valid_json(tmp_path):
    root = _make_root(tmp_path)
    planned = sync._claude_settings(root)
    settings = json.loads(planned.content)
    assert "PreToolUse" in settings["hooks"]
    assert "SessionStart" in settings["hooks"]
    # commands point at the keystone hook scripts
    text = planned.content
    assert "_forge/keystone/hooks/git-commit-guard.py" in text
    assert "_forge/keystone/hooks/analysis-guard.py" in text


def test_codex_hooks_wires_neutral_hook_entrypoint(tmp_path):
    root = _make_root(tmp_path)
    files, errors = sync._planned_files(root)
    assert errors == []
    planned = next(item for item in files if item.path.relative_to(root).as_posix() == ".codex/hooks.json")
    hooks = json.loads(planned.content)["hooks"]
    assert "PreToolUse" in hooks
    assert "SessionStart" in hooks
    text = planned.content
    assert "_forge/keystone/hooks/codex-hook.py" in text
    assert "analysis-guard" in text
    assert "role-on-code" in text
    assert "session-start" in text


def test_planned_files_include_all_vendor_pointers(tmp_path):
    root = _make_root(tmp_path)
    files, errors = sync._planned_files(root)
    rels = {planned.path.relative_to(root).as_posix() for planned in files}
    assert {
        "CLAUDE.md",
        "GEMINI.md",
        ".github/copilot-instructions.md",
        ".codex/README.md",
        ".codex/hooks.json",
    } <= rels
    assert errors == []
    for planned in files:
        if planned.path.name == "CLAUDE.md":
            assert sync.GENERATED in planned.content  # do-not-edit banner present


def test_apply_check_mode_reports_without_writing(tmp_path):
    root = _make_root(tmp_path)
    files, _ = sync._planned_files(root)
    result = sync._apply(files, write=False)
    assert result.changed  # nothing generated yet → all stale
    assert not (root / "CLAUDE.md").exists()  # check mode did not write


def test_apply_write_then_clean(tmp_path):
    root = _make_root(tmp_path)
    files, _ = sync._planned_files(root)
    sync._apply(files, write=True)
    assert (root / "CLAUDE.md").exists()
    # second pass: everything matches, nothing changed
    files2, _ = sync._planned_files(root)
    assert sync._apply(files2, write=False).changed == []


def test_apply_check_reports_obsolete_generated_skill_stub(tmp_path):
    root = _make_root(tmp_path)
    stale = root / ".claude" / "skills" / "old-skill" / "SKILL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text(f"# old-skill\n\n<!-- {sync.GENERATED} -->\n", encoding="utf-8")

    files, _ = sync._planned_files(root)
    result = sync._apply(files, write=False, root=root)

    assert stale in result.deleted
    assert stale.exists()


def test_apply_write_deletes_obsolete_generated_skill_stub(tmp_path):
    root = _make_root(tmp_path)
    stale = root / ".claude" / "skills" / "old-skill" / "SKILL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text(f"# old-skill\n\n<!-- {sync.GENERATED} -->\n", encoding="utf-8")

    files, _ = sync._planned_files(root)
    result = sync._apply(files, write=True, root=root)

    assert stale in result.deleted
    assert not stale.exists()
    assert not stale.parent.exists()


def test_apply_does_not_delete_user_authored_skill_stub(tmp_path):
    root = _make_root(tmp_path)
    user_file = root / ".claude" / "skills" / "manual" / "SKILL.md"
    user_file.parent.mkdir(parents=True)
    user_file.write_text("# manual\n\nNo generated banner.\n", encoding="utf-8")

    files, _ = sync._planned_files(root)
    result = sync._apply(files, write=True, root=root)

    assert user_file not in result.deleted
    assert user_file.exists()


# --------------------------------------------------------------------------------------
# main()
# --------------------------------------------------------------------------------------


def test_main_check_returns_1_when_stale_then_0_when_synced(tmp_path):
    root = _make_root(tmp_path)
    assert sync.main(["--project-root", str(root), "--check"]) == 1
    assert sync.main(["--project-root", str(root)]) == 0  # write
    assert sync.main(["--project-root", str(root), "--check"]) == 0  # now clean


def test_main_check_returns_1_for_obsolete_generated_skill_stub(tmp_path):
    root = _make_root(tmp_path)
    assert sync.main(["--project-root", str(root)]) == 0
    stale = root / ".claude" / "skills" / "old-skill" / "SKILL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text(f"# old-skill\n\n<!-- {sync.GENERATED} -->\n", encoding="utf-8")

    assert sync.main(["--project-root", str(root), "--check"]) == 1
    assert stale.exists()
    assert sync.main(["--project-root", str(root)]) == 0
    assert not stale.exists()


def test_main_dry_run_does_not_write(tmp_path):
    root = _make_root(tmp_path)
    assert sync.main(["--project-root", str(root), "--dry-run"]) == 0
    assert not (root / "CLAUDE.md").exists()


def test_main_check_and_dry_run_are_mutually_exclusive(tmp_path):
    root = _make_root(tmp_path)
    with pytest.raises(SystemExit):
        sync.main(["--project-root", str(root), "--check", "--dry-run"])
