"""``akmon check`` — the consumer half of the Python rule catalog (ADR 0014 §4, C89 slice 2).

Three layers of carrier: every ``ast`` rule in the catalog has an implementation and a fixture
pair it fails and passes; the ``[python]`` configuration is validated strictly and applied in a
fixed order; and the launcher lists, suppresses, reports and exits as the design says.
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import check as check_cli
import pytest

from common import python_rules
from common.python_rule_checks import RULES

ROOT = Path(__file__).resolve().parents[2]
CATALOG = python_rules.load_catalog(ROOT)
CHECKED = python_rules.checked_rules(CATALOG)

# rule id -> (source that breaks the rule, source that keeps it)
CASES: dict[str, tuple[str, str]] = {
    "specific-suppression": ("x = 1  # noqa\n", "x = 1  # noqa: E501\n"),
    "import-modules": ("from collections import OrderedDict\n", "from os import path\n"),
    "no-wildcard-import": ("from os import *\n", "import os\n"),
    "absolute-imports": ("from . import sibling\n", "from pkg import sibling\n"),
    "no-bare-except": ("try:\n    x()\nexcept:\n    raise\n", "try:\n    x()\nexcept ValueError:\n    raise\n"),
    "no-broad-except": (
        "try:\n    x()\nexcept Exception:\n    log()\n",
        "try:\n    x()\nexcept Exception:\n    log()\n    raise\n",
    ),
    "no-silent-except": ("try:\n    x()\nexcept Exception:\n    pass\n", "try:\n    x()\nexcept KeyError:\n    pass\n"),
    "no-assert-validation": ("assert x\n", "if not x:\n    raise ValueError(x)\n"),
    "raise-from": (
        "try:\n    x()\nexcept KeyError:\n    raise ValueError('k')\n",
        "try:\n    x()\nexcept KeyError:\n    raise ValueError('k') from None\n",
    ),
    "exception-suffix": ("class Oops(Exception):\n    pass\n", "class OopsError(Exception):\n    pass\n"),
    "no-global-statement": ("def f():\n    global X\n    X = 1\n", "def f():\n    return 1\n"),
    "simple-comprehension": ("y = [a for a in x for b in a]\n", "y = [a for a in x if a]\n"),
    "default-iterator": ("for k in d.keys():\n    pass\n", "for k in d:\n    pass\n"),
    "lambda-use": ("f = lambda x: x\n", "def f(x):\n    return x\n"),
    "no-mutable-default": ("def f(x=[]):\n    return x\n", "def f(x=()):\n    return x\n"),
    "none-and-bool-compare": ("if x == None:\n    pass\n", "if x is None:\n    pass\n"),
    "implicit-false": ("if len(x):\n    pass\n", "if x:\n    pass\n"),
    "no-staticmethod": ("class A:\n    @staticmethod\n    def f():\n        pass\n", "def f():\n    pass\n"),
    "no-power-features": ("getattr(obj, name)\n", "getattr(obj, 'name')\n"),
    "annotate-public": ("def f(x):\n    return x\n", "def f(x: int) -> int:\n    return x\n"),
    "explicit-optional": (
        "def f(x: int = None) -> None:\n    pass\n",
        "def f(x: int | None = None) -> None:\n    pass\n",
    ),
    "docstrings": ('"""Mod."""\n\n\ndef f():\n    pass\n', '"""Mod."""\n\n\ndef f():\n    """Do f."""\n'),
    "no-string-concat-loop": ("s = ''\nfor x in y:\n    s += 'a'\n", "s = ''.join('a' for x in y)\n"),
    "logging-format": ("logger.info(f'{x}')\n", "logger.info('%s', x)\n"),
    "open-with-context": ("f = open(p)\n", "with open(p) as f:\n    pass\n"),
    "todo-format": ("# TODO fix this\n", "# TODO: https://example.com/1 - fix this\n"),
    "naming": ("class my_class:\n    pass\n", "class MyClass:\n    pass\n"),
    "short-names": ("q = 1\n", "count = 1\n"),
    "function-length": ("def f():\n" + "    x = 1\n" * 45, "def f():\n    return 1\n"),
    "no-blocking-in-async": (
        "import time\n\n\nasync def f():\n    time.sleep(1)\n",
        "import asyncio\n\n\nasync def f():\n    await asyncio.sleep(1)\n",
    ),
    "stdlib-only": ("import requests\n", "import json\n"),
}


def _only(rule_id: str, **params: object) -> python_rules.Settings:
    severity = dict.fromkeys(CHECKED, "off")
    severity[rule_id] = "error"
    effective = {name: dict(rule["params"]) for name, rule in CHECKED.items()}
    effective[rule_id].update(params)
    return python_rules.Settings(severity=severity, params=effective)


def _hits(rule_id: str, source: str, root: Path, relative: str = "pkg/mod.py", **params: object) -> list:
    settings = _only(rule_id, **params)
    findings = python_rules.check_source(root, relative, textwrap.dedent(source), CATALOG, settings)
    return [finding for finding in findings if finding.code == f"python.{rule_id}"]


def test_every_ast_rule_in_the_catalog_has_an_implementation_and_no_other_does():
    assert set(RULES) == set(CHECKED)


def test_every_implemented_rule_has_a_fixture_pair():
    assert set(CASES) == set(RULES)


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_a_rule_flags_its_bad_case_and_passes_its_good_one(rule_id, tmp_path):
    bad, good = CASES[rule_id]
    assert _hits(rule_id, bad, tmp_path), rule_id
    assert _hits(rule_id, good, tmp_path) == [], rule_id


def test_naming_leaves_a_nested_class_body_and_a_global_name_alone(tmp_path):
    """Two false positives the attached consumer's tests surfaced, both of which ruff's N806
    rightly ignores: constants in the body of a class defined inside a test, and a module global
    a function rebinds after declaring it ``global``."""
    source = """
    START_TS = None


    def test_enum():
        class Codes:
            TEST_1 = "a"

        global START_TS
        START_TS = 1
    """
    assert _hits("naming", source, tmp_path) == []


def test_the_module_name_is_held_to_lower_with_under_only_inside_a_package(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    assert _hits("naming", "x = 1\n", tmp_path, relative="pkg/Bad-Name.py")
    assert _hits("naming", "x = 1\n", tmp_path, relative="scripts/run-me.py") == []


# --------------------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("table", "fragment"),
    [
        ({"rules": {"no-such-rule": "off"}}, "unknown rule 'no-such-rule'"),
        ({"rules": {"layout": "warn"}}, "does not run (check = 'formatter')"),
        ({"rules": {"function-length": {"max_lines": "sixty"}}}, "max_lines must be a int"),
        ({"rules": {"function-length": {"max_line": 60}}}, "unknown parameter 'max_line'"),
        ({"rules": {"naming": "loud"}}, "severity must be error, warn or off"),
        ({"environments": {"lambda": ["x/**"]}}, "unknown environment 'lambda'"),
        ({"per-path": {"legacy/**": {"no-such-rule": "off"}}}, "does not run: 'no-such-rule'"),
        ({"exclude": "demo"}, "exclude must be a list"),
        ({"rule": {}}, "unknown key 'rule'"),
    ],
)
def test_a_configuration_mistake_is_reported_not_guessed_at(table, fragment):
    _, problems = python_rules.read_settings(CATALOG, table)
    assert any(fragment in problem for problem in problems), problems


def test_a_valid_configuration_reports_nothing_and_takes_effect():
    settings, problems = python_rules.read_settings(
        CATALOG, {"rules": {"no-staticmethod": "off", "function-length": {"severity": "error", "max_lines": 60}}}
    )
    assert problems == []
    assert python_rules.effective_severity("no-staticmethod", "a.py", CATALOG, settings) == "off"
    assert python_rules.effective_severity("function-length", "a.py", CATALOG, settings) == "error"
    assert settings.params["function-length"]["max_lines"] == 60


def test_severity_resolves_in_order_default_tests_environment_per_path():
    settings, problems = python_rules.read_settings(
        CATALOG,
        {"environments": {"stdlib": ["tools/boot/**"]}, "per-path": {"tests/legacy/**": {"annotate-public": "warn"}}},
    )
    assert problems == []
    severity = python_rules.effective_severity
    assert severity("annotate-public", "src/a.py", CATALOG, settings) == "warn"
    assert severity("annotate-public", "tests/test_a.py", CATALOG, settings) == "off"  # the catalog's tests = off
    assert severity("annotate-public", "tests/legacy/test_a.py", CATALOG, settings) == "warn"  # per-path wins
    assert severity("stdlib-only", "src/a.py", CATALOG, settings) == "off"
    assert severity("stdlib-only", "tools/boot/setup.py", CATALOG, settings) == "error"  # the environment's paths


# --------------------------------------------------------------------------------------
# suppression and parsing
# --------------------------------------------------------------------------------------


def test_a_line_is_suppressed_by_its_rule_id_or_by_a_noqa_naming_a_mapped_code(tmp_path):
    bad = "try:\n    x()\nexcept:  {}\n    raise\n"
    assert _hits("no-bare-except", bad.format("# akmon: ignore[no-bare-except] legacy shim"), tmp_path) == []
    assert _hits("no-bare-except", bad.format("# noqa: E722"), tmp_path) == []
    assert _hits("no-bare-except", bad.format("# noqa"), tmp_path)  # a bare noqa suppresses nothing
    assert _hits("no-bare-except", bad.format("# noqa: E501"), tmp_path)  # nor does another rule's code


def test_a_suppression_without_a_rule_or_a_reason_is_itself_a_finding(tmp_path):
    assert _hits("specific-suppression", "x = 1  # akmon: ignore\n", tmp_path)
    assert _hits("specific-suppression", "x = 1  # akmon: ignore[naming]\n", tmp_path)
    assert _hits("specific-suppression", "x = 1  # akmon: ignore[naming] generated code\n", tmp_path) == []


def test_a_file_that_does_not_parse_is_reported_not_raised(tmp_path):
    findings = python_rules.check_source(tmp_path, "a.py", "def (:\n", CATALOG, _only("naming"))
    assert [finding.code for finding in findings] == ["python.parse-error"]
    assert findings[0].severity == "warn"


# --------------------------------------------------------------------------------------
# the launcher
# --------------------------------------------------------------------------------------


def _project(tmp_path: Path, toml: str = "") -> Path:
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (tmp_path / "_aitna").mkdir()
    (tmp_path / "_aitna" / ".akmon.toml").write_text(toml, encoding="utf-8")
    return tmp_path


def test_check_exits_one_on_an_error_and_zero_once_the_rule_is_off(tmp_path, capsys):
    root = _project(tmp_path)
    module = root / "mod.py"
    module.write_text('"""Mod."""\n\ntry:\n    pass\nexcept:\n    raise\n', encoding="utf-8")
    assert check_cli.main(["--project-root", str(root), str(module)]) == 1
    assert "ERROR python.no-bare-except mod.py:5:1" in capsys.readouterr().out

    (root / "_aitna" / ".akmon.toml").write_text('[python.rules]\nno-bare-except = "off"\n', encoding="utf-8")
    assert check_cli.main(["--project-root", str(root), str(module)]) == 0


def test_a_broken_record_is_a_configuration_error_not_a_default(tmp_path, capsys):
    root = _project(tmp_path, "[python\n")
    (root / "mod.py").write_text('"""Mod."""\n', encoding="utf-8")
    assert check_cli.main(["--project-root", str(root), str(root / "mod.py")]) == 1
    assert "ERROR python.config" in capsys.readouterr().out


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        check=True,
        capture_output=True,
    )


def test_changed_checks_only_what_differs_from_head_and_never_the_dev_layer(tmp_path):
    root = _project(tmp_path)
    (root / "old.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "base")
    (root / "new.py").write_text("y = 2\n", encoding="utf-8")
    (root / "_aitna" / "tool.py").write_text("z = 3\n", encoding="utf-8")
    settings, _ = python_rules.read_settings(CATALOG, {})

    assert python_rules.project_files(root, settings, changed=True) == ["new.py"]
    assert python_rules.project_files(root, settings) == ["new.py", "old.py"]


def test_print_ruff_selects_the_codes_of_the_rules_that_run(tmp_path, capsys):
    root = _project(tmp_path, '[python.rules]\nno-bare-except = "off"\n')
    assert check_cli.main(["--project-root", str(root), "--print-ruff"]) == 0
    fragment = capsys.readouterr().out
    assert '"B006"' in fragment  # no-mutable-default runs by default
    assert '"E722"' not in fragment  # switched off above
    assert 'convention = "google"' in fragment


def test_nothing_in_a_private_module_is_public_api(tmp_path):
    source = "def f():\n    pass\n"
    assert _hits("docstrings", source, tmp_path, relative="pkg/_impl.py") == []
    assert _hits("docstrings", source, tmp_path, relative="pkg/_internal/mod.py") == []
    assert _hits("docstrings", source, tmp_path, relative="pkg/__init__.py")


def test_verify_validates_the_python_table_and_not_the_code(tmp_path):
    """``verify`` owns integration health: a misspelled rule id in the record is its business,
    a finding in the project's code is ``akmon check``'s."""
    import verify

    root = _project(tmp_path, '[python.rules]\nno-staticmehtod = "off"\n')
    (root / "mod.py").write_text("try:\n    pass\nexcept:\n    raise\n", encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.check_python_config()
    assert [(f.severity, f.code) for f in verifier.findings] == [("error", "python.config")]
    assert "no-staticmehtod" in verifier.findings[0].message

    (root / "_aitna" / ".akmon.toml").write_text('[python.rules]\nno-staticmethod = "off"\n', encoding="utf-8")
    verifier = verify.Verifier(root)
    verifier.check_python_config()
    assert [(f.severity, f.code) for f in verifier.findings] == [("ok", "python.config")]
