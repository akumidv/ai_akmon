#!/usr/bin/env python3
"""Unit-table probe for the Python implementation (C101).

The corpus's unit tables (design §2) test the *functions* the JavaScript implementation must
mirror and cannot inherit: what the stdlib gives Python and not JS (shlex splitting, glob
matching, the JSON writer, code-point sorting), and the shared data-driven answers whose result
is a value rather than a process (version ordering, record parsing, the runtime's commands, the
``[check]`` table and the argv it builds). A scenario of kind ``unit`` names a
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
    """Version parsing, ordering and the npm carrier spelling, against the tree's common/versions."""
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
        # The table asks the comparator, not the key: an order key compared with `<` is a
        # Python-only answer, and the JS twin must give the same one (units/versions.toml).
        try:
            actual = module.compare_versions(case["a"], case["b"])
        except ValueError:
            actual = "error"
        results.append({"index": 1000 + index, "expected": case["expected"], "actual": actual})
    for index, case in enumerate(table.get("semver", [])):
        results.append(
            {"index": 2000 + index, "expected": case["expected"], "actual": module.semver_spelling(case["input"])}
        )
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


# ---------------------------------------------------------------------------------------
# The two mouths below are the first to answer from a *shared data file*. `common/runtime.py`
# and `common/check_runner.py` read their tables out of `common/*.json` on every call, so the
# Python side reaches them through the module — which resolves the file beside itself, i.e.
# inside the snapshot — while the JS side is fed the same file by its mouth, exactly the way
# the module's twin is handed its data at the entry point.
# ---------------------------------------------------------------------------------------


def _data_document(repo: Path, relative: str) -> object:
    """One data file of the tree under test, as the module beside it reads it."""
    return json.loads((repo / relative).read_text(encoding="utf-8"))


def _data_parts(document: object, paths: list[str]) -> list:
    """The text a table names by data-file path, flattened one level.

    A `text` row states *where* its answer lives (`check_config.no_checks`) instead of
    repeating it: the data file is the one owner of that prose, and what the table has to pin
    is the accessor's pairing with its key and the order of a multi-part answer.
    """
    parts = []
    for path in paths:
        node = document
        for step in path.split("."):
            node = node.get(step) if isinstance(node, dict) else None
        if isinstance(node, list):
            parts.extend(node)
        else:
            parts.append(node)
    return parts


def _text_parts(answer: object) -> list:
    """One accessor's answer as the flat list of text parts the table compares against."""
    return list(answer) if isinstance(answer, (list, tuple)) else [answer]


def _render_check(check: object) -> dict:
    """One declared check in the only form a table can carry it: three fields, lists not tuples.

    Python answers with a frozen dataclass whose argv and files are tuples; a tuple is *not*
    equal to the list the table spells, so the conversion is the mouth's job, not the table's.
    """
    return {"name": check.name, "argv": list(check.argv), "files": list(check.files)}


def _runtime_labels(module: types.ModuleType, table: dict) -> list[dict]:
    """The population, carrier and modality labels the module declares (index base 0)."""
    labels = {
        "GENERATED_WIRING": module.GENERATED_WIRING,
        "OWN_TOOLING": module.OWN_TOOLING,
        "POSIX_SHELL": module.POSIX_SHELL,
        "REQUIRED": module.REQUIRED,
        "OPTIONAL": module.OPTIONAL,
        "REQUIRED_ON": module.REQUIRED_ON,
    }
    results = []
    for index, case in enumerate(table.get("label", [])):
        results.append({"index": index, "expected": case.get("expected"), "actual": labels.get(case.get("name"))})
    return results


def _render_declaration(declaration: object) -> dict | None:
    """One runtime declaration as {binary, population, modality}; an absent one stays null."""
    if declaration is None:
        return None
    return {"binary": declaration.binary, "population": declaration.population, "modality": declaration.modality}


def _runtime_declared(module: types.ModuleType, table: dict) -> list[dict]:
    """The ordered declaration list, answered by the position the row names (index base 1000)."""
    declarations = module.declared_runtimes()
    results = []
    for index, case in enumerate(table.get("declared", [])):
        position = case.get("index")
        in_range = isinstance(position, int) and 0 <= position < len(declarations)
        found = declarations[position] if in_range else None
        actual = _render_declaration(found)
        results.append({"index": 1000 + index, "expected": case.get("expected"), "actual": actual})
    return results


def _runtime_named_argv(module: types.ModuleType, case: dict) -> list | None:
    """The argv a named constructor answers; a row naming no known builder answers null."""
    named = case.get("named")
    if named == "version_command":
        return list(module.version_command(case.get("harness")))
    if named == "codex_hooks_list_command":
        return list(module.codex_hooks_list_command())
    return None


