"""Unit tests for the vendor-neutral akmon hook logic (``hook_core``).

These cover the decision functions only — no vendor payload shapes (that is
``claude_adapter``'s job) and no live git (the commit guard takes an explicit ``branch``).

Run from the akmon root::

    python3 -m pytest tests
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import hook_core
import pytest
from hook_core import (
    HookResult,
    agent_names,
    analysis_write_result,
    commit_guard_decision,
    git_commit_guard_result,
    is_code_path,
    is_planning_doc,
    privilege_escalation_guard_result,
    role_on_code_result,
    session_start_result,
)

import common.jsondata as common_jsondata
from common.materialization import materialized_markdown

_AKMON = Path(__file__).resolve().parents[2]

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


def test_command_word_boundaries_are_ascii():
    # The JavaScript twin's ``\b`` is ASCII-only (C104), so a letter of another script is a boundary
    # in both: "ésudo" is a command word next to a stray letter, not one longer word.
    assert privilege_escalation_guard_result("ésudo ls") is not None
    assert privilege_escalation_guard_result("sudoé ls") is not None
    assert privilege_escalation_guard_result("sudo_x") is None
    # The same boundary for the commit guard: `βgit` is another word, so no git command is there.
    assert _guard("βgit push") is None
    assert _guard("git pushé") is None
    assert _guard("gitpush") is None


@pytest.mark.parametrize(
    "command",
    [
        "echo git-commit-guard",
        "python3 hooks/git-commit-guard.py --x",
        "cat .git/hooks/pre-push",
        "git add pre-commit-config.yaml",
        "my_git push",
        "git.exe push",
        "git log commit.md",
    ],
)
def test_a_name_that_holds_git_or_a_subcommand_is_not_a_command(command):
    # `git` and a subcommand are command words, not pieces of a file or hook name: a shell command that
    # only mentions `git-commit-guard` (an echo, a grep, the hook's own path) is not a commit.
    assert _guard(command, "/main") is None


@pytest.mark.parametrize("command", ["git commit-tree HEAD", "/usr/bin/git commit -m x"])
def test_a_subcommand_family_and_an_absolute_git_stay_guarded(command):
    assert _guard(command, "/main") is not None


def test_merge_base_is_not_a_merge():
    # It used to match as `merge` (the pattern allowed a hyphen after a subcommand); the subcommand is compared whole.
    assert _guard("git merge-base a b", "/main") is None


# --------------------------------------------------------------------------------------
# git_commit_guard_result (C190, ADR-0029/D09)
# --------------------------------------------------------------------------------------

_CASES = json.loads((_AKMON / "meta" / "conformance" / "units" / "commit_guard_cases.json").read_text(encoding="utf-8"))
_REPOSITORIES = {directory: hook_core.RepositoryFacts(**facts) for directory, facts in _CASES["repositories"].items()}


def _lookup(directory):
    return _REPOSITORIES.get(directory)


def _guard(command, start="/wt", **keywords):
    """The guard run as the session would at ``start``, with the shared table's repositories."""
    return commit_guard_decision(command, hook_core.RunFacts(directory=start, **keywords), _lookup)


def _label(case):
    return f"{case['start']}: {case['command']!r}"


@pytest.mark.parametrize("case", _CASES["scanner"], ids=_label)
def test_the_scanner_finds_the_git_commands_the_shared_table_lists(case):
    found = hook_core.git_invocations(case["command"], case["start"], home_directory=case["home"])
    assert [[item.subcommand, item.directory] for item in found] == case["expected"]


@pytest.mark.parametrize("case", _CASES["guard"], ids=_label)
def test_the_guard_decides_as_the_shared_table_says(case):
    result = _guard(
        case["command"],
        case["start"],
        permission_mode=case["mode"],
        attended=case["attended"],
        actor=case.get("actor", "developer"),
        run_branch=case.get("run_branch"),
    )
    if case["decision"] == "pass":
        assert result is None
        return
    assert result is not None
    assert result.permission_decision == case["decision"]
    for text in case["contains"]:
        assert text in result.permission_reason
    for text in case["absent"]:
        assert text not in result.permission_reason


def test_non_git_command_is_ignored():
    assert git_commit_guard_result("ls -la") is None
    assert git_commit_guard_result("python3 build.py") is None


def test_command_mentioning_git_without_a_guarded_subcommand_passes():
    assert _guard("git status", "/main") is None
    assert _guard("git diff --stat", "/main") is None


def test_co_authored_by_is_denied_case_insensitively():
    for command in (
        'git commit -m "x\n\nCo-Authored-By: Claude <noreply@anthropic.com>"',
        'git commit -m "co-authored-by: someone"',
    ):
        result = _guard(command)
        assert result is not None
        assert result.permission_decision == "deny"
        assert "Co-Authored-By" in result.permission_reason


@pytest.mark.parametrize("actor", ["developer", "autonomous"])
@pytest.mark.parametrize(
    "command",
    ['git commit -m "Co-Authored-By: Claude"', "gh pr create --body 'Co-Authored-By: Claude'"],
)
def test_the_trailer_floor_is_decided_before_and_without_the_access_matrix(monkeypatch, actor, command):
    # A matrix that would pass the trailer, or one that cannot be read, does not lift the deny.
    def unread_matrix(*_args, **_keywords):
        raise AssertionError("the trailer floor must not read the access matrix")

    monkeypatch.setattr(hook_core, "_Access", unread_matrix)
    monkeypatch.setattr(hook_core.access_matrix, "read_data", unread_matrix)
    result = _guard(command, "/main", actor=actor)
    assert result is not None
    assert result.permission_decision == "deny"
    assert "Co-Authored-By" in result.permission_reason


def test_co_authored_check_precedes_the_repository_check():
    # Even in a linked worktree (a commit would otherwise pass) the trailer is denied.
    result = _guard('git commit -m "Co-authored-by: x" ', "/wt")
    assert result is not None
    assert result.permission_decision == "deny"


def test_the_trailer_is_denied_in_a_heredoc_body_the_command_scan_skips():
    command = "git commit -F - <<'EOF'\nsubject\n\nCo-Authored-By: Claude\nEOF"
    assert hook_core.git_invocations(command, "/wt") == [hook_core.GitInvocation("commit", "/wt", ("-F", "-"))]
    result = _guard(command)
    assert result is not None
    assert result.permission_decision == "deny"


def test_a_heredoc_body_that_mentions_a_git_command_is_not_one():
    command = "cat <<'EOF'\nRun `git merge --squash feature` in the owner's checkout.\nEOF"
    assert _guard(command, "/main", permission_mode="default") is None


def test_a_quoted_argument_that_mentions_a_git_command_is_not_one():
    assert _guard("grep 'git merge' notes.md", "/main", permission_mode="default") is None
    assert _guard('echo "git push"', "/main", permission_mode="default") is None


def test_push_and_tag_ask_even_in_a_linked_worktree():
    for sub in ("push origin main", "tag v1"):
        result = _guard(f"git {sub}", "/wt", permission_mode="default")
        assert result is not None, sub
        assert result.permission_decision == "ask", sub
        assert "push and tag" in result.permission_reason


