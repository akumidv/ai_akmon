"""Unit tests for the akmon pointer/hook-wiring generator (``sync``).

These build throwaway project trees under ``tmp_path``; nothing touches the real repo.

Run from the akmon root::

    python3 -m pytest tests
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import sync

# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def _make_root(tmp_path: Path) -> Path:
    """A minimal mounted tree that ``is_project_root`` accepts."""
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


def test_merge_replaces_non_list_existing_with_wanted(tmp_path):
    wanted = [_akmon_entry("_aitna/akmon/hooks/git-commit-guard.py")]
    assert sync._merge_hook_entries("garbage", wanted, tmp_path) == wanted


def test_merge_preserves_user_hooks_and_adds_wanted(tmp_path):
    user = {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-hook.sh"}]}
    wanted = [_akmon_entry("_aitna/akmon/hooks/git-commit-guard.py")]
    merged = sync._merge_hook_entries([user], wanted, tmp_path)
    assert user in merged
    assert wanted[0] in merged


def test_merge_is_idempotent(tmp_path):
    wanted = [_akmon_entry("_aitna/akmon/hooks/git-commit-guard.py")]
    once = sync._merge_hook_entries([], wanted, tmp_path)
    twice = sync._merge_hook_entries(once, wanted, tmp_path)
    assert once == twice


def test_merge_drops_stale_akmon_entry_on_rename(tmp_path):
    # A previous sync wrote the hook at an old path; the wanted set now uses a new path.
    stale = _akmon_entry("_aitna/akmon/hooks/old-name.py")
    wanted = [_akmon_entry("_aitna/akmon/hooks/git-commit-guard.py")]
    merged = sync._merge_hook_entries([stale], wanted, tmp_path)
    assert stale not in merged  # stale akmon entry removed, not duplicated
    assert merged == wanted


def test_merge_keeps_mixed_entry_that_is_not_purely_akmon(tmp_path):
    # An entry combining a akmon command with a user command is not "akmon-owned".
    mixed = {
        "matcher": "Bash",
        "hooks": [
            {"type": "command", "command": 'python3 "_aitna/akmon/hooks/git-commit-guard.py"'},
            {"type": "command", "command": "user-extra.sh"},
        ],
    }
    merged = sync._merge_hook_entries([mixed], [], tmp_path)
    assert mixed in merged


def test_is_akmon_entry_recognises_marker(tmp_path):
    assert sync._is_akmon_entry(_akmon_entry("x/_aitna/akmon/hooks/h.py"), tmp_path)
    assert not sync._is_akmon_entry({"matcher": "Bash", "hooks": [{"command": "other.sh"}]}, tmp_path)
    assert not sync._is_akmon_entry({"matcher": "Bash", "hooks": []}, tmp_path)


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


def test_skill_sources_reads_one_folder_reached_through_two_roots_once(tmp_path):
    # akmon on itself: the mount directory resolves to the project root, so the standard's
    # `skills/` and the project's own `skills/` are one folder.
    _make_skill(tmp_path, "skills", "alpha")
    (tmp_path / "_aitna").mkdir()
    (tmp_path / "_aitna" / "akmon").symlink_to(tmp_path, target_is_directory=True)
    sources, errors = sync._skill_sources(tmp_path)
    assert [source.parent.name for source in sources] == ["alpha"]
    assert errors == []


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
    assert {"Bash|mcp__akmon-browser__.*", "Edit|Write|MultiEdit", "Task|Agent"} <= all_matchers


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
            assert sync.generated_marker() in planned.content  # do-not-edit banner present


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
    stale.write_text(f"# old-skill\n\n<!-- {sync.generated_marker()} -->\n", encoding="utf-8")

    files, _ = sync._planned_files(root)
    result = sync._apply(files, write=False, root=root)

    assert stale in result.deleted
    assert stale.exists()


def test_apply_write_deletes_obsolete_generated_skill_stub(tmp_path):
    root = _make_root(tmp_path)
    stale = root / ".claude" / "skills" / "old-skill" / "SKILL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text(f"# old-skill\n\n<!-- {sync.generated_marker()} -->\n", encoding="utf-8")

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
# skill stubs (C79/D2-41)
# --------------------------------------------------------------------------------------

_ALPHA_FRONTMATTER = (
    "name: alpha\ndescription: Produces an alpha report. Use when asked for alpha.\nmetadata:\n  owner: demo"
)


def _planned_stubs(root: Path) -> dict[str, str]:
    files, errors = sync._planned_files(root)
    assert errors == []
    return {
        planned.path.relative_to(root).as_posix(): planned.content
        for planned in files
        if planned.path.name == "SKILL.md"
    }


def test_skill_stub_carries_the_source_frontmatter_in_both_harness_dirs(tmp_path):
    root = _make_root(tmp_path)
    source = root / "skills" / "alpha" / "SKILL.md"
    source.parent.mkdir(parents=True)
    source.write_text(f"---\n{_ALPHA_FRONTMATTER}\n---\n\n# alpha\n\nBody.\n", encoding="utf-8")

    expected = (
        f"---\n# {sync.generated_banner(root)}\n{_ALPHA_FRONTMATTER}\n---\n\n# alpha\n\n"
        "Source skill: [../../../skills/alpha/SKILL.md](../../../skills/alpha/SKILL.md)\n\n"
        "Read and follow the source SKILL.md. Do not duplicate its contents here.\n"
    )
    assert _planned_stubs(root) == {
        ".claude/skills/alpha/SKILL.md": expected,
        ".agents/skills/alpha/SKILL.md": expected,
    }


def test_skill_stub_without_source_frontmatter_stays_a_bare_pointer(tmp_path):
    root = _make_root(tmp_path)
    _make_skill(root, "skills", "beta")

    stubs = _planned_stubs(root)

    assert set(stubs) == {".claude/skills/beta/SKILL.md", ".agents/skills/beta/SKILL.md"}
    for content in stubs.values():
        assert content.startswith(f"# beta\n\n<!-- {sync.generated_banner(root)} -->\n\nSource skill: ")


def test_skill_stub_outside_the_repository_points_through_akmon_path(tmp_path):
    (tmp_path / "project").mkdir()
    root = _make_root(tmp_path / "project")
    source = tmp_path / "wheel" / "skills" / "alpha" / "SKILL.md"
    source.parent.mkdir(parents=True)
    source.write_text(f"---\n{_ALPHA_FRONTMATTER}\n---\n", encoding="utf-8")

    stubs = sync._skill_stubs(root, source)

    assert [stub.path.relative_to(root).as_posix() for stub in stubs] == [
        ".claude/skills/alpha/SKILL.md",
        ".agents/skills/alpha/SKILL.md",
    ]
    for stub in stubs:
        assert "Source skill: `$(akmon path)/skills/alpha/SKILL.md`" in stub.content
        assert stub.content.startswith(f"---\n# {sync.generated_banner(root)}\n{_ALPHA_FRONTMATTER}\n---\n")


@pytest.mark.parametrize(
    ("text", "block"),
    [
        ("---\nname: a\nmetadata:\n  owner: b\n---\n# a\n", "name: a\nmetadata:\n  owner: b"),
        ("---\n---\n", ""),
        ("---\nname: a\n", None),
        ("# a\n---\nname: a\n---\n", None),
        ("", None),
    ],
)
def test_skill_frontmatter_block(text, block):
    assert sync._skill_frontmatter_block(text) == block


def test_apply_write_deletes_obsolete_generated_agents_skill_stub(tmp_path):
    root = _make_root(tmp_path)
    stale = root / ".agents" / "skills" / "old-skill" / "SKILL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text(f"---\n# {sync.generated_marker()}\nname: old-skill\n---\n", encoding="utf-8")

    files, _ = sync._planned_files(root)
    result = sync._apply(files, write=True, root=root)

    assert result.deleted == [stale]
    assert not stale.parent.exists()
    assert (root / ".agents" / "skills").is_dir()  # pruning stops at the skills directory


# --------------------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("mount", ["submodule", "vendored", "subtree"])
def test_main_refuses_a_mounted_node_record_and_writes_nothing(tmp_path, capsys, mount):
    """The C129 amendment of ADR 0020 D02: a mounted record naming ``ecosystem = "node"`` runs the
    JavaScript implementation from the mount. This one refuses it as it refuses a Node package record
    (exit 2, one line naming the ecosystem), rather than rewrite the Node wiring in its own spelling."""
    root = _make_root(tmp_path)
    (root / "_aitna" / ".akmon.toml").write_text(f'mount = "{mount}"\necosystem = "node"\n', encoding="utf-8")
    before = sorted(path.relative_to(root) for path in root.rglob("*"))
    assert sync.main(["--project-root", str(root)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert 'names ecosystem = "node"' in captured.err
    assert captured.err.count("\n") == 1
    # the CLI it names is the mount's own, not the package's npx (C129 step 8)
    assert captured.err.endswith("for it: node _aitna/akmon/js/akmon/cli.mjs sync\n")
    assert sorted(path.relative_to(root) for path in root.rglob("*")) == before


def test_main_names_npx_for_a_node_package_record(tmp_path, capsys):
    root = _make_root(tmp_path)
    (root / "_aitna" / ".akmon.toml").write_text('mount = "package"\necosystem = "node"\n', encoding="utf-8")
    assert sync.main(["--project-root", str(root)]) == 2
    assert capsys.readouterr().err.endswith("for it: npx akmon sync\n")


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
    stale.write_text(f"# old-skill\n\n<!-- {sync.generated_marker()} -->\n", encoding="utf-8")

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
# configurable dev-layer root (the `.aitna-root` declaration) — A4
# --------------------------------------------------------------------------------------


def _make_root_at(tmp_path: Path, aitna: str) -> Path:
    """A minimal tree whose dev-layer root is ``aitna`` (e.g. ``tools/ai``), declared in ``.aitna-root``."""
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (tmp_path / ".aitna-root").write_text(f"{aitna}\n", encoding="utf-8")
    (tmp_path / aitna / "akmon").mkdir(parents=True)
    return tmp_path


def test_aitna_root_name_defaults_to_aitna_without_a_declaration(tmp_path):
    root = _make_root(tmp_path)
    assert not (root / ".aitna-root").exists()
    assert sync.aitna_root_name(root) == "_aitna"


def test_aitna_root_name_reads_the_declaration_and_strips_trailing_slashes(tmp_path):
    (tmp_path / ".aitna-root").write_text("tools/ai/\n", encoding="utf-8")
    assert sync.aitna_root_name(tmp_path) == "tools/ai"


def test_aitna_root_name_refuses_an_absolute_declaration(tmp_path):
    """A leading slash is an absolute path, refused rather than stripped into a relative one."""
    (tmp_path / ".aitna-root").write_text("/tools/ai/\n", encoding="utf-8")
    with pytest.raises(ValueError, match="relative to the project root"):
        sync.aitna_root_name(tmp_path)


def test_aitna_root_name_refuses_a_blank_declaration(tmp_path):
    (tmp_path / ".aitna-root").write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot be empty"):
        sync.aitna_root_name(tmp_path)


def test_akmon_root_derives_from_the_declared_dev_root(tmp_path):
    (tmp_path / ".aitna-root").write_text("tools/ai\n", encoding="utf-8")
    assert sync.akmon_root(tmp_path) == tmp_path / "tools" / "ai" / "akmon"


def test_generated_hook_commands_use_custom_aitna_root(tmp_path):
    root = _make_root_at(tmp_path, "tools/ai")
    claude = sync._claude_settings(root).content
    assert "tools/ai/akmon/hooks/git-commit-guard.py" in claude
    assert "_aitna/akmon/hooks" not in claude
    files, errors = sync._planned_files(root)
    assert errors == []
    codex = next(f for f in files if f.path.name == "hooks.json").content
    assert "tools/ai/akmon/hooks/codex-hook.py" in codex
    assert "_aitna/akmon/hooks" not in codex


def test_akmon_hook_marker_tracks_custom_aitna_root(tmp_path):
    root = _make_root_at(tmp_path, "tools/ai")
    entry = _akmon_entry("x/tools/ai/akmon/hooks/h.py")
    assert sync._is_akmon_entry(entry, root)
    # an entry at the default path is no longer "akmon-owned" under the custom root
    assert not sync._is_akmon_entry(_akmon_entry("x/_aitna/akmon/hooks/h.py"), root)


def test_skill_sources_search_custom_aitna_root(tmp_path):
    (tmp_path / ".aitna-root").write_text("tools/ai\n", encoding="utf-8")
    _make_skill(tmp_path, "tools/ai/akmon/skills", "alpha")
    _make_skill(tmp_path, "tools/ai/skills", "beta")
    sources, errors = sync._skill_sources(tmp_path)
    assert errors == []
    assert {s.parent.name for s in sources} == {"alpha", "beta"}


def test_full_generation_under_custom_root_is_idempotent(tmp_path):
    root = _make_root_at(tmp_path, "tools/ai")
    assert sync.main(["--project-root", str(root)]) == 0  # write
    assert sync.main(["--project-root", str(root), "--check"]) == 0  # clean second pass
    banner = (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert "tools/ai/akmon/bin/sync.py" in banner  # GENERATED banner tracks the root


# --------------------------------------------------------------------------------------
# read_akmon_toml — the defensive fallback must agree with tomllib on inline comments
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
        "[tool.example]\nakmon = { enabled = true }\n",
        encoding="utf-8",
    )
    assert sync.package_pin_status(tmp_path) == "none"


@pytest.mark.parametrize(
    ("manifest", "expected"),
    [
        ('[dependency-groups]\ndev = [\n    "setuptools>=75",\n    "akmon==0.4.0",\n]\n', "dev"),
        ('[project]\ndependencies = [\n    "pandas",\n    "akmon==0.4.0",\n]\n', "runtime"),
        ('[dependency-groups]\ndev = [\n    "akmon[all]==0.4.0",\n]\n', "dev"),
        ('[dependency-groups]\ndev = [\n    "akmon @ https://x/p.zip#sha256=ab",  # pin\n]\n', "dev"),
        ("[project]\ndependencies = [\n    \"akmon>=0.4; python_version >= '3.11'\",\n]\n", "runtime"),
        ('[project.optional-dependencies]\nagent = [\n    "akmon==0.4.0",\n]\n', "runtime"),
        ("[project]\ndependencies = [\n    'akmon==0.4.0',\n]\n", "runtime"),
        ('[tool.pdm.dev-dependencies]\nagent = [\n    "akmon==0.4.0",\n]\n', "dev"),
    ],
    ids=["dev-group", "runtime", "extras", "url-hash", "marker", "extra", "single-quoted", "pdm-dev"],
)
def test_package_pin_status_reads_a_versioned_element_of_a_multiline_array(tmp_path, manifest, expected):
    """One requirement per line is what `uv add --dev` and formatters write, and `akmon==X.Y.Z` is the
    pin the packaging design names once akmon is on PyPI. Every one of these read as no pin at all."""
    (tmp_path / "pyproject.toml").write_text(manifest, encoding="utf-8")
    assert sync.package_pin_status(tmp_path) == expected


@pytest.mark.parametrize(
    ("manifest", "expected"),
    [
        ('[tool.poetry.group.dev]\ndependencies = { akmon = "^0.4" }\n', "dev"),
        ('[tool.poetry.group.dev]\ndependencies.akmon = "^0.4"\n', "dev"),
        ('[tool.poetry]\ndependencies = { akmon = "^0.4" }\n', "runtime"),
        ('[tool.poetry.dev-dependencies]\nakmon = "^0.4"\n', "dev"),
        ('[dependency-groups]\ndev = [{include-group = "lint"}, "akmon==0.4.0"]\nlint = ["ruff"]\n', "dev"),
    ],
    ids=[
        "poetry-inline-table",
        "poetry-dotted-key",
        "poetry-runtime-inline-table",
        "poetry-legacy-dev",
        "include-group",
    ],
)
def test_package_pin_status_reads_the_declaration_not_its_spelling(tmp_path, manifest, expected):
    """The same declaration has several valid TOML spellings; each one names the same pin."""
    (tmp_path / "pyproject.toml").write_text(manifest, encoding="utf-8")
    assert sync.package_pin_status(tmp_path) == expected


@pytest.mark.parametrize(
    "manifest",
    [
        '[dependency-groups]\ndev = [\n    "pytest",  # akmon later\n]\n',
        '[dependency-groups]\ndev = [\n    "akmon-plugin==1.0",\n]\n',
        '[project]\ndescription = "akmon==0.4.0 is a dev tool"\n',
    ],
    ids=["comment", "prefix-named-distribution", "prose"],
)
def test_package_pin_status_ignores_what_is_not_a_requirement_naming_akmon(tmp_path, manifest):
    (tmp_path / "pyproject.toml").write_text(manifest, encoding="utf-8")
    assert sync.package_pin_status(tmp_path) == "none"


def test_package_pin_status_reports_a_manifest_that_is_not_valid_toml(tmp_path):
    """uv cannot read such a file either, so "no pin" would name the wrong cause."""
    (tmp_path / "pyproject.toml").write_text('[dependency-groups]\ndev = [\n    "akmon==0.4.0",\n', encoding="utf-8")
    assert sync.package_pin_status(tmp_path) == "unreadable"


# --------------------------------------------------------------------------------------
# self-hosting: akmon's own tree is the project root (C207)
# --------------------------------------------------------------------------------------


def _self_hosted_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tree with no mount that the running script treats as its own."""
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    monkeypatch.setattr(sync, "_TREE_ROOT", tmp_path.resolve())
    return tmp_path


