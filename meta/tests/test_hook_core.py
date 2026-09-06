"""Unit tests for the vendor-neutral akmon hook logic (``hook_core``).

These cover the decision functions only — no vendor payload shapes (that is
``claude_adapter``'s job) and no live git (the commit guard takes an explicit ``branch``).

Run from the akmon root::

    python3 -m pytest tests
"""

from __future__ import annotations

from pathlib import Path

import hook_core
import pytest
from hook_core import (
    HookResult,
    agent_names,
    analysis_write_result,
    d2_ledger_reminder_result,
    d2_pending_count,
    d2_sensitive_paths,
    d2_status_counts,
    d2_status_line,
    d2_tracking_active,
    git_commit_guard_result,
    is_code_path,
    is_d2_sensitive_path,
    is_planning_doc,
    privilege_escalation_guard_result,
    role_on_code_result,
    session_start_result,
)

from common.materialization import materialized_markdown

# --------------------------------------------------------------------------------------
# privilege_escalation_guard_result
# --------------------------------------------------------------------------------------


def test_sudo_command_is_denied():
    for command in ("sudo rm -rf /", "sudo -n true", "apt-get update && sudo apt-get install x"):
        result = privilege_escalation_guard_result(command)
        assert result is not None
        assert result.permission_decision == "deny"
        assert "sudo" in result.permission_reason


def test_command_without_sudo_is_ignored():
    assert privilege_escalation_guard_result("ls -la") is None
    assert privilege_escalation_guard_result("git commit -m x") is None


def test_sudo_as_substring_of_another_word_is_not_matched():
    # word boundary: a path/name that merely contains "sudo" must not trip the guard.
    assert privilege_escalation_guard_result("ls /opt/pseudo-tool") is None


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
        result = git_commit_guard_result(
            f"git {sub} origin main", branch="feature/x", permission_mode="default"
        )
        assert result is not None, sub
        assert result.permission_decision == "ask", sub
        assert "owner owns commits" in result.permission_reason


def test_push_with_inline_config_is_still_caught():
    result = git_commit_guard_result(
        "git -c user.name=x push origin main", branch="feature/x", permission_mode="default"
    )
    assert result is not None
    assert result.permission_decision == "ask"


def test_commit_on_main_asks():
    result = git_commit_guard_result('git commit -m "x"', branch="main", permission_mode="default")
    assert result is not None
    assert result.permission_decision == "ask"
    assert "main" in result.permission_reason


def test_commit_on_master_asks():
    result = git_commit_guard_result('git commit -m "x"', branch="master", permission_mode="default")
    assert result is not None
    assert result.permission_decision == "ask"


def test_commit_on_empty_branch_asks_with_detached_head_wording():
    result = git_commit_guard_result('git commit -m "x"', branch="", permission_mode="default")
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
    result = git_commit_guard_result(
        'git commit -m "x"', permission_mode="default"
    )  # branch defaults to live lookup
    assert result is not None
    assert result.permission_decision == "ask"


# --------------------------------------------------------------------------------------
# ask -> deny escalation for unattended sessions (C31/D2-10)
# --------------------------------------------------------------------------------------


def test_ask_escalates_to_deny_outside_interactive_default():
    for mode in (None, "acceptEdits", "plan", "dontAsk", "bypassPermissions", "somethingUnknown"):
        result = git_commit_guard_result(
            "git commit -m 'x'", branch="main", permission_mode=mode
        )
        assert result is not None, mode
        assert result.permission_decision == "deny", mode
        assert "escalated ask" in result.permission_reason, mode
        assert "main" in result.permission_reason, mode  # original reason text preserved


def test_ask_stays_ask_in_interactive_default_mode():
    result = git_commit_guard_result('git commit -m "x"', branch="main", permission_mode="default")
    assert result is not None
    assert result.permission_decision == "ask"
    assert "escalated" not in result.permission_reason


def test_escalation_does_not_touch_deny_decisions():
    # The co-authored-by guard is already a `deny` — escalation logic should leave it alone
    # (no double-escalation wording) regardless of permission_mode.
    result = git_commit_guard_result(
        'git commit -m "Co-authored-by: x"', branch="feature/x", permission_mode="acceptEdits"
    )
    assert result is not None
    assert result.permission_decision == "deny"
    assert "escalated" not in result.permission_reason


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
    _make_agent(tmp_path / "_aitna" / "agents", "architect")
    _make_agent(tmp_path / "_aitna" / "agents", "engineer")
    _make_agent(tmp_path / "agents", "options-analyst")

    result = session_start_result(tmp_path)
    assert isinstance(result, HookResult)
    assert result.event_name == "SessionStart"
    ctx = result.additional_context
    assert "DEVELOP (build the project): architect, engineer" in ctx
    assert "OPERATE (run/use from outside): options-analyst" in ctx
    assert "_aitna/memory/" in ctx


def test_session_start_dev_only_omits_operate_line(tmp_path):
    _make_agent(tmp_path / "_aitna" / "agents", "engineer")
    result = session_start_result(tmp_path)
    assert result is not None
    assert "DEVELOP" in result.additional_context
    assert "OPERATE" not in result.additional_context


