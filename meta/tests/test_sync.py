"""Unit tests for the akmon pointer/hook-wiring generator (``sync``).

These build throwaway project trees under ``tmp_path``; nothing touches the real repo.

Run from the akmon root::

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
    (tmp_path / "_aitna" / "akmon").mkdir(parents=True)
    return tmp_path


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
# hook-entry merge (incl. the akmon-managed rewrite fix)
# --------------------------------------------------------------------------------------


def _akmon_entry(path: str, matcher: str = "Bash") -> dict:
    return {"matcher": matcher, "hooks": [{"type": "command", "command": f'python3 "{path}"'}]}


def test_merge_replaces_non_list_existing_with_wanted():
    wanted = [_akmon_entry("_aitna/akmon/hooks/git-commit-guard.py")]
    assert sync._merge_hook_entries("garbage", wanted) == wanted


def test_merge_preserves_user_hooks_and_adds_wanted():
    user = {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-hook.sh"}]}
    wanted = [_akmon_entry("_aitna/akmon/hooks/git-commit-guard.py")]
    merged = sync._merge_hook_entries([user], wanted)
    assert user in merged
    assert wanted[0] in merged


def test_merge_is_idempotent():
    wanted = [_akmon_entry("_aitna/akmon/hooks/git-commit-guard.py")]
    once = sync._merge_hook_entries([], wanted)
    twice = sync._merge_hook_entries(once, wanted)
    assert once == twice


def test_merge_drops_stale_akmon_entry_on_rename():
    # A previous sync wrote the hook at an old path; the wanted set now uses a new path.
    stale = _akmon_entry("_aitna/akmon/hooks/old-name.py")
    wanted = [_akmon_entry("_aitna/akmon/hooks/git-commit-guard.py")]
    merged = sync._merge_hook_entries([stale], wanted)
    assert stale not in merged  # stale akmon entry removed, not duplicated
    assert merged == wanted


def test_merge_keeps_mixed_entry_that_is_not_purely_akmon():
    # An entry combining a akmon command with a user command is not "akmon-owned".
    mixed = {
        "matcher": "Bash",
        "hooks": [
            {"type": "command", "command": 'python3 "_aitna/akmon/hooks/git-commit-guard.py"'},
            {"type": "command", "command": "user-extra.sh"},
        ],
    }
    merged = sync._merge_hook_entries([mixed], [])
    assert mixed in merged


def test_is_akmon_entry_recognises_marker():
    assert sync._is_akmon_entry(_akmon_entry("x/_aitna/akmon/hooks/h.py"))
    assert not sync._is_akmon_entry({"matcher": "Bash", "hooks": [{"command": "other.sh"}]})
    assert not sync._is_akmon_entry({"matcher": "Bash", "hooks": []})


# --------------------------------------------------------------------------------------
# _skill_sources
# --------------------------------------------------------------------------------------


def _make_skill(base: Path, root_rel: str, name: str) -> None:
    skill = base / root_rel / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")


def test_skill_sources_finds_skills_across_roots(tmp_path):
    _make_skill(tmp_path, "_aitna/akmon/skills", "alpha")
    _make_skill(tmp_path, "skills", "beta")
    sources, errors = sync._skill_sources(tmp_path)
    names = sorted(source.parent.name for source in sources)
    assert names == ["alpha", "beta"]
    assert errors == []


def test_skill_sources_reports_duplicate_names(tmp_path):
    _make_skill(tmp_path, "_aitna/akmon/skills", "dup")
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
    # commands point at the akmon hook scripts
    text = planned.content
    assert "_aitna/akmon/hooks/git-commit-guard.py" in text
    assert "_aitna/akmon/hooks/analysis-guard.py" in text
    # the delegation nudge is one combined-matcher entry (edit + shell + subagent tools):
    # the merge dedups by command, so the same script must not appear in several groups
    matchers_with_nudge = {
        entry["matcher"]
        for entry in settings["hooks"]["PreToolUse"]
        if any("delegation-nudge.py" in hook["command"] for hook in entry["hooks"])
    }
    assert matchers_with_nudge == {"Bash|Edit|Write|MultiEdit|Task|Agent|Read|Grep|Glob"}
    # the pre-existing groups keep their hooks (regression: entry-level dedup must not
    # swallow them)
    all_matchers = {entry["matcher"] for entry in settings["hooks"]["PreToolUse"]}
    assert {"Bash", "Edit|Write|MultiEdit", "Task|Agent"} <= all_matchers


def test_codex_hooks_wires_neutral_hook_entrypoint(tmp_path):
    root = _make_root(tmp_path)
    files, errors = sync._planned_files(root)
    assert errors == []
    planned = next(item for item in files if item.path.relative_to(root).as_posix() == ".codex/hooks.json")
    hooks = json.loads(planned.content)["hooks"]
    assert "PreToolUse" in hooks
    assert "SessionStart" in hooks
    text = planned.content
    assert "_aitna/akmon/hooks/codex-hook.py" in text
    assert "analysis-guard" in text
    assert "role-on-code" in text
    assert "session-start" in text


def test_codex_pretooluse_matcher_names_routes_not_spellings(tmp_path):
    # C49: measured on codex 0.146.0 — `Edit`, `Write` and `apply_patch` are three aliases
    # for one patch call, and the shell (the route its model took when the patch was denied)
    # matches as `Bash`. The matcher must therefore name two routes, and must not widen to
    # `.*`, which would put an unconditional hook on the hottest tool.
    root = _make_root(tmp_path)
    files, _ = sync._planned_files(root)
    planned = next(item for item in files if item.path.relative_to(root).as_posix() == ".codex/hooks.json")
    matchers = [entry["matcher"] for entry in json.loads(planned.content)["hooks"]["PreToolUse"]]

    assert matchers == ["Bash|apply_patch"]
    for spelling in ("Edit", "Write", "MultiEdit", ".*"):
        assert spelling not in matchers[0]


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
            assert sync.GENERATED_MARKER in planned.content  # do-not-edit banner present


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
    stale.write_text(f"# old-skill\n\n<!-- {sync.GENERATED_MARKER} -->\n", encoding="utf-8")

    files, _ = sync._planned_files(root)
    result = sync._apply(files, write=False, root=root)

    assert stale in result.deleted
    assert stale.exists()


def test_apply_write_deletes_obsolete_generated_skill_stub(tmp_path):
    root = _make_root(tmp_path)
    stale = root / ".claude" / "skills" / "old-skill" / "SKILL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text(f"# old-skill\n\n<!-- {sync.GENERATED_MARKER} -->\n", encoding="utf-8")

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
    stale.write_text(f"# old-skill\n\n<!-- {sync.GENERATED_MARKER} -->\n", encoding="utf-8")

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


# --------------------------------------------------------------------------------------
# configurable dev-layer root (AITNA_ROOT) — A4
# --------------------------------------------------------------------------------------


def _make_root_at(tmp_path: Path, aitna: str) -> Path:
    """A minimal tree whose dev-layer root is ``aitna`` (e.g. ``tools/ai``)."""
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (tmp_path / aitna / "akmon").mkdir(parents=True)
    return tmp_path


def test_aitna_root_name_defaults_to_aitna(monkeypatch):
    monkeypatch.delenv("AITNA_ROOT", raising=False)
    assert sync.aitna_root_name() == "_aitna"


def test_aitna_root_name_reads_env_and_strips_slashes(monkeypatch):
    monkeypatch.setenv("AITNA_ROOT", "/tools/ai/")
    assert sync.aitna_root_name() == "tools/ai"


def test_aitna_root_name_blank_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("AITNA_ROOT", "")
    assert sync.aitna_root_name() == "_aitna"


def test_akmon_root_derives_from_configured_aitna(monkeypatch, tmp_path):
    monkeypatch.setenv("AITNA_ROOT", "tools/ai")
    assert sync.akmon_root(tmp_path) == tmp_path / "tools" / "ai" / "akmon"


def test_generated_hook_commands_use_custom_aitna_root(monkeypatch, tmp_path):
    monkeypatch.setenv("AITNA_ROOT", "tools/ai")
    root = _make_root_at(tmp_path, "tools/ai")
    claude = sync._claude_settings(root).content
    assert "tools/ai/akmon/hooks/git-commit-guard.py" in claude
    assert "_aitna/akmon/hooks" not in claude
    files, errors = sync._planned_files(root)
    assert errors == []
    codex = next(f for f in files if f.path.name == "hooks.json").content
    assert "tools/ai/akmon/hooks/codex-hook.py" in codex
    assert "_aitna/akmon/hooks" not in codex


def test_akmon_hook_marker_tracks_custom_aitna_root(monkeypatch):
    monkeypatch.setenv("AITNA_ROOT", "tools/ai")
    entry = _akmon_entry("x/tools/ai/akmon/hooks/h.py")
    assert sync._is_akmon_entry(entry)
    # an entry at the default path is no longer "akmon-owned" under the custom root
    assert not sync._is_akmon_entry(_akmon_entry("x/_aitna/akmon/hooks/h.py"))


def test_skill_sources_search_custom_aitna_root(monkeypatch, tmp_path):
    monkeypatch.setenv("AITNA_ROOT", "tools/ai")
    _make_skill(tmp_path, "tools/ai/akmon/skills", "alpha")
    _make_skill(tmp_path, "tools/ai/skills", "beta")
    sources, errors = sync._skill_sources(tmp_path)
    assert errors == []
    assert {s.parent.name for s in sources} == {"alpha", "beta"}


def test_full_generation_under_custom_root_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("AITNA_ROOT", "tools/ai")
    root = _make_root_at(tmp_path, "tools/ai")
    assert sync.main(["--project-root", str(root)]) == 0  # write
    assert sync.main(["--project-root", str(root), "--check"]) == 0  # clean second pass
    banner = (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert "tools/ai/akmon/bin/sync.py" in banner  # GENERATED banner tracks the root


# --------------------------------------------------------------------------------------
# read_akmon_toml — the pre-3.11 fallback must agree with tomllib on inline comments
# --------------------------------------------------------------------------------------


def test_strip_inline_comment_drops_a_trailing_comment():
    assert sync._strip_inline_comment('"poetry run pytest"   # optional') == '"poetry run pytest"'
    assert sync._strip_inline_comment("v0.3.0 # the pin") == "v0.3.0"


def test_strip_inline_comment_ends_a_basic_string_at_the_closing_quote():
    """`\\"` inside a basic string is an escaped quote, not the end of the value — stopping at
    the first quote handed back a truncated fragment with the escape still dangling."""
    assert sync._strip_inline_comment(r'"say \"hi\" twice"  # note') == r'"say \"hi\" twice"'
    assert sync._strip_inline_comment(r"'literal \ backslash'  # note") == r"'literal \ backslash'"


def test_strip_inline_comment_keeps_a_hash_inside_the_value():
    """A `#` inside a quoted value is data — cutting there would corrupt the value."""
    assert sync._strip_inline_comment('"run --tag #1"') == '"run --tag #1"'
    assert sync._strip_inline_comment('"unterminated # still data') == '"unterminated # still data'


def test_read_akmon_toml_ignores_inline_comments(tmp_path):
    """The shape BOOTSTRAP §C documents parsed differently on 3.9/3.10 than on 3.11+."""
    record = tmp_path / ".akmon.toml"
    record.write_text(
        'akmon_version = "v0.3.0"   # where this project sits\n'
        'attached_archetype = "package/python"\n'
        "\n"
        "[test]\n"
        'runner = "poetry run pytest"       # optional — pinned at attach\n',
        encoding="utf-8",
    )
    fields = sync.read_akmon_toml(record)
    assert fields["akmon_version"] == "v0.3.0"
    assert fields["test"]["runner"] == "poetry run pytest"


# --------------------------------------------------------------------------------------
# the package-mode manifest pin — one owner for `init` and `verify` (ADR 0009 §4)
# --------------------------------------------------------------------------------------


def test_package_pin_status_answers_none_without_a_manifest(tmp_path):
    assert sync.package_pin_status(tmp_path) == "none"


def test_package_pin_status_reports_the_worst_declaration_not_the_first(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[dependency-groups]\ndev = ["akmon"]\n\n[project]\ndependencies = ["akmon"]\n',
        encoding="utf-8",
    )
    assert sync.package_pin_status(tmp_path) == "runtime"


def test_package_pin_status_ignores_a_source_override(tmp_path):
    """`[tool.uv.sources]` says where a package comes from, never that it is required."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["pandas"]\n\n[tool.uv.sources]\nakmon = { git = "https://x" }\n',
        encoding="utf-8",
    )
    assert sync.package_pin_status(tmp_path) == "none"


def test_package_pin_status_normalizes_distribution_name_case(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[dependency-groups]\ndev = ["AkMoN @ git+https://x"]\n',
        encoding="utf-8",
    )
    assert sync.package_pin_status(tmp_path) == "dev"


def test_package_pin_status_supports_legacy_uv_dev_dependencies(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv]\ndev-dependencies = ["akmon @ git+https://x"]\n',
        encoding="utf-8",
    )
    assert sync.package_pin_status(tmp_path) == "dev"


def test_package_pin_status_ignores_akmon_key_in_an_unrelated_tool_section(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.example]\nakmon = { enabled = true }\n',
        encoding="utf-8",
    )
    assert sync.package_pin_status(tmp_path) == "none"