def test_is_self_hosted_for_the_running_tree_without_a_mount(tmp_path, monkeypatch):
    assert sync.is_self_hosted(_self_hosted_root(tmp_path, monkeypatch))


def test_is_self_hosted_is_false_for_a_consumer(tmp_path):
    assert not sync.is_self_hosted(_make_root(tmp_path))


def test_is_self_hosted_is_false_when_a_mount_exists(tmp_path, monkeypatch):
    root = _self_hosted_root(tmp_path, monkeypatch)
    (root / "_aitna" / "akmon").mkdir(parents=True)
    assert not sync.is_self_hosted(root)


def test_is_self_hosted_is_false_in_package_mode(tmp_path, monkeypatch):
    root = _self_hosted_root(tmp_path, monkeypatch)
    (root / "_aitna").mkdir()
    (root / "_aitna" / ".akmon.toml").write_text('mount = "package"\n', encoding="utf-8")
    assert not sync.is_self_hosted(root)


def test_self_hosted_wiring_names_the_in_tree_hooks(tmp_path, monkeypatch):
    root = _self_hosted_root(tmp_path, monkeypatch)
    blob = json.dumps(sync._claude_hooks(root)) + json.dumps(sync._codex_hooks(root))
    assert "$CLAUDE_PROJECT_DIR/hooks/git-commit-guard.py" in blob
    assert "$(git rev-parse --show-toplevel)/hooks/codex-hook.py" in blob
    assert "/akmon/hooks/" not in blob


