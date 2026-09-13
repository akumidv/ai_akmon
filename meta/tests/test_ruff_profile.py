"""akmon's Python rules, ``profiles/ruff.toml`` — a standard ruff configuration (ADR 0014 §3).

The rules must run without akmon, the two standard ways: ``ruff check --config`` and a project's
own ``extend``. The second carries a measured subtlety these tests pin: the test-file ignores of an
extended configuration must still reach the project's tests, and ``target-version`` must still come
from the project's own ``requires-python``.

akmon itself runs exactly the rules it offers — its ``pyproject.toml`` extends the profile and adds
no rule of its own — except the size family, whose per-file exceptions are C91's ratchet: an entry
may leave the list, none may join it, and one no longer needed fails until it is removed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "profiles" / "ruff.toml"

pytest.importorskip("ruff", reason="ruff is akmon's development dependency")


def _ruff(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--no-cache", "--output-format", "concise", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    return result.stdout


def _sources(root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "a.py").write_text(
        '"""A."""\n\n\ndef f(x: list = []) -> list:  # noqa: D103\n    assert x\n    return x\n'
    )
    (root / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n")


def test_the_profile_is_a_valid_ruff_configuration_without_a_target_version():
    config = tomllib.loads(PROFILE.read_text(encoding="utf-8"))
    assert "target-version" not in config  # ruff infers it from the project's requires-python
    assert config["lint"]["pydocstyle"]["convention"] == "google"


def test_the_rules_run_standalone_with_config(tmp_path):
    _sources(tmp_path)
    out = _ruff(tmp_path, "--config", str(PROFILE), ".")
    assert "src/a.py" in out and "B006" in out and "S101" in out
    assert "tests/test_a.py" not in out  # the test ignores reach tests at any depth


def test_a_project_extending_the_profile_keeps_the_test_ignores_and_its_own_target(tmp_path):
    rules = tmp_path / "_aitna" / ".akmon" / "profiles" / "ruff.toml"
    rules.parent.mkdir(parents=True)
    shutil.copy(PROFILE, rules)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "p"\nversion = "0"\nrequires-python = ">=3.12"\n\n'
        '[tool.ruff]\nextend = "_aitna/.akmon/profiles/ruff.toml"\n',
        encoding="utf-8",
    )
    _sources(tmp_path)
    out = _ruff(tmp_path, ".")
    assert "src/a.py" in out and "S101" in out
    assert "tests/test_a.py" not in out
    settings = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--no-cache", "--show-settings", "src/a.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "unresolved_target_version = 3.12" in settings


# --------------------------------------------------------------------------------------
# akmon's own configuration, and the C91 size ratchet
# --------------------------------------------------------------------------------------

SIZE_FAMILY = ("C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915")

# The size-family offenders when C91 opened. An entry may leave; none may join.
_C91_BASELINE = frozenset(
    {
        ("bin/verify.py", "C901"),
        ("common/codex_hooks.py", "C901"),
        ("common/codex_hooks.py", "PLR0912"),
        ("common/findings.py", "C901"),
        ("hooks/hook_core.py", "PLR0911"),
        ("meta/checks/runtime.py", "C901"),
        ("meta/checks/runtime.py", "PLR0912"),
        ("meta/checks/runtime.py", "PLR0915"),
        ("meta/self_ci.py", "PLR0913"),
        ("meta/tests/test_coverage_map.py", "PLR0913"),
        ("meta/tests/test_findings.py", "PLR0913"),
        ("src/akmon/_init.py", "C901"),
        ("src/akmon/_init.py", "PLR0911"),
        ("src/akmon/_init.py", "PLR0912"),
        ("src/akmon/_init.py", "PLR0913"),
        ("src/akmon/_init.py", "PLR0915"),
        ("src/akmon/cli.py", "PLR0911"),
        ("tools/model_routing/gate_pack.py", "PLR0913"),
        ("tools/model_routing/stats.py", "C901"),
        ("tools/model_routing/stats.py", "PLR0912"),
        ("tools/model_routing/stats.py", "PLR0913"),
        ("tools/tasks/archive.py", "PLR0911"),
    }
)


def _akmon_ruff() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["ruff"]


def _c91_exceptions() -> set[tuple[str, str]]:
    ignores = _akmon_ruff()["lint"]["extend-per-file-ignores"]
    return {(path, code) for path, codes in ignores.items() for code in codes}


def test_akmon_runs_exactly_the_rules_it_offers():
    ruff = _akmon_ruff()
    assert ruff["extend"] == "profiles/ruff.toml"
    assert set(ruff) <= {"extend", "target-version", "lint"}
    assert set(ruff["lint"]) <= {"allowed-confusables", "extend-per-file-ignores"}


def test_the_c91_exceptions_are_the_size_family_and_never_grow():
    exceptions = _c91_exceptions()
    assert {code for _, code in exceptions} <= set(SIZE_FAMILY)
    assert exceptions <= _C91_BASELINE, "C91 only shrinks: bring the new offender under the limit instead"


def test_every_c91_exception_is_still_needed():
    result = subprocess.run(
        [
            *(sys.executable, "-m", "ruff", "check", "--no-cache", "--output-format", "json"),
            *("--config", str(PROFILE), "--select", ",".join(SIZE_FAMILY), "."),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    offenders = {(Path(f["filename"]).relative_to(ROOT).as_posix(), f["code"]) for f in json.loads(result.stdout)}
    assert _c91_exceptions() - offenders == set(), "no longer offending: remove these from pyproject.toml"
    assert offenders - _c91_exceptions() == set(), "a new size-family offender: bring it under the limit"