def test_session_start_none_when_no_agents(tmp_path):
    assert session_start_result(tmp_path) is None


def test_session_start_includes_develop_discriminator_when_dev_agents_exist(tmp_path):
    # A10: the routing rule (decompose→review · construct→architect · realize→engineer) is
    # surfaced up front, not only after a code/planning edit.
    _make_agent(tmp_path / "_aitna" / "agents", "engineer")
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
# session_start_result — stale-guardrail notice (C77)
# --------------------------------------------------------------------------------------


def _guardrail_tree(tmp_path: Path, text: str) -> Path:
    tree = tmp_path / "installed"
    (tree / "guardrails").mkdir(parents=True)
    (tree / "guardrails" / "_common.md").write_text(text, encoding="utf-8")
    return tree


def _materialized(root: Path, text: str) -> Path:
    dest = root / "_aitna" / ".akmon" / "guardrails"
    dest.mkdir(parents=True)
    path = dest / "_common.md"
    path.write_text(materialized_markdown(text), encoding="utf-8")
    return path


def _running_tree(monkeypatch, tree: Path) -> None:
    """Stand in for "the tree this hook executes from" — in production the installed wheel."""
    monkeypatch.setattr(hook_core, "akmon_runtime_root", lambda project_root: tree)


def test_session_start_is_quiet_when_the_guardrail_copy_is_current(monkeypatch, tmp_path):
    text = "# Common\n\nrule\n"
    _running_tree(monkeypatch, _guardrail_tree(tmp_path, text))
    _materialized(tmp_path, text)
    _make_agent(tmp_path / "_aitna" / "agents", "engineer")

    result = session_start_result(tmp_path)
    assert "akmon sync" not in result.additional_context
    assert result.system_message is None


def test_session_start_reports_guardrails_the_running_akmon_has_moved_past(monkeypatch, tmp_path):
    """The window no CI gate covers: the pin bump installed new hooks, the repository still
    holds the previous release's rules, and nothing else in the session would say so."""
    _running_tree(monkeypatch, _guardrail_tree(tmp_path, "# Common\n\nnew rule\n"))
    _materialized(tmp_path, "# Common\n\nold rule\n")
    _make_agent(tmp_path / "_aitna" / "agents", "engineer")

    result = session_start_result(tmp_path)
    notice = result.additional_context.splitlines()[-1]
    assert notice.startswith("\u26a0 akmon:")
    assert "_common.md" in notice
    assert "akmon sync" in notice
    # The restart is part of the instruction: the @-import is expanded once, at session start,
    # so a mid-session sync fixes the file and changes nothing already in context.
    assert "start a new session" in notice
    # Owner-addressed — it asks for a command and a restart the model cannot perform.
    assert result.system_message == notice


def test_session_start_speaks_the_notice_even_with_no_agent_charters(monkeypatch, tmp_path):
    """A project with no agents gets no reminder, but the rules it just loaded being the wrong
    ones is not a fact about its charters."""
    _running_tree(monkeypatch, _guardrail_tree(tmp_path, "# Common\n\nnew rule\n"))
    _materialized(tmp_path, "# Common\n\nold rule\n")

    result = session_start_result(tmp_path)
    assert result is not None
    assert result.additional_context == result.system_message
    assert "_common.md" in result.additional_context


def test_session_start_stays_none_with_no_agents_and_no_materialization(monkeypatch, tmp_path):
    _running_tree(monkeypatch, _guardrail_tree(tmp_path, "# Common\n\nrule\n"))
    assert session_start_result(tmp_path) is None


def test_session_start_ignores_leftover_package_guardrails_in_mounted_mode(monkeypatch, tmp_path):
    """Mounted AGENTS imports the mount directly; an old package copy is not active input."""
    mounted = tmp_path / "_aitna" / "akmon"
    (mounted / "guardrails").mkdir(parents=True)
    (mounted / "guardrails" / "_common.md").write_text(
        "# Common\n\nmounted rule\n", encoding="utf-8"
    )
    _running_tree(monkeypatch, mounted)
    _materialized(tmp_path, "# Common\n\nold package rule\n")
    _make_agent(tmp_path / "_aitna" / "agents", "engineer")

    result = session_start_result(tmp_path)
    assert result is not None
    assert "akmon sync" not in result.additional_context
    assert result.system_message is None


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
    assert not is_code_path("/repo/_aitna/akmon/hooks/hook_core.py")  # akmon itself
    assert not is_code_path("/repo/_aitna/memory/note.py")
    assert not is_code_path("/repo/.claude/settings.py")


def test_is_code_path_handles_backslash_separators():
    assert is_code_path("src\\alphavar\\foo.py")
    assert not is_code_path("C:\\repo\\docs\\foo.py")


# --------------------------------------------------------------------------------------
# path-form invariant (C47): every predicate answers the same for both forms of a path
# --------------------------------------------------------------------------------------