def test_self_hosted_sync_replaces_its_in_tree_entries_instead_of_duplicating_them(tmp_path, monkeypatch):
    root = _self_hosted_root(tmp_path, monkeypatch)
    data = sync.read_sync_data()
    settings = root / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps(sync._claude_hooks(root, data)), encoding="utf-8")
    planned = {file.path: file.content for file in sync._planned_files(root, data)[0]}
    assert json.loads(planned[settings]) == sync._claude_hooks(root, data)


def test_a_consumer_keeps_an_in_tree_looking_entry_as_its_own(tmp_path):
    root = _make_root(tmp_path)
    data = sync.read_sync_data()
    own = _akmon_entry("$CLAUDE_PROJECT_DIR/hooks/mine.py")
    merged = sync._merge_hook_entries([own], sync._claude_hooks(root, data)["hooks"]["PreToolUse"], root, data)
    assert own in merged


def test_a_mounted_consumers_python_wiring_is_spelled_from_the_shared_template(tmp_path):
    root = _make_root(tmp_path)
    claude = sync._claude_hooks(root)["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    codex = sync._codex_hooks(root)["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert claude == 'python3 "$CLAUDE_PROJECT_DIR/_aitna/akmon/hooks/git-commit-guard.py"'
    assert codex.startswith('python3 "$(git rev-parse --show-toplevel)/_aitna/akmon/hooks/codex-hook.py" ')


def test_no_python_hook_command_is_spelled_inline_in_the_sync_script():
    """C207: the template lives in ``sync.json`` only; the JavaScript sync reads the same one."""
    source = Path(sync.__file__).read_text(encoding="utf-8")
    assert 'python3 "' not in source


def test_import_base_is_empty_when_self_hosted_and_the_mount_otherwise(tmp_path, monkeypatch):
    (tmp_path / "consumer").mkdir()
    (tmp_path / "own").mkdir()
    consumer = _make_root(tmp_path / "consumer")
    assert sync.import_base(consumer) == "_aitna/akmon"
    assert sync.import_prefix(consumer) == "@_aitna/akmon/"
    root = _self_hosted_root(tmp_path / "own", monkeypatch)
    assert sync.import_base(root) == ""
    assert sync.import_prefix(root) == "@"


def test_self_hosted_sync_writes_the_in_tree_imports_region(tmp_path, monkeypatch):
    root = _self_hosted_root(tmp_path, monkeypatch)
    data = sync.read_sync_data()
    markers = data["imports_region"]
    stale = f"# AGENTS\n\n{_HEADING}\n\n{markers['open']}\n@_aitna/akmon/guardrails/_common.md\n{markers['close']}\n"
    region = sync.imports_region("", data)
    assert region[1] == "@guardrails/_common.md"
    wanted = sync.sync_imports_region(stale, root, data)
    assert [line for line in wanted.splitlines() if line.startswith("@")] == region[1:-1]
    assert sync.sync_imports_region(wanted, root, data) == wanted


# --------------------------------------------------------------------------------------
# bin/sync.json — the shared sync text and tables (C102)
# --------------------------------------------------------------------------------------

_SYNC_DATA = json.loads((Path(sync.__file__).parent / "sync.json").read_text(encoding="utf-8"))


def test_sync_data_pins_its_structure():
    """The data file is the single owner of the sync text: pin the key set and a few
    characteristic exact values so a transcription drift is caught here, not in the corpus."""
    assert set(_SYNC_DATA) == {
        "cli_name",
        "default_launcher_rel",
        "akmon_hook_markers",
        # the in-tree spellings recognised when akmon runs sync on itself (C207)
        "akmon_in_tree_hook_markers",
        # the Python hook command templates both implementations spell the wiring from: a consumer's
        # Python wiring, and akmon's own self-hosted wiring (C207)
        "python_hook_command",
        "python_codex_hook_command",
        # the JavaScript sync's own keys (C105): the Node wiring spelling and the refusal of a record
        # that is not Node package mode; this file never reads them
        "node_hook_command",
        "node_codex_hook_command",
        "unsupported_record",
        "unsupported_found",
        # the Python sync's refusal of a record the JavaScript implementation wrote (C105), and the
        # CLI it names per mode (C129); verify names it too
        "python_refuses_ecosystem",
        "node_cli",
        "claude_hooks",
        "codex_hooks",
        "vendor_pointers",
        "planned_files",
        "skill_stubs",
        "skill_stub_dirs",
        "always_imported",
        "imports_region",
        "moved_imports",
        # the language → profile map init writes a fresh block from and verify checks against (C127)
        "language_profiles",
        "ruff_configs",
        # the ruff.toml init writes and verify's check.ruff-without-python recognizes, and the
        # manifests that make a project a Python one (C129)
        "ruff_toml_template",
        "python_markers",
        "check_findings",
        "summary_verbs",
    }
    assert _SYNC_DATA["cli_name"] == "akmon"
    assert _SYNC_DATA["default_launcher_rel"] == ".venv/bin/akmon"
    # the third marker's quote sits before `hook` (the launcher is quoted in the wiring); the
    # trailing space is what keeps it from matching a prose mention
    # the fourth is the Node package spelling (ADR 0020 D05, C104): the JS sync writes it, the
    # Python sync only has to recognise it so a mode switch replaces it instead of orphaning it;
    # the fifth is the Node mount's (the C129 amendment of ADR 0020 D02), recognised the same way
    assert _SYNC_DATA["akmon_hook_markers"] == [
        "{{aitna}}/akmon/hooks/",
        "{{aitna}}/.akmon/hooks/",
        '{{cli}}" hook ',
        "/node_modules/akmon/js/hooks/",
        "{{aitna}}/akmon/js/hooks/",
    ]
    assert _SYNC_DATA["akmon_in_tree_hook_markers"] == [
        "$CLAUDE_PROJECT_DIR/hooks/",
        "$(git rev-parse --show-toplevel)/hooks/",
        "$CLAUDE_PROJECT_DIR/js/hooks/",
        "$(git rev-parse --show-toplevel)/js/hooks/",
    ]
    assert _SYNC_DATA["python_hook_command"] == 'python3 "{{anchor}}/{{hooks_dir}}/{{script}}.py"'
    assert _SYNC_DATA["python_codex_hook_command"] == 'python3 "{{anchor}}/{{hooks_dir}}/codex-hook.py"'
    # one template per harness, the hooks directory a placeholder: node_modules/akmon/js/hooks in
    # package mode, <dev root>/akmon/js/hooks in a mounted one (js/bin/sync.mjs::nodeHooksDir)
    assert _SYNC_DATA["node_hook_command"] == 'node "{{anchor}}/{{hooks_dir}}/{{script}}.mjs"'
    assert _SYNC_DATA["node_codex_hook_command"] == 'node "{{anchor}}/{{hooks_dir}}/codex-hook.mjs"'
    # the wiring tables: matcher entries and hook commands, order load-bearing
    assert list(_SYNC_DATA["claude_hooks"]) == ["PreToolUse", "SessionStart", "UserPromptSubmit", "Stop"]
    assert len(_SYNC_DATA["claude_hooks"]["PreToolUse"]) == 4
    assert _SYNC_DATA["claude_hooks"]["PreToolUse"][0] == {
        "matcher": "Bash|mcp__akmon-browser__.*",
        "commands": ["git-commit-guard"],
    }
    assert _SYNC_DATA["claude_hooks"]["Stop"][0]["commands"] == ["gate-audit"]
    # the owner's `/style` switch is captured per turn beside the orchestrator detection (ADR 0031/D03)
    assert _SYNC_DATA["claude_hooks"]["UserPromptSubmit"] == [
        {"matcher": None, "commands": ["model-routing", "work-style"]}
    ]
    assert _SYNC_DATA["codex_hooks"]["PreToolUse"][0]["matcher"] == "Bash|apply_patch"
    assert _SYNC_DATA["codex_hooks"]["SessionStart"][0]["commands"] == [
        ["session-start", "Loading akmon session reminders"],
        ["learning-reminder", "Checking the learning-run reminder"],
    ]
    # a per-turn event takes no matcher (M65): the Codex writer leaves a null one out
    assert _SYNC_DATA["codex_hooks"]["UserPromptSubmit"] == [
        {"matcher": None, "commands": [["work-style", "Checking for a work-style switch"]]}
    ]
    assert list(_SYNC_DATA["planned_files"]) == [
        ["CLAUDE.md", "claude_md"],
        [".github/copilot-instructions.md", "copilot_md"],
        ["GEMINI.md", "gemini_md"],
        [".codex/README.md", "codex_readme"],
        [".codex/hooks.json", "codex_hooks_text"],
    ]
    assert _SYNC_DATA["skill_stubs"]["no_frontmatter"] == "# {{name}}\n\n<!-- {{banner}} -->\n\n{{body}}"
    assert _SYNC_DATA["skill_stubs"]["with_frontmatter"] == (
        "---\n# {{banner}}\n{{frontmatter}}\n---\n\n# {{name}}\n\n{{body}}"
    )
    assert _SYNC_DATA["skill_stub_dirs"] == [".claude/skills", ".agents/skills"]
    assert _SYNC_DATA["always_imported"] == ["guardrails/_common.md", "rules/collaboration.md", "rules/templates.md"]
    assert _SYNC_DATA["imports_region"] == {"open": "<!-- akmon:imports -->", "close": "<!-- /akmon:imports -->"}
    assert _SYNC_DATA["moved_imports"] == {"guardrails/python.md": "profiles/python.md"}
    assert _SYNC_DATA["ruff_configs"][0] == ["pyproject.toml", ["tool", "ruff"]]
    assert _SYNC_DATA["check_findings"]["stale"]["message"] == "generated file is stale or missing: {{relative}}"
    assert _SYNC_DATA["summary_verbs"]["no_changes"] == "akmon sync: no changes"
    assert _SYNC_DATA["summary_verbs"]["changed"] == {"dry_run": "would update", "write": "updated"}


def test_sync_data_loader_reads_exactly_the_sync_json(monkeypatch):
    """The loader reads ``sync.json`` beside ``sync.py`` — the path the wheel, the self-CI
    fixture and the corpus snapshot all place the file at."""
    seen: list[Path] = []
    real_read = sync.jsondata.read

    def spy(path):
        seen.append(path)
        return real_read(path)

    monkeypatch.setattr(sync.jsondata, "read", spy)
    data = sync.read_sync_data()
    assert sync._cli_name(data) == "akmon"
    assert sync._skill_stub_dirs(data) == (".claude/skills", ".agents/skills")
    assert seen == [Path(sync.__file__).parent / "sync.json"]


def test_one_sync_run_reads_sync_json_once(tmp_path, monkeypatch, capsys):
    """``main`` reads ``sync.json`` once and passes it down (C102): the plan, every skill stub,
    the hook merge and the check report all use that one read."""
    root = _make_root(tmp_path)
    _make_skill(root, "skills", "alpha")
    _make_skill(root, "skills", "beta")
    seen: list[str] = []
    real_read = sync.jsondata.read

    def spy(path):
        seen.append(Path(path).name)
        return real_read(path)

    monkeypatch.setattr(sync.jsondata, "read", spy)
    assert sync.main(["--project-root", str(root)]) == 0
    assert sync.main(["--project-root", str(root), "--check"]) == 0
    capsys.readouterr()
    assert seen.count("sync.json") == 2  # once per run


def test_sync_data_file_error_propagates_uncaught(monkeypatch, tmp_path):
    """A missing or broken ``sync.json`` is a loud failure, not a swallowed one — from the
    entry point and from a public function called on its own."""

    def broken_read(path):
        raise sync.jsondata.DataFileError(f"akmon data file missing: {path}")

    monkeypatch.setattr(sync.jsondata, "read", broken_read)
    root = _make_root(tmp_path)
    with pytest.raises(sync.jsondata.DataFileError, match=r"sync\.json"):
        sync.main(["--project-root", str(root)])
    with pytest.raises(sync.jsondata.DataFileError, match=r"sync\.json"):
        sync._planned_files(root)
    with pytest.raises(sync.jsondata.DataFileError, match=r"sync\.json"):
        sync._codex_hooks(root)


# --------------------------------------------------------------------------------------
# language profiles (C127): the mapping init writes from and verify checks against
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("languages", "expected"),
    [
        (["python"], ["python.md"]),
        (["package/python"], ["python.md"]),
        (["JavaScript"], ["js.md"]),
        (["service/typescript"], ["js.md"]),
        (["python", "javascript"], ["python.md", "js.md"]),
        (["unclassified"], []),
        (["<archetype>/<language>"], []),
        (["rust"], []),
        ([], []),
    ],
)
def test_language_profiles_map_the_named_languages(tmp_path, languages, expected):
    assert [found.profile for found in sync.language_profiles(tmp_path, languages)] == expected