def test_a_commit_in_a_linked_worktree_passes_and_in_the_main_checkout_asks():
    heredoc = "git commit -m \"$(cat <<'EOF'\nsubject\n\nbody\nEOF\n)\""
    assert _guard(heredoc, "/wt", permission_mode="default") is None
    result = _guard(heredoc, "/main", permission_mode="default")
    assert result is not None
    assert result.permission_decision == "ask"
    assert "/main (not a linked worktree)" in result.permission_reason


def test_the_directory_the_command_acts_on_decides_not_the_session_directory():
    assert _guard("cd /wt && git commit -m x", "/main", permission_mode="default") is None
    assert _guard("git -C /wt commit -m x", "/main", permission_mode="default") is None
    assert _guard("git -C /main commit -m x", "/wt", permission_mode="default") is not None
    assert _guard("bash -c 'git merge x'", "/main", permission_mode="default") is not None


def test_a_commit_on_a_default_branch_or_a_detached_head_asks_in_a_worktree_too():
    for start, wording in (("/wt-main", "on 'main'"), ("/wt-master", "on 'master'"), ("/wt-detached", "detached HEAD")):
        result = _guard("git commit -m x", start, permission_mode="default")
        assert result is not None, start
        assert result.permission_decision == "ask"
        assert wording in result.permission_reason


def test_the_repository_is_asked_per_history_writing_invocation_with_its_directory():
    asked = []

    def lookup(directory):
        asked.append(directory)
        return _lookup(directory)

    commit_guard_decision(
        "git status && git push; cd /main && git commit -m y", hook_core.RunFacts(directory="/s"), lookup
    )
    assert asked == []  # the push decided before any commit was looked up
    commit_guard_decision(
        "cd /wt && git commit -m x && git status; git log", hook_core.RunFacts(directory="/s"), lookup
    )
    assert asked == ["/wt"]


def test_an_unresolvable_directory_asks_without_a_lookup():
    asked = []
    result = commit_guard_decision(
        'cd "$HOME/w" && git commit -m x', hook_core.RunFacts(directory="/wt", permission_mode="default"), asked.append
    )
    assert asked == []
    assert result is not None
    assert result.permission_decision == "ask"
    assert "cannot resolve" in result.permission_reason


def _git(cwd, *arguments):
    subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *arguments],
        check=True,
        capture_output=True,
        stdin=subprocess.DEVNULL,
    )


@pytest.fixture
def repositories(tmp_path):
    """A main checkout on ``main`` with a commit, a linked worktree on ``feat`` and a detached one."""
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q", "-b", "main")
    _git(main, "commit", "-q", "--allow-empty", "-m", "first")
    _git(main, "worktree", "add", "-q", "-b", "feat", str(tmp_path / "wt"))
    _git(main, "worktree", "add", "-q", "--detach", str(tmp_path / "detached"))
    (tmp_path / "plain").mkdir()
    return tmp_path


def test_repository_facts_reads_git_for_the_directory_it_is_given(repositories):
    facts = hook_core.RepositoryFacts
    assert hook_core.repository_facts(str(repositories / "main")) == facts(linked=False, branch="main")
    assert hook_core.repository_facts(str(repositories / "wt")) == facts(linked=True, branch="feat")
    assert hook_core.repository_facts(str(repositories / "detached")) == facts(linked=True, branch="")
    assert hook_core.repository_facts(str(repositories / "plain")) is None
    assert hook_core.repository_facts(str(repositories / "missing")) is None


def test_the_live_lookup_passes_a_worktree_and_asks_for_everything_else(repositories):
    def run(directory, command="git commit -m x"):
        return git_commit_guard_result(command, directory=str(directory), permission_mode="default")

    assert run(repositories / "wt") is None
    assert run(repositories / "wt", f"cd {repositories / 'main'} && git commit -m x") is not None
    assert run(repositories / "main") is not None
    assert run(repositories / "detached") is not None
    result = run(repositories / "plain")
    assert result is not None
    assert "not a git repository" in result.permission_reason
    assert run(repositories / "wt", "git -C . commit -m x") is None


def test_the_scanner_keeps_the_arguments_after_the_subcommand():
    found = hook_core.git_invocations("git -C /x branch -D 'a b' -- c", "/s")
    assert found == [hook_core.GitInvocation("branch", "/x", ("-D", "a b", "--", "c"))]


def test_the_scanner_marks_a_git_run_under_configuration_overrides():
    for command in (
        "git -c push.default=current push",
        "git --config-env push.default=V push",
        "git --config-env=a=B push",
    ):
        (found,) = hook_core.git_invocations(command, "/s")
        assert (found.subcommand, found.arguments, found.config_override) == ("push", (), True), command
    (plain,) = hook_core.git_invocations("git -C /x push origin x", "/s")
    assert plain.config_override is False


def test_the_scanner_keeps_every_word_after_api_options_included():
    (found,) = hook_core.git_invocations("gh -R o/r api -X POST repos/o/r/issues -f a=b", "/s")
    assert (found.program, found.subcommand, found.arguments) == (
        "gh",
        "api",
        ("-X", "POST", "repos/o/r/issues", "-f", "a=b"),
    )
    (action,) = hook_core.git_invocations("gh repo sync o/r", "/s")
    assert (action.subcommand, action.arguments) == ("repo sync", ("o/r",))


@pytest.fixture
def job_repositories(repositories):
    """The ``repositories`` with job branches, a branch ``other`` to try to move, and a worktree on a job branch."""
    main = repositories / "main"
    for branch in ("_aitna/a", "_aitna/b", "other"):
        _git(main, "branch", branch)
    _git(main, "worktree", "add", "-q", "-b", "_aitna/job", str(repositories / "job"))
    return repositories


_LIVE_ASKS = [
    "git branch -D other",
    "git branch -d other",
    "git branch -D _aitna/a other",
    "git branch -fD feat",
    "git branch --force other HEAD",
    "git branch -m other renamed",
    "git branch -M _aitna/a renamed",
    "git branch -m renamed",
    "git branch --copy other _aitna/c",
    "git fetch . HEAD:other",
    "git fetch . +HEAD:refs/heads/other",
    "git checkout -B other",
    "git switch -C other",
    "git switch --force-create other",
    "git symbolic-ref HEAD refs/heads/other",
    "git symbolic-ref -d refs/heads/other",
    "git update-ref refs/heads/other HEAD",
    "git update-ref -d refs/heads/other",
    "git replace HEAD HEAD~0",
    "git filter-branch --all",
    "git fast-import",
    "git worktree remove ../wt",
    "git worktree move ../wt ../elsewhere",
    "git worktree prune",
    "git worktree lock ../wt",
    "git worktree unlock ../wt",
    "git worktree repair",
]
_LIVE_PASSES = [
    "git branch -D _aitna/a",
    "git branch -d _aitna/a _aitna/b",
    "git branch -fD _aitna/a",
    "git branch -m _aitna/a _aitna/renamed",
    "git branch --copy _aitna/a _aitna/c",
    "git branch -m _aitna/renamed",
    "git branch brand-new HEAD",
    "git branch -u origin/main",
    "git fetch . HEAD:_aitna/a",
    "git fetch . HEAD:refs/remotes/origin/x",
    "git checkout -B _aitna/a",
    "git switch -C _aitna/a",
    "git checkout -b other-new",
    "git symbolic-ref HEAD",
    "git symbolic-ref HEAD refs/heads/_aitna/a",
    "git update-ref refs/heads/_aitna/a HEAD",
    "git update-ref -d refs/heads/_aitna/b",
    "git worktree list",
    'echo "git branch -D other"',
]


