"""``akmon init`` decides once what ``akmon check`` runs (ADR 0014 §4, as amended).

The project's own linters when it has any; ruff with akmon's rules — the standard ``extend`` —
when it has none; or nothing. Each case is pinned here against ``_setup_checks`` directly, with
nobody asked (the defaults ``--yes`` and a non-interactive run take).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from akmon import _init

RULES = "_aitna/akmon/profiles/ruff.toml"


def _setup(root: Path, choice: str | None = None, record_text: str = 'mount = "submodule"\n') -> tuple[dict, list]:
    record = root / "_aitna" / ".akmon.toml"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(record_text, encoding="utf-8")
    next_steps: list[str] = []
    _init._setup_checks(root, record, RULES, choice, ask=False, log=lambda message: None, next_steps=next_steps)
    return tomllib.loads(record.read_text(encoding="utf-8")), next_steps


def test_a_project_with_its_own_linters_runs_them_through_its_manager_untouched(tmp_path):
    pyproject = '[project]\nname = "p"\n\n[tool.ruff]\nline-length = 100\n'
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (tmp_path / "mypy.ini").write_text("[mypy]\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")

    record, next_steps = _setup(tmp_path)
    assert record["check"] == {"ruff": "uv run ruff check {files}", "mypy": "uv run mypy {files}"}
    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == pyproject  # its own rules win
    assert next_steps == []


def test_flake8_and_pylint_are_found_in_their_own_files(tmp_path):
    (tmp_path / "setup.cfg").write_text("[metadata]\nname = p\n\n[flake8]\nmax-line-length = 99\n", encoding="utf-8")
    (tmp_path / ".pylintrc").write_text("[MAIN]\n", encoding="utf-8")
    record, _ = _setup(tmp_path)
    assert record["check"] == {"flake8": "flake8 {files}", "pylint": "pylint {files}"}


def test_a_project_with_no_linter_gets_ruff_with_akmons_rules_the_standard_way(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "p"\n', encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")

    record, next_steps = _setup(tmp_path)
    assert record["check"] == {"ruff": "uv run ruff check {files}"}
    pyproject = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["tool"]["ruff"]["extend"] == RULES
    assert next_steps == ["add ruff as a development dependency so `akmon check` can run it: `uv add --dev ruff`"]


def test_without_a_pyproject_the_rules_arrive_in_a_ruff_toml(tmp_path):
    record, _ = _setup(tmp_path)
    assert record["check"] == {"ruff": "ruff check {files}"}
    assert tomllib.loads((tmp_path / "ruff.toml").read_text(encoding="utf-8"))["extend"] == RULES


def test_choosing_none_records_nothing_and_says_where_checks_go(tmp_path):
    record, next_steps = _setup(tmp_path, choice="none")
    assert "check" not in record
    assert not (tmp_path / "ruff.toml").exists()
    assert any("[check]" in step for step in next_steps)


def test_a_realign_leaves_an_existing_choice_alone(tmp_path):
    (tmp_path / ".flake8").write_text("[flake8]\n", encoding="utf-8")
    record, _ = _setup(tmp_path, record_text='[check]\nlint = "make lint"\n')
    assert record["check"] == {"lint": "make lint"}


def test_akmons_rules_never_replace_an_extend_the_project_already_chose(tmp_path):
    pyproject = '[project]\nname = "p"\n\n[tool.ruff]\nextend = "../shared/ruff.toml"\n'
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    record, next_steps = _setup(tmp_path, choice="akmon")
    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == pyproject
    assert record["check"] == {"ruff": "ruff check {files}"}
    assert any("already extends `../shared/ruff.toml`" in step for step in next_steps)
