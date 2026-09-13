"""``akmon check`` — a thin runner over the checks a project declares (ADR 0014 §4, as amended).

akmon checks no code itself: these carriers pin that the ``[check]`` table is read strictly, that
``{files}`` becomes the files a run covers, that every command's result is one finding, and that
``verify`` validates the table without running anything.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import check as check_cli
import pytest

from common import check_runner
from common.check_runner import Check


def test_a_command_string_and_a_table_are_both_checks():
    checks, problems = check_runner.read_checks(
        {"lint": "uv run ruff check {files}", "types": {"command": "mypy {files}", "files": ["*.py", "*.pyi"]}}
    )
    assert problems == []
    assert checks == [
        Check("lint", ("uv", "run", "ruff", "check", "{files}"), ("*.py",)),
        Check("types", ("mypy", "{files}"), ("*.py", "*.pyi")),
    ]


@pytest.mark.parametrize(
    ("table", "fragment"),
    [
        ("ruff check", "must be a table of named commands"),
        ({"lint": ""}, "needs a non-empty `command`"),
        ({"lint": {"cmd": "ruff"}}, "unknown key 'cmd'"),
        ({"lint": {"command": "ruff", "files": "*.py"}}, "files must be a non-empty list"),
        ({"lint": 3}, "must be a command string or a table"),
        ({"lint": 'ruff "unclosed'}, "does not split into arguments"),
    ],
)
def test_a_malformed_entry_is_reported_and_not_run(table, fragment):
    checks, problems = check_runner.read_checks(table)
    assert checks == []
    assert any(fragment in problem for problem in problems), problems


def test_files_covers_the_project_or_only_the_matching_changes():
    check = Check("lint", ("ruff", "check", "{files}"), ("*.py",))
    assert check_runner.argv_for(check, None) == ["ruff", "check", "."]
    assert check_runner.argv_for(check, ["src/a.py", "README.md", "b.py"]) == ["ruff", "check", "src/a.py", "b.py"]
    assert check_runner.argv_for(check, ["README.md"]) is None
    unplaced = Check("types", ("mypy", "src"))
    assert check_runner.argv_for(unplaced, ["README.md"]) == ["mypy", "src"]


def test_every_command_is_one_finding_and_its_exit_decides_the_severity(tmp_path):
    def runner(argv, **kwargs):
        if argv[0] == "missing":
            raise FileNotFoundError(argv[0])
        return subprocess.CompletedProcess(argv, 0 if argv[0] == "good" else 2)

    checks = [Check("a", ("good",)), Check("b", ("bad", "{files}")), Check("c", ("missing",))]
    findings = check_runner.run_checks(tmp_path, checks, None, runner=runner)
    assert [(f.severity, f.target) for f in findings] == [
        ("ok", "[check].a"),
        ("error", "[check].b"),
        ("error", "[check].c"),
    ]
    assert "exited 2" in findings[1].message
    assert "`missing` is not installed" in findings[2].message


def _project(tmp_path: Path, toml: str) -> Path:
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (tmp_path / "_aitna").mkdir()
    (tmp_path / "_aitna" / ".akmon.toml").write_text(toml, encoding="utf-8")
    return tmp_path


def _python(code: str) -> str:
    """A command running ``code``, as a TOML string value (JSON's string form is valid TOML)."""
    return json.dumps(shlex.join([sys.executable, "-c", code]))


def test_check_runs_the_declared_commands_and_exits_by_their_result(tmp_path, capsys):
    root = _project(tmp_path, f"[check]\npasses = {_python('pass')}\n")
    assert check_cli.main(["--project-root", str(root)]) == 0
    (root / "_aitna" / ".akmon.toml").write_text(f"[check]\nfails = {_python('raise SystemExit(3)')}\n")
    assert check_cli.main(["--project-root", str(root)]) == 1
    assert "exited 3" in capsys.readouterr().out


def test_no_declared_check_is_a_warning_not_a_failure(tmp_path, capsys):
    root = _project(tmp_path, 'mount = "submodule"\n')
    assert check_cli.main(["--project-root", str(root)]) == 0
    assert "WARN check.config" in capsys.readouterr().out


def test_a_broken_record_fails_the_check(tmp_path, capsys):
    root = _project(tmp_path, "[check\n")
    assert check_cli.main(["--project-root", str(root)]) == 1
    assert "ERROR check.config" in capsys.readouterr().out


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        check=True,
        capture_output=True,
    )


def test_changed_files_are_what_differs_from_head_and_never_the_dev_layer(tmp_path):
    root = _project(tmp_path, "")
    (root / "old.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "base")
    (root / "new.py").write_text("y = 2\n", encoding="utf-8")
    (root / "_aitna" / "tool.py").write_text("z = 3\n", encoding="utf-8")
    assert check_runner.changed_files(root) == ["new.py"]


def test_verify_validates_the_check_table_and_runs_nothing(tmp_path):
    """``verify`` owns integration health: a malformed entry silently stops a check from running,
    so it is ``verify``'s business; the check's own result is ``akmon check``'s."""
    import verify

    root = _project(tmp_path, '[check]\nlint = ""\n')
    verifier = verify.Verifier(root)
    verifier.check_check_config()
    assert [(f.severity, f.code) for f in verifier.findings] == [("error", "check.config")]

    (root / "_aitna" / ".akmon.toml").write_text(f"[check]\nlint = {_python('raise SystemExit(1)')}\n")
    verifier = verify.Verifier(root)
    verifier.check_check_config()
    assert [(f.severity, f.code) for f in verifier.findings] == [("ok", "check.config")]