@pytest.mark.parametrize("directory", ["wt", "main", "job"])
@pytest.mark.parametrize("command", _LIVE_ASKS)
def test_ref_writing_commands_ask_in_a_real_repository_in_any_directory(job_repositories, directory, command):
    start = str(job_repositories / directory)
    result = git_commit_guard_result(command, directory=start, permission_mode="default")
    assert result is not None, command
    assert result.permission_decision == "ask"
    assert "_aitna/" in result.permission_reason


@pytest.mark.parametrize("directory", ["wt", "main", "job"])
@pytest.mark.parametrize("command", _LIVE_PASSES)
def test_job_branch_ref_commands_pass_in_a_real_repository_in_any_directory(job_repositories, directory, command):
    start = str(job_repositories / directory)
    if command == "git branch -m _aitna/renamed" and directory != "job":
        # the one-name rename acts on the current branch, which only the job worktree has as a job branch
        assert git_commit_guard_result(command, directory=start, permission_mode="default") is not None
        return
    assert git_commit_guard_result(command, directory=start, permission_mode="default") is None, command


def test_a_git_refusal_that_depends_on_the_checkout_is_not_what_the_guard_relies_on(job_repositories):
    """``other`` is checked out nowhere, so git itself would delete it; the guard asks all the same."""
    result = git_commit_guard_result(
        "git branch -D other", directory=str(job_repositories / "job"), permission_mode="default"
    )
    assert result is not None
    assert "'other'" in result.permission_reason


# --------------------------------------------------------------------------------------
# ask -> deny escalation for unattended sessions (C31/D2-10)
# --------------------------------------------------------------------------------------


def test_ask_escalates_to_deny_outside_interactive_default():
    for mode in (None, "acceptEdits", "plan", "dontAsk", "bypassPermissions", "somethingUnknown"):
        result = _guard("git commit -m 'x'", "/main", permission_mode=mode)
        assert result is not None, mode
        assert result.permission_decision == "deny", mode
        assert "escalated ask" in result.permission_reason, mode
        assert "/main" in result.permission_reason, mode  # original reason text preserved


# ADR-0025/D06: the host's attendance statement decides; the permission mode decides only where the
# host states nothing, and a mode that skips every question is never attended.
_ATTENDANCE_CELLS = [
    # (permission_mode, attended, the ask passes)
    ("auto", True, True),
    ("default", False, False),
    ("default", None, True),
    ("auto", None, False),
    ("bypassPermissions", True, False),
    ("dontAsk", True, False),
]


@pytest.mark.parametrize(("mode", "attended", "passes"), _ATTENDANCE_CELLS)
def test_ask_is_attended_by_the_host_statement_then_the_mode(mode, attended, passes):
    assert hook_core.ask_is_attended(mode, attended=attended) is passes


@pytest.mark.parametrize(("mode", "attended", "passes"), _ATTENDANCE_CELLS)
def test_commit_guard_ask_follows_attendance(mode, attended, passes):
    result = _guard("git push origin x", permission_mode=mode, attended=attended)
    assert result is not None
    assert result.permission_decision == ("ask" if passes else "deny")
    assert ("escalated ask" in result.permission_reason) is not passes
    if not passes:
        assert f"permission_mode={mode!r}" in result.permission_reason
        assert f"CLAUDE_CODE_SESSION_ATTENDED={'unset' if attended is None else int(attended)}" in (
            result.permission_reason
        )
        assert "ADR-0025/D06" in result.permission_reason


@pytest.mark.parametrize(("mode", "attended", "passes"), _ATTENDANCE_CELLS)
def test_delegation_ask_follows_attendance(monkeypatch, tmp_path, mode, attended, passes):
    _nudge_setup(monkeypatch, tmp_path, threshold=2, ask_threshold=4)
    for _ in range(3):
        hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1")
    result = hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1", permission_mode=mode, attended=attended)
    assert isinstance(result, HookResult)
    assert result.permission_decision == ("ask" if passes else "deny")


def test_the_core_never_reads_the_environment_for_attendance(monkeypatch):
    # Configuration is read at the entry point (ADR-0025/D06): the variable alone changes nothing here.
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "1")
    result = _guard("git push", permission_mode="auto")
    assert result is not None
    assert result.permission_decision == "deny"


def test_ask_stays_ask_in_interactive_default_mode():
    result = _guard('git commit -m "x"', "/main", permission_mode="default")
    assert result is not None
    assert result.permission_decision == "ask"
    assert "escalated" not in result.permission_reason


def test_escalation_does_not_touch_deny_decisions():
    # The co-authored-by guard is already a `deny` — escalation logic should leave it alone
    # (no double-escalation wording) regardless of permission_mode.
    result = _guard('git commit -m "Co-authored-by: x"', permission_mode="acceptEdits")
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


def test_agent_names_lists_the_shipped_agents_in_chain_order_then_the_rest_by_name(tmp_path):
    known = hook_core.agent_definitions()
    for name in ("release", "analyst", "learning", "development", "zeta"):
        _make_agent(tmp_path, name)
    assert agent_names(tmp_path, known) == ["development", "learning", "release", "analyst", "zeta"]


def test_agent_names_leaves_out_a_legacy_role_directory_whose_agent_has_its_own_charter(tmp_path):
    known = hook_core.agent_definitions()
    for name in ("development", "review", "architect", "engineer", "learn", "learning"):
        _make_agent(tmp_path, name)
    assert agent_names(tmp_path, known) == ["development", "learning"]


def test_agent_names_keeps_a_legacy_role_directory_whose_agent_has_no_charter_yet(tmp_path):
    known = hook_core.agent_definitions()
    for name in ("development", "review", "learn"):
        _make_agent(tmp_path, name)
    # `development/` owns review, architect and engineer; `learning/` is absent, so `learn/` stays listed
    assert agent_names(tmp_path, known) == ["development", "learn"]


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
    assert "agents and the roles they work in: architect — role architect; engineer — role engineer" in ctx
    assert "OPERATE (run/use from outside), agents and the roles they work in: options-analyst — role" in ctx
    assert "_aitna/memory/" in ctx


