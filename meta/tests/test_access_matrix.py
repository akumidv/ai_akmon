"""The access matrix: the data file, the actor carrier and the guard's reading of both (ADR 0031/D07).

The JavaScript twin pins the same cases in ``js/common/access_matrix.test.mjs``; the decisions the
matrix gives the commit guard are the shared table ``meta/conformance/units/commit_guard_cases.json``.
"""

from __future__ import annotations

import copy

import hook_core
import pytest

from common import access_matrix, jsondata

DATA = access_matrix.read_data()
ROWS = access_matrix.actor_rows(DATA)
TEXTS = hook_core._hook_core_data()
HISTORY_CLASSES = sorted(name for name in DATA["developer"] if name.startswith("history_"))


def test_the_matrix_has_one_row_per_actor_and_every_row_the_same_classes():
    assert set(DATA) == {actor.value for actor in access_matrix.Actor} | {
        access_matrix.PROTECTED_BRANCHES_KEY,
        access_matrix.RUN_BRANCH_PATTERNS_KEY,
    }
    assert set(ROWS) == {actor.value for actor in access_matrix.Actor}
    classes = set(DATA["developer"])
    for actor, row in ROWS.items():
        assert set(row) == classes, actor
        assert set(row.values()) <= set(access_matrix.OUTCOMES), actor


def test_every_class_has_a_reason_text_and_every_history_class_a_where_text_for_each_actor():
    for actor, row in ROWS.items():
        assert set(TEXTS["access_reasons"][actor]) == set(row), actor
        assert set(TEXTS["access_where"][actor]) == set(HISTORY_CLASSES), actor
        for key in (*TEXTS["access_reasons"][actor].values(), *TEXTS["access_where"][actor].values()):
            assert isinstance(TEXTS[key], str), key


def test_the_developer_row_is_the_guard_before_the_matrix():
    # push and tag ask everywhere; history passes only in a linked worktree on a named branch; a ref write asks.
    row = DATA["developer"]
    assert {name: row[name] for name in HISTORY_CLASSES if row[name] == "allow"} == {"history_worktree_branch": "allow"}
    assert {row[name] for name in HISTORY_CLASSES} == {"allow", "ask"}
    for name in ("push_own_branch", "push_own_branch_forced", "push_default_branch", "push_other_branch", "tag"):
        assert row[name] == "ask", name
    assert row["ref_write"] == "ask"
    assert (row["pr_create"], row["pr_create_other_base"]) == ("ask", "ask")
    # git config and `gh api` passed before the matrix, and still do for the developer
    assert (row["config_push_write"], row["forge_write_other"]) == ("allow", "allow")
    assert row["ai_trailer"] == "deny"


def test_the_autonomous_row_is_the_run_branch_column():
    row = DATA["autonomous"]
    assert {name for name in HISTORY_CLASSES if row[name] == "allow"} == {
        "history_checkout_branch",
        "history_worktree_branch",
    }
    assert {row[name] for name in HISTORY_CLASSES} == {"allow", "deny"}
    assert row["push_own_branch"] == "allow"
    assert row["push_own_branch_forced"] == "ask"
    assert row["push_default_branch"] == row["push_other_branch"] == "deny"
    assert (row["tag"], row["ref_write"]) == ("ask", "ask")
    assert (row["pr_create"], row["pr_merge"], row["release_create"]) == ("allow", "ask", "ask")
    assert row["pr_create_other_base"] == "deny"
    assert (row["config_push_write"], row["forge_write_other"]) == ("deny", "ask")
    assert row["ai_trailer"] == "deny"


def test_develop_and_the_release_branches_are_protected_for_the_autonomous_actor_only():
    protected = DATA[access_matrix.PROTECTED_BRANCHES_KEY]
    assert protected == {"developer": [], "autonomous": ["develop", "release/*"]}
    assert access_matrix.protected_branches(DATA, access_matrix.Actor.AUTONOMOUS) == ("develop", "release/*")
    assert access_matrix.protected_branches(DATA, access_matrix.Actor.DEVELOPER) == ()


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({}, access_matrix.Actor.DEVELOPER),
        ({"AKMON_ACTOR": "developer"}, access_matrix.Actor.DEVELOPER),
        ({"AKMON_ACTOR": "autonomous"}, access_matrix.Actor.AUTONOMOUS),
        ({"AKMON_ACTOR": ""}, access_matrix.Actor.DEVELOPER),
        ({"AKMON_ACTOR": "guided"}, access_matrix.Actor.DEVELOPER),
        ({"AKMON_ACTOR": "Autonomous"}, access_matrix.Actor.DEVELOPER),
        ({"AKMON_ACTOR": " autonomous"}, access_matrix.Actor.DEVELOPER),
        ({"OTHER": "autonomous"}, access_matrix.Actor.DEVELOPER),
    ],
)
def test_the_actor_is_autonomous_only_for_that_exact_value(environ, expected):
    assert access_matrix.actor_from_environment(environ) is expected


