"""Unit tests for the release-check test-runner resolution (``release_check``).

Focus: how ``_pytest_command`` picks a runner — the pinned ``[test].runner`` from the
integration record first, then discovery. ``release_check`` lives under ``tools/release/`` (not
on the test ``sys.path``), so load it by file path. Nothing touches the real repo.
"""

from __future__ import annotations

import builtins
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_KEYSTONE = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_spec = importlib.util.spec_from_file_location(
    "release_check", _KEYSTONE / "tools" / "release" / "release_check.py"
)
release_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_check)


def _attach(root: Path, body: str) -> None:
    (root / "_aitna").mkdir(parents=True, exist_ok=True)
    (root / "_aitna" / ".akmon.toml").write_text(body, encoding="utf-8")


def test_akmon_check_runs_only_upstream_gates(monkeypatch, tmp_path):
    pytest_command = ["pytest", str(release_check.META / "tests")]
    captured = {}

    def fake_pytest_command(root, tests):
        assert root == release_check.KEYSTONE_ROOT
        assert tests == str(release_check.META / "tests")
        return pytest_command

    def fake_run_commands(root, commands):
        captured["root"] = root
        captured["commands"] = commands
        return []

    monkeypatch.setattr(release_check, "_pytest_command", fake_pytest_command)
    monkeypatch.setattr(release_check, "_run_commands", fake_run_commands)
    # The version join has its own tests below; here it is silenced so this stays a test of
    # which commands the akmon subject runs.
    monkeypatch.setattr(release_check, "check_release_versions", lambda _root: [])

    assert release_check.run_check(tmp_path, "akmon") == 0
    assert captured == {
        "root": release_check.KEYSTONE_ROOT,
        "commands": [
            [sys.executable, str(release_check.META / "self_ci.py")],
            pytest_command,
        ],
    }


def test_pinned_runner_is_used_verbatim_with_test_path(tmp_path):
    _attach(tmp_path, 'akmon_version = "v9"\n\n[test]\nrunner = "poetry run pytest"\n')
    assert release_check._pytest_command(tmp_path, "TESTS") == ["poetry", "run", "pytest", "TESTS"]


def test_pinned_runner_ignores_comments_and_blank_value(tmp_path):
    _attach(tmp_path, '# runner = "not this one"\n[test]\nrunner = ""\n')  # commented + empty → no pin
    assert release_check._pinned_test_runner(tmp_path) is None


def test_no_attach_record_falls_back_to_discovery(tmp_path):
    # No .akmon.toml at all: discovery must still yield a runnable pytest invocation.
    assert release_check._pinned_test_runner(tmp_path) is None
    cmd = release_check._pytest_command(tmp_path, "TESTS")
    assert cmd[-1] == "TESTS" and "pytest" in " ".join(cmd)


def test_dev_venv_discovered_as_python_dash_m(tmp_path):
    # A discovered dev venv must be invoked as `<venv>/bin/python -m pytest`, never bin/pytest.
    venv_python = tmp_path / "_aitna" / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("#!/bin/sh\n", encoding="utf-8")
    cmd = release_check._pytest_command(tmp_path, "TESTS")
    assert cmd == [str(venv_python), "-m", "pytest", "TESTS"]


def test_toml_read_falls_back_when_tomllib_absent(tmp_path, monkeypatch):
    # Injected import failure exercises fail-open behavior, not a pre-3.11 support promise.
    _attach(tmp_path, 'akmon_version = "v9"\n\n[test]\nrunner = "poetry run pytest"\n')
    real_import = builtins.__import__

    def no_tomllib(name, *args, **kwargs):
        if name == "tomllib":
            raise ImportError("simulated: no tomllib on this host")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_tomllib)
    assert release_check._pinned_test_runner(tmp_path) == "poetry run pytest"


# --------------------------------------------------------------------------------------
# version ↔ changelog cross-check (C54, design §4 — owner choice F9)
# --------------------------------------------------------------------------------------
#
# The join is exercised over a controlled tag corpus rather than a repository per case: the
# rules under test are about which tag/heading/literal combinations are acceptable, and
# ``_git_tags`` is pinned separately, once, against a real repository — so nothing here is
# checked only against a stub.