@pytest.mark.parametrize("breakage", ["not json", "missing", '{"styles": null}', "{}"])
def test_a_broken_work_style_file_loses_the_work_style_line_and_nothing_else(monkeypatch, tmp_path, breakage):
    _make_agent(tmp_path / "_aitna" / "agents", "architect")
    whole = session_start_result(tmp_path).additional_context
    assert "work style: delegating (default)" in whole
    broken = tmp_path / "work_style.json"
    if breakage != "missing":
        broken.write_text(breakage, encoding="utf-8")
    monkeypatch.setattr(hook_core.work_style, "read_data", lambda: common_jsondata.read(broken))
    if breakage == "not json":
        with pytest.raises(common_jsondata.DataFileError):
            hook_core.work_style.read_data()
    result = session_start_result(tmp_path)
    assert result is not None
    assert result.additional_context == "\n".join(line for line in whole.split("\n") if "work style:" not in line)


def test_a_work_style_failure_of_another_kind_is_not_swallowed(monkeypatch, tmp_path):
    _make_agent(tmp_path / "_aitna" / "agents", "architect")

    def unreadable():
        raise RuntimeError("not a data-file error")

    monkeypatch.setattr(hook_core.work_style, "read_data", unreadable)
    with pytest.raises(RuntimeError, match="not a data-file error"):
        session_start_result(tmp_path)


def test_session_start_recommends_only_the_role_declaration_form(tmp_path):
    # ADR 0027/D03: `🧭 role:` is the form the hooks recommend; `🧭 agent:` is read as an alias
    # but never printed in guidance.
    _make_agent(tmp_path / "_aitna" / "agents", "development")
    ctx = session_start_result(tmp_path).additional_context
    assert "🧭 role: <name> — <focus>" in ctx
    assert "🧭 agent:" not in ctx
    assert "agents and the roles they work in: development — roles review, architect, engineer" in ctx


def test_role_and_planning_guidance_recommend_only_the_role_declaration_form(monkeypatch, tmp_path):
    _isolate_marker_dir(monkeypatch, tmp_path)
    code = role_on_code_result(hook_core.edit_tool(), "src/alphavar/x.py", "session-A")
    planning = analysis_write_result(hook_core.edit_tool(), "_aitna/design/probe.md", "session-A", tmp_path / "repo")
    for result in (code, planning):
        assert result is not None
        assert "🧭 role: " in result.additional_context
        assert "🧭 agent:" not in result.additional_context


def test_session_start_reads_an_agent_as_its_roles_never_as_a_role_to_declare(tmp_path):
    agents = tmp_path / "_aitna" / "agents"
    _make_agent(agents, "development")
    (agents / "development" / "README.md").write_text(
        "## review\nRole of record: `roles/review.md`.\n## architect\n`_aitna/akmon/roles/architect.md`\n"
        "## engineer\n`roles/engineer.md` and again `roles/review.md`\n",
        encoding="utf-8",
    )
    _make_agent(agents, "release")  # a charter that names no role: the agent is its own role
    ctx = session_start_result(tmp_path).additional_context
    assert "development — roles review, architect, engineer; release — role release" in ctx
    assert "Pick by operation" in ctx or "Pick the role" in ctx
    assert "decompose an existing thing → review" in ctx


def test_agent_roles_follow_the_definitions_then_the_charter_then_the_agent_name(tmp_path):
    _make_agent(tmp_path, "learn")
    _make_agent(tmp_path, "development")
    (tmp_path / "development" / "README.md").write_text("see roles/README.md and roles/Review.md\n", encoding="utf-8")
    known = {"development": ["review", "architect", "engineer"], "learning": ["learn"]}
    # a named agent takes its definition's roles, whatever its charter says
    assert hook_core.agent_roles(tmp_path, "development", known) == ["review", "architect", "engineer"]
    assert hook_core.agent_roles(tmp_path, "learning", known) == ["learn"]
    # an agent no definition names keeps the charter fallback: its references, else its own name
    assert hook_core.agent_roles(tmp_path, "learn", known) == ["learn"]
    assert hook_core.agent_roles(tmp_path, "development", {}) == ["development"]
    assert hook_core.agent_roles(tmp_path, "missing", known) == ["missing"]
    (tmp_path / "learn" / "README.md").write_text("see `akmon/roles/review.md` and roles/learn.md\n", encoding="utf-8")
    assert hook_core.agent_roles(tmp_path, "learn", known) == ["review", "learn"]


def test_the_shipped_definitions_name_the_three_agents_and_their_roles():
    assert hook_core.agent_definitions() == {
        "development": ["review", "architect", "engineer"],
        "learning": ["learn"],
        "release": ["release"],
    }


def test_the_shipped_definitions_are_keyed_in_chain_order():
    assert list(hook_core.agent_definitions()) == ["development", "learning", "release"]


def test_session_start_names_the_roles_of_the_development_learning_and_release_agents(tmp_path):
    for agent in ("release", "learning", "development"):
        _make_agent(tmp_path / "_aitna" / "agents", agent)
    ctx = session_start_result(tmp_path).additional_context
    assert (
        "agents and the roles they work in: development — roles review, architect, engineer; "
        "learning — role learn; release — role release"
    ) in ctx  # agents list in name order, as `agent_names` sorts them


def test_session_start_lists_a_projects_own_agents_after_the_shipped_ones(tmp_path):
    for agent in ("release", "analyst", "development"):
        _make_agent(tmp_path / "_aitna" / "agents", agent)
    (tmp_path / "_aitna" / "agents" / "analyst" / "README.md").write_text("runs `roles/analyst.md`\n", encoding="utf-8")
    ctx = session_start_result(tmp_path).additional_context
    assert ("development — roles review, architect, engineer; release — role release; analyst — role analyst") in ctx


def test_session_start_does_not_list_a_legacy_role_directory_beside_its_agents_charter(tmp_path):
    for agent in ("development", "engineer", "review", "learn"):
        _make_agent(tmp_path / "_aitna" / "agents", agent)
    ctx = session_start_result(tmp_path).additional_context
    # `development/` replaces review/architect/engineer; `learning/` is absent, so `learn/` stays
    assert "development — roles review, architect, engineer; learn — role learn" in ctx
    assert "engineer — role" not in ctx
    assert "review — role" not in ctx


def test_a_legacy_learn_charter_directory_keeps_the_fallback_role(tmp_path):
    _make_agent(tmp_path / "_aitna" / "agents", "learn")
    ctx = session_start_result(tmp_path).additional_context
    assert "agents and the roles they work in: learn — role learn" in ctx


def test_the_shipped_agent_definition_files_are_not_operate_agents(tmp_path):
    # akmon runs on itself: its root `agents/` holds definition files and `agents.json`, not charters.
    desk = tmp_path / "agents"
    desk.mkdir()
    for name in ("README.md", "development.md", "release.md", "learning.md", "agents.json"):
        (desk / name).write_text("definition", encoding="utf-8")
    _make_agent(tmp_path / "_aitna" / "agents", "development")
    ctx = session_start_result(tmp_path).additional_context
    assert "OPERATE" not in ctx
    # a project's own runtime agent is still listed, and its role is its charter's, never a shipped agent's
    _make_agent(desk, "release")
    (desk / "release" / "README.md").write_text("runs `roles/analyst.md`\n", encoding="utf-8")
    ctx = session_start_result(tmp_path).additional_context
    assert "OPERATE (run/use from outside), agents and the roles they work in: release — role analyst" in ctx


