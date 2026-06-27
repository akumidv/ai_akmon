"""Unit tests for the vendor-neutral keystone hook logic (``hook_core``).

These cover the decision functions only — no vendor payload shapes (that is
``claude_adapter``'s job) and no live git (the commit guard takes an explicit ``branch``).

Run from the keystone root::

    python3 -m pytest tests
"""

from __future__ import annotations

from pathlib import Path

import hook_core
from hook_core import (
    HookResult,
    agent_names,
    analysis_write_result,
    git_commit_guard_result,
    is_code_path,
    is_planning_doc,
    role_on_code_result,
    session_start_result,
)

# --------------------------------------------------------------------------------------
# git_commit_guard_result
# --------------------------------------------------------------------------------------


def test_non_git_command_is_ignored():
    assert git_commit_guard_result("ls -la") is None
    assert git_commit_guard_result("python3 build.py") is None


def test_command_mentioning_git_without_a_guarded_subcommand_passes():
    # 'git' substring is present but no push/tag/merge/commit/co-author → no decision.
    assert git_commit_guard_result("git status") is None
    assert git_commit_guard_result("git diff --stat") is None


def test_co_authored_by_is_denied_case_insensitively():
    for command in (
        'git commit -m "x\n\nCo-Authored-By: Claude <noreply@anthropic.com>"',
        'git commit -m "co-authored-by: someone"',
    ):
        result = git_commit_guard_result(command, branch="feature/x")
        assert result is not None
        assert result.permission_decision == "deny"
        assert "Co-Authored-By" in result.permission_reason


def test_co_authored_check_precedes_branch_check():
    # Even on a feature branch (commit would otherwise pass) the trailer is denied.
    result = git_commit_guard_result(
        'git commit -m "Co-authored-by: x" ', branch="feature/safe"
    )
    assert result is not None
    assert result.permission_decision == "deny"


def test_push_tag_merge_ask_for_confirmation():
    for sub in ("push", "tag", "merge"):
        result = git_commit_guard_result(f"git {sub} origin main", branch="feature/x")
        assert result is not None, sub
        assert result.permission_decision == "ask", sub
        assert "owner owns commits" in result.permission_reason


def test_push_with_inline_config_is_still_caught():
    result = git_commit_guard_result("git -c user.name=x push origin main", branch="feature/x")
    assert result is not None
    assert result.permission_decision == "ask"


def test_commit_on_main_asks():
    result = git_commit_guard_result('git commit -m "x"', branch="main")
    assert result is not None
    assert result.permission_decision == "ask"
    assert "main" in result.permission_reason


def test_commit_on_master_asks():
    result = git_commit_guard_result('git commit -m "x"', branch="master")
    assert result is not None
    assert result.permission_decision == "ask"


def test_commit_on_empty_branch_asks_with_detached_head_wording():
    result = git_commit_guard_result('git commit -m "x"', branch="")
    assert result is not None
    assert result.permission_decision == "ask"
    assert "detached HEAD" in result.permission_reason


def test_commit_on_feature_branch_passes():
    assert git_commit_guard_result('git commit -m "x"', branch="feature/work") is None
    assert git_commit_guard_result("git -c user.name=x commit --amend", branch="dev") is None


def test_pipe_boundary_prevents_false_positive():
    # 'push' appears only after a pipe, so [^|&;]* should not bridge to it.
    assert git_commit_guard_result("echo git | grep push", branch="feature/x") is None


def test_word_boundary_avoids_substring_match():
    # 'legitimate' contains 'git' but no standalone guarded subcommand.
    assert git_commit_guard_result("legitimate_tool run", branch="feature/x") is None


def test_resolved_branch_uses_live_git_when_branch_is_none(monkeypatch):
    monkeypatch.setattr(hook_core, "current_git_branch", lambda: "main")
    result = git_commit_guard_result('git commit -m "x"')  # branch defaults to live lookup
    assert result is not None
    assert result.permission_decision == "ask"


