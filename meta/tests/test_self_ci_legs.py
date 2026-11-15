"""Tests for ``meta/self_ci_legs.py``: which self-CI legs a set of changed paths selects.

The table (``meta/self_ci_legs.json``) is data a skip depends on, so what is pinned here is the
safety rule — a leg is skipped only when no changed path matches it, and an unknown path runs every
leg — and that the table cannot drift from the legs ``self_ci`` runs or from the corpus snapshot.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import subprocess
import sys
from pathlib import Path

import pytest
import self_ci
import self_ci_legs

_AKMON = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def table() -> self_ci_legs.LegTable:
    return self_ci_legs.read_leg_table()


def _selected(table: self_ci_legs.LegTable, *paths: str) -> frozenset[str]:
    return table.select(list(paths)).legs


def test_every_leg_declares_the_paths_it_reads(table):
    assert set(table.legs) == set(self_ci.LEG_IDS)
    for leg, patterns in table.legs.items():
        assert patterns, f"leg {leg} declares no paths, so nothing could ever select it"


def test_the_legs_run_guards_name_exactly_the_declared_legs():
    """``self_ci`` skips a leg with ``"<id>" in selected``; every such id is a declared leg and none is missing."""
    guarded = {
        node.left.value
        for node in ast.walk(ast.parse(inspect.getsource(self_ci)))
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Constant)
        and isinstance(node.ops[0], ast.In)
        and isinstance(node.comparators[0], ast.Name)
        and node.comparators[0].id == "selected"
    }
    assert guarded == set(self_ci.LEG_IDS)


@pytest.mark.parametrize("changed", (None, [], ["."], [".", "js/akmon/cli.mjs"]))
def test_a_full_run_selects_every_leg(table, changed):
    selection = table.select(changed)
    assert selection.legs == set(self_ci.LEG_IDS)
    assert selection.full
    assert selection.skipped == ()


def test_an_unknown_path_selects_every_leg(table):
    selection = table.select(["some/new/place/file.xyz"])
    assert selection.legs == set(self_ci.LEG_IDS)
    assert "no leg declares it" in selection.reasons["js-lint"]


def test_one_unknown_path_overrides_an_otherwise_narrow_change(table):
    assert _selected(table, "docs/design/x.md", "mystery.bin") == set(self_ci.LEG_IDS)


@pytest.mark.parametrize(
    "path",
    (
        "meta/TASKS_ARCHIVE.md",
        "meta/MEASUREMENTS.md",
        "meta/reviews/alternatives/README.md",
        "meta/experiments/README.md",
        "meta/tests/test_init.py",
        "docs/design/roadmap-view.md",
        "docs/adr/README.md",
    ),
)
def test_a_path_no_leg_reads_selects_nothing(table, path):
    selection = table.select([path])
    assert selection.legs == frozenset()
    assert set(selection.skipped) == set(self_ci.LEG_IDS)


def test_the_backlog_and_the_adrs_select_only_the_decision_record_check(table):
    assert _selected(table, "meta/TASKS.md") == {"decision-records"}
    assert _selected(table, "docs/adr/0031-work-styles-delegating-and-controlling.md") == {"decision-records"}


def test_a_javascript_source_selects_the_js_legs_and_what_runs_the_js(table):
    selected = _selected(table, "js/akmon/cli.mjs")
    assert {"js-typecheck", "js-unit", "js-lint", "js-format", "corpus", "corpus-node", "fuzz"} <= selected
    assert {"fixture", "wheel-smoke", "npm-smoke", "runtime"} <= selected
    assert not selected & {"js-deps", "always-loaded", "capabilities", "canary", "decision-records"}


def test_a_lockfile_selects_the_install_and_the_toolchain_but_not_the_corpus(table):
    selected = _selected(table, "package-lock.json")
    assert {"js-deps", "js-typecheck", "js-lint", "js-format", "npm-smoke"} <= selected
    assert not selected & {"corpus", "corpus-node", "fuzz", "canary", "decision-records"}


def test_shipped_prose_skips_the_js_toolchain_and_the_corpora(table):
    selected = _selected(table, "guardrails/_common.md")
    assert {"fixture", "wheel-smoke", "npm-smoke", "always-loaded", "canary", "js-unit"} <= selected
    assert not selected & {"js-deps", "js-typecheck", "js-lint", "js-format", "corpus", "corpus-node", "fuzz"}


def test_the_selfci_files_select_every_leg(table):
    assert _selected(table, "meta/self_ci.py") == set(self_ci.LEG_IDS)
    assert _selected(table, "meta/self_ci_legs.json") == set(self_ci.LEG_IDS)


def test_the_glob_dialect():
    assert self_ci_legs.path_matches("README.md", ["*.md"])
    assert not self_ci_legs.path_matches("docs/README.md", ["*.md"])
    assert self_ci_legs.path_matches("a.mjs", ["**/*.mjs"])
    assert self_ci_legs.path_matches("a/b/c.mjs", ["**/*.mjs"])
    assert self_ci_legs.path_matches("js/a/b.mjs", ["js/**"])
    assert not self_ci_legs.path_matches("jsx/a.mjs", ["js/**"])
    assert self_ci_legs.path_matches("docs/adr/0031-x.md", ["docs/adr/[0-9][0-9][0-9][0-9]-*.md"])
    assert not self_ci_legs.path_matches("docs/adr/README.md", ["docs/adr/[0-9][0-9][0-9][0-9]-*.md"])


def test_an_undeclared_set_reference_is_refused(tmp_path):
    path = tmp_path / "legs.json"
    path.write_text('{"sets": {}, "always": [], "no_leg": [], "legs": {"x": ["@missing"]}}', encoding="utf-8")
    with pytest.raises(self_ci_legs.jsondata.DataFileError, match="@missing"):
        self_ci_legs.read_leg_table(path)


def test_the_report_names_every_leg_that_ran_or_was_skipped(table):
    lines = self_ci_legs.report_lines(table.select(["meta/TASKS.md"]))
    assert "self-ci: run decision-records — meta/TASKS.md" in lines
    skipped = [line for line in lines if line.startswith("self-ci: skip ")]
    assert len(skipped) == len(self_ci.LEG_IDS) - 1
    assert self_ci_legs.report_lines(table.select(None)) == ["self-ci: full run, every leg"]
    assert any("nothing to run" in line for line in self_ci_legs.report_lines(table.select(["docs/x.md"])))


def _fake_run(seen):
    def fake_run(akmon_root, fuzz_depth, selected):
        seen["selected"] = selected
        return []

    return fake_run


def test_main_prints_the_selection_even_when_quiet_and_runs_only_the_selected_legs(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(self_ci, "_run", _fake_run(seen))
    assert self_ci.main(["--quiet", "meta/TASKS.md"]) == 0
    assert seen["selected"] == {"decision-records"}
    out = capsys.readouterr().out
    assert "self-ci: change set: paths given (1)" in out
    assert "self-ci: run decision-records" in out
    assert "self-ci: skip js-unit" in out
    assert self_ci.main(["--quiet", "."]) == 0
    assert seen["selected"] == set(self_ci.LEG_IDS)


def test_main_without_paths_reads_the_change_set_from_git(monkeypatch, capsys, tmp_path):
    seen = {}
    monkeypatch.setattr(self_ci, "_run", _fake_run(seen))
    monkeypatch.setattr(self_ci, "_AKMON_ROOT", _git_repo(tmp_path))
    (tmp_path / "meta" / "TASKS.md").write_text("changed\n", encoding="utf-8")
    assert self_ci.main(["--quiet"]) == 0
    assert seen["selected"] == {"decision-records"}
    assert "self-ci: change set: git (1 changed paths)" in capsys.readouterr().out


def test_main_on_a_clean_tree_is_a_full_run(monkeypatch, capsys, tmp_path):
    seen = {}
    monkeypatch.setattr(self_ci, "_run", _fake_run(seen))
    monkeypatch.setattr(self_ci, "_AKMON_ROOT", _git_repo(tmp_path))
    assert self_ci.main(["--quiet"]) == 0
    assert seen["selected"] == set(self_ci.LEG_IDS)
    out = capsys.readouterr().out
    assert "self-ci: change set: git: clean tree, full run" in out
    assert "deferred" not in out


def test_main_full_runs_every_leg_even_on_a_dirty_tree_and_takes_no_paths(monkeypatch, capsys, tmp_path):
    seen = {}
    monkeypatch.setattr(self_ci, "_run", _fake_run(seen))
    monkeypatch.setattr(self_ci, "_AKMON_ROOT", _git_repo(tmp_path))
    (tmp_path / "meta" / "TASKS.md").write_text("changed\n", encoding="utf-8")
    assert self_ci.main(["--quiet", "--full"]) == 0
    assert seen["selected"] == set(self_ci.LEG_IDS)
    assert "self-ci: change set: full run (--full)" in capsys.readouterr().out
    with pytest.raises(SystemExit) as refused:
        self_ci.main(["--full", "meta/TASKS.md"])
    assert refused.value.code == 2


def test_main_names_a_git_failure_in_one_line(monkeypatch, tmp_path):
    monkeypatch.setattr(self_ci, "_AKMON_ROOT", tmp_path)  # not a git repository
    with pytest.raises(SystemExit) as refused:
        self_ci.main(["--quiet"])
    assert str(refused.value).startswith("self-ci: cannot read the change set from git:")


def test_the_slowest_legs_are_marked_full_only_in_the_data(table):
    assert set(table.full_only) == {"fuzz", "corpus-node"}
    assert set(table.full_only) <= set(table.legs)


def test_a_full_only_leg_is_deferred_in_a_pre_commit_selection_and_runs_in_a_full_one(table):
    selection = table.select(["js/akmon/cli.mjs"], defer_full_only=True)
    assert set(selection.deferred) == {"fuzz", "corpus-node"}
    assert not selection.legs & set(selection.deferred)
    assert not set(selection.skipped) & set(selection.deferred)
    assert {"js-unit", "corpus"} <= selection.legs
    assert table.select(["js/akmon/cli.mjs"]).legs == set(self_ci.LEG_IDS) - set(selection.skipped) - {"js-deps"}
    full = table.select(None, defer_full_only=True)
    assert full.deferred == () and full.legs == set(self_ci.LEG_IDS)


def test_a_full_only_leg_no_path_selects_is_skipped_not_deferred(table):
    selection = table.select(["meta/TASKS.md"], defer_full_only=True)
    assert selection.deferred == ()
    assert {"fuzz", "corpus-node"} <= set(selection.skipped)


def test_the_report_has_one_deferred_line_per_deferred_leg(table):
    lines = self_ci_legs.report_lines(table.select(["js/akmon/cli.mjs"], defer_full_only=True))
    assert "self-ci: fuzz: deferred to the full run / CI" in lines
    assert "self-ci: corpus-node: deferred to the full run / CI" in lines
    assert len([line for line in lines if "deferred" in line]) == 2
    assert not any(line.startswith("self-ci: run fuzz") for line in lines)


def test_main_defers_the_full_only_legs_for_paths_and_runs_them_in_a_full_run(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(self_ci, "_run", _fake_run(seen))
    assert self_ci.main(["--quiet", "js/akmon/cli.mjs"]) == 0
    assert not seen["selected"] & {"fuzz", "corpus-node"}
    assert "self-ci: fuzz: deferred to the full run / CI" in capsys.readouterr().out
    assert self_ci.main(["--quiet", "--full"]) == 0
    assert {"fuzz", "corpus-node"} <= seen["selected"]


def test_an_unknown_full_only_leg_is_refused(tmp_path):
    path = tmp_path / "legs.json"
    path.write_text(
        '{"sets": {}, "always": [], "no_leg": [], "full_only": ["nope"], "legs": {"x": ["a"]}}', encoding="utf-8"
    )
    with pytest.raises(self_ci_legs.jsondata.DataFileError, match="nope"):
        self_ci_legs.read_leg_table(path)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def _git_repo(root: Path) -> Path:
    """A throwaway repository holding one committed file per place the tests change."""
    _git(root, "init", "-q")
    (root / "meta").mkdir()
    (root / "meta" / "TASKS.md").write_text("tasks\n", encoding="utf-8")
    (root / "README.md").write_text("readme\n", encoding="utf-8")
    (root / "kept.txt").write_text("a longer text that a rename keeps similar enough\n" * 5, encoding="utf-8")
    (root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def test_the_git_change_set_of_a_clean_tree_is_empty(tmp_path):
    assert self_ci_legs.git_changed_paths(_git_repo(tmp_path)) == []


def test_the_git_change_set_holds_staged_unstaged_untracked_and_dev_layer_paths(tmp_path):
    repo = _git_repo(tmp_path)
    (repo / "meta" / "TASKS.md").write_text("edited\n", encoding="utf-8")  # unstaged, the dev layer
    (repo / "README.md").write_text("edited\n", encoding="utf-8")
    _git(repo, "add", "README.md")  # staged
    (repo / "meta" / "new_check.py").write_text("x = 1\n", encoding="utf-8")  # untracked, in a new place
    (repo / "ignored.txt").write_text("x\n", encoding="utf-8")  # ignored: absent
    assert self_ci_legs.git_changed_paths(repo) == ["README.md", "meta/TASKS.md", "meta/new_check.py"]


def test_a_meta_only_change_selects_a_leg_through_git(tmp_path, table):
    repo = _git_repo(tmp_path)
    (repo / "meta" / "TASKS.md").write_text("edited\n", encoding="utf-8")
    change_set = self_ci_legs.resolve_change_set(repo)
    assert change_set.paths == ("meta/TASKS.md",)
    assert table.select(change_set.paths, defer_full_only=True).legs == {"decision-records"}


def test_a_rename_counts_both_its_old_and_its_new_path(tmp_path):
    repo = _git_repo(tmp_path)
    _git(repo, "mv", "kept.txt", "moved.txt")  # staged rename
    assert self_ci_legs.git_changed_paths(repo) == ["kept.txt", "moved.txt"]


def test_an_untracked_directory_lists_its_files_and_a_deletion_its_path(tmp_path):
    repo = _git_repo(tmp_path)
    (repo / "new_dir" / "deep").mkdir(parents=True)
    (repo / "new_dir" / "deep" / "a.mjs").write_text("x\n", encoding="utf-8")
    (repo / "README.md").unlink()
    assert self_ci_legs.git_changed_paths(repo) == ["README.md", "new_dir/deep/a.mjs"]


def test_resolve_change_set_picks_the_source(tmp_path):
    repo = _git_repo(tmp_path)
    clean = self_ci_legs.resolve_change_set(repo)
    assert clean.paths is None and "clean tree" in clean.source
    assert self_ci_legs.resolve_change_set(repo, ["a.md"]).paths == ("a.md",)
    assert self_ci_legs.resolve_change_set(repo, ["."]).paths is None
    (repo / "README.md").write_text("edited\n", encoding="utf-8")
    assert self_ci_legs.resolve_change_set(repo).source == "git (1 changed paths)"
    assert self_ci_legs.resolve_change_set(repo, full=True).paths is None


def test_git_failure_raises(tmp_path):
    with pytest.raises(self_ci_legs.ChangeSetError, match="failed"):
        self_ci_legs.git_changed_paths(tmp_path)


def test_the_ci_workflow_runs_self_ci_as_a_full_run():
    steps = (_AKMON / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    commands = [line.strip() for line in steps.splitlines() if "meta/self_ci.py" in line and "run:" in line]
    assert commands, "ci.yml no longer runs meta/self_ci.py"
    assert all("--full" in command for command in commands), commands


def test_akmons_record_runs_self_ci_without_files_so_it_runs_under_changed_too():
    import tomllib

    record = tomllib.loads((_AKMON / "meta" / ".akmon.toml").read_text(encoding="utf-8"))
    assert record["check"]["self-ci"] == "python3 meta/self_ci.py"


def test_the_corpus_legs_read_every_file_the_corpus_snapshot_carries(table):
    """The snapshot list is the corpus's own; a path it carries that the corpus legs do not read would let a
    change to it skip the corpus. Stand-ins are the corpus's own copies of prose, so the prose is not an input."""
    path = _AKMON / "meta" / "conformance" / "corpus.py"
    spec = importlib.util.spec_from_file_location("self_ci_legs_probe_corpus", path)
    corpus = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = corpus
    try:
        spec.loader.exec_module(corpus)
    finally:
        del sys.modules[spec.name]
    carried = {
        *corpus.SNAPSHOT_FILES,
        *corpus.snapshot_hooks(_AKMON),
        *corpus.snapshot_js(_AKMON),
    } - set(corpus.standins())
    unread = sorted(carried - {name for name in carried if self_ci_legs.path_matches(name, table.legs["corpus"])})
    assert unread == []
    assert table.legs["corpus-node"] == table.legs["corpus"] == table.legs["fuzz"]