def test_session_start_dev_only_omits_operate_line(tmp_path):
    _make_agent(tmp_path / "_aitna" / "agents", "engineer")
    result = session_start_result(tmp_path)
    assert result is not None
    assert "DEVELOP" in result.additional_context
    assert "OPERATE" not in result.additional_context


def test_session_start_none_when_no_agents(tmp_path):
    assert session_start_result(tmp_path) is None


def test_session_start_includes_develop_discriminator_when_dev_agents_exist(tmp_path):
    # A29: the routing rule (decompose→review · construct→architect · realize→engineer) is
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
    assert "Pick the role the task calls for, one of the roles listed above, never an agent name" in ctx


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
    path.write_text(materialized_markdown(text, root), encoding="utf-8")
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
    (mounted / "guardrails" / "_common.md").write_text("# Common\n\nmounted rule\n", encoding="utf-8")
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


def _default_project(tmp_path: Path) -> Path:
    """A fixture project with no ``.aitna-root``: its dev-layer root is the default ``_aitna``.

    akmon's own repository declares ``meta`` there, so a test that expects the default root
    must not classify against the working directory's project.
    """
    root = tmp_path / "repo"
    (root / "_aitna").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    return root


def _relocated_project(tmp_path: Path, name: str = "tools/ai") -> Path:
    """A fixture project whose ``.aitna-root`` declares ``name`` as the dev-layer root."""
    root = tmp_path / "repo"
    (root / name).mkdir(parents=True)
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (root / ".aitna-root").write_text(f"{name}\n", encoding="utf-8")
    return root


def test_is_code_path_true_for_source_extensions():
    assert is_code_path("src/alphavar/option_class.py")
    assert is_code_path("pkg/mod.ts")
    assert is_code_path("WEIRD/CASE.PY")  # case-insensitive


def test_is_code_path_false_for_non_code_extensions():
    assert not is_code_path("README.md")
    assert not is_code_path("notes.txt")
    assert not is_code_path("data.csv")


def test_is_code_path_false_for_excluded_segments(tmp_path):
    # Claude sends absolute file paths, so the segments are slash-delimited as designed.
    root = _default_project(tmp_path)
    assert not is_code_path(f"{root}/docs/dev/PROJECT_OVERVIEW.py", root)  # under /docs/
    assert not is_code_path(f"{root}/_aitna/akmon/hooks/hook_core.py", root)  # akmon itself
    assert not is_code_path(f"{root}/_aitna/memory/note.py", root)
    assert not is_code_path(f"{root}/.claude/settings.py", root)


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


@pytest.mark.parametrize("relative", _PATH_FORM_CORPUS)
def test_path_predicates_agree_on_relative_and_absolute_forms(tmp_path, relative):
    absolute = str(tmp_path / relative)
    assert is_code_path(relative, tmp_path) == is_code_path(absolute, tmp_path)
    assert is_planning_doc(relative, tmp_path) == is_planning_doc(absolute, tmp_path)


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


def test_path_predicates_reject_absolute_targets_outside_project(tmp_path):
    outside = tmp_path.parent / "_aitna" / "design" / "probe.md"
    assert not is_code_path(str(outside), tmp_path)
    assert not is_planning_doc(str(outside), tmp_path)


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
    relative = analysis_write_result(hook_core.edit_tool(), "_aitna/design/probe.md", "sess-rel", root)
    absolute = analysis_write_result(hook_core.edit_tool(), absolute_form, "sess-abs", root)
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
    assert role_on_code_result(hook_core.edit_tool(), "README.md", "s1") is None
    assert role_on_code_result(hook_core.edit_tool(), None, "s1") is None


def test_role_on_code_fires_once_per_session(monkeypatch, tmp_path):
    _isolate_marker_dir(monkeypatch, tmp_path)
    edit = hook_core.edit_tool()

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


def test_is_planning_doc_matches_backlog_and_design_docs(tmp_path):
    root = _default_project(tmp_path)
    assert is_planning_doc(f"{root}/_aitna/TASKS.md", root)
    assert is_planning_doc(f"{root}/_aitna/TASKS_ARCHIVE.md", root)
    assert is_planning_doc(f"{root}/_aitna/design/forecast/README.md", root)
    assert is_planning_doc(f"{root}/docs/dev/decisions/0003-x.md", root)
    assert is_planning_doc(f"{root}/docs/dev/ARCHITECTURE_REQUIREMENTS.md", root)
    assert is_planning_doc(f"{root}/_aitna/akmon/pipelines/tasks.md", root)


def test_is_planning_doc_rejects_code_and_unrelated_docs(tmp_path):
    root = _default_project(tmp_path)
    assert not is_planning_doc(f"{root}/src/alphavar/option_class.py", root)  # code
    assert not is_planning_doc(f"{root}/_aitna/akmon/hooks/hook_core.py", root)  # akmon code, not .md
    assert not is_planning_doc(f"{root}/README.md", root)  # top-level doc, not a planning root
    assert not is_planning_doc(f"{root}/_aitna/memory/note.md", root)  # memory is not a backlog/design doc


def test_analysis_write_ignores_non_edit_kinds(monkeypatch, tmp_path):
    _isolate_marker_dir(monkeypatch, tmp_path)
    root = _default_project(tmp_path)
    assert analysis_write_result("read", f"{root}/_aitna/TASKS.md", "s1", root) is None
    assert analysis_write_result("bash", f"{root}/_aitna/TASKS.md", "s1", root) is None


def test_analysis_write_ignores_non_planning_paths(monkeypatch, tmp_path):
    _isolate_marker_dir(monkeypatch, tmp_path)
    root = _default_project(tmp_path)
    assert analysis_write_result(hook_core.edit_tool(), f"{root}/src/alphavar/x.py", "s1", root) is None
    assert analysis_write_result(hook_core.edit_tool(), None, "s1", root) is None


def test_analysis_write_fires_once_per_session(monkeypatch, tmp_path):
    _isolate_marker_dir(monkeypatch, tmp_path)
    root = _default_project(tmp_path)
    edit = hook_core.edit_tool()

    first = analysis_write_result(edit, f"{root}/_aitna/TASKS.md", "session-A", root)
    assert isinstance(first, HookResult)
    assert first.event_name == "PreToolUse"
    assert "Analysis-before-mutation" in first.additional_context

    # same session → suppressed
    assert analysis_write_result(edit, f"{root}/_aitna/design/x.md", "session-A", root) is None

    # different session → fires again
    assert isinstance(analysis_write_result(edit, f"{root}/_aitna/TASKS.md", "session-B", root), HookResult)


def test_analysis_guard_and_role_on_code_are_disjoint(monkeypatch, tmp_path):
    # A code edit triggers role-on-code, not the analysis guard; a backlog edit, the reverse.
    _isolate_marker_dir(monkeypatch, tmp_path)
    root = _default_project(tmp_path)
    edit = hook_core.edit_tool()
    assert analysis_write_result(edit, f"{root}/src/alphavar/x.py", "s1", root) is None
    assert role_on_code_result(edit, f"{root}/_aitna/TASKS.md", "s2", root) is None


