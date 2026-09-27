#!/usr/bin/env python3
"""Unit-table probe for the Python implementation (C101).

The corpus's stdlib-gap tables (design §2) test the *functions* the JavaScript
implementation must mirror: version ordering, record parsing, shlex splitting, glob
matching, the JSON writer, and code-point sorting. A scenario of kind ``unit`` names a
subcommand here and a shared table under ``units/``; the probe feeds every case to the
tree-under-test's own function and compares with the table's expected value. The table is
the spec — the probe is only the mouth the Python implementation answers through (the JS
implementation gets its own probe at the same contract in C103).

Usage: python3 meta/conformance/probe.py <subcommand> <table.toml> [--tree REPO]
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import shlex
import sys
import tempfile
import tomllib
import types
from pathlib import Path

CORPUS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = CORPUS_ROOT.parents[1]


def _load_module(repo: Path, relative: str, name: str) -> types.ModuleType:
    # common/ modules import each other by package name; the repo root is the package path.
    repo_str = str(repo)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)
    spec = importlib.util.spec_from_file_location(name, repo / relative)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _version_order_key(value: object) -> list | None:
    """order_key's answer in table form: null or [X, Y, Z, position]."""
    return list(value) if value is not None else None


def probe_versions(repo: Path, table: dict) -> list[dict]:
    """Version parsing and ordering against the tree-under-test's common/versions."""
    module = _load_module(repo, "common/versions.py", "conform_versions")
    results = []
    for index, case in enumerate(table.get("case", [])):
        recorded = case["input"]
        # An expected field left out of the table is the null answer (TOML has no null).
        expected = case["expected"]
        actual = {
            "split_base": module.split_version(recorded)[0],
            "split_ahead": module.split_version(recorded)[1],
            "is_final": module.is_final(recorded),
            "order": _version_order_key(module.order_key(recorded)),
        }
        results.append(
            {
                "index": index,
                "expected": {
                    "split_base": expected.get("split_base"),
                    "split_ahead": expected.get("split_ahead"),
                    "is_final": expected.get("is_final"),
                    "order": expected.get("order"),
                },
                "actual": actual,
            }
        )
    for index, case in enumerate(table.get("pair", [])):
        order_a = module.order_key(case["a"])
        order_b = module.order_key(case["b"])
        actual = 0 if order_a == order_b else (-1 if order_a < order_b else 1)
        results.append({"index": 1000 + index, "expected": case["expected"], "actual": actual})
    return results


def probe_record(repo: Path, table: dict) -> list[dict]:
    """Record parsing and inline-comment stripping against the tree-under-test's common/record."""
    module = _load_module(repo, "common/record.py", "conform_record")
    results = []
    for index, case in enumerate(table.get("case", [])):
        path = None
        if not case.get("absent"):
            with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as handle:
                if "text" in case:
                    handle.write(case["text"])
                path = Path(handle.name)
        try:
            lenient = module.read_akmon_toml(path) if path else {}
            if path:
                try:
                    strict = module.read_akmon_toml_strict(path)
                    strict_ok = True
                except module.RecordError:
                    strict, strict_ok = None, False
            else:
                strict, strict_ok = {}, True
        finally:
            if path:
                path.unlink()
        expected = case["expected"]
        results.append(
            {
                "index": index,
                "expected": {
                    "lenient": expected.get("lenient"),
                    "strict": expected.get("strict"),
                    "strict_ok": expected.get("strict_ok"),
                },
                "actual": {"lenient": lenient, "strict": strict, "strict_ok": strict_ok},
            }
        )
    strip_results = []
    for index, case in enumerate(table.get("strip", [])):
        strip_results.append(
            {"index": index, "expected": case["expected"], "actual": module._strip_inline_comment(case["input"])}
        )
    results.extend(strip_results)
    return results


def probe_shlex(_repo: Path, table: dict) -> list[dict]:
    """Shlex splitting and joining against the standard library (the JS side must mirror both).

    A case names either ``input`` (``shlex.split``; ``expected`` is ``{argv, error}``) or
    ``join`` (``shlex.join`` on that argv list; ``expected`` is the plain output string) —
    the two operations `common/check_runner.py`'s display line and argv parsing both need.
    """
    results = []
    for index, case in enumerate(table.get("case", [])):
        if "join" in case:
            actual = shlex.join(case["join"])
            results.append({"index": index, "expected": case["expected"], "actual": actual})
            continue
        try:
            actual = shlex.split(case["input"])
            error = False
        except ValueError:
            actual, error = None, True
        results.append(
            {
                "index": index,
                "expected": {"argv": case["expected"].get("argv"), "error": case["expected"].get("error", False)},
                "actual": {"argv": actual, "error": error},
            }
        )
    return results


def probe_glob(_repo: Path, table: dict) -> list[dict]:
    """Glob matching against fnmatch (case-sensitive, the corpus's form)."""
    results = []
    for index, case in enumerate(table.get("case", [])):
        actual = fnmatch.fnmatchcase(case["name"], case["pattern"])
        results.append({"index": index, "expected": case["expected"], "actual": actual})
    return results


def _json_form(value: object, form: str) -> str:
    if form == "hook":  # the hook stdout document: one line, default separators
        return json.dumps(value)
    if form == "wiring":  # generated wiring files: indent=2 + trailing newline
        return json.dumps(value, indent=2) + "\n"
    if form == "canonical":  # the registry's content hash: sorted, compact
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    raise ValueError(f"unknown json form {form!r}")


def probe_json(_repo: Path, table: dict) -> list[dict]:
    """JSON writer forms against the standard library's json module.

    TOML has no null, so a case cannot spell one directly in ``value``. ``null_keys`` names
    top-level keys of ``value`` to replace with ``None`` before dumping — the table's only way
    to pin ``json.dumps``'s ``null`` spelling.
    """
    results = []
    for index, case in enumerate(table.get("case", [])):
        value = case["value"]
        null_keys = case.get("null_keys")
        if null_keys:
            value = dict(value)
            for key in null_keys:
                value[key] = None
        actual = _json_form(value, case["form"])
        results.append({"index": index, "expected": case["expected"], "actual": actual})
    return results


def probe_sort(_repo: Path, table: dict) -> list[dict]:
    """Code-point sorting of a string list (the JS side must mirror it)."""
    results = []
    for index, case in enumerate(table.get("case", [])):
        actual = sorted(case["input"])
        results.append({"index": index, "expected": case["expected"], "actual": actual})
    return results


PROBES = {
    "versions": probe_versions,
    "record": probe_record,
    "shlex": probe_shlex,
    "glob": probe_glob,
    "json": probe_json,
    "sort": probe_sort,
}


def main(argv: list[str] | None = None) -> int:
    """Run one probe against its unit table; print the ok/failed document, exit 1 on a miss."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probe", choices=sorted(PROBES))
    parser.add_argument("table", type=Path)
    parser.add_argument("--tree", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    table = tomllib.loads(args.table.read_text(encoding="utf-8"))
    results = PROBES[args.probe](Path(args.tree).resolve(), table)
    failed = [r for r in results if r["expected"] != r["actual"]]
    print(json.dumps({"ok": not failed, "failed": failed}, indent=2, ensure_ascii=False, default=str))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
