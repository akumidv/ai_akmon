"""akmon's Python rules, ``profiles/ruff.toml`` — a standard ruff configuration (ADR 0014 §3).

The rules must run without akmon, the two standard ways: ``ruff check --config`` and a project's
own ``extend``. The second carries a measured subtlety these tests pin: the test-file ignores of an
extended configuration must still reach the project's tests, and ``target-version`` must still come
from the project's own ``requires-python``.

akmon itself runs exactly the rules it offers — its ``pyproject.toml`` extends the profile and adds
no rule, ignore or per-file exception of its own. The size family included (C91): a limit is met,
never waived, so an inline ``noqa`` on one of its codes counts as an offender.
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
# akmon's own configuration, and the size family (C91)
# --------------------------------------------------------------------------------------

SIZE_FAMILY = ("C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915")


def _akmon_ruff() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["ruff"]


def test_akmon_runs_exactly_the_rules_it_offers():
    ruff = _akmon_ruff()
    assert ruff["extend"] == "profiles/ruff.toml"
    assert set(ruff) <= {"extend", "target-version", "lint"}
    assert set(ruff["lint"]) <= {"allowed-confusables"}  # no rule, ignore or per-file exception of its own


def test_akmon_meets_every_size_limit_without_an_exception():
    # --ignore-noqa: `ruff check` honours an inline suppression of a size code; this carrier does not.
    result = subprocess.run(
        [
            *(sys.executable, "-m", "ruff", "check", "--no-cache", "--ignore-noqa", "--output-format", "json"),
            *("--config", str(PROFILE), "--select", ",".join(SIZE_FAMILY), "."),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    offenders = [
        f"{Path(f['filename']).relative_to(ROOT).as_posix()}:{f['location']['row']} {f['code']}"
        for f in json.loads(result.stdout)
    ]
    assert offenders == [], "bring these under the profile's size limits"