# --------------------------------------------------------------------------------------
# configurable dev-layer root (the `.aitna-root` declaration, ADR 0022 D09) — A4
# --------------------------------------------------------------------------------------


def test_aitna_root_resolvers_default_and_override(tmp_path):
    root = _default_project(tmp_path)
    assert hook_core.aitna_root_name(root) == "_aitna"
    assert hook_core.aitna_root(root) == root / "_aitna"
    (root / ".aitna-root").write_text("tools/ai\n", encoding="utf-8")
    assert hook_core.aitna_root_name(root) == "tools/ai"
    assert hook_core.aitna_root(root) == root / "tools" / "ai"


def test_runtime_root_display_is_project_relative_when_the_tree_is_in_the_repo(monkeypatch, tmp_path):
    """A mounted consumer executes the hook out of its own repository, so the spelling an agent
    is handed is the project-relative one it reads everywhere else."""
    mount = tmp_path / "_aitna" / "akmon"
    mount.mkdir(parents=True)
    monkeypatch.setattr(hook_core, "_TREE_ROOT", mount)
    assert hook_core.runtime_root_display(tmp_path) == "_aitna/akmon"


def test_runtime_root_display_uses_the_cli_when_the_tree_is_not_the_mount(tmp_path):
    """Mode ``package``: the tree is inside the installed wheel, so its literal path carries the
    venv's Python version and is wrong on the next bump. ``akmon path`` is spelled instead."""
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    assert hook_core.runtime_root_display(tmp_path) == "$(akmon path)"


def test_runtime_root_display_rejects_the_wheels_tree_inside_the_project_venv(monkeypatch, tmp_path):
    """The measured case, on a real package-mode consumer: the wheel's tree lives *under* the
    project root, at ``.venv/lib/python3.14/site-packages/akmon/_tree``. A containment test
    therefore succeeds and spells the venv's Python version into the recovery command — the one
    command a person runs when routing is already broken."""
    wheel_tree = tmp_path / ".venv" / "lib" / "python3.14" / "site-packages" / "akmon" / "_tree"
    wheel_tree.mkdir(parents=True)
    monkeypatch.setattr(hook_core, "_TREE_ROOT", wheel_tree)
    assert hook_core.runtime_root_display(tmp_path) == "$(akmon path)"


def test_is_code_path_excludes_custom_dev_root(tmp_path):
    root = _relocated_project(tmp_path)
    # the relocated dev tree is excluded from "code"...
    assert not is_code_path(f"{root}/tools/ai/akmon/hooks/hook_core.py", root)
    assert not is_code_path(f"{root}/tools/ai/memory/note.py", root)
    # ...and the old default path is now just ordinary code (the layer moved away from it)
    assert is_code_path(f"{root}/_aitna/akmon/hooks/hook_core.py", root)


def test_is_planning_doc_tracks_custom_dev_root(tmp_path):
    root = _relocated_project(tmp_path)
    assert is_planning_doc(f"{root}/tools/ai/TASKS.md", root)
    assert is_planning_doc(f"{root}/tools/ai/design/x.md", root)
    assert is_planning_doc(f"{root}/tools/ai/akmon/pipelines/tasks.md", root)
    # the default path no longer counts as the planning surface under the custom root
    assert not is_planning_doc(f"{root}/_aitna/TASKS.md", root)


def test_dev_root_declaration_is_read_from_the_project_root_not_the_working_directory(monkeypatch, tmp_path):
    """The root passed in decides: akmon's own checkout (declaring ``meta``) is the cwd here."""
    root = _default_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert not is_code_path(f"{root}/_aitna/memory/note.py", root)
    assert is_code_path(f"{root}/meta/memory/note.py", root)


def test_session_start_reads_custom_dev_root_agents(tmp_path):
    root = _relocated_project(tmp_path)
    agents = root / "tools" / "ai" / "agents" / "architect"
    agents.mkdir(parents=True)
    (agents / "README.md").write_text("# architect\n", encoding="utf-8")
    result = session_start_result(root)
    assert isinstance(result, HookResult)
    assert "architect" in result.additional_context
    assert "tools/ai/memory/" in result.additional_context  # memory hint tracks the root


# --------------------------------------------------------------------------------------
# delegation_nudge_result
# --------------------------------------------------------------------------------------


def _nudge_setup(monkeypatch, tmp_path, threshold=3, ask_threshold=None, grace=0):
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setenv("AKMON_DELEGATION_NUDGE_THRESHOLD", str(threshold))
    monkeypatch.setenv("AKMON_DELEGATION_GRACE", str(grace))
    if ask_threshold is not None:
        monkeypatch.setenv("AKMON_DELEGATION_ASK_THRESHOLD", str(ask_threshold))
    else:
        monkeypatch.delenv("AKMON_DELEGATION_ASK_THRESHOLD", raising=False)


def test_delegation_nudge_ignores_unrecognized_kinds(monkeypatch, tmp_path):
    _nudge_setup(monkeypatch, tmp_path, threshold=1)
    assert hook_core.delegation_nudge_result("something-else", "s1") is None
    assert hook_core.delegation_nudge_result("network", "s1") is None


def test_delegation_nudge_counts_a_read_as_half(monkeypatch, tmp_path):
    # Read/Grep/Glob normalize to hook_core.read_tool() and count toward the drift score — the
    # orchestrator "does everything" on reads and sweeps too — but at half an edit (C88/D2-46).
    _nudge_setup(monkeypatch, tmp_path, threshold=3)
    for _ in range(5):
        assert hook_core.delegation_nudge_result(hook_core.read_tool(), "s1") is None
    result = hook_core.delegation_nudge_result(hook_core.read_tool(), "s1")
    assert isinstance(result, HookResult)
    assert "drift score of 3" in result.additional_context


def test_delegation_nudge_suppressed_in_subagent(monkeypatch, tmp_path):
    # C28d: a subagent call (agent_id present in the payload) must never nudge or ask, even
    # well past both thresholds — k_* delegates have no Task tool to act on the reminder.
    _nudge_setup(monkeypatch, tmp_path, threshold=3, ask_threshold=5)
    for _ in range(25):
        assert hook_core.delegation_nudge_result(hook_core.read_tool(), "s1", is_subagent=True) is None


def test_delegation_nudge_subagent_calls_do_not_charge_counter(monkeypatch, tmp_path):
    # C28d: Claude Code shares session_id between the main chain and a subagent, so subagent
    # calls must not increment the shared counter. Precede a main-chain run with a pile of
    # subagent calls (all suppressed), then confirm the main chain still needs the full
    # advisory threshold before the first advisory fires.
    _nudge_setup(monkeypatch, tmp_path, threshold=3)
    for _ in range(12):
        assert hook_core.delegation_nudge_result(hook_core.read_tool(), "s1", is_subagent=True) is None

    threshold = hook_core.delegation_nudge_threshold()
    for _ in range(threshold - 1):
        assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1", is_subagent=False) is None
    result = hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1", is_subagent=False)
    assert isinstance(result, HookResult)
    assert f"drift score of {threshold}" in result.additional_context