# Claude Code always sends an absolute `file_path`; Codex passes through what the patch
# body carried (`*** Add File: note.txt`), which is repo-relative. A predicate that answers
# differently for the two forms is a guardrail that exists for one vendor only — and says
# nothing when it does not match, so the gap is invisible until a live probe finds it.
_PATH_FORM_CORPUS = (
    "src/alphavar/option_class.py",
    "docs/dev/x.py",
    "_aitna/design/probe-n2-hookfire.md",
    "_aitna/design/forecast/README.md",
    "_aitna/TASKS.md",
    "_aitna/TASKS_ARCHIVE.md",
    "_aitna/akmon/hooks/hook_core.py",
    "_aitna/akmon/pipelines/tasks.md",
    "_aitna/memory/note.md",
    ".claude/settings.py",
    "README.md",
    "pkg/mod.ts",
    "notes.txt",
)

_D2_GLOBS = ["src/**/*.py", "_aitna/design/**", "**/TASKS.md"]


@pytest.mark.parametrize("relative", _PATH_FORM_CORPUS)
def test_path_predicates_agree_on_relative_and_absolute_forms(tmp_path, relative):
    absolute = str(tmp_path / relative)
    assert is_code_path(relative, tmp_path) == is_code_path(absolute, tmp_path)
    assert is_planning_doc(relative, tmp_path) == is_planning_doc(absolute, tmp_path)
    assert is_d2_sensitive_path(relative, tmp_path, _D2_GLOBS) == is_d2_sensitive_path(absolute, tmp_path, _D2_GLOBS)


def test_relative_paths_get_the_right_answer_not_merely_a_consistent_one(tmp_path):
    # Equality alone would also hold if both forms were wrong; these pin the answers.
    # The first is the exact path probe G2 edited in alphavar, where the guard stayed mute.
    assert is_planning_doc("_aitna/design/probe-n2-hookfire.md", tmp_path)
    assert is_planning_doc("_aitna/TASKS.md", tmp_path)
    assert is_code_path("src/alphavar/option_class.py", tmp_path)
    assert not is_code_path("docs/dev/x.py", tmp_path)  # a doc tree is not code, in either form
    assert not is_code_path("_aitna/akmon/hooks/hook_core.py", tmp_path)


def test_project_root_is_stripped_before_segments_are_matched(tmp_path):
    # The other half of "normalize first": a repository that happens to live under a
    # directory called `docs` used to have every file in it classified as a non-code path.
    root = tmp_path / "docs" / "myproject"
    (root / "src").mkdir(parents=True)
    assert is_code_path(str(root / "src" / "x.py"), root)
    assert not is_code_path(str(root / "docs" / "dev" / "x.py"), root)  # its own docs tree still excluded


@pytest.mark.parametrize(
    "relative, canonical",
    (
        ("./_aitna/design/./probe.md", "_aitna/design/probe.md"),
        ("src/pkg/../x.py", "src/x.py"),
        ("src//pkg///x.py", "src/pkg/x.py"),
    ),
)
def test_path_predicates_canonicalize_relative_dot_dot_and_duplicate_separators(tmp_path, relative, canonical):
    absolute = str((tmp_path / canonical).resolve(strict=False))
    assert is_code_path(relative, tmp_path) == is_code_path(absolute, tmp_path)
    assert is_planning_doc(relative, tmp_path) == is_planning_doc(absolute, tmp_path)
    assert is_d2_sensitive_path(relative, tmp_path, _D2_GLOBS) == is_d2_sensitive_path(
        absolute, tmp_path, _D2_GLOBS
    )


@pytest.mark.parametrize(
    "outside",
    (
        "../_aitna/design/probe.md",
        "../src/pkg/x.py",
        "../TASKS.md",
    ),
)
def test_path_predicates_reject_relative_traversal_outside_project(tmp_path, outside):
    assert not is_code_path(outside, tmp_path)
    assert not is_planning_doc(outside, tmp_path)
    assert not is_d2_sensitive_path(outside, tmp_path, _D2_GLOBS)


def test_path_predicates_reject_absolute_targets_outside_project(tmp_path):
    outside = tmp_path.parent / "_aitna" / "design" / "probe.md"
    assert not is_code_path(str(outside), tmp_path)
    assert not is_planning_doc(str(outside), tmp_path)
    assert not is_d2_sensitive_path(str(outside), tmp_path, ["**"])


def test_a_symlinked_subtree_is_still_a_project_target(tmp_path):
    # The traversal guard must reject a path that *leaves* the project without rejecting one
    # that is merely *linked*. Anchoring through `Path.resolve()` followed the symlink and put
    # both of these outside the root, silencing every predicate underneath — a silent
    # non-match, which is the failure C47 exists to remove, re-entered through the guard.
    # Real shapes: an `_aitna` dev layer kept outside the repo, a monorepo's shared source,
    # an `_aitna/akmon` linked at a developer's own akmon checkout.
    project = tmp_path / "proj"
    (project / "src").mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "aitna" / "design").mkdir(parents=True)
    (elsewhere / "shared").mkdir()
    (project / "_aitna").symlink_to(elsewhere / "aitna")
    (project / "src" / "shared").symlink_to(elsewhere / "shared")

    assert is_planning_doc("_aitna/TASKS.md", project)
    assert is_planning_doc("_aitna/design/probe.md", project)
    assert is_code_path("src/shared/x.py", project)
    assert is_d2_sensitive_path("src/shared/x.py", project, _D2_GLOBS)
    # The absolute form through the same link agrees — the C47 invariant, on linked paths.
    assert is_planning_doc(str(project / "_aitna" / "TASKS.md"), project)
    assert is_code_path(str(project / "src" / "shared" / "x.py"), project)