def test_outcome_reads_the_row_and_the_class():
    assert access_matrix.outcome(DATA, access_matrix.Actor.AUTONOMOUS, "pr_create") == "allow"
    assert access_matrix.outcome(DATA, access_matrix.Actor.DEVELOPER, "pr_create") == "ask"


def test_a_hole_in_the_matrix_raises_instead_of_reading_as_permission():
    with pytest.raises(jsondata.DataFileError, match="no entry for actor 'autonomous', action 'nope'"):
        access_matrix.outcome(DATA, access_matrix.Actor.AUTONOMOUS, "nope")
    with pytest.raises(jsondata.DataFileError, match="no entry for actor 'developer'"):
        access_matrix.outcome({}, access_matrix.Actor.DEVELOPER, "tag")
    with pytest.raises(jsondata.DataFileError, match="is 'maybe'"):
        access_matrix.outcome({"developer": {"tag": "maybe"}}, access_matrix.Actor.DEVELOPER, "tag")


def test_the_guard_reads_the_outcomes_from_the_data_not_from_code(monkeypatch):
    # Flip one cell: the autonomous push of its own branch now asks; nothing else changed.
    flipped = {actor: {**row} for actor, row in DATA.items()}
    flipped["autonomous"]["push_own_branch"] = "ask"
    monkeypatch.setattr(access_matrix, "read_data", lambda: flipped)
    repositories = {"/wt": hook_core.RepositoryFacts(linked=True, branch="feat")}
    run = hook_core.RunFacts(
        actor=access_matrix.Actor.AUTONOMOUS, permission_mode="default", directory="/wt", run_branch="feat"
    )
    result = hook_core.commit_guard_decision("git push origin feat", run, repositories.get)
    assert result is not None
    assert result.permission_decision == "ask"
    assert "own branch 'feat'" in result.permission_reason


# --- D-C203-RUN-BRANCH: the autonomous actor's own branch --------------------------------------------------------


def test_the_autonomous_row_has_a_class_for_a_history_write_off_the_run_branch():
    assert DATA["autonomous"]["history_not_run_branch"] == "deny"
    # a developer never reaches the class (the guard asks the run branch of an autonomous run only); its cell
    # keeps the shape total and equals the developer's other checkout-branch outcome
    assert DATA["developer"]["history_not_run_branch"] == DATA["developer"]["history_checkout_branch"] == "ask"


def test_the_run_branch_patterns_are_per_actor_regexes_and_the_developer_has_none():
    patterns = DATA[access_matrix.RUN_BRANCH_PATTERNS_KEY]
    assert patterns["developer"] == []
    assert len(patterns["autonomous"]) == 1


@pytest.mark.parametrize(
    ("branch", "own"),
    [
        ("agent/C203-run", True),
        ("agent/C203", True),
        ("agent/C203/sub", True),
        ("agent/C203.1", True),
        ("agent/C203_x", True),
        ("agent/A76-x", True),
        ("agent/B15-y", True),
        ("agent/_T3-local", True),
        ("agent/_T3", True),
        ("agent/C1-x", True),
        ("agent/c203-x", False),
        ("agent/C203x", False),
        ("agent/CC203-x", False),
        ("agent/_T-x", False),
        ("agent/T3-x", True),  # `T3` is a task id (a letter and digits), like `C203`
        ("agent/fix-thing", False),
        ("agent/", False),
        ("agent", False),
        ("feat", False),
        ("x/agent/C203-run", False),
        ("agent/C203-run\nx", True),  # only the start of the name is read
        ("main", False),
        ("", False),
    ],
)
def test_a_branch_under_agent_starting_with_a_task_id_is_the_autonomous_run_branch(branch, own):
    assert access_matrix.is_own_branch(DATA, access_matrix.Actor.AUTONOMOUS, branch, None) is own


@pytest.mark.parametrize("branch", ["agent/C203-run", "feat", "anything", "agent/fix"])
def test_a_named_run_branch_is_the_only_own_branch_for_an_autonomous_run(branch):
    autonomous = access_matrix.Actor.AUTONOMOUS
    assert access_matrix.is_own_branch(DATA, autonomous, branch, branch) is True
    assert access_matrix.is_own_branch(DATA, autonomous, "agent/C203-run", "feat") is False  # exact, not a pattern
    assert access_matrix.is_own_branch(DATA, autonomous, "feat/sub", "feat") is False