def test_language_profiles_read_the_manifests_python_first(tmp_path):
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert sync.language_profiles(tmp_path, []) == [
        sync.LanguageProfile("python.md", "pyproject.toml"),
        sync.LanguageProfile("js.md", "package.json"),
    ]


def test_language_profiles_name_the_manifest_over_the_language(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert sync.language_profiles(tmp_path, ["package/python", "javascript"]) == [
        sync.LanguageProfile("python.md", "pyproject.toml"),
        sync.LanguageProfile("js.md", "javascript"),
    ]


def test_profile_imports_skip_code_spans_and_fenced_blocks():
    text = (
        "Import one per line (`@_aitna/.akmon/profiles/<name>.md`, `@_aitna/.akmon/profiles/js.md`).\n\n"
        "```\n@_aitna/.akmon/profiles/quant.md\n```\n\n"
        "@_aitna/.akmon/guardrails/_common.md\n@_aitna/.akmon/profiles/python.md\n"
        "  @_aitna/akmon/profiles/js.md\n@profiles/python-stdlib.md\nmail@profiles/x.md\n"
    )
    assert [(found.prefix, found.name, found.line) for found in sync.profile_imports(text)] == [
        ("_aitna/.akmon/", "python.md", "@_aitna/.akmon/profiles/python.md"),
        ("_aitna/akmon/", "js.md", "@_aitna/akmon/profiles/js.md"),
        ("", "python-stdlib.md", "@profiles/python-stdlib.md"),
    ]


# --------------------------------------------------------------------------------------
# has_python — what counts as Python (C129; the JavaScript twin is hasPython)
# --------------------------------------------------------------------------------------


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True)


