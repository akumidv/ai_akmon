"""``akmon init`` decides once what ``akmon check`` runs (ADR 0014 §4, as amended).

The project's own linters when it has any; ruff with akmon's rules — the standard ``extend`` —
when it has none; or nothing. Each case is pinned here against ``_setup_checks`` directly, with
nobody asked (the defaults ``--yes`` and a non-interactive run take).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from akmon import __version__, _init

RULES = "_aitna/akmon/profiles/ruff.toml"


def _setup(root: Path, choice: str | None = None, record_text: str = 'mount = "submodule"\n') -> tuple[dict, list]:
    record = root / "_aitna" / ".akmon.toml"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(record_text, encoding="utf-8")
    attach = _init._Attach(root, "_aitna", "submodule", previous=None)
    assert attach.rules_path == RULES
    _init._setup_checks(attach, record, choice, ask=False, log=lambda message: None)
    return tomllib.loads(record.read_text(encoding="utf-8")), attach.next_steps


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


def test_choosing_none_records_an_empty_table_and_says_where_checks_go(tmp_path):
    record, next_steps = _setup(tmp_path, choice="none")
    assert record["check"] == {}
    assert not (tmp_path / "ruff.toml").exists()
    assert any("[check]" in step for step in next_steps)
    assert (tmp_path / "_aitna" / ".akmon.toml").read_text(encoding="utf-8") == (
        'mount = "submodule"\n\n[check]\n'
        "# What `akmon check` runs: the project's own commands, `{files}` becoming the files a run covers.\n"
    )


def test_a_node_project_with_no_python_manifest_gets_no_ruff(tmp_path):
    """C129: ``package.json`` and no Python files — ruff has nothing to lint, so the default is
    the empty table ``--checks none`` records, and the next step says where the JS checks go."""
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    record, next_steps = _setup(tmp_path)
    assert record["check"] == {}
    assert not (tmp_path / "ruff.toml").exists()
    tag = _init._tag_for_version(__version__)
    assert next_steps == [
        "this project has package.json and no Python files, so no ruff was set up: name the project's "
        "own JavaScript checks under `[check]` in .akmon.toml, or move this mount to the JavaScript "
        "implementation of akmon, which needs no Python, with "
        "`node _aitna/akmon/js/akmon/cli.mjs init --ecosystem node`, then have it detect them with "
        "`node _aitna/akmon/js/akmon/cli.mjs init --checks own` (a first attach of a Node repository is "
        f"`npx github:akumidv/ai_akmon#{tag} init --mode submodule`)"
    ]


@pytest.mark.parametrize("python", ["requirements.txt", "Pipfile", "uv.lock", "app/x.py"])
def test_a_node_project_with_python_files_keeps_the_ruff_default(tmp_path, python):
    """C129 (owner accepted (a)): a requirements file, a lockfile or a Python source is Python, so
    ``package.json`` beside it does not turn the ruff default off."""
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / python).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / python).write_text("", encoding="utf-8")
    record, next_steps = _setup(tmp_path)
    assert "ruff" in record["check"]
    assert not any("no Python files" in step for step in next_steps)


def test_a_node_project_in_package_mode_is_named_no_switch(tmp_path):
    """The move to the JavaScript implementation serves a mounted record only (C129 step 8)."""
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    record = tmp_path / "_aitna" / ".akmon.toml"
    record.parent.mkdir(parents=True)
    record.write_text('mount = "package"\n', encoding="utf-8")
    attach = _init._Attach(tmp_path, "_aitna", "package", previous=None)
    _init._setup_checks(attach, record, None, ask=False, log=lambda message: None)
    assert attach.next_steps == [
        "this project has package.json and no Python files, so no ruff was set up: name the project's "
        "own JavaScript checks under `[check]` in .akmon.toml"
    ]


def test_an_explicit_akmon_choice_still_sets_up_ruff_in_a_node_project(tmp_path):
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    record, _ = _setup(tmp_path, choice="akmon")
    assert record["check"] == {"ruff": "ruff check {files}"}
    assert tomllib.loads((tmp_path / "ruff.toml").read_text(encoding="utf-8"))["extend"] == RULES


@pytest.mark.parametrize(
    ("manifest", "text"),
    [("pyproject.toml", '[project]\nname = "p"\n'), ("setup.py", ""), ("setup.cfg", "[metadata]\nname = p\n")],
)
def test_a_python_manifest_beside_package_json_keeps_the_ruff_default(tmp_path, manifest, text):
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / manifest).write_text(text, encoding="utf-8")
    record, _ = _setup(tmp_path)
    assert record["check"] == {"ruff": "ruff check {files}"}


def test_a_node_project_with_its_own_python_linter_keeps_it(tmp_path):
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "ruff.toml").write_text("line-length = 100\n", encoding="utf-8")
    record, _ = _setup(tmp_path)
    assert record["check"] == {"ruff": "ruff check {files}"}


def test_the_written_ruff_toml_is_the_shared_template(tmp_path):
    """The file verify's ``check.ruff-without-python`` matches byte for byte (``bin/sync.json``)."""
    _setup(tmp_path, choice="akmon")
    assert (tmp_path / "ruff.toml").read_bytes() == (
        b"# ruff with akmon's Python rules; adjust them here with extend-select, extend-ignore and\n"
        b'# per-file-ignores.\nextend = "_aitna/akmon/profiles/ruff.toml"\n'
    )


