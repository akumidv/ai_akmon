#!/usr/bin/env python3
"""akmon's Python check — the consumer half of the rule catalog (ADR 0014 §3-4).

``profiles/python.rules.toml`` owns every Python rule a program checks: its text, its ruff
codes, its default severity and parameters. This module applies the rules marked
``check = "ast"`` to a project's code, configured by the ``[python]`` table of the integration
record; the rule implementations live in ``common/python_rule_checks.py``, one function per
catalog id.

A consumer never needs ruff, or any linter, for this: ruff is akmon's own development
dependency. The check is stdlib-only (``ast``, ``tokenize``, ``fnmatch``) and parses with the
interpreter that runs it, so a file using newer syntax is reported as ``parse-error`` rather than
checked — the reason ``akmon check`` is best run from the project's own environment.
"""

from __future__ import annotations

import ast
import fnmatch
import io
import re
import subprocess
import sys
import tokenize
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from common.findings import Finding
from common.project_root import aitna_root_name
from common.python_rule_checks import RULES, Source

CATALOG = Path("profiles") / "python.rules.toml"
CONFIG_TARGET = ".akmon.toml [python]"

_SEVERITIES = ("error", "warn", "off")
_CONFIG_KEYS = {"exclude", "environments", "rules", "per-path"}
_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist", ".tox"}
_IGNORE_RE = re.compile(r"#\s*akmon:\s*ignore\[([^\]]*)\]\s*(.*)$")
_NOQA_RE = re.compile(r"#\s*noqa:\s*([A-Z][A-Z0-9]*(?:\s*,\s*[A-Z][A-Z0-9]*)*)")


def load_catalog(tree_root: Path) -> dict:
    """The catalog shipped with ``tree_root`` — the standard tree that is running."""
    import tomllib

    with (tree_root / CATALOG).open("rb") as handle:
        return tomllib.load(handle)


def checked_rules(catalog: Mapping) -> dict[str, dict]:
    """The rules this check implements: ``check = "ast"``. Formatter-owned and akmon-only rules
    are catalogued for akmon's own ruff and never run here."""
    return {rule_id: rule for rule_id, rule in catalog["rule"].items() if rule["check"] == "ast"}


@dataclass(frozen=True)
class Settings:
    """The project's configuration, validated: what it set, and nothing it merely misspelled."""

    severity: Mapping[str, str] = field(default_factory=dict)
    params: Mapping[str, Mapping[str, object]] = field(default_factory=dict)
    exclude: tuple[str, ...] = ()
    environments: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    per_path: tuple[tuple[str, Mapping[str, str]], ...] = ()


def _string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _same_type(value: object, default: object) -> bool:
    if isinstance(default, list):
        return _string_list(value)
    return type(value) is type(default)


def _read_rules(catalog: Mapping, raw: object, problems: list[str]) -> tuple[dict, dict]:
    checked = checked_rules(catalog)
    severity: dict[str, str] = {}
    params = {rule_id: dict(rule["params"]) for rule_id, rule in checked.items()}
    if not isinstance(raw, dict):
        problems.append("[python.rules] must be a table")
        return severity, params
    for rule_id, value in raw.items():
        if rule_id not in catalog["rule"]:
            problems.append(f"[python.rules] names an unknown rule {rule_id!r}")
            continue
        if rule_id not in checked:
            kind = catalog["rule"][rule_id]["check"]
            problems.append(f"[python.rules] sets {rule_id!r}, which akmon check does not run (check = {kind!r})")
            continue
        table = {"severity": value} if isinstance(value, str) else value
        if not isinstance(table, dict):
            problems.append(f"[python.rules].{rule_id} must be a severity or a table")
            continue
        defaults = checked[rule_id]["params"]
        for key, item in table.items():
            if key == "severity":
                if item in _SEVERITIES:
                    severity[rule_id] = item
                else:
                    problems.append(f"[python.rules].{rule_id} severity must be error, warn or off, got {item!r}")
            elif key not in defaults:
                problems.append(f"[python.rules].{rule_id} has an unknown parameter {key!r}")
            elif not _same_type(item, defaults[key]):
                expected = type(defaults[key]).__name__
                problems.append(f"[python.rules].{rule_id}.{key} must be a {expected}, got {item!r}")
            else:
                params[rule_id][key] = item
    return severity, params