def test_current_git_branch_returns_string():
    # Smoke: never raises, always a str (empty when not in a repo / git missing).
    assert isinstance(hook_core.current_git_branch(), str)


# --------------------------------------------------------------------------------------
# agent_names
# --------------------------------------------------------------------------------------


def _make_agent(base: Path, name: str, *, with_readme: bool = True) -> None:
    agent_dir = base / name
    agent_dir.mkdir(parents=True)
    if with_readme:
        (agent_dir / "README.md").write_text("charter", encoding="utf-8")


def test_agent_names_lists_only_dirs_with_readme_sorted(tmp_path):
    _make_agent(tmp_path, "engineer")
    _make_agent(tmp_path, "architect")
    _make_agent(tmp_path, "draft", with_readme=False)  # no README → excluded
    (tmp_path / ".hidden").mkdir()  # dotdir → excluded
    (tmp_path / "loose.md").write_text("x", encoding="utf-8")  # file → excluded
    assert agent_names(tmp_path) == ["architect", "engineer"]


def test_agent_names_missing_directory_returns_empty(tmp_path):
    assert agent_names(tmp_path / "does-not-exist") == []


# --------------------------------------------------------------------------------------
# session_start_result
# --------------------------------------------------------------------------------------


def test_session_start_lists_dev_and_desk_agents(tmp_path):
    _make_agent(tmp_path / "_forge" / "agents", "architect")
    _make_agent(tmp_path / "_forge" / "agents", "engineer")
    _make_agent(tmp_path / "agents", "options-analyst")

    result = session_start_result(tmp_path)
    assert isinstance(result, HookResult)
    assert result.event_name == "SessionStart"
    ctx = result.additional_context
    assert "DEVELOP (build the project): architect, engineer" in ctx
    assert "OPERATE (run/use from outside): options-analyst" in ctx
    assert "_forge/memory/" in ctx


def test_session_start_dev_only_omits_operate_line(tmp_path):
    _make_agent(tmp_path / "_forge" / "agents", "engineer")
    result = session_start_result(tmp_path)
    assert result is not None
    assert "DEVELOP" in result.additional_context
    assert "OPERATE" not in result.additional_context


def test_session_start_none_when_no_agents(tmp_path):
    assert session_start_result(tmp_path) is None


def test_session_start_includes_develop_discriminator_when_dev_agents_exist(tmp_path):
    # A10: the routing rule (decompose→review · construct→architect · realize→engineer) is
    # surfaced up front, not only after a code/planning edit.
    _make_agent(tmp_path / "_forge" / "agents", "engineer")
    ctx = session_start_result(tmp_path).additional_context
    assert "decompose an existing thing → review" in ctx
    assert "construct a new structure/decision → architect" in ctx
    assert "realize a decided structure in code → engineer" in ctx


def test_session_start_operate_only_uses_generic_pick_line(tmp_path):
    # With no DEVELOP agents, the DEVELOP-specific discriminator would be noise: fall back.
    _make_agent(tmp_path / "agents", "options-analyst")
    ctx = session_start_result(tmp_path).additional_context
    assert "→ review" not in ctx  # no DEVELOP discriminator
    assert "Pick the one the task calls for" in ctx


# --------------------------------------------------------------------------------------
# is_code_path
# --------------------------------------------------------------------------------------


def test_is_code_path_true_for_source_extensions():
    assert is_code_path("src/alphavar/option_class.py")
    assert is_code_path("pkg/mod.ts")
    assert is_code_path("WEIRD/CASE.PY")  # case-insensitive


def test_is_code_path_false_for_non_code_extensions():
    assert not is_code_path("README.md")
    assert not is_code_path("notes.txt")
    assert not is_code_path("data.csv")


def test_is_code_path_false_for_excluded_segments():
    # Claude sends absolute file paths, so the segments are slash-delimited as designed.
    assert not is_code_path("/repo/docs/dev/PROJECT_OVERVIEW.py")  # under /docs/
    assert not is_code_path("/repo/_forge/keystone/hooks/hook_core.py")  # keystone itself
    assert not is_code_path("/repo/_forge/memory/note.py")
    assert not is_code_path("/repo/.claude/settings.py")


