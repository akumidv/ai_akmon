"""The Python rule catalog, ``profiles/python.rules.toml`` — the one owner of every checked rule.

ADR 0014 §3 makes the catalog data with four readers: akmon's consumer check, akmon's own ruff
configuration, the profile prose that cites rule ids, and a printed ruff fragment. These carriers
hold the catalog's shape and the prose's citations to it, so no reader meets a rule it cannot
interpret or a citation that names nothing.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "profiles" / "python.rules.toml"

_FIELDS = {"source", "text", "ruff", "check", "default", "tests", "params"}
_CHECKS = {"ast", "formatter", "ruff"}
_SEVERITIES = {"error", "warn", "off"}
_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_SOURCE_RE = re.compile(r"^(?:google:\d+(?:\.\d+)*|akmon)$")
_RUFF_CODE_RE = re.compile(r"^[A-Z]+[0-9]*$")
_CITATION_RE = re.compile(r"`python:([a-z0-9-]+)`")


def _catalog() -> dict:
    with CATALOG_PATH.open("rb") as handle:
        return tomllib.load(handle)


def _rules() -> dict[str, dict]:
    return _catalog()["rule"]


def test_every_rule_carries_exactly_the_catalog_fields():
    rules = _rules()
    assert rules
    for rule_id, rule in rules.items():
        assert _ID_RE.match(rule_id), rule_id
        assert set(rule) == _FIELDS, (rule_id, sorted(set(rule) ^ _FIELDS))


def test_every_field_holds_a_value_its_readers_understand():
    for rule_id, rule in _rules().items():
        assert _SOURCE_RE.match(rule["source"]), (rule_id, rule["source"])
        assert rule["text"].endswith("."), rule_id
        assert rule["check"] in _CHECKS, (rule_id, rule["check"])
        assert rule["default"] in _SEVERITIES, (rule_id, rule["default"])
        assert rule["tests"] in {"on", "off"}, (rule_id, rule["tests"])
        assert isinstance(rule["params"], dict), rule_id
        assert isinstance(rule["ruff"], list), rule_id
        for code in rule["ruff"]:
            assert _RUFF_CODE_RE.match(code), (rule_id, code)


def test_no_ruff_code_belongs_to_two_rules():
    """A code in two rules would give akmon's ruff and the consumer check two owners of one
    finding, and a `# noqa` naming it would suppress two rules at once."""
    owners: dict[str, str] = {}
    for rule_id, rule in _rules().items():
        for code in rule["ruff"]:
            assert code not in owners, (code, owners.get(code), rule_id)
            owners[code] = rule_id


def test_a_formatter_rule_is_never_on_for_a_consumer():
    """Layout belongs to the project's own formatter; the consumer check never becomes a second
    owner of it."""
    for rule_id, rule in _rules().items():
        if rule["check"] == "formatter":
            assert rule["default"] == "off", rule_id


def test_an_akmon_only_rule_is_never_on_for_a_consumer():
    """``check = "ruff"`` means no consumer implementation exists, so a default other than
    ``off`` would promise a check that never runs."""
    for rule_id, rule in _rules().items():
        if rule["check"] == "ruff":
            assert rule["default"] == "off", rule_id


def test_every_environment_names_a_shipped_profile_and_known_rules():
    environments = _catalog()["environment"]
    assert environments
    rules = _rules()
    for name, environment in environments.items():
        assert (ROOT / "profiles" / environment["profile"]).is_file(), name
        assert environment["rules"], name
        assert set(environment["rules"]) <= set(rules), name


def test_akmons_own_overrides_name_a_rule_parameter_that_exists():
    rules = _rules()
    for rule_id, override in _catalog()["akmon"].items():
        assert rule_id in rules, rule_id
        assert set(override) <= set(rules[rule_id]["params"]), rule_id


def test_every_rule_the_docs_cite_is_in_the_catalog():
    """A document names a checked rule as `python:<id>` and never restates it; a citation of an
    id the catalog lacks points a reader at nothing."""
    catalog = set(_rules())
    cited: dict[str, set[str]] = {}
    for path in [*sorted((ROOT / "profiles").glob("*.md")), *sorted((ROOT / "guardrails").glob("*.md"))]:
        ids = set(_CITATION_RE.findall(path.read_text(encoding="utf-8")))
        if ids:
            cited[path.name] = ids
    assert cited, "no document cites a catalog rule — the citation form changed?"
    for name, ids in cited.items():
        assert ids <= catalog, (name, sorted(ids - catalog))