def test_a_root_named_through_a_symlinked_alias_still_matches(tmp_path):
    # The opposite case, and the reason the resolved comparison is kept as a fallback: the
    # discovered root and the payload may name one directory through different aliases
    # (`/tmp` vs `/private/tmp`, a checkout reached through a linked home).
    real = tmp_path / "real"
    (real / "_aitna").mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(real)

    assert is_planning_doc(str(alias / "_aitna" / "TASKS.md"), real)
    assert is_planning_doc(str(real / "_aitna" / "TASKS.md"), alias)


def test_analysis_guard_fires_on_the_relative_form_codex_delivers(monkeypatch, tmp_path):
    # C47 end to end at the decision level: the same edit, spelled the way each vendor
    # spells it, must reach the same reminder.
    _isolate_marker_dir(monkeypatch, tmp_path)
    root = tmp_path / "repo"
    absolute_form = str(root / "_aitna" / "design" / "probe.md")
    relative = analysis_write_result(hook_core.EDIT_TOOL, "_aitna/design/probe.md", "sess-rel", root)
    absolute = analysis_write_result(hook_core.EDIT_TOOL, absolute_form, "sess-abs", root)
    assert isinstance(relative, HookResult)
    assert relative.additional_context == absolute.additional_context


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


# --------------------------------------------------------------------------------------
# d2_ledger_reminder_result + config/glob helpers
# --------------------------------------------------------------------------------------


def _make_d2_project(tmp_path: Path, *, globs: str | None = '["src/**/lib/**"]') -> Path:
    """A minimal project root with AGENTS.md + <aitna>/akmon; optional [d2_ledger] config."""
    root = tmp_path / "proj"
    aitna = root / "_aitna"
    (aitna / "akmon").mkdir(parents=True)
    (root / "AGENTS.md").write_text("x", encoding="utf-8")
    if globs is not None:
        (aitna / ".akmon.toml").write_text(f"[d2_ledger]\nsensitive_paths = {globs}\n", encoding="utf-8")
    return root


def test_d2_sensitive_paths_reads_configured_globs(tmp_path):
    root = _make_d2_project(tmp_path)
    assert d2_sensitive_paths(root) == ["src/**/lib/**"]


def test_d2_sensitive_paths_empty_without_config(tmp_path):
    root = _make_d2_project(tmp_path, globs=None)
    assert d2_sensitive_paths(root) == []


def test_is_d2_sensitive_path_matches_relative_glob(tmp_path):
    root = _make_d2_project(tmp_path)
    globs = ["src/**/lib/**"]
    assert is_d2_sensitive_path(str(root / "src/pkg/lib/x.py"), root, globs)
    assert not is_d2_sensitive_path(str(root / "README.md"), root, globs)


def test_d2_ledger_reminder_ignores_non_edit_and_missing_path(monkeypatch, tmp_path):
    _isolate_marker_dir(monkeypatch, tmp_path)
    root = _make_d2_project(tmp_path)
    assert d2_ledger_reminder_result("bash", str(root / "src/pkg/lib/x.py"), "s1", root) is None
    assert d2_ledger_reminder_result(hook_core.EDIT_TOOL, None, "s1", root) is None


def test_d2_ledger_reminder_silent_when_unconfigured(monkeypatch, tmp_path):
    # No [d2_ledger] config -> the hook can't tell what's sensitive, so it stays silent (design §5.A).
    _isolate_marker_dir(monkeypatch, tmp_path)
    root = _make_d2_project(tmp_path, globs=None)
    assert d2_ledger_reminder_result(hook_core.EDIT_TOOL, str(root / "src/pkg/lib/x.py"), "s1", root) is None


def test_d2_ledger_reminder_silent_on_non_sensitive_path(monkeypatch, tmp_path):
    _isolate_marker_dir(monkeypatch, tmp_path)
    root = _make_d2_project(tmp_path)
    assert d2_ledger_reminder_result(hook_core.EDIT_TOOL, str(root / "README.md"), "s1", root) is None


def test_d2_ledger_reminder_fires_once_per_session(monkeypatch, tmp_path):
    _isolate_marker_dir(monkeypatch, tmp_path)
    root = _make_d2_project(tmp_path)
    edit = hook_core.EDIT_TOOL
    sensitive = str(root / "src/pkg/lib/x.py")

    first = d2_ledger_reminder_result(edit, sensitive, "sess-A", root)
    assert isinstance(first, HookResult)
    assert first.event_name == "PreToolUse"
    assert "D2 ledger" in first.additional_context

    # Same session → suppressed by the marker file.
    assert d2_ledger_reminder_result(edit, sensitive, "sess-A", root) is None
    # Different session → fires again.
    assert isinstance(d2_ledger_reminder_result(edit, sensitive, "sess-B", root), HookResult)