def _read_per_path(catalog: Mapping, raw: object, problems: list[str]) -> tuple[tuple[str, dict[str, str]], ...]:
    if not isinstance(raw, dict):
        problems.append("[python.per-path] must be a table")
        return ()
    checked = checked_rules(catalog)
    entries = []
    for pattern, overrides in raw.items():
        if not isinstance(overrides, dict):
            problems.append(f"[python.per-path].{pattern!r} must be a table of rule severities")
            continue
        kept = {}
        for rule_id, level in overrides.items():
            if rule_id not in checked:
                problems.append(f"[python.per-path].{pattern!r} names a rule akmon check does not run: {rule_id!r}")
            elif level not in _SEVERITIES:
                problems.append(f"[python.per-path].{pattern!r}.{rule_id} must be error, warn or off, got {level!r}")
            else:
                kept[rule_id] = level
        entries.append((pattern, kept))
    return tuple(entries)


def read_settings(catalog: Mapping, table: object) -> tuple[Settings, list[str]]:
    """The settings in the record's ``[python]`` table, and every problem found in it.

    Strict by design: an unknown key, rule, environment or parameter, or a value of the wrong
    type, is a problem to report, and the key is ignored rather than guessed at — a misspelled
    ``off`` that silently left a rule on is exactly what this refuses to do.
    """
    problems: list[str] = []
    if table is None:
        table = {}
    if not isinstance(table, dict):
        return Settings(params={k: dict(r["params"]) for k, r in checked_rules(catalog).items()}), [
            "[python] must be a table"
        ]
    problems.extend(f"[python] has an unknown key {key!r}" for key in sorted(set(table) - _CONFIG_KEYS))
    exclude = table.get("exclude", [])
    if not _string_list(exclude):
        problems.append("[python].exclude must be a list of glob patterns")
        exclude = []
    environments: dict[str, tuple[str, ...]] = {}
    raw_environments = table.get("environments", {})
    if not isinstance(raw_environments, dict):
        problems.append("[python].environments must be a table of path lists")
        raw_environments = {}
    for name, patterns in raw_environments.items():
        if f"python-{name}" not in catalog.get("environment", {}):
            problems.append(f"[python].environments names an unknown environment {name!r}")
        elif not _string_list(patterns):
            problems.append(f"[python].environments.{name} must be a list of glob patterns")
        else:
            environments[f"python-{name}"] = tuple(patterns)
    severity, params = _read_rules(catalog, table.get("rules", {}), problems)
    per_path = _read_per_path(catalog, table.get("per-path", {}), problems)
    return Settings(severity, params, tuple(exclude), environments, per_path), problems


def is_test_module(relative: str) -> bool:
    """A test module by the conventions every Python test runner shares."""
    parts = relative.split("/")
    name = parts[-1]
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
        or any(part in {"test", "tests"} for part in parts[:-1])
    )


def _matches(relative: str, patterns: tuple[str, ...] | list[str]) -> bool:
    return any(fnmatch.fnmatchcase(relative, pattern) for pattern in patterns)


def effective_severity(rule_id: str, relative: str, catalog: Mapping, settings: Settings) -> str:
    """What one rule is for one file: the configured or default severity, off in tests when the
    catalog says so, on where an environment the file runs in brings the rule, and finally the
    project's per-path overrides, the last matching one winning."""
    rule = catalog["rule"][rule_id]
    level = settings.severity.get(rule_id, rule["default"])
    if rule["tests"] == "off" and is_test_module(relative):
        level = "off"
    for environment, patterns in settings.environments.items():
        if rule_id in catalog["environment"][environment]["rules"] and _matches(relative, patterns):
            level = settings.severity.get(rule_id, "error")
    for pattern, overrides in settings.per_path:
        if rule_id in overrides and fnmatch.fnmatchcase(relative, pattern):
            level = overrides[rule_id]
    return level


def _comments(text: str) -> list[tuple[int, int, str]]:
    try:
        return [
            (token.start[0], token.start[1], token.string)
            for token in tokenize.generate_tokens(io.StringIO(text).readline)
            if token.type == tokenize.COMMENT
        ]
    except (tokenize.TokenError, SyntaxError):
        return []


def _suppressions(comments: list[tuple[int, int, str]]) -> dict[int, tuple[set[str], set[str]]]:
    """Per line: the rule ids an ``# akmon: ignore[...]`` names, and the codes a ``# noqa:`` names."""
    by_line: dict[int, tuple[set[str], set[str]]] = {}
    for line, _, comment in comments:
        ids, codes = by_line.setdefault(line, (set(), set()))
        ignore = _IGNORE_RE.search(comment)
        if ignore:
            ids.update(part.strip() for part in ignore.group(1).split(",") if part.strip())
        noqa = _NOQA_RE.search(comment)
        if noqa:
            codes.update(code.strip() for code in noqa.group(1).split(","))
    return by_line


def _suppressed(rule_id: str, rule: Mapping, entry: tuple[set[str], set[str]] | None) -> bool:
    if entry is None:
        return False
    ids, codes = entry
    return rule_id in ids or any(code.startswith(ruff) for code in codes for ruff in rule["ruff"])