def test_a_realign_keeps_none(tmp_path):
    """C123: ``none`` is recorded, so the realign's ``--yes`` default (akmon's rules for a project
    with no linter) does not replace it."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "p"\n', encoding="utf-8")
    _setup(tmp_path, choice="none")
    path = tmp_path / "_aitna" / ".akmon.toml"
    recorded = path.read_text(encoding="utf-8")
    attach = _init._Attach(tmp_path, "_aitna", "submodule", previous=None)
    _init._setup_checks(attach, path, None, ask=False, log=lambda message: None)
    assert path.read_text(encoding="utf-8") == recorded
    assert not (tmp_path / "ruff.toml").exists()
    assert "tool" not in tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))


def test_choosing_own_with_nothing_found_records_an_empty_table_and_a_realign_keeps_it(tmp_path):
    """C123: ``own`` with no tool found records what ``none`` records, so the realign's ``--yes``
    default (akmon's rules for a project with no linter) does not replace it."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "p"\n', encoding="utf-8")
    record, next_steps = _setup(tmp_path, choice="own")
    assert record["check"] == {}
    path = tmp_path / "_aitna" / ".akmon.toml"
    recorded = path.read_text(encoding="utf-8")
    assert recorded == (
        'mount = "submodule"\n\n[check]\n'
        "# What `akmon check` runs: the project's own commands, `{files}` becoming the files a run covers.\n"
    )
    assert next_steps == ["no linter configuration was found: name the project's checks under `[check]` in .akmon.toml"]
    attach = _init._Attach(tmp_path, "_aitna", "submodule", previous=None)
    _init._setup_checks(attach, path, None, ask=False, log=lambda message: None)
    assert path.read_text(encoding="utf-8") == recorded
    assert not (tmp_path / "ruff.toml").exists()
    assert "tool" not in tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))


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


class _Terminal:
    """A stdin that is a terminal; ``input`` is patched separately."""

    def isatty(self) -> bool:
        return True


def test_end_of_input_at_a_terminal_prompt_is_not_confirmed(monkeypatch, capsys):
    def _eof(prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr(_init.sys, "stdin", _Terminal())
    monkeypatch.setattr("builtins.input", _eof)
    assert _init._confirm("attach?") is False  # as the JS twin: end of input does not confirm
    assert capsys.readouterr().out == "\n"


def test_a_terminal_answer_confirms_on_empty_or_yes_only(monkeypatch):
    monkeypatch.setattr(_init.sys, "stdin", _Terminal())
    for answer, confirmed in (("", True), (" Y ", True), ("yes", True), ("n", False), ("maybe", False)):
        monkeypatch.setattr("builtins.input", lambda prompt, answer=answer: answer)
        assert _init._confirm("attach?") is confirmed


_EMPTY_CHECK = (
    'mount = "submodule"\n\n[check]\n'
    "# What `akmon check` runs: the project's own commands, `{files}` becoming the files a run covers.\n"
)


def test_an_explicit_checks_flag_decides_an_empty_check_table_again(tmp_path):
    """C129 audit F4: the owner asks again — ``--checks`` re-decides a table that records nothing
    (the JavaScript twin is ``withoutEmptyChecks``); one table is left, never two."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "p"\n\n[tool.ruff]\n', encoding="utf-8")
    record, _ = _setup(tmp_path, choice="own", record_text=_EMPTY_CHECK)
    assert "ruff" in record["check"]
    text = (tmp_path / "_aitna" / ".akmon.toml").read_text(encoding="utf-8")
    assert text.count("[check]") == 1


def test_no_flag_keeps_an_empty_check_table_and_a_flag_keeps_a_named_one(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "p"\n\n[tool.ruff]\n', encoding="utf-8")
    record, _ = _setup(tmp_path, choice=None, record_text=_EMPTY_CHECK)
    assert record["check"] == {}
    named = _EMPTY_CHECK + 'mypy = "uv run mypy"\n'
    record, _ = _setup(tmp_path, choice="akmon", record_text=named)
    assert record["check"] == {"mypy": "uv run mypy"}


def test_without_empty_checks_cuts_only_an_empty_single_table():
    assert _init._without_empty_checks(_EMPTY_CHECK) == 'mount = "submodule"\n'
    assert _init._without_empty_checks(_EMPTY_CHECK + 'x = "y"\n') is None
    assert _init._without_empty_checks(_EMPTY_CHECK + "[check.sub]\n") is None
    assert _init._without_empty_checks('mount = "submodule"\n') is None