# --------------------------------------------------------------------------------------
# d2 ledger session counter (phase 3)
# --------------------------------------------------------------------------------------


_LEDGER_TWO_PENDING = (
    "# D2 ledger\n\n## Pending\n\n"
    "| id | kind | what | anchor | draft | second_opinion |\n"
    "|----|------|------|--------|-------|----------------|\n"
    "| D2-1 | math | a | x:1 |  |  |\n"
    "| D2-3 | data-shape | b | y:2 |  |  |\n\n"
    "## Verified\n\n"
    "| id | kind | what | anchor | commit |\n"
    "|----|------|------|--------|--------|\n"
    "| D2-2 | architecture | c | z:1 | abc1234 |\n"
)

_LEDGER_PENDING_AND_APPROVED = _LEDGER_TWO_PENDING.replace(
    "## Verified",
    "## Approved\n\n"
    "| id | kind | what | anchor | draft | second_opinion |\n"
    "|----|------|------|--------|-------|----------------|\n"
    "| D2-4 | architecture | d | q.py:1 | draft | review |\n\n"
    "## Verified",
)


def test_count_pending_rows_counts_only_the_pending_section():
    # The verified row also starts with "| D2-", so the counter must stop at "## Verified".
    assert hook_core._count_pending_rows(_LEDGER_TWO_PENDING) == 2


def test_count_pending_rows_zero_on_empty_tables():
    assert hook_core._count_pending_rows("## Pending\n\n## Verified\n") == 0


def test_count_d2_rows_reports_pending_and_approved():
    assert hook_core._count_d2_rows(_LEDGER_PENDING_AND_APPROVED) == (2, 1)


def _write_ledger(root: Path, text: str) -> None:
    (root / "_aitna" / "D2_LEDGER.md").write_text(text, encoding="utf-8")


def test_d2_pending_count_zero_without_ledger(tmp_path):
    assert d2_pending_count(_make_d2_project(tmp_path)) == 0


def test_d2_pending_count_reads_pending_rows(tmp_path):
    root = _make_d2_project(tmp_path)
    _write_ledger(root, _LEDGER_TWO_PENDING)
    assert d2_pending_count(root) == 2


def test_d2_status_counts_reads_both_open_states(tmp_path):
    root = _make_d2_project(tmp_path)
    _write_ledger(root, _LEDGER_PENDING_AND_APPROVED)
    assert d2_status_counts(root) == (2, 1)


def test_d2_tracking_active_with_config(tmp_path):
    assert d2_tracking_active(_make_d2_project(tmp_path)) is True


def test_d2_tracking_active_with_ledger_only(tmp_path):
    root = _make_d2_project(tmp_path, globs=None)
    _write_ledger(root, "## Pending\n\n## Verified\n")
    assert d2_tracking_active(root) is True


def test_d2_tracking_active_false_when_unused(tmp_path):
    assert d2_tracking_active(_make_d2_project(tmp_path, globs=None)) is False


def test_d2_status_line_format():
    assert d2_status_line(3, 2) == "D2 ledger: 3 pending, 2 approved"
    assert d2_status_line(0, 0) == "D2 ledger: 0 pending, 0 approved"


def test_core_names_no_vendor_tools():
    # The neutral core must not hardcode any vendor's tool names — those live in the adapters.
    source = (Path(hook_core.__file__)).read_text(encoding="utf-8")
    for vendor_tool in ("apply_patch", "MultiEdit", '"Edit"', '"Write"'):
        assert vendor_tool not in source, vendor_tool


# --------------------------------------------------------------------------------------
# is_planning_doc / analysis_write_result
# --------------------------------------------------------------------------------------


def test_is_planning_doc_matches_backlog_and_design_docs():
    assert is_planning_doc("/repo/_aitna/TASKS.md")
    assert is_planning_doc("/repo/_aitna/TASKS_ARCHIVE.md")
    assert is_planning_doc("/repo/_aitna/design/forecast/README.md")
    assert is_planning_doc("/repo/docs/dev/decisions/0003-x.md")
    assert is_planning_doc("/repo/docs/dev/ARCHITECTURE_REQUIREMENTS.md")
    assert is_planning_doc("/repo/_aitna/akmon/pipelines/tasks.md")


def test_is_planning_doc_rejects_code_and_unrelated_docs():
    assert not is_planning_doc("/repo/src/alphavar/option_class.py")  # code
    assert not is_planning_doc("/repo/_aitna/akmon/hooks/hook_core.py")  # akmon code, not .md
    assert not is_planning_doc("/repo/README.md")  # top-level doc, not a planning root
    assert not is_planning_doc("/repo/_aitna/memory/note.md")  # memory is not a backlog/design doc


def test_analysis_write_ignores_non_edit_kinds(monkeypatch, tmp_path):
    _isolate_marker_dir(monkeypatch, tmp_path)
    assert analysis_write_result("read", "/r/_aitna/TASKS.md", "s1") is None
    assert analysis_write_result("bash", "/r/_aitna/TASKS.md", "s1") is None