_NON_FINAL_CORPUS = (
    "1.2.3.dev0",
    "1.2.3a1",
    "1.2.3b2",
    "1.2.3rc1",
    "1.2.3.post1",
    "1.2.3+local.1",
    "1.2.3rc1.dev4",
    "1.2.3.post1.dev0",
    "1.2.3rc1+local.1",
)


def _tree(root: Path, *, version: str | None = None, static: str | None = None,
          changelog: str | None = "## Unreleased\n") -> Path:
    """A synthetic release subject: the three file-borne version carriers, each optional."""
    if version is not None:
        (root / "pyproject.toml").write_text(
            f'[project]\nname = "demo"\nversion = "{version}"\n\n[tool.other]\nversion = "9.9.9"\n',
            encoding="utf-8",
        )
    if static is not None:
        (root / "src" / "akmon").mkdir(parents=True, exist_ok=True)
        (root / "src" / "akmon" / "__init__.py").write_text(
            f'"""doc."""\n\n_STATIC_VERSION = "{static}"\n', encoding="utf-8"
        )
    if changelog is not None:
        (root / "CHANGELOG.md").write_text(f"# Changelog\n\n{changelog}", encoding="utf-8")
    return root


def _check(root: Path, monkeypatch, tags: tuple[str, ...] = ()) -> list:
    """Run the join with the tag corpus supplied rather than discovered."""
    monkeypatch.setattr(release_check, "_git_tags", lambda _root: list(tags))
    return release_check.check_release_versions(root)


def _codes(findings, severity: str) -> list[str]:
    return [finding.code for finding in findings if finding.severity == severity]


# --- the two consistent states ---------------------------------------------------------


def test_a_non_final_version_over_an_unreleased_heading_passes(tmp_path, monkeypatch):
    _tree(tmp_path, version="0.4.0.dev0", static="0.4.0.dev0")
    findings = _check(tmp_path, monkeypatch, tags=("v0.3.0",))
    assert _codes(findings, "error") == []
    assert _codes(findings, "warn") == ["release.undocumented-tag"]  # the corpus tag, not the window


def test_a_final_version_over_its_own_heading_passes(tmp_path, monkeypatch):
    _tree(tmp_path, version="0.4.0", static="0.4.0", changelog="## v0.4.0\n\n## v0.3.0\n")
    findings = _check(tmp_path, monkeypatch, tags=("v0.3.0",))
    assert _codes(findings, "error") == []
    assert _codes(findings, "warn") == []


# --- the non-final branch: the full PEP 440 corpus, not `.devN` alone (F9/3) -------------


@pytest.mark.parametrize("version", _NON_FINAL_CORPUS)
def test_every_non_final_spelling_requires_a_topmost_unreleased_heading(version, tmp_path, monkeypatch):
    _tree(tmp_path, version=version, static=version, changelog="## v1.2.3\n\n## Unreleased\n")
    findings = _check(tmp_path, monkeypatch, tags=())
    assert _codes(findings, "error") == ["release.changelog-window"]


@pytest.mark.parametrize("version", _NON_FINAL_CORPUS)
def test_every_non_final_spelling_passes_with_the_heading_on_top(version, tmp_path, monkeypatch):
    _tree(tmp_path, version=version, static=version, changelog="## Unreleased\n\n## v1.2.3\n")
    assert _codes(_check(tmp_path, monkeypatch, tags=()), "error") == []


# --- the final branch: two separate negatives -------------------------------------------


def test_a_final_version_with_no_released_heading_at_all_fails(tmp_path, monkeypatch):
    _tree(tmp_path, version="0.4.0", static="0.4.0", changelog="## Unreleased\n")
    findings = _check(tmp_path, monkeypatch, tags=())
    assert _codes(findings, "error") == ["release.changelog-window"]
    assert "carries no released heading" in findings[-1].message


def test_a_final_version_below_a_different_topmost_released_heading_fails(tmp_path, monkeypatch):
    # The matching heading exists — further down. Searching anywhere would pass this tree.
    _tree(tmp_path, version="0.4.0", static="0.4.0", changelog="## v0.5.0\n\n## v0.4.0\n")
    findings = _check(tmp_path, monkeypatch, tags=())
    assert _codes(findings, "error") == ["release.changelog-window"]
    assert "`## v0.5.0`" in findings[-1].message