def test_is_code_path_segment_match_requires_surrounding_slashes():
    # Documents a sharp edge: a *top-level relative* path has no leading slash, so the
    # "/docs/" segment does not match and the file is treated as code. Harmless in
    # practice (Claude passes absolute paths) but worth pinning.
    assert is_code_path("docs/dev/x.py")


def test_is_code_path_handles_backslash_separators():
    assert is_code_path("src\\alphavar\\foo.py")
    assert not is_code_path("C:\\repo\\docs\\foo.py")


# --------------------------------------------------------------------------------------
# role_on_code_result
# --------------------------------------------------------------------------------------


def _isolate_marker_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))


def test_role_on_code_ignores_non_edit_kinds(monkeypatch, tmp_path):
    # The core works on the neutral kind only; anything but EDIT_TOOL is ignored.
    _isolate_marker_dir(monkeypatch, tmp_path)
    assert role_on_code_result("read", "src/x.py", "s1") is None
    assert role_on_code_result("bash", "src/x.py", "s1") is None


def test_role_on_code_ignores_non_code_paths(monkeypatch, tmp_path):
    _isolate_marker_dir(monkeypatch, tmp_path)
    assert role_on_code_result(hook_core.EDIT_TOOL, "README.md", "s1") is None
    assert role_on_code_result(hook_core.EDIT_TOOL, None, "s1") is None


def test_role_on_code_fires_once_per_session(monkeypatch, tmp_path):
    _isolate_marker_dir(monkeypatch, tmp_path)
    edit = hook_core.EDIT_TOOL

    first = role_on_code_result(edit, "src/alphavar/x.py", "session-A")
    assert isinstance(first, HookResult)
    assert first.event_name == "PreToolUse"
    assert "engineer" in first.additional_context

    # Same session → suppressed by the marker file.
    second = role_on_code_result(edit, "src/alphavar/y.py", "session-A")
    assert second is None

    # Different session → fires again.
    other = role_on_code_result(edit, "src/alphavar/z.py", "session-B")
    assert isinstance(other, HookResult)


def test_core_names_no_vendor_tools():
    # The neutral core must not hardcode any vendor's tool names — those live in the adapters.
    source = (Path(hook_core.__file__)).read_text(encoding="utf-8")
    for vendor_tool in ("apply_patch", "MultiEdit", '"Edit"', '"Write"'):
        assert vendor_tool not in source, vendor_tool


# --------------------------------------------------------------------------------------
# is_planning_doc / analysis_write_result
# --------------------------------------------------------------------------------------


def test_is_planning_doc_matches_backlog_and_design_docs():
    assert is_planning_doc("/repo/_forge/TASKS.md")
    assert is_planning_doc("/repo/_forge/TASKS_ARCHIVE.md")
    assert is_planning_doc("/repo/_forge/design/forecast/README.md")
    assert is_planning_doc("/repo/docs/dev/decisions/0003-x.md")
    assert is_planning_doc("/repo/docs/dev/ARCHITECTURE_REQUIREMENTS.md")
    assert is_planning_doc("/repo/_forge/keystone/pipelines/tasks.md")


def test_is_planning_doc_rejects_code_and_unrelated_docs():
    assert not is_planning_doc("/repo/src/alphavar/option_class.py")  # code
    assert not is_planning_doc("/repo/_forge/keystone/hooks/hook_core.py")  # keystone code, not .md
    assert not is_planning_doc("/repo/README.md")  # top-level doc, not a planning root
    assert not is_planning_doc("/repo/_forge/memory/note.md")  # memory is not a backlog/design doc


def test_analysis_write_ignores_non_edit_kinds(monkeypatch, tmp_path):
    _isolate_marker_dir(monkeypatch, tmp_path)
    assert analysis_write_result("read", "/r/_forge/TASKS.md", "s1") is None
    assert analysis_write_result("bash", "/r/_forge/TASKS.md", "s1") is None