def test_analysis_write_ignores_non_planning_paths(monkeypatch, tmp_path):
    _isolate_marker_dir(monkeypatch, tmp_path)
    assert analysis_write_result(hook_core.EDIT_TOOL, "/r/src/alphavar/x.py", "s1") is None
    assert analysis_write_result(hook_core.EDIT_TOOL, None, "s1") is None


def test_analysis_write_fires_once_per_session(monkeypatch, tmp_path):
    _isolate_marker_dir(monkeypatch, tmp_path)
    edit = hook_core.EDIT_TOOL

    first = analysis_write_result(edit, "/r/_aitna/TASKS.md", "session-A")
    assert isinstance(first, HookResult)
    assert first.event_name == "PreToolUse"
    assert "Analysis-before-mutation" in first.additional_context

    # same session → suppressed
    assert analysis_write_result(edit, "/r/_aitna/design/x.md", "session-A") is None

    # different session → fires again
    assert isinstance(analysis_write_result(edit, "/r/_aitna/TASKS.md", "session-B"), HookResult)


def test_analysis_guard_and_role_on_code_are_disjoint(monkeypatch, tmp_path):
    # A code edit triggers role-on-code, not the analysis guard; a backlog edit, the reverse.
    _isolate_marker_dir(monkeypatch, tmp_path)
    edit = hook_core.EDIT_TOOL
    assert analysis_write_result(edit, "/r/src/alphavar/x.py", "s1") is None
    assert role_on_code_result(edit, "/r/_aitna/TASKS.md", "s2") is None


# --------------------------------------------------------------------------------------
# configurable dev-layer root (AITNA_ROOT) — A4
# --------------------------------------------------------------------------------------


def test_aitna_root_resolvers_default_and_override(monkeypatch, tmp_path):
    monkeypatch.delenv("AITNA_ROOT", raising=False)
    assert hook_core.aitna_root_name() == "_aitna"
    assert hook_core.aitna_root(tmp_path) == tmp_path / "_aitna"
    monkeypatch.setenv("AITNA_ROOT", "tools/ai")
    assert hook_core.aitna_root_name() == "tools/ai"
    assert hook_core.aitna_root(tmp_path) == tmp_path / "tools" / "ai"


def test_runtime_root_display_is_project_relative_when_the_tree_is_in_the_repo(monkeypatch, tmp_path):
    """A mounted consumer executes the hook out of its own repository, so the spelling an agent
    is handed is the project-relative one it reads everywhere else."""
    mount = tmp_path / "_aitna" / "akmon"
    mount.mkdir(parents=True)
    monkeypatch.setattr(hook_core, "_TREE_ROOT", mount)
    assert hook_core.runtime_root_display(tmp_path) == "_aitna/akmon"
    assert "_aitna/akmon/tools/d2_ledger/d2_ledger.py" in hook_core.d2_ledger_reminder_message(tmp_path)


def test_runtime_root_display_uses_the_cli_when_the_tree_is_not_the_mount(tmp_path):
    """Mode ``package``: the tree is inside the installed wheel, so its literal path carries the
    venv's Python version and is wrong on the next bump. ``akmon path`` is spelled instead."""
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    assert hook_core.runtime_root_display(tmp_path) == "$(akmon path)"
    message = hook_core.d2_ledger_reminder_message(tmp_path)
    assert "$(akmon path)/tools/d2_ledger/d2_ledger.py" in message
    assert "site-packages" not in message


def test_runtime_root_display_rejects_the_wheels_tree_inside_the_project_venv(monkeypatch, tmp_path):
    """The measured case, on a real package-mode consumer: the wheel's tree lives *under* the
    project root, at ``.venv/lib/python3.14/site-packages/akmon/_tree``. A containment test
    therefore succeeds and spells the venv's Python version into the recovery command — the one
    command a person runs when routing is already broken."""
    wheel_tree = tmp_path / ".venv" / "lib" / "python3.14" / "site-packages" / "akmon" / "_tree"
    wheel_tree.mkdir(parents=True)
    monkeypatch.setattr(hook_core, "_TREE_ROOT", wheel_tree)
    assert hook_core.runtime_root_display(tmp_path) == "$(akmon path)"
    assert "site-packages" not in hook_core.d2_ledger_reminder_message(tmp_path)


def test_is_code_path_excludes_custom_dev_root(monkeypatch):
    monkeypatch.setenv("AITNA_ROOT", "tools/ai")
    # the relocated dev tree is excluded from "code"...
    assert not is_code_path("/repo/tools/ai/akmon/hooks/hook_core.py")
    assert not is_code_path("/repo/tools/ai/memory/note.py")
    # ...and the old default path is now just ordinary code (the layer moved away from it)
    assert is_code_path("/repo/_aitna/akmon/hooks/hook_core.py")