# --- the two literals (F9/2) ------------------------------------------------------------


def test_disagreeing_version_literals_fail(tmp_path, monkeypatch):
    _tree(tmp_path, version="0.4.0", static="0.4.0.dev0")
    findings = _check(tmp_path, monkeypatch, tags=())
    assert "release.version-literals" in _codes(findings, "error")


def test_agreeing_version_literals_are_reported_rather_than_assumed(tmp_path, monkeypatch):
    _tree(tmp_path, version="0.4.0.dev0", static="0.4.0.dev0")
    findings = _check(tmp_path, monkeypatch, tags=())
    assert "release.version-literals" in _codes(findings, "ok")


# --- absent inputs are said out loud, never passed quietly (F9/4) ------------------------


def test_no_version_source_at_all_produces_an_explicit_skip(tmp_path, monkeypatch):
    _tree(tmp_path)  # a CHANGELOG, no pyproject, no _STATIC_VERSION
    findings = _check(tmp_path, monkeypatch, tags=())
    assert _codes(findings, "error") == []
    assert _codes(findings, "warn") == ["release.check-skipped"]
    assert findings != []  # the point of F9/4: a skip is reported, not a silent clean pass


def test_a_missing_changelog_skips_both_rules_that_needed_it(tmp_path, monkeypatch):
    # The window rule and tag coverage both read the changelog, so both say so: a rule that
    # silently does not run is the failure F9/4 exists to remove.
    _tree(tmp_path, version="0.4.0", static="0.4.0", changelog=None)
    findings = _check(tmp_path, monkeypatch, tags=("v0.1.0",))
    assert _codes(findings, "error") == []
    assert _codes(findings, "warn") == ["release.check-skipped", "release.check-skipped"]
    assert "compared against nothing" in findings[-2].message
    assert "no tag was checked" in findings[-1].message


def test_without_git_each_dependent_rule_skips_on_its_own(tmp_path, monkeypatch):
    _tree(tmp_path, version="0.4.0", static="0.4.0", changelog="## v0.4.0\n")
    monkeypatch.setattr(release_check.shutil, "which", lambda _name: None)
    findings = release_check.check_release_versions(tmp_path)
    skips = [finding for finding in findings if finding.code == "release.check-skipped"]
    assert len(skips) == 2  # the re-release question and the tag-coverage question, separately
    assert _codes(findings, "error") == []


def test_a_rule_that_does_not_apply_is_not_reported_as_skipped(tmp_path, monkeypatch):
    # A non-final version raises no re-release question at all, so only tag coverage is skipped.
    _tree(tmp_path, version="0.4.0.dev0", static="0.4.0.dev0")
    monkeypatch.setattr(release_check.shutil, "which", lambda _name: None)
    findings = release_check.check_release_versions(tmp_path)
    assert [finding.code for finding in findings if finding.code == "release.check-skipped"] == [
        "release.check-skipped"
    ]


# --- tags: coverage warns, re-release warns (F9/5) --------------------------------------


def test_an_older_tag_missing_its_heading_warns_without_failing(tmp_path, monkeypatch):
    _tree(tmp_path, version="0.4.0.dev0", static="0.4.0.dev0",
          changelog="## Unreleased\n\n## v0.3.0\n\n## v0.1.0\n")
    findings = _check(tmp_path, monkeypatch, tags=("v0.1.0", "v0.2.0", "v0.3.0"))
    assert _codes(findings, "error") == []
    warns = [finding for finding in findings if finding.code == "release.undocumented-tag"]
    assert [finding.target for finding in warns] == ["v0.2.0"]  # the newest tag is documented


def test_a_final_version_with_its_tag_already_cut_warns_and_does_not_error(tmp_path, monkeypatch):
    _tree(tmp_path, version="0.4.0", static="0.4.0", changelog="## v0.4.0\n")
    findings = _check(tmp_path, monkeypatch, tags=("v0.4.0",))
    retag = [finding for finding in findings if finding.code == "release.retag"]
    assert [finding.severity for finding in retag] == ["warn"]  # exactly warn, not error
    assert _codes(findings, "error") == []