def _runtime_argv(module: types.ModuleType, table: dict) -> list[dict]:
    """The command builders: the table's prefix plus a caller's tail (bases 2000 and 3000)."""
    results = []
    for index, case in enumerate(table.get("command", [])):
        argv = module.harness_command(case.get("harness"), case.get("operation"), *case.get("extra", []))
        results.append({"index": 2000 + index, "expected": case.get("expected"), "actual": list(argv)})
    for index, case in enumerate(table.get("named", [])):
        actual = _runtime_named_argv(module, case)
        results.append({"index": 3000 + index, "expected": case.get("expected"), "actual": actual})
    return results


def _runtime_errors(module: types.ModuleType, table: dict) -> list[dict]:
    """The refusal for an undeclared harness or operation, by its whole text (index base 5000).

    The message is spec, not decoration: both sides quote the unknown name the same way and list
    what is known in the same order, and it is all an owner gets when a caller asks a harness for
    an operation nobody declared.
    """
    results = []
    for index, case in enumerate(table.get("error", [])):
        try:
            module.harness_command(case.get("harness"), case.get("operation"))
            actual = None
        except ValueError as exc:
            actual = str(exc)
        results.append({"index": 5000 + index, "expected": case.get("expected"), "actual": actual})
    return results


def probe_runtime(repo: Path, table: dict) -> list[dict]:
    """The harness-command map and the runtime declaration, against the tree's common/runtime."""
    module = _load_module(repo, "common/runtime.py", "conform_runtime")
    results = _runtime_labels(module, table)
    results += _runtime_declared(module, table)
    results += _runtime_argv(module, table)
    for index, case in enumerate(table.get("binaries", [])):
        results.append(
            {
                "index": 4000 + index,
                "expected": case.get("expected"),
                "actual": list(module.harness_binaries()),
            }
        )
    results += _runtime_errors(module, table)
    return results


def _check_entries(module: types.ModuleType, table: dict) -> list[dict]:
    """``read_checks`` over a whole ``[check]`` table: the checks and every problem (base 0)."""
    results = []
    for index, case in enumerate(table.get("case", [])):
        checks, problems = module.read_checks(case.get("table"))
        expected = case.get("expected") or {}
        want = {"checks": expected.get("checks"), "problems": expected.get("problems")}
        got = {"checks": [_render_check(check) for check in checks], "problems": list(problems)}
        results.append({"index": index, "expected": want, "actual": got})
    return results


def _check_argv(module: types.ModuleType, table: dict) -> list[dict]:
    """``argv_for``: the ``{files}`` expansion and the nothing-to-do refusal (index base 1000)."""
    results = []
    for index, case in enumerate(table.get("argv", [])):
        check = module.Check("case", tuple(case.get("argv", [])), tuple(case.get("files", ())))
        answer = module.argv_for(check, case.get("changed"))
        expected = case.get("expected") or {}
        actual = None if answer is None else list(answer)
        results.append({"index": 1000 + index, "expected": {"argv": expected.get("argv")}, "actual": {"argv": actual}})
    return results


def _check_made(module: types.ModuleType, table: dict) -> list[dict]:
    """The ``Check`` type itself: its three fields and its empty-patterns rule (index base 2000)."""
    results = []
    for index, case in enumerate(table.get("make", [])):
        argv = tuple(case.get("argv", []))
        check = module.Check(case.get("name", ""), argv, tuple(case.get("files", ())))
        results.append({"index": 2000 + index, "expected": case.get("expected"), "actual": _render_check(check)})
    return results


def _check_texts(module: types.ModuleType, data: object, table: dict) -> list[dict]:
    """The text accessors against the data-file path each row names (index base 3000).

    A row's ``keys`` are where the answer must live, so the table pins the accessor-to-key
    pairing — and the order of a two-part answer — without holding a second copy of prose the
    data file already owns.
    """
    getters = {
        "config_target": module.config_target,
        "files_placeholder": module.files_placeholder,
        "default_files": module.default_files,
        "repair_record_fix": module.repair_record_fix,
        "repair_record_verify_fix": module.repair_record_verify_fix,
        "correct_entry_fix": module.correct_entry_fix,
        "no_checks": module.no_checks,
        "scope_fix": module.scope_fix,
        "check_table_ok": module.check_table_ok,
    }
    results = []
    for index, case in enumerate(table.get("text", [])):
        getter = getters.get(case.get("getter"))
        unknown = getter is None
        expected = None if unknown else _data_parts(data, case.get("keys", []))
        actual = None if unknown else _text_parts(getter())
        results.append({"index": 3000 + index, "expected": expected, "actual": actual})
    return results


def probe_check_runner(repo: Path, table: dict) -> list[dict]:
    """``[check]`` reading and argv building, against the tree's common/check_runner."""
    module = _load_module(repo, "common/check_runner.py", "conform_check_runner")
    data = _data_document(repo, "common/check_runner.json")
    results = _check_entries(module, table)
    results += _check_argv(module, table)
    results += _check_made(module, table)
    results += _check_texts(module, data, table)
    return results


PROBES = {
    "versions": probe_versions,
    "record": probe_record,
    "shlex": probe_shlex,
    "glob": probe_glob,
    "json": probe_json,
    "sort": probe_sort,
    "runtime": probe_runtime,
    "check_runner": probe_check_runner,
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