def test_delegation_nudge_fires_once_without_delegation_between(monkeypatch, tmp_path):
    _nudge_setup(monkeypatch, tmp_path, threshold=3)
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.shell_tool(), "s1") is None
    result = hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1")
    assert isinstance(result, HookResult)
    assert "Delegation check" in result.additional_context
    assert "drift score of 3" in result.additional_context
    assert result.permission_decision is None  # advisory only, never blocks
    # Past the threshold in the same episode, with no delegation in between → silenced
    # by the marker, even as mutations keep piling up.
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    # A different session has its own counter and marker.
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s2") is None


def test_delegation_nudge_resets_on_subagent_delegation(monkeypatch, tmp_path):
    _nudge_setup(monkeypatch, tmp_path, threshold=3)
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    # Delegation resets the consecutive-mutation counter...
    assert hook_core.delegation_nudge_result(hook_core.subagent_tool(), "s1") is None
    # ...so the next two mutations stay under the threshold.
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is not None


def test_delegation_nudge_rearms_after_subagent_delegation(monkeypatch, tmp_path):
    _nudge_setup(monkeypatch, tmp_path, threshold=3)
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    first = hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1")
    assert isinstance(first, HookResult)
    # Silenced by the marker until a delegation happens.
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    # A subagent delegation resets the counter AND re-arms the reminder (removes the marker).
    assert hook_core.delegation_nudge_result(hook_core.subagent_tool(), "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    second = hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1")
    assert isinstance(second, HookResult)
    assert "Delegation check" in second.additional_context


def test_delegation_nudge_threshold_env_fallback(monkeypatch):
    monkeypatch.delenv("AKMON_DELEGATION_NUDGE_THRESHOLD", raising=False)
    assert hook_core.delegation_nudge_threshold() == 30
    monkeypatch.setenv("AKMON_DELEGATION_NUDGE_THRESHOLD", "not-a-number")
    assert hook_core.delegation_nudge_threshold() == 30
    monkeypatch.setenv("AKMON_DELEGATION_NUDGE_THRESHOLD", "-5")
    assert hook_core.delegation_nudge_threshold() == 30
    monkeypatch.setenv("AKMON_DELEGATION_NUDGE_THRESHOLD", "25")
    assert hook_core.delegation_nudge_threshold() == 25


def test_delegation_ask_threshold_env_fallback_and_clamp(monkeypatch):
    monkeypatch.delenv("AKMON_DELEGATION_NUDGE_THRESHOLD", raising=False)
    monkeypatch.delenv("AKMON_DELEGATION_ASK_THRESHOLD", raising=False)
    assert hook_core.delegation_ask_threshold() == 120
    monkeypatch.setenv("AKMON_DELEGATION_ASK_THRESHOLD", "not-a-number")
    assert hook_core.delegation_ask_threshold() == 120
    monkeypatch.setenv("AKMON_DELEGATION_ASK_THRESHOLD", "-5")
    assert hook_core.delegation_ask_threshold() == 120
    monkeypatch.setenv("AKMON_DELEGATION_ASK_THRESHOLD", "40")
    assert hook_core.delegation_ask_threshold() == 40
    # Clamped to at least the advisory threshold: an ask threshold configured below the
    # advisory one would be reachable before the advisory itself, which makes no sense.
    monkeypatch.setenv("AKMON_DELEGATION_NUDGE_THRESHOLD", "50")
    monkeypatch.setenv("AKMON_DELEGATION_ASK_THRESHOLD", "30")
    assert hook_core.delegation_ask_threshold() == 50


def test_delegation_nudge_graduates_to_ask_on_sustained_drift(monkeypatch, tmp_path):
    _nudge_setup(monkeypatch, tmp_path, threshold=2, ask_threshold=4)
    # Advisory fires once at the advisory threshold (regression).
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    advisory = hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1")
    assert isinstance(advisory, HookResult)
    assert advisory.permission_decision is None
    assert "Delegation check" in advisory.additional_context
    # Silenced by the advisory marker while under the ask threshold.
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    # At the ask threshold, a hard `ask` fires — with a non-empty reason — in an interactive
    # default-mode session.
    ask = hook_core.delegation_nudge_result(hook_core.shell_tool(), "s1", permission_mode="default")
    assert isinstance(ask, HookResult)
    assert ask.permission_decision == "ask"
    assert ask.permission_reason
    assert "drift score of 4" in ask.permission_reason
    # Fires once per episode: the next call past the threshold is silenced by its own marker.
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    # A subagent delegation clears BOTH markers, so a later drift can advise/ask again.
    assert hook_core.delegation_nudge_result(hook_core.subagent_tool(), "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    reprised_advisory = hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1")
    assert isinstance(reprised_advisory, HookResult)
    assert reprised_advisory.permission_decision is None


def test_delegation_nudge_ask_escalates_to_deny_outside_interactive_default(monkeypatch, tmp_path):
    # C31/D2-10: a background/child session (or any non-default permission_mode) was observed
    # to silently no-op a hook-forced `ask` — escalate to `deny` there instead.
    _nudge_setup(monkeypatch, tmp_path, threshold=2, ask_threshold=4)
    for _ in range(3):
        hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1")
    result = hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1", permission_mode="acceptEdits")
    assert isinstance(result, HookResult)
    assert result.permission_decision == "deny"
    assert "escalated ask" in result.permission_reason
    assert "drift score of 4" in result.permission_reason


def test_delegation_nudge_opening_calls_of_a_stretch_score_nothing(monkeypatch, tmp_path):
    # C88/D2-46: orientation is free — the first `grace` calls of a stretch add nothing, and a
    # delegation starts a new stretch with a new grace.
    _nudge_setup(monkeypatch, tmp_path, threshold=2, grace=3)
    for _ in range(4):
        assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is not None
    assert hook_core.delegation_nudge_result(hook_core.subagent_tool(), "s1") is None
    for _ in range(4):
        assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is not None


def test_delegation_nudge_read_never_carries_the_ask(monkeypatch, tmp_path):
    # C88/D2-46: past the ask threshold a read passes untouched — no ask, no deny, and the ask
    # is not spent on it — and the next edit or shell call carries it.
    _nudge_setup(monkeypatch, tmp_path, threshold=2, ask_threshold=4)
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is None
    assert hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1") is not None  # the advisory
    for _ in range(6):  # 2 → 5 on reads alone: past the ask threshold
        assert hook_core.delegation_nudge_result(hook_core.read_tool(), "s1", permission_mode="acceptEdits") is None
    denied = hook_core.delegation_nudge_result(hook_core.shell_tool(), "s1", permission_mode="acceptEdits")
    assert isinstance(denied, HookResult)
    assert denied.permission_decision == "deny"
    assert "drift score of 6" in denied.permission_reason


def test_delegation_grace_env_fallback(monkeypatch):
    monkeypatch.delenv("AKMON_DELEGATION_GRACE", raising=False)
    assert hook_core.delegation_grace() == 8
    monkeypatch.setenv("AKMON_DELEGATION_GRACE", "not-a-number")
    assert hook_core.delegation_grace() == 8
    monkeypatch.setenv("AKMON_DELEGATION_GRACE", "-1")
    assert hook_core.delegation_grace() == 8
    monkeypatch.setenv("AKMON_DELEGATION_GRACE", "0")
    assert hook_core.delegation_grace() == 0