def test_git_tags_are_read_from_a_real_repository(tmp_path, monkeypatch):
    # The one place the corpus is not supplied: the reading itself, against a real repo.
    if shutil.which("git") is None:  # pragma: no cover - git is present on the dev bench
        pytest.skip("git is unavailable")
    _tree(tmp_path, version="0.4.0", static="0.4.0", changelog="## v0.4.0\n")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}
    for command in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "x"],
                    ["tag", "v0.4.0"], ["tag", "v0.2.0"], ["tag", "0.1.0"],
                    ["tag", "not-a-version"], ["tag", "v0.3"], ["tag", "v0.3.0rc1"]):
        subprocess.run(["git", "-C", str(tmp_path), *command], check=True, env=env,
                       capture_output=True)
    # Both spellings are release tags; nothing else is. Read here rather than through the
    # supplied corpus, because the corpus tests replace this function and would never see it.
    assert release_check._git_tags(tmp_path) == ["0.1.0", "v0.2.0", "v0.4.0"]
    findings = release_check.check_release_versions(tmp_path)
    assert sorted(_codes(findings, "warn")) == [
        "release.retag", "release.tag-spelling", "release.undocumented-tag"
    ]


def test_git_tags_returns_none_outside_a_repository(tmp_path):
    if shutil.which("git") is None:  # pragma: no cover - git is present on the dev bench
        pytest.skip("git is unavailable")
    assert release_check._git_tags(tmp_path) is None  # not [] — the question was never answered


# --- normalization (F9/6) ---------------------------------------------------------------


@pytest.mark.parametrize("version", ["0.4.0", "v0.4.0"])
def test_the_leading_v_is_a_spelling_not_a_different_version(version, tmp_path, monkeypatch):
    _tree(tmp_path, version=version, static=version, changelog="## v0.4.0\n")
    assert _codes(_check(tmp_path, monkeypatch, tags=()), "error") == []


def test_a_describe_suffix_means_ahead_of_the_tag_rather_than_at_it(tmp_path, monkeypatch):
    # Past v0.4.0 is not v0.4.0: the tree is mid-cycle, so it wants `## Unreleased`.
    _tree(tmp_path, version="v0.4.0-3-gdeadbee", static="v0.4.0-3-gdeadbee",
          changelog="## v0.4.0\n")
    assert _codes(_check(tmp_path, monkeypatch, tags=()), "error") == ["release.changelog-window"]
    _tree(tmp_path, changelog="## Unreleased\n\n## v0.4.0\n")
    assert _codes(_check(tmp_path, monkeypatch, tags=()), "error") == []


# --- reading the carriers ----------------------------------------------------------------


def test_the_project_version_is_read_from_its_own_table(tmp_path):
    _tree(tmp_path, version="7.7.7")  # the fixture also writes [tool.other] version = "9.9.9"
    assert release_check._pyproject_version(tmp_path / "pyproject.toml") == "7.7.7"


def test_the_project_version_is_read_without_tomllib_too(tmp_path, monkeypatch):
    _tree(tmp_path, version="7.7.7")
    real_import = builtins.__import__

    def no_tomllib(name, *args, **kwargs):
        if name == "tomllib":
            raise ImportError("simulated: no tomllib on this host")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_tomllib)
    assert release_check._pyproject_version(tmp_path / "pyproject.toml") == "7.7.7"


# --- the live tree: P1.3's acceptance ----------------------------------------------------


def test_the_live_tree_carries_a_consistent_version_pair():
    findings = release_check.check_release_versions(_KEYSTONE)
    assert [finding.code for finding in findings if finding.severity == "error"] == []


# --- the repairs outside the checker -----------------------------------------------------
#
# A checker that reports a mismatch the release procedure keeps re-creating is theatre, so the
# procedure carries its own carriers: the plan must stage both version literals, and it must
# name the bump before it reaches `git add`.


def _plan_lines(capsys, subject: str = "akmon") -> list[str]:
    assert release_check.run_plan("v9.9.9", subject) == 0
    return capsys.readouterr().out.splitlines()