def _put(root: Path, relative: str, text: str = "") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    "marker",
    [
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
        "requirements-dev.txt",
        "Pipfile",
        "uv.lock",
        "poetry.lock",
    ],
)
def test_has_python_reads_a_marker_file_at_the_root(tmp_path: Path, marker: str) -> None:
    _put(tmp_path, "package.json", "{}")
    assert not sync.has_python(tmp_path, _SYNC_DATA, "_aitna")
    _put(tmp_path, marker)
    assert sync.has_python(tmp_path, _SYNC_DATA, "_aitna")


def test_has_python_reads_markers_at_the_root_only(tmp_path: Path) -> None:
    _put(tmp_path, "package.json", "{}")
    _put(tmp_path, "docs/requirements.txt")
    assert not sync.has_python(tmp_path, _SYNC_DATA, "_aitna")


def test_has_python_counts_tracked_sources_outside_the_dev_layer_and_node_modules(tmp_path: Path) -> None:
    for relative in ("package.json", "app/x.py", "_aitna/akmon/bin/sync.py", "node_modules/pkg/y.py"):
        _put(tmp_path, relative)
    _git(tmp_path, "init", "-q")
    assert not sync.has_python(tmp_path, _SYNC_DATA, "_aitna"), "untracked app/x.py"
    _git(tmp_path, "add", "-f", "_aitna", "node_modules")
    assert not sync.has_python(tmp_path, _SYNC_DATA, "_aitna"), "tracked, but the dev layer and node_modules"
    assert sync.has_python(tmp_path, _SYNC_DATA, "tools/ai"), "another dev layer leaves _aitna as project code"
    _git(tmp_path, "add", "app/x.py")
    assert sync.has_python(tmp_path, _SYNC_DATA, "_aitna")