def test_analysis_write_ignores_non_planning_paths(monkeypatch, tmp_path):
    _isolate_marker_dir(monkeypatch, tmp_path)
    assert analysis_write_result(hook_core.EDIT_TOOL, "/r/src/alphavar/x.py", "s1") is None
    assert analysis_write_result(hook_core.EDIT_TOOL, None, "s1") is None


def test_analysis_write_fires_once_per_session(monkeypatch, tmp_path):
    _isolate_marker_dir(monkeypatch, tmp_path)
    edit = hook_core.EDIT_TOOL

    first = analysis_write_result(edit, "/r/_forge/TASKS.md", "session-A")
    assert isinstance(first, HookResult)
    assert first.event_name == "PreToolUse"
    assert "Analysis-before-mutation" in first.additional_context

    # same session → suppressed
    assert analysis_write_result(edit, "/r/_forge/design/x.md", "session-A") is None

    # different session → fires again
    assert isinstance(analysis_write_result(edit, "/r/_forge/TASKS.md", "session-B"), HookResult)


def test_analysis_guard_and_role_on_code_are_disjoint(monkeypatch, tmp_path):
    # A code edit triggers role-on-code, not the analysis guard; a backlog edit, the reverse.
    _isolate_marker_dir(monkeypatch, tmp_path)
    edit = hook_core.EDIT_TOOL
    assert analysis_write_result(edit, "/r/src/alphavar/x.py", "s1") is None
    assert role_on_code_result(edit, "/r/_forge/TASKS.md", "s2") is None


# --------------------------------------------------------------------------------------
# configurable dev-layer root (FORGE_ROOT) — A4
# --------------------------------------------------------------------------------------


def test_forge_root_resolvers_default_and_override(monkeypatch, tmp_path):
    monkeypatch.delenv("FORGE_ROOT", raising=False)
    assert hook_core.forge_root_name() == "_forge"
    assert hook_core.keystone_root(tmp_path) == tmp_path / "_forge" / "keystone"
    monkeypatch.setenv("FORGE_ROOT", "tools/ai")
    assert hook_core.forge_root_name() == "tools/ai"
    assert hook_core.forge_root(tmp_path) == tmp_path / "tools" / "ai"
    assert hook_core.keystone_root(tmp_path) == tmp_path / "tools" / "ai" / "keystone"


def test_is_code_path_excludes_custom_dev_root(monkeypatch):
    monkeypatch.setenv("FORGE_ROOT", "tools/ai")
    # the relocated dev tree is excluded from "code"...
    assert not is_code_path("/repo/tools/ai/keystone/hooks/hook_core.py")
    assert not is_code_path("/repo/tools/ai/memory/note.py")
    # ...and the old default path is now just ordinary code (the layer moved away from it)
    assert is_code_path("/repo/_forge/keystone/hooks/hook_core.py")


def test_is_planning_doc_tracks_custom_dev_root(monkeypatch):
    monkeypatch.setenv("FORGE_ROOT", "tools/ai")
    assert is_planning_doc("/repo/tools/ai/TASKS.md")
    assert is_planning_doc("/repo/tools/ai/design/x.md")
    assert is_planning_doc("/repo/tools/ai/keystone/pipelines/tasks.md")
    # the default path no longer counts as the planning surface under the custom root
    assert not is_planning_doc("/repo/_forge/TASKS.md")


def test_session_start_reads_custom_dev_root_agents(monkeypatch, tmp_path):
    monkeypatch.setenv("FORGE_ROOT", "tools/ai")
    agents = tmp_path / "tools" / "ai" / "agents" / "architect"
    agents.mkdir(parents=True)
    (agents / "README.md").write_text("# architect\n", encoding="utf-8")
    result = session_start_result(tmp_path)
    assert isinstance(result, HookResult)
    assert "architect" in result.additional_context
    assert "tools/ai/memory/" in result.additional_context  # memory hint tracks the root