def _assert_plan_bumps_both_literals_before_staging(lines: list[str]) -> None:
    staged = next(index for index, line in enumerate(lines) if line.startswith("git add "))
    for carrier in ("CHANGELOG.md", "pyproject.toml", "src/akmon/__init__.py"):
        assert carrier in lines[staged], f"{carrier} is not staged"
    bumped = next(index for index, line in enumerate(lines) if "_STATIC_VERSION" in line)
    assert bumped < staged, "the version bump is described after `git add`"


def test_the_plan_stages_both_version_literals_before_committing(capsys):
    _assert_plan_bumps_both_literals_before_staging(_plan_lines(capsys))


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda lines: [line.replace(" pyproject.toml", "") for line in lines],
                     id="omits-pyproject"),
        pytest.param(lambda lines: [line.replace(" src/akmon/__init__.py", "") for line in lines],
                     id="omits-static-version"),
        pytest.param(
            lambda lines: (
                [line for line in lines if "_STATIC_VERSION" not in line]
                + [line for line in lines if "_STATIC_VERSION" in line]
            ),
            id="bumps-after-git-add",
        ),
    ],
)
def test_the_plan_contract_fails_on_a_mutated_plan(mutate, capsys):
    with pytest.raises(AssertionError):
        _assert_plan_bumps_both_literals_before_staging(mutate(_plan_lines(capsys)))


_FALSE_TAG_CLAIM_RE = re.compile(
    r"(?:cut|deriv|produc|deduc)\w*\s+the\s+(?:real\s+)?version\s+from\s+the\s+git\s+tag",
    re.IGNORECASE,
)


def test_the_package_does_not_claim_the_tag_produces_the_built_version():
    # Half of why the shipped defect reproduced: `__init__.py` asserted that the release
    # pipeline cuts the real version from the git tag, which a static hatchling version makes
    # false. It is a literal string in a source file, so it is pinned as one.
    text = (_KEYSTONE / "src" / "akmon" / "__init__.py").read_text(encoding="utf-8")
    assert not _FALSE_TAG_CLAIM_RE.search(text)
    assert "pyproject.toml" in text  # it names what actually produces the number
    assert _FALSE_TAG_CLAIM_RE.search(
        "The release pipeline cuts the real version from the git tag"
    )  # the seed the pin exists to catch


def test_the_check_mode_fails_on_a_version_error_even_when_the_suites_are_green(monkeypatch, tmp_path):
    # The join is wired into the gate, not merely importable: a red version pair fails --check.
    monkeypatch.setattr(release_check, "_pytest_command", lambda root, tests: ["true"])
    monkeypatch.setattr(release_check, "_run_commands", lambda root, commands: [])
    monkeypatch.setattr(
        release_check, "check_release_versions",
        lambda _root: [release_check.Finding("error", "release.changelog-window", "seeded", "", "Repair it.")],
    )
    assert release_check.run_check(tmp_path, "akmon") == 1


def test_the_check_mode_does_not_fail_on_a_version_warning(monkeypatch, tmp_path):
    monkeypatch.setattr(release_check, "_pytest_command", lambda root, tests: ["true"])
    monkeypatch.setattr(release_check, "_run_commands", lambda root, commands: [])
    monkeypatch.setattr(
        release_check, "check_release_versions",
        lambda _root: [release_check.Finding("warn", "release.retag", "seeded", "", "Confirm it.")],
    )
    assert release_check.run_check(tmp_path, "akmon") == 0


# --- heading vocabulary and untrusted text ------------------------------------------------


@pytest.mark.parametrize(
    "heading", ["v1.2.3", "1.2.3", "[1.2.3] - 2024-01-01", "v1.2.3 (2024-01-01)"]
)
def test_a_released_heading_may_say_more_than_its_version(heading, tmp_path, monkeypatch):
    # The `package` subject reads a consuming project's changelog, where Keep a Changelog's
    # `## [1.2.3] - <date>` is ordinary. Demanding a bare version would report "no released
    # heading" over a file full of them.
    _tree(tmp_path, version="1.2.3", static="1.2.3", changelog=f"## {heading}\n")
    assert _codes(_check(tmp_path, monkeypatch, tags=()), "error") == []