def test_has_python_walks_outside_a_work_tree_skipping_dev_layer_node_modules_dot_dirs(tmp_path: Path) -> None:
    _put(tmp_path, "package.json", "{}")
    for skipped in ("tools/ai/akmon/x.py", "node_modules/p/x.py", ".venv/x.py"):
        _put(tmp_path, skipped)
    assert not sync.has_python(tmp_path, _SYNC_DATA, "tools/ai")
    _put(tmp_path, "src/deep/app.py")
    assert sync.has_python(tmp_path, _SYNC_DATA, "tools/ai")
    bounded = {**_SYNC_DATA, "python_markers": {**_SYNC_DATA["python_markers"], "walk_limit": 3}}
    assert not sync.has_python(tmp_path, bounded, "tools/ai"), "the walk stopped first"


# --------------------------------------------------------------------------------------
# the akmon block's managed imports region (ADR 0018/D02 amendment)
# --------------------------------------------------------------------------------------

_REGION_OPEN = "<!-- akmon:imports -->"
_REGION_CLOSE = "<!-- /akmon:imports -->"
_HEADING = "## Dev layer — akmon"


def _region(base: str = "_aitna/akmon") -> str:
    """The expected region text for ``base``, one trailing newline."""
    lines = [_REGION_OPEN, *(f"@{base}/{name}" for name in _SYNC_DATA["always_imported"]), _REGION_CLOSE]
    return "\n".join(lines) + "\n"