@pytest.mark.parametrize("run_branch", [None, "feat", "agent/C203-run"])
def test_every_branch_is_a_developers_own(run_branch):
    assert access_matrix.is_own_branch(DATA, access_matrix.Actor.DEVELOPER, "whatever", run_branch) is True


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({}, None),
        ({"AKMON_RUN_BRANCH": ""}, None),
        ({"AKMON_RUN_BRANCH": "agent/C203-run"}, "agent/C203-run"),
        ({"AKMON_RUN_BRANCH": " agent/x"}, " agent/x"),  # the name is exact: nothing is trimmed
        ({"OTHER": "agent/C203-run"}, None),
    ],
)
def test_the_run_branch_is_the_environment_value_when_set(environ, expected):
    assert access_matrix.run_branch_from_environment(environ) == expected


@pytest.mark.parametrize(
    ("names", "branch", "protected"),
    [
        (["develop"], "develop", True),
        (["develop"], "develop2", False),
        (["develop"], "develop/x", False),
        (["release/*"], "release/1.0", True),
        (["release/*"], "release/", True),
        (["release/*"], "release", False),
        (["release/*"], "releases/1", False),
        (["release/*"], "x/release/1", False),
        (["*"], "anything", True),
        (["a*b"], "axb", False),  # a glob is a trailing `*` only
        ([], "develop", False),
    ],
)
def test_a_protected_name_is_exact_or_a_prefix_when_it_ends_in_a_star(names, branch, protected):
    assert access_matrix.is_protected_branch(names, branch) is protected


@pytest.mark.parametrize(
    "broken",
    [
        None,
        [],
        {"developer": []},
        {"developer": [], "autonomous": "^agent/"},
        {"developer": [], "autonomous": [1]},
        {"developer": [], "autonomous": [""]},
        {"developer": None, "autonomous": ["^agent/"]},
        {"developer": [], "autonomous": ["(unclosed"]},
    ],
)
def test_read_data_refuses_run_branch_patterns_of_the_wrong_shape(monkeypatch, broken):
    mangled = copy.deepcopy(DATA)
    if broken is None:
        del mangled[access_matrix.RUN_BRANCH_PATTERNS_KEY]
    else:
        mangled[access_matrix.RUN_BRANCH_PATTERNS_KEY] = broken
    monkeypatch.setattr(access_matrix.jsondata, "read", lambda _path: mangled)
    with pytest.raises(jsondata.DataFileError, match="run_branch_patterns"):
        access_matrix.read_data()


def test_the_guard_reads_the_run_branch_patterns_from_the_data_not_from_code(monkeypatch):
    changed = copy.deepcopy(DATA)
    changed[access_matrix.RUN_BRANCH_PATTERNS_KEY]["autonomous"] = ["^bot/"]
    monkeypatch.setattr(access_matrix, "read_data", lambda: changed)
    repositories = {
        "/bot": hook_core.RepositoryFacts(linked=False, branch="bot/x"),
        "/agent": hook_core.RepositoryFacts(linked=False, branch="agent/C203-x"),
    }
    autonomous = hook_core.RunFacts(actor=access_matrix.Actor.AUTONOMOUS, permission_mode="default")

    def guard(command, start):
        run = hook_core.RunFacts(actor=autonomous.actor, permission_mode="default", directory=start)
        return hook_core.commit_guard_decision(command, run, repositories.get)

    assert guard("git commit -m x", "/bot") is None
    assert guard("git push origin bot/x", "/bot") is None
    assert guard("git commit -m x", "/agent").permission_decision == "deny"


def test_a_developer_never_reaches_the_run_branch_class(monkeypatch):
    # Soften the class for every actor; a developer's outcome on a checkout branch is the class it had before.
    changed = copy.deepcopy(DATA)
    changed["developer"]["history_not_run_branch"] = "deny"
    monkeypatch.setattr(access_matrix, "read_data", lambda: changed)
    repositories = {"/clone": hook_core.RepositoryFacts(linked=False, branch="feat")}
    run = hook_core.RunFacts(actor=access_matrix.Actor.DEVELOPER, permission_mode="default", directory="/clone")
    result = hook_core.commit_guard_decision("git commit -m x", run, repositories.get)
    assert result.permission_decision == "ask"
    assert "not the run's own branch" not in result.permission_reason


def test_a_developer_push_asks_the_repository_nothing():
    asked = []

    def lookup(directory):
        asked.append(directory)

    hook_core.commit_guard_decision("git push origin feat", hook_core.RunFacts(directory="/wt"), lookup)
    assert asked == []


def test_an_unknown_actor_string_is_refused_where_the_guard_is_called_directly():
    with pytest.raises(ValueError, match="guided"):
        hook_core.commit_guard_decision("git push", hook_core.RunFacts(actor="guided", directory="/wt"), lambda _: None)