@pytest.mark.parametrize("heading", ["Unreleased", "[Unreleased]", "unreleased"])
def test_the_unreleased_heading_is_recognized_in_both_spellings(heading, tmp_path, monkeypatch):
    _tree(tmp_path, version="1.2.3.dev0", static="1.2.3.dev0", changelog=f"## {heading}\n")
    assert _codes(_check(tmp_path, monkeypatch, tags=()), "error") == []


def test_a_pre_release_heading_does_not_count_as_a_released_one(tmp_path, monkeypatch):
    # No `vX.Y.Z` tag matches `## v1.2.3rc1`, so it cannot satisfy a final version.
    _tree(tmp_path, version="1.2.3", static="1.2.3", changelog="## v1.2.3rc1\n")
    assert _codes(_check(tmp_path, monkeypatch, tags=()), "error") == ["release.changelog-window"]


def test_a_version_literal_carrying_a_line_separator_is_escaped_not_crashed(tmp_path, monkeypatch):
    # The literals are read out of files; the envelope refuses to construct on a raw separator,
    # so a hostile or corrupt literal must be escaped at the boundary rather than raise.
    _tree(tmp_path, static="0.4.0 dev", version="0.4.0")
    findings = _check(tmp_path, monkeypatch, tags=())
    literals = [finding for finding in findings if finding.code == "release.version-literals"]
    assert [finding.severity for finding in literals] == ["error"]
    assert "\\u2028" in literals[0].message and " " not in literals[0].message


# --- the five mutations that survived the first adversarial pass -------------------------


def test_a_version_mentioned_mid_heading_does_not_name_a_release(tmp_path, monkeypatch):
    # `.search` instead of `.match` would read this as the released heading for 1.2.3.
    _tree(tmp_path, version="1.2.3", static="1.2.3", changelog="## Fixed in 1.2.3\n")
    assert _codes(_check(tmp_path, monkeypatch, tags=()), "error") == ["release.changelog-window"]


def test_the_two_literals_must_be_equal_literally_not_after_normalization(tmp_path, monkeypatch):
    # F9/2 says *literally* equal. `v0.4.0` and `0.4.0` are the same version and still two
    # different strings: one release bump is two edits, and both edits write the same text.
    _tree(tmp_path, version="v0.4.0", static="0.4.0", changelog="## v0.4.0\n")
    assert "release.version-literals" in _codes(_check(tmp_path, monkeypatch, tags=()), "error")


def test_the_pyproject_literal_is_the_one_the_window_is_checked_against(tmp_path, monkeypatch):
    # It is the literal hatchling stamps into the wheel, so it decides which window applies.
    # With the fallback winning, this tree would look like a consistent non-final release.
    _tree(tmp_path, version="0.4.0", static="0.4.0.dev0", changelog="## Unreleased\n")
    codes = _codes(_check(tmp_path, monkeypatch, tags=()), "error")
    assert codes == ["release.version-literals", "release.changelog-window"]


def test_tag_coverage_without_a_changelog_is_skipped_out_loud(tmp_path, monkeypatch):
    _tree(tmp_path, version="0.4.0.dev0", static="0.4.0.dev0", changelog=None)
    findings = _check(tmp_path, monkeypatch, tags=("v0.1.0",))
    assert [finding.code for finding in findings] == ["release.version-literals",
                                                      "release.check-skipped",
                                                      "release.check-skipped"]
    assert _codes(findings, "error") == []


def test_the_project_version_is_not_taken_from_an_earlier_table(tmp_path, monkeypatch):
    # The fallback parser is section-scoped; a foreign table *above* `[project]` is what
    # proves it, since an unscoped scan would return the first `version` line it meets.
    (tmp_path / "pyproject.toml").write_text(
        '[tool.other]\nversion = "9.9.9"\n\n[project]\nname = "demo"\nversion = "7.7.7"\n',
        encoding="utf-8",
    )
    real_import = builtins.__import__

    def no_tomllib(name, *args, **kwargs):
        if name == "tomllib":
            raise ImportError("simulated: no tomllib on this host")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_tomllib)
    assert release_check._pyproject_version(tmp_path / "pyproject.toml") == "7.7.7"


