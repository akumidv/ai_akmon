"""Unit tests for the dev-layer validator's test-runner resolution (``meta/bin/validate.py``).

Focus: how ``Validator._pytest_command`` decides that a runner resolves *here*. The guard is
derived from this root's manifest, not from whether ``pytest`` happens to be on PATH, and an
unresolvable runner must degrade to a skip-warning rather than a spurious failure.
``validate.py`` lives under ``meta/bin/`` (not on the test ``sys.path``), so load it by file
path. Nothing touches the real repo.
"""

from __future__ import annotations

import builtins
import importlib.util
import sys
from pathlib import Path

_KEYSTONE = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_spec = importlib.util.spec_from_file_location("akmon_validate", _KEYSTONE / "meta" / "bin" / "validate.py")
validate = importlib.util.module_from_spec(_spec)
# Registered before ``exec_module``: the module uses ``from __future__ import annotations`` with a
# dataclass, whose string-annotation resolution looks itself up in ``sys.modules`` while the class
# body executes — the same recipe ``cli._load_module_from_path`` documents.
sys.modules[_spec.name] = validate
_spec.loader.exec_module(validate)

_WITH_PYTEST = '[project]\nname = "x"\nversion = "0"\n\n[dependency-groups]\ndev = ["pytest>=8", "ruff>=0.8"]\n'
_WITHOUT_PYTEST = '[project]\nname = "x"\nversion = "0"\n\n[dependency-groups]\ndev = ["ruff>=0.8"]\n'


def _manifest(root: Path, body: str) -> None:
    (root / "pyproject.toml").write_text(body, encoding="utf-8")