def test_gh_invocations_carry_their_program_and_group_action():
    found = hook_core.git_invocations("git push && cd /w && gh -R o/r pr create --fill", "/s")
    assert [(item.program, item.subcommand, item.directory) for item in found] == [
        ("git", "push", "/s"),
        ("gh", "pr create", "/w"),
    ]
    assert found[1].arguments == ("--fill",)
    assert hook_core.GitInvocation("status", "/s").program == "git"


def test_gh_and_glab_invocations_carry_their_program_and_group_action():
    found = hook_core.git_invocations("glab -R o/r mr create -b develop && /usr/bin/glab mr merge 3", "/s")
    assert [(item.program, item.subcommand, item.arguments) for item in found] == [
        ("glab", "mr create", ("-b", "develop")),
        ("glab", "mr merge", ("3",)),
    ]


def test_the_shipped_matrix_passes_the_trailer_floor():
    access_matrix.check_trailer_floor(DATA)
    assert all(row[access_matrix.AI_TRAILER_CLASS] == "deny" for row in ROWS.values())


@pytest.mark.parametrize("cell", ["allow", "ask", None])
def test_read_data_refuses_a_matrix_whose_trailer_cell_is_not_deny_for_any_actor(monkeypatch, cell):
    for actor in ("developer", "autonomous"):
        softened = copy.deepcopy(DATA)
        if cell is None:
            del softened[actor][access_matrix.AI_TRAILER_CLASS]
        else:
            softened[actor][access_matrix.AI_TRAILER_CLASS] = cell
        monkeypatch.setattr(access_matrix.jsondata, "read", lambda _path, data=softened: data)
        with pytest.raises(jsondata.DataFileError, match=f"'{actor}'/'ai_trailer'"):
            access_matrix.read_data()


@pytest.mark.parametrize(
    "broken",
    [
        None,
        [],
        {"developer": []},
        {"developer": [], "autonomous": "develop"},
        {"developer": [], "autonomous": [1]},
        {"developer": [], "autonomous": [""]},
        {"developer": None, "autonomous": ["develop"]},
    ],
)
def test_read_data_refuses_a_protected_branches_of_the_wrong_shape(monkeypatch, broken):
    mangled = copy.deepcopy(DATA)
    if broken is None:
        del mangled[access_matrix.PROTECTED_BRANCHES_KEY]
    else:
        mangled[access_matrix.PROTECTED_BRANCHES_KEY] = broken
    monkeypatch.setattr(access_matrix.jsondata, "read", lambda _path: mangled)
    with pytest.raises(jsondata.DataFileError, match="protected_branches"):
        access_matrix.read_data()


def test_the_guard_reads_the_protected_branches_from_the_data_not_from_code(monkeypatch):
    changed = copy.deepcopy(DATA)
    changed[access_matrix.PROTECTED_BRANCHES_KEY] = {"developer": ["feat"], "autonomous": ["release"]}
    monkeypatch.setattr(access_matrix, "read_data", lambda: changed)
    repositories = {
        "/wt": hook_core.RepositoryFacts(linked=True, branch="feat"),
        "/rel": hook_core.RepositoryFacts(linked=True, branch="release"),
        "/dev": hook_core.RepositoryFacts(linked=True, branch="develop"),
    }
    autonomous = access_matrix.Actor.AUTONOMOUS

    def guard(command, start, actor):
        run = hook_core.RunFacts(actor=actor, permission_mode="default", directory=start)
        return hook_core.commit_guard_decision(command, run, repositories.get)

    assert guard("git commit -m x", "/rel", autonomous).permission_decision == "deny"
    assert guard("git push origin release", "/wt", autonomous).permission_decision == "deny"
    assert guard("git commit -m x", "/dev", autonomous) is None  # develop is no longer protected
    # a developer's protected branch counts the same way: the matrix names it, the guard obeys
    assert guard("git commit -m x", "/wt", access_matrix.Actor.DEVELOPER).permission_decision == "ask"


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("gh pr create --fill", None),
        ("gh pr create --base develop", "develop"),
        ("gh pr create --base=develop", "develop"),
        ("gh pr create -B develop", "develop"),
        ("gh pr create -Bdevelop", "develop"),
        ("gh pr create --base", ""),
        ("gh pr create -b develop", None),  # gh's -b is the body
        ("glab mr create -b develop", "develop"),
        ("glab mr create --target-branch=develop", "develop"),
        ("glab mr create --base develop", None),  # not a glab option
    ],
)
def test_the_pull_request_base_is_read_from_the_programs_own_options(command, expected):
    [invocation] = hook_core.git_invocations(command, "/s")
    assert hook_core._pull_request_base(invocation, TEXTS) == expected