def test_is_planning_doc_tracks_custom_dev_root(monkeypatch):
    monkeypatch.setenv("AITNA_ROOT", "tools/ai")
    assert is_planning_doc("/repo/tools/ai/TASKS.md")
    assert is_planning_doc("/repo/tools/ai/design/x.md")
    assert is_planning_doc("/repo/tools/ai/akmon/pipelines/tasks.md")
    # the default path no longer counts as the planning surface under the custom root
    assert not is_planning_doc("/repo/_aitna/TASKS.md")


def test_session_start_reads_custom_dev_root_agents(monkeypatch, tmp_path):
    monkeypatch.setenv("AITNA_ROOT", "tools/ai")
    agents = tmp_path / "tools" / "ai" / "agents" / "architect"
    agents.mkdir(parents=True)
    (agents / "README.md").write_text("# architect\n", encoding="utf-8")
    result = session_start_result(tmp_path)
    assert isinstance(result, HookResult)
    assert "architect" in result.additional_context
    assert "tools/ai/memory/" in result.additional_context  # memory hint tracks the root


# --------------------------------------------------------------------------------------
# delegation_nudge_result
# --------------------------------------------------------------------------------------


def _nudge_setup(monkeypatch, tmp_path, threshold=3, ask_threshold=None):
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setenv("KEYSTONE_DELEGATION_NUDGE_THRESHOLD", str(threshold))
    if ask_threshold is not None:
        monkeypatch.setenv("KEYSTONE_DELEGATION_ASK_THRESHOLD", str(ask_threshold))
    else:
        monkeypatch.delenv("KEYSTONE_DELEGATION_ASK_THRESHOLD", raising=False)


def test_delegation_nudge_ignores_unrecognized_kinds(monkeypatch, tmp_path):
    _nudge_setup(monkeypatch, tmp_path, threshold=1)
    assert hook_core.delegation_nudge_result("something-else", "s1") is None
    assert hook_core.delegation_nudge_result("network", "s1") is None


def test_delegation_nudge_counts_read_kind(monkeypatch, tmp_path):
    # Read/Grep/Glob normalize to hook_core.READ_TOOL and now count toward the drift counter
    # (previously only edit/shell did — the orchestrator "does everything" specifically on
    # reads/sweeps, which the nudge used to be blind to).
    _nudge_setup(monkeypatch, tmp_path, threshold=3)
    assert hook_core.delegation_nudge_result(hook_core.READ_TOOL, "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.READ_TOOL, "s1") is None
    result = hook_core.delegation_nudge_result(hook_core.READ_TOOL, "s1")
    assert isinstance(result, HookResult)
    assert "3 consecutive" in result.additional_context


def test_delegation_nudge_suppressed_in_subagent(monkeypatch, tmp_path):
    # C28d: a subagent call (agent_id present in the payload) must never nudge or ask, even
    # well past both thresholds — k_* delegates have no Task tool to act on the reminder.
    _nudge_setup(monkeypatch, tmp_path, threshold=3, ask_threshold=5)
    for _ in range(25):
        assert hook_core.delegation_nudge_result(hook_core.READ_TOOL, "s1", is_subagent=True) is None


def test_delegation_nudge_subagent_calls_do_not_charge_counter(monkeypatch, tmp_path):
    # C28d: Claude Code shares session_id between the main chain and a subagent, so subagent
    # calls must not increment the shared counter. Precede a main-chain run with a pile of
    # subagent calls (all suppressed), then confirm the main chain still needs the full
    # advisory threshold before the first advisory fires.
    _nudge_setup(monkeypatch, tmp_path, threshold=3)
    for _ in range(12):
        assert hook_core.delegation_nudge_result(hook_core.READ_TOOL, "s1", is_subagent=True) is None

    threshold = hook_core.delegation_nudge_threshold()
    for _ in range(threshold - 1):
        assert hook_core.delegation_nudge_result(hook_core.READ_TOOL, "s1", is_subagent=False) is None
    result = hook_core.delegation_nudge_result(hook_core.READ_TOOL, "s1", is_subagent=False)
    assert isinstance(result, HookResult)
    assert f"{threshold} consecutive" in result.additional_context


def test_delegation_nudge_fires_once_without_delegation_between(monkeypatch, tmp_path):
    _nudge_setup(monkeypatch, tmp_path, threshold=3)
    assert hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.SHELL_TOOL, "s1") is None
    result = hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1")
    assert isinstance(result, HookResult)
    assert "Delegation check" in result.additional_context
    assert "3 consecutive" in result.additional_context
    assert result.permission_decision is None  # advisory only, never blocks
    # Past the threshold in the same episode, with no delegation in between → silenced
    # by the marker, even as mutations keep piling up.
    assert hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1") is None
    # A different session has its own counter and marker.
    assert hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s2") is None


def test_delegation_nudge_resets_on_subagent_delegation(monkeypatch, tmp_path):
    _nudge_setup(monkeypatch, tmp_path, threshold=3)
    assert hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1") is None
    # Delegation resets the consecutive-mutation counter...
    assert hook_core.delegation_nudge_result(hook_core.SUBAGENT_TOOL, "s1") is None
    # ...so the next two mutations stay under the threshold.
    assert hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1") is not None