def _fix(rule_id: str) -> str:
    return f"Change the code to meet python:{rule_id}, or suppress the line with `# akmon: ignore[{rule_id}] <reason>`"


def check_source(root: Path, relative: str, text: str, catalog: Mapping, settings: Settings) -> list[Finding]:
    """Every finding for one file's source text."""
    try:
        tree = ast.parse(text, filename=relative)
    except (SyntaxError, ValueError) as exc:
        line = getattr(exc, "lineno", None) or 1
        version = f"{sys.version_info.major}.{sys.version_info.minor}"
        return [
            Finding(
                "warn",
                "python.parse-error",
                f"does not parse under Python {version}, so it was not checked: {getattr(exc, 'msg', exc)}",
                f"{relative}:{line}",
                "Run akmon check under the project's own interpreter, for example `uv run akmon check`",
            )
        ]
    comments = _comments(text)
    source = Source(root, relative, tree, text.splitlines(), comments, is_test_module(relative))
    suppressions = _suppressions(comments)
    findings = []
    for rule_id, rule in checked_rules(catalog).items():
        level = effective_severity(rule_id, relative, catalog, settings)
        if level == "off":
            continue
        for line, column, message in RULES[rule_id](source, settings.params[rule_id]):
            if _suppressed(rule_id, rule, suppressions.get(line)):
                continue
            findings.append(Finding(level, f"python.{rule_id}", message, f"{relative}:{line}:{column}", _fix(rule_id)))
    return findings


class ScopeError(RuntimeError):
    """The files to check could not be listed."""


def _git_names(root: Path, *args: str) -> list[str]:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True)
    return [name for name in result.stdout.decode("utf-8", "replace").split("\0") if name]


def _walk(root: Path) -> list[str]:
    return [
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if not any(part in _SKIP_DIRS for part in path.relative_to(root).parts)
    ]


def project_files(root: Path, settings: Settings, *, changed: bool = False) -> list[str]:
    """The Python files in scope: tracked and untracked-but-not-ignored ones, or with ``changed``
    only those that differ from ``HEAD`` — never the dev layer, never an excluded path."""
    try:
        if changed:
            names = _git_names(root, "diff", "--name-only", "-z", "HEAD", "--")
            names += _git_names(root, "ls-files", "--others", "--exclude-standard", "-z")
        else:
            names = _git_names(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    except (OSError, subprocess.CalledProcessError) as exc:
        if changed:
            raise ScopeError(f"cannot list the files changed against HEAD: {exc}") from exc
        names = _walk(root)
    dev_layer = f"{aitna_root_name()}/"
    return sorted(
        {
            name
            for name in names
            if name.endswith(".py")
            and not name.startswith(dev_layer)
            and not _matches(name, settings.exclude)
            and (root / name).is_file()
        }
    )


def check_files(root: Path, files: list[str], catalog: Mapping, settings: Settings) -> list[Finding]:
    findings = []
    for relative in files:
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(
                Finding(
                    "warn",
                    "python.parse-error",
                    f"cannot be read, so it was not checked: {exc}",
                    relative,
                    "Make the file readable as UTF-8 or exclude it in [python].exclude",
                )
            )
            continue
        findings.extend(check_source(root, relative, text, catalog, settings))
    return findings


def ruff_fragment(catalog: Mapping, settings: Settings) -> str:
    """A ruff configuration fragment selecting the codes of every rule this project runs, for a
    project that also uses ruff and wants the two to agree. Printed, never written."""
    selected, test_ignores = [], []
    for rule_id, rule in checked_rules(catalog).items():
        if settings.severity.get(rule_id, rule["default"]) == "off":
            continue
        selected.extend(rule["ruff"])
        if rule["tests"] == "off":
            test_ignores.extend(rule["ruff"])

    def toml_list(codes: list[str]) -> str:
        return "[" + ", ".join(f'"{code}"' for code in codes) + "]"

    lines = ["[tool.ruff.lint]", f"extend-select = {toml_list(selected)}"]
    if settings.severity.get("docstrings", catalog["rule"]["docstrings"]["default"]) != "off":
        lines += ["", "[tool.ruff.lint.pydocstyle]", 'convention = "google"']
    if settings.severity.get("absolute-imports", catalog["rule"]["absolute-imports"]["default"]) != "off":
        lines += ["", "[tool.ruff.lint.flake8-tidy-imports]", 'ban-relative-imports = "all"']
    if test_ignores:
        lines += ["", "[tool.ruff.lint.per-file-ignores]"]
        lines += [f'"{pattern}" = {toml_list(test_ignores)}' for pattern in ("**/test_*.py", "**/tests/**")]
    return "\n".join(lines) + "\n"