def test_delegation_nudge_defaults_are_the_replayed_rule(monkeypatch):
    # C88/D2-46: the weights, the grace and the thresholds are the rule the replay chose
    # (M72, M73) — changing any of them is a new owner decision, not a tuning edit.
    for name in (
        "AKMON_DELEGATION_NUDGE_THRESHOLD",
        "AKMON_DELEGATION_ASK_THRESHOLD",
        "AKMON_DELEGATION_GRACE",
    ):
        monkeypatch.delenv(name, raising=False)
    assert hook_core._delegation_weights() == {
        hook_core.read_tool(): 0.5,
        hook_core.edit_tool(): 1.0,
        hook_core.shell_tool(): 1.0,
    }
    assert (
        hook_core.delegation_nudge_threshold(),
        hook_core.delegation_ask_threshold(),
        hook_core.delegation_grace(),
    ) == (30, 120, 8)


def test_delegation_nudge_reads_a_counter_written_by_the_previous_rule(monkeypatch, tmp_path):
    # A session that spans the upgrade finds a one-number counter; it reads as calls with no
    # score yet — neither a crash nor a fresh grace.
    _nudge_setup(monkeypatch, tmp_path, threshold=1, grace=5)
    (tmp_path / "akmon-delegation-nudge-s1.count").write_text("12", encoding="utf-8")
    result = hook_core.delegation_nudge_result(hook_core.edit_tool(), "s1")
    assert isinstance(result, HookResult)
    assert "drift score of 1" in result.additional_context


# --------------------------------------------------------------------------------------
# system_message field (C21)
# --------------------------------------------------------------------------------------


def test_hook_result_with_system_message():
    result = HookResult(event_name="PreToolUse", system_message="[akmon] → k_explorer")
    assert result.system_message == "[akmon] → k_explorer"


def test_hook_result_system_message_is_optional():
    result = HookResult(event_name="SessionStart")
    assert result.system_message is None


# --------------------------------------------------------------------------------------
# C102 — the policy tables and reminder texts live in hooks/hook_core.json beside the reader
# --------------------------------------------------------------------------------------


def test_hook_core_json_holds_the_policy_and_texts():
    data = hook_core._hook_core_data()
    assert set(data) == {
        "code_extensions",
        "non_code_segments",
        "planning_doc_segments",
        "planning_doc_files",
        "delegation",
        "interactive_default_permission_mode",
        "unattended_permission_modes",
        "unclassified_shell_route_notice",
        "session_start",
        "role_on_code_message",
        "analysis_before_mutation_message",
        "drift_score_text",
        "delegation_roster",
        "delegation_nudge_message",
        "delegation_ask_message",
        "privilege_escalation_reason",
        "git_commit_no_ai_trailer_reason",
        "git_commit_push_tag_merge_reason",
        "git_commit_history_reason",
        "git_commit_ref_reason",
        "git_commit_ref_target_current_branch",
        "git_commit_ref_target_stdin",
        "git_commit_guard_crash_reason",
        "git_commit_where_unresolved",
        "git_commit_where_not_repository",
        "git_commit_where_checkout",
        "git_commit_where_detached",
        "git_commit_where_default_branch",
        "git_commit_where_branch",
        "git_commit_where_not_run_branch",
        "git_commit_history_reason_autonomous",
        "git_push_own_branch_reason_autonomous",
        "git_push_own_branch_forced_reason_autonomous",
        "git_push_default_branch_reason_autonomous",
        "git_push_other_branch_reason_autonomous",
        "git_tag_reason_autonomous",
        "git_config_push_write_reason",
        "git_config_push_write_reason_autonomous",
        "gh_forge_write_other_reason",
        "gh_forge_write_other_reason_autonomous",
        "gh_pr_create_reason",
        "gh_pr_merge_reason",
        "gh_release_create_reason",
        "gh_pr_create_other_base_reason",
        "gh_pr_create_reason_autonomous",
        "gh_pr_create_other_base_reason_autonomous",
        "gh_publish_reason_autonomous",
        "access_reasons",
        "access_where",
        "git_publishing_subcommands",
        "git_push_valued_options",
        "git_push_long_flags",
        "git_push_all_target",
        "git_push_implicit_target",
        "git_push_config_target",
        "git_config_valued_options",
        "git_config_read_options",
        "git_config_key_write_options",
        "git_config_section_write_options",
        "git_config_edit_options",
        "git_config_actions",
        "git_config_push_keys",
        "git_config_edit_target",
        "gh_action_classes",
        "glab_action_classes",
        "forge_group_aliases",
        "forge_action_aliases",
        "forge_api_class",
        "forge_api_write_methods",
        "forge_api_method_options",
        "forge_api_field_options",
        "pr_base_options",
        "git_history_subcommands",
        "git_job_branch_prefix",
        "git_heads_prefix",
        "git_remotes_prefix",
        "git_ref_unconditional",
        "git_fetch_valued_options",
        "git_default_branches",
        "escalated_ask_suffix",
        "stale_guardrail_notice",
    }
    assert data["code_extensions"][:3] == [".py", ".pyi", ".ts"]
    assert data["code_extensions"][-2:] == [".m", ".mm"]
    assert data["delegation"] == {
        "nudge_threshold": 30,
        "nudge_threshold_env": "AKMON_DELEGATION_NUDGE_THRESHOLD",
        "ask_threshold": 120,
        "ask_threshold_env": "AKMON_DELEGATION_ASK_THRESHOLD",
        "grace": 8,
        "grace_env": "AKMON_DELEGATION_GRACE",
        "weights": {"read": 0.5, "edit": 1.0, "shell": 1.0},
    }
    assert data["interactive_default_permission_mode"] == "default"
    assert data["unattended_permission_modes"] == ["bypassPermissions", "dontAsk"]
    assert data["git_publishing_subcommands"] == ["push", "tag"]
    assert "commit" in data["git_history_subcommands"]
    assert "merge-base" not in data["git_history_subcommands"]
    assert data["git_default_branches"] == ["main", "master"]
    assert "🧭" in data["session_start"]["format_line"]
    assert "½" in data["drift_score_text"]


def test_hook_core_loader_reads_the_data_file_beside_it(monkeypatch):
    seen: list[Path] = []
    real_read = common_jsondata.read

    def capture(path: Path):
        seen.append(path)
        return real_read(path)

    monkeypatch.setattr(common_jsondata, "read", capture)
    hook_core.role_on_code_message()
    assert seen and all(path == Path(hook_core.__file__).parent / "hook_core.json" for path in seen)


def test_a_hook_core_data_file_error_propagates_uncaught(monkeypatch):
    def broken(path: Path):
        raise common_jsondata.DataFileError(f"akmon data file missing: {path}")

    monkeypatch.setattr(common_jsondata, "read", broken)
    with pytest.raises(common_jsondata.DataFileError, match="missing"):
        privilege_escalation_guard_result("sudo x")