def _agents_root(tmp_path: Path, agents_md: str) -> Path:
    """A mounted project whose mount ships the standard's rule files and profiles, so no import dangles."""
    root = _make_root(tmp_path)
    (root / "AGENTS.md").write_text(agents_md, encoding="utf-8")
    for name in [*_SYNC_DATA["always_imported"], "profiles/python.md", "profiles/js.md"]:
        _put(root, f"_aitna/akmon/{name}", "# Rule\n")
    return root


def test_imports_region_is_the_markers_around_one_import_per_always_imported_file():
    assert sync.imports_region("_aitna/akmon") == [
        _REGION_OPEN,
        "@_aitna/akmon/guardrails/_common.md",
        "@_aitna/akmon/rules/collaboration.md",
        "@_aitna/akmon/rules/templates.md",
        _REGION_CLOSE,
    ]
    assert sync.imports_region("tools/ai/.akmon")[1] == "@tools/ai/.akmon/guardrails/_common.md"


def test_import_base_follows_the_mode_and_the_dev_root(tmp_path):
    root = _make_root(tmp_path)
    assert sync.import_base(root) == "_aitna/akmon"
    assert sync.import_prefix(root) == "@_aitna/akmon/"
    (root / "_aitna" / ".akmon.toml").write_text('mount = "package"\n', encoding="utf-8")
    assert sync.import_base(root) == "_aitna/.akmon"


def test_sync_rewrites_the_body_of_an_existing_region(tmp_path):
    text = (
        f"# AGENTS.md\n\n{_HEADING}\n\nHand-owned prose.\n\n{_REGION_OPEN}\n@_aitna/akmon/guardrails/_common.md\n"
        f"@somewhere/else.md\n{_REGION_CLOSE}\n@_aitna/akmon/profiles/python.md\n\n## Peer\n\nKept.\n"
    )
    root = _agents_root(tmp_path, text)
    expected = text.replace(
        f"{_REGION_OPEN}\n@_aitna/akmon/guardrails/_common.md\n@somewhere/else.md\n{_REGION_CLOSE}\n", _region()
    )
    assert sync.sync_imports_region(text, root) == expected
    files, errors = sync._planned_files(root)
    assert errors == []
    assert [planned.content for planned in files if planned.path == root / "AGENTS.md"] == [expected]
    assert sync.main(["--project-root", str(root)]) == 0
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == expected
    assert sync.main(["--project-root", str(root), "--check"]) == 0  # a second pass finds nothing to do