# --- tags in either spelling, and the plan that reopens the cycle ------------------------


def test_a_tag_cut_without_the_v_prefix_is_reported_rather_than_dropped(tmp_path, monkeypatch):
    # `vX.Y.Z` is the release tag's only admissible spelling, so `1.2.3` is a misspelled tag —
    # excluded from both git-dependent rules, and said out loud rather than filtered in silence.
    _tree(tmp_path, version="1.2.3", static="1.2.3", changelog="## v1.2.3\n")
    findings = _check(tmp_path, monkeypatch, tags=("1.2.3", "1.0.0"))
    warns = [finding for finding in findings if finding.severity == "warn"]
    assert [finding.code for finding in warns] == ["release.tag-spelling", "release.tag-spelling"]
    assert [finding.target for finding in warns] == ["1.2.3", "1.0.0"]
    assert _codes(findings, "error") == []


def test_a_misspelled_tag_is_not_read_as_the_release_it_names(tmp_path, monkeypatch):
    # It must not answer the re-release question either: there is no admissible tag for 1.2.3.
    _tree(tmp_path, version="1.2.3", static="1.2.3", changelog="## v1.2.3\n")
    findings = _check(tmp_path, monkeypatch, tags=("1.2.3",))
    assert "release.retag" not in [finding.code for finding in findings]


def _assert_plan_reopens_the_cycle(lines: list[str]) -> None:
    tagged = next(index for index, line in enumerate(lines) if line.startswith("git tag "))
    reopened = [index for index, line in enumerate(lines) if "dev0" in line and "Unreleased" in line]
    assert reopened, "the plan never says how to return to the development state"
    assert reopened[0] > tagged, "the reopen step is described before the tag"


def test_the_plan_says_how_to_reopen_the_cycle_after_the_tag(capsys):
    # Otherwise the tree sits at a released version whose tag exists, and every later --check
    # reports a re-release — the procedure producing what the checker complains about again.
    _assert_plan_reopens_the_cycle(_plan_lines(capsys))


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda lines: [line for line in lines if "dev0" not in line], id="omits-reopen"),
        pytest.param(
            lambda lines: (
                [line for line in lines if "dev0" in line]
                + [line for line in lines if "dev0" not in line]
            ),
            id="reopens-before-the-tag",
        ),
    ],
)
def test_the_reopen_contract_fails_on_a_mutated_plan(mutate, capsys):
    with pytest.raises(AssertionError):
        _assert_plan_reopens_the_cycle(mutate(_plan_lines(capsys)))


def test_the_integration_record_is_read_from_the_configured_dev_layer(tmp_path, monkeypatch):
    """A relocated dev layer must not make the pinned runner invisible.

    The record path was spelled ``_aitna`` directly, so under ``AITNA_ROOT=tools/ai`` the
    pinned ``[test].runner`` was never seen and the check silently fell through to discovery —
    running the project's tests under a different interpreter than the one attach pinned.
    """
    monkeypatch.setenv("AITNA_ROOT", "tools/ai")
    (tmp_path / "tools" / "ai").mkdir(parents=True)
    (tmp_path / "tools" / "ai" / ".akmon.toml").write_text(
        '[test]\nrunner = "poetry run pytest"\n', encoding="utf-8"
    )
    assert release_check._pinned_test_runner(tmp_path) == "poetry run pytest"
    assert release_check._pytest_command(tmp_path, "TESTS") == ["poetry", "run", "pytest", "TESTS"]


def test_the_dev_venv_is_discovered_under_the_configured_dev_layer(tmp_path, monkeypatch):
    monkeypatch.setenv("AITNA_ROOT", "tools/ai")
    venv_python = tmp_path / "tools" / "ai" / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("#!/bin/sh\n", encoding="utf-8")
    assert release_check._pytest_command(tmp_path, "TESTS") == [str(venv_python), "-m", "pytest", "TESTS"]


def test_the_release_charter_path_follows_the_configured_dev_layer(monkeypatch):
    monkeypatch.setenv("AITNA_ROOT", "tools/ai")
    assert release_check._release_charter() == "tools/ai/agents/release/README.md"