def test_delegation_nudge_rearms_after_subagent_delegation(monkeypatch, tmp_path):
    _nudge_setup(monkeypatch, tmp_path, threshold=3)
    assert hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1") is None
    first = hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1")
    assert isinstance(first, HookResult)
    # Silenced by the marker until a delegation happens.
    assert hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1") is None
    # A subagent delegation resets the counter AND re-arms the reminder (removes the marker).
    assert hook_core.delegation_nudge_result(hook_core.SUBAGENT_TOOL, "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1") is None
    second = hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1")
    assert isinstance(second, HookResult)
    assert "Delegation check" in second.additional_context


def test_delegation_nudge_threshold_env_fallback(monkeypatch):
    monkeypatch.delenv("KEYSTONE_DELEGATION_NUDGE_THRESHOLD", raising=False)
    assert hook_core.delegation_nudge_threshold() == 10
    monkeypatch.setenv("KEYSTONE_DELEGATION_NUDGE_THRESHOLD", "not-a-number")
    assert hook_core.delegation_nudge_threshold() == 10
    monkeypatch.setenv("KEYSTONE_DELEGATION_NUDGE_THRESHOLD", "-5")
    assert hook_core.delegation_nudge_threshold() == 10
    monkeypatch.setenv("KEYSTONE_DELEGATION_NUDGE_THRESHOLD", "25")
    assert hook_core.delegation_nudge_threshold() == 25


def test_delegation_ask_threshold_env_fallback_and_clamp(monkeypatch):
    monkeypatch.delenv("KEYSTONE_DELEGATION_NUDGE_THRESHOLD", raising=False)
    monkeypatch.delenv("KEYSTONE_DELEGATION_ASK_THRESHOLD", raising=False)
    assert hook_core.delegation_ask_threshold() == 20
    monkeypatch.setenv("KEYSTONE_DELEGATION_ASK_THRESHOLD", "not-a-number")
    assert hook_core.delegation_ask_threshold() == 20
    monkeypatch.setenv("KEYSTONE_DELEGATION_ASK_THRESHOLD", "-5")
    assert hook_core.delegation_ask_threshold() == 20
    monkeypatch.setenv("KEYSTONE_DELEGATION_ASK_THRESHOLD", "30")
    assert hook_core.delegation_ask_threshold() == 30
    # Clamped to at least the advisory threshold: an ask threshold configured below the
    # advisory one would be reachable before the advisory itself, which makes no sense.
    monkeypatch.setenv("KEYSTONE_DELEGATION_NUDGE_THRESHOLD", "50")
    monkeypatch.setenv("KEYSTONE_DELEGATION_ASK_THRESHOLD", "30")
    assert hook_core.delegation_ask_threshold() == 50


def test_delegation_nudge_graduates_to_ask_on_sustained_drift(monkeypatch, tmp_path):
    _nudge_setup(monkeypatch, tmp_path, threshold=2, ask_threshold=4)
    # Advisory fires once at the advisory threshold (regression).
    assert hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1") is None
    advisory = hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1")
    assert isinstance(advisory, HookResult)
    assert advisory.permission_decision is None
    assert "Delegation check" in advisory.additional_context
    # Silenced by the advisory marker while under the ask threshold.
    assert hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1") is None
    # At the ask threshold, a hard `ask` fires — with a non-empty reason — in an interactive
    # default-mode session.
    ask = hook_core.delegation_nudge_result(hook_core.READ_TOOL, "s1", permission_mode="default")
    assert isinstance(ask, HookResult)
    assert ask.permission_decision == "ask"
    assert ask.permission_reason
    assert "4 consecutive" in ask.permission_reason
    # Fires once per episode: the next call past the threshold is silenced by its own marker.
    assert hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1") is None
    # A subagent delegation clears BOTH markers, so a later drift can advise/ask again.
    assert hook_core.delegation_nudge_result(hook_core.SUBAGENT_TOOL, "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1") is None
    reprised_advisory = hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1")
    assert isinstance(reprised_advisory, HookResult)
    assert reprised_advisory.permission_decision is None


def test_delegation_nudge_ask_escalates_to_deny_outside_interactive_default(monkeypatch, tmp_path):
    # C31/D2-10: a background/child session (or any non-default permission_mode) was observed
    # to silently no-op a hook-forced `ask` — escalate to `deny` there instead.
    _nudge_setup(monkeypatch, tmp_path, threshold=2, ask_threshold=4)
    for _ in range(3):
        hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1")
    result = hook_core.delegation_nudge_result(hook_core.EDIT_TOOL, "s1", permission_mode="acceptEdits")
    assert isinstance(result, HookResult)
    assert result.permission_decision == "deny"
    assert "escalated ask" in result.permission_reason
    assert "4 consecutive" in result.permission_reason


# --------------------------------------------------------------------------------------
# system_message field (C21)
# --------------------------------------------------------------------------------------


def test_hook_result_with_system_message():
    result = HookResult(event_name="PreToolUse", system_message="[akmon] → k_explorer")
    assert result.system_message == "[akmon] → k_explorer"


def test_hook_result_system_message_is_optional():
    result = HookResult(event_name="SessionStart")
    assert result.system_message is None