def test_sync_migrates_the_single_common_import_into_the_region(tmp_path):
    text = (
        f"# AGENTS.md\n\n{_HEADING}\n\nProse.\n\n"
        "@_aitna/akmon/guardrails/_common.md\n@_aitna/akmon/profiles/python.md\n"
    )
    root = _agents_root(tmp_path, text)
    assert sync.sync_imports_region(text, root) == (
        f"# AGENTS.md\n\n{_HEADING}\n\nProse.\n\n{_region()}@_aitna/akmon/profiles/python.md\n"
    )


def test_sync_migration_folds_every_hand_written_rule_import_into_the_one_region(tmp_path):
    text = (
        f"{_HEADING}\n\n@_aitna/akmon/guardrails/_common.md\nprose\n@_aitna/akmon/rules/templates.md\n"
        "@_aitna/akmon/profiles/js.md\n"
    )
    root = _agents_root(tmp_path, text)
    assert sync.sync_imports_region(text, root) == f"{_HEADING}\n\n{_region()}prose\n@_aitna/akmon/profiles/js.md\n"


def test_sync_migration_leaves_a_quoted_or_fenced_import_alone(tmp_path):
    text = (
        f"{_HEADING}\n\nSee `@_aitna/akmon/guardrails/_common.md`.\n\n```\n@_aitna/akmon/guardrails/_common.md\n```\n\n"
        "@_aitna/akmon/profiles/js.md\n"
    )
    root = _agents_root(tmp_path, text)
    synced = sync.sync_imports_region(text, root)
    assert synced == text.replace("@_aitna/akmon/profiles/js.md\n", _region() + "@_aitna/akmon/profiles/js.md\n")


def test_sync_inserts_the_region_before_the_first_profile_import_when_no_rule_line_exists(tmp_path):
    text = f"# AGENTS.md\n\n{_HEADING}\n\nProse.\n\n@_aitna/akmon/profiles/python.md\n@_aitna/akmon/profiles/js.md\n"
    root = _agents_root(tmp_path, text)
    assert sync.sync_imports_region(text, root) == (
        f"# AGENTS.md\n\n{_HEADING}\n\nProse.\n\n{_region()}@_aitna/akmon/profiles/python.md\n"
        "@_aitna/akmon/profiles/js.md\n"
    )


def test_sync_appends_the_region_to_the_end_of_the_block_when_there_is_no_anchor_line(tmp_path):
    text = f"# AGENTS.md\n\n{_HEADING}\n\nHand-tuned block.\n\n## Peer\n\nKept.\n"
    root = _agents_root(tmp_path, text)
    assert sync.sync_imports_region(text, root) == (
        f"# AGENTS.md\n\n{_HEADING}\n\nHand-tuned block.\n\n{_region()}\n## Peer\n\nKept.\n"
    )


def test_sync_appends_to_a_block_that_ends_the_file_without_a_final_newline(tmp_path):
    text = f"{_HEADING}\n\nHand-tuned block."
    root = _agents_root(tmp_path, text)
    assert sync.sync_imports_region(text, root) == f"{text}\n\n{_region().rstrip()}"


def test_sync_leaves_agents_md_without_an_akmon_block_alone(tmp_path):
    text = "# AGENTS.md\n\n@_aitna/akmon/guardrails/_common.md\n"
    root = _agents_root(tmp_path, text)
    assert sync.sync_imports_region(text, root) == text
    files, errors = sync._planned_files(root)
    assert errors == []
    assert root / "AGENTS.md" not in {planned.path for planned in files}
    assert sync.main(["--project-root", str(root)]) == 0
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == text


def test_sync_reports_an_unbalanced_region_as_a_plan_error_and_writes_nothing(tmp_path):
    text = f"{_HEADING}\n\n{_REGION_OPEN}\n@_aitna/akmon/guardrails/_common.md\n"
    root = _agents_root(tmp_path, text)
    with pytest.raises(ValueError, match="unbalanced imports region"):
        sync.sync_imports_region(text, root)
    _, errors = sync._planned_files(root)
    assert len(errors) == 1
    assert "unbalanced imports region" in errors[0]
    assert sync.main(["--project-root", str(root)]) == 2
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == text


def test_sync_re_points_the_region_when_the_mode_changes(tmp_path):
    text = f"{_HEADING}\n\n{_region('_aitna/akmon')}@_aitna/akmon/profiles/python.md\n"
    root = _agents_root(tmp_path, text)
    (root / "_aitna" / ".akmon.toml").write_text('mount = "package"\n', encoding="utf-8")
    synced = sync.sync_imports_region(text, root)
    assert synced.startswith(f"{_HEADING}\n\n{_region('_aitna/.akmon')}")
    assert synced.endswith("@_aitna/akmon/profiles/python.md\n")  # the profile line is hand-owned


def test_sync_check_names_the_expected_lines_when_the_region_drifted(tmp_path, capsys):
    text = f"{_HEADING}\n\n{_REGION_OPEN}\n@_aitna/akmon/guardrails/_common.md\n{_REGION_CLOSE}\n"
    root = _agents_root(tmp_path, text)
    assert sync.main(["--project-root", str(root), "--check"]) == 1
    out = capsys.readouterr().out
    line = next(line for line in out.splitlines() if "AGENTS.md" in line and "sync.stale-generated" in line)
    assert line.startswith("ERROR sync.stale-generated ")
    for expected in sync.imports_region("_aitna/akmon"):
        assert expected in line
    assert (root / "AGENTS.md").read_text(encoding="utf-8") == text  # --check writes nothing


def test_sync_check_flags_a_block_with_no_region_at_all(tmp_path, capsys):
    root = _agents_root(tmp_path, f"{_HEADING}\n\n@_aitna/akmon/guardrails/_common.md\n")
    assert sync.main(["--project-root", str(root), "--check"]) == 1
    assert "sync.stale-generated" in capsys.readouterr().out