def _hide_pytest(monkeypatch) -> None:
    """Make ``import pytest`` fail inside the validator, leaving every other import alone."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pytest":
            raise ImportError("pytest is not importable in this fixture")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def _uv_on_path(monkeypatch, *, uv: bool = True, pytest_binary: bool = False) -> None:
    def fake_which(name):
        if name == "uv":
            return "/usr/bin/uv" if uv else None
        if name == "pytest":
            return "/usr/bin/pytest" if pytest_binary else None
        return None

    monkeypatch.setattr(validate.shutil, "which", fake_which)


# --------------------------------------------------------------------------------------
# runner resolution
# --------------------------------------------------------------------------------------


def test_importable_pytest_wins_without_consulting_the_manifest(tmp_path):
    runner, reason = validate.Validator(tmp_path)._pytest_command()
    assert runner == [sys.executable, "-m", "pytest"]
    assert reason == ""


def test_uv_is_claimed_when_the_manifest_declares_pytest_and_pytest_is_not_installed(tmp_path, monkeypatch):
    """The case the old ``which("uv") and which("pytest")`` guard refused — the one uv handles."""
    _manifest(tmp_path, _WITH_PYTEST)
    _hide_pytest(monkeypatch)
    _uv_on_path(monkeypatch, uv=True, pytest_binary=False)
    runner, reason = validate.Validator(tmp_path)._pytest_command()
    assert runner == ["uv", "run", "pytest"]
    assert reason == ""


def test_pytest_on_path_does_not_make_an_unresolvable_root_resolvable(tmp_path, monkeypatch):
    """The other half of the old guard: PATH said yes where the manifest provisions nothing."""
    _manifest(tmp_path, _WITHOUT_PYTEST)
    _hide_pytest(monkeypatch)
    _uv_on_path(monkeypatch, uv=True, pytest_binary=True)
    runner, reason = validate.Validator(tmp_path)._pytest_command()
    assert runner is None
    assert "declares no pytest" in reason


def test_no_manifest_is_a_skip_with_its_own_reason(tmp_path, monkeypatch):
    _hide_pytest(monkeypatch)
    _uv_on_path(monkeypatch, uv=True)
    runner, reason = validate.Validator(tmp_path)._pytest_command()
    assert runner is None
    assert "no pyproject.toml" in reason


def test_no_uv_is_a_skip_with_its_own_reason(tmp_path, monkeypatch):
    _manifest(tmp_path, _WITH_PYTEST)
    _hide_pytest(monkeypatch)
    _uv_on_path(monkeypatch, uv=False)
    runner, reason = validate.Validator(tmp_path)._pytest_command()
    assert runner is None
    assert "uv is not on PATH" in reason


def test_unparsable_manifest_is_a_skip_not_a_claim(tmp_path, monkeypatch):
    _manifest(tmp_path, "[project\nname = broken")
    _hide_pytest(monkeypatch)
    _uv_on_path(monkeypatch, uv=True)
    runner, reason = validate.Validator(tmp_path)._pytest_command()
    assert runner is None
    assert "does not parse" in reason


def test_unresolvable_runner_warns_and_never_fails(tmp_path, monkeypatch):
    """The invariant the probe exists for: absence is a skip-warning, not a red test run."""
    (tmp_path / "meta" / "tests").mkdir(parents=True)
    _hide_pytest(monkeypatch)
    _uv_on_path(monkeypatch, uv=False)
    validator = validate.Validator(tmp_path)
    validator.run_tests()
    assert [finding.severity for finding in validator.findings] == ["warn"]
    assert "unit tests skipped: pytest is not importable" in validator.findings[0].message


# --------------------------------------------------------------------------------------
# manifest reading
# --------------------------------------------------------------------------------------


def test_default_groups_configuration_is_honoured(tmp_path, monkeypatch):
    _manifest(
        tmp_path,
        '[project]\nname = "x"\nversion = "0"\n\n[dependency-groups]\nci = ["pytest>=8"]\n'
        '\n[tool.uv]\ndefault-groups = ["ci"]\n',
    )
    _hide_pytest(monkeypatch)
    _uv_on_path(monkeypatch, uv=True)
    runner, _ = validate.Validator(tmp_path)._pytest_command()
    assert runner == ["uv", "run", "pytest"]


def test_a_group_uv_does_not_install_by_default_does_not_count(tmp_path, monkeypatch):
    _manifest(tmp_path, '[project]\nname = "x"\nversion = "0"\n\n[dependency-groups]\nci = ["pytest>=8"]\n')
    _hide_pytest(monkeypatch)
    _uv_on_path(monkeypatch, uv=True)
    runner, reason = validate.Validator(tmp_path)._pytest_command()
    assert runner is None
    assert "declares no pytest" in reason


def test_pytest_declared_as_a_project_dependency_counts(tmp_path, monkeypatch):
    _manifest(tmp_path, '[project]\nname = "x"\nversion = "0"\ndependencies = ["pytest>=8"]\n')
    _hide_pytest(monkeypatch)
    _uv_on_path(monkeypatch, uv=True)
    runner, _ = validate.Validator(tmp_path)._pytest_command()
    assert runner == ["uv", "run", "pytest"]


def test_requirement_name_reads_the_head_of_a_pep_508_string():
    assert validate._requirement_name("pytest>=8") == "pytest"
    assert validate._requirement_name(" pytest ") == "pytest"
    assert validate._requirement_name('pytest[extra]>=8; python_version >= "3.9"') == "pytest"
    assert validate._requirement_name("pytest-cov") == "pytest-cov"


# --------------------------------------------------------------------------------------
# the self-CI failure diagnostic
# --------------------------------------------------------------------------------------


def _self_ci_result(root: Path, monkeypatch, *, stdout: str, stderr: str = "", code: int = 1):
    """Run ``run_self_ci`` against a stubbed child process and return the findings."""
    (root / "meta").mkdir(parents=True, exist_ok=True)
    (root / "meta" / "self_ci.py").write_text("# stub\n", encoding="utf-8")

    class _Completed:
        returncode = code

    completed = _Completed()
    completed.stdout = stdout
    completed.stderr = stderr
    monkeypatch.setattr(validate.subprocess, "run", lambda *a, **k: completed)
    validator = validate.Validator(root)
    validator.run_self_ci()
    return validator.findings


def test_a_failing_self_ci_is_reported_by_its_error_not_by_its_last_line(tmp_path, monkeypatch):
    # The failing leg is followed by unrelated warnings in the same stream, which is the normal
    # shape: a `warn` finding does not fail the run, so it is routinely the last line printed.
    findings = _self_ci_result(
        tmp_path, monkeypatch,
        stdout="OK a.b: fine → Keep it.\n"
               "ERROR selfci.wheel-smoke: installed-wheel smoke failed: boom → Fix it.\n"
               "WARN c.d: unrelated → Note it.\n",
    )
    assert [finding.severity for finding in findings] == ["error"]
    assert "wheel-smoke" in findings[0].message
    assert "unrelated" not in findings[0].message


def test_a_self_ci_that_crashed_without_findings_still_names_something(tmp_path, monkeypatch):
    findings = _self_ci_result(tmp_path, monkeypatch, stdout="", stderr="Traceback\nValueError: boom\n")
    assert "ValueError: boom" in findings[0].message


def test_a_self_ci_that_printed_nothing_reports_its_exit_code(tmp_path, monkeypatch):
    findings = _self_ci_result(tmp_path, monkeypatch, stdout="", stderr="", code=3)
    assert "exit 3" in findings[0].message
