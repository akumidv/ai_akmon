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
import contextlib
import dataclasses
import fnmatch
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import stat
import sys
import tempfile
import time
import tomllib
import types
from collections.abc import Iterator
from contextlib import contextmanager
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


# ---------------------------------------------------------------------------------------
# The two mouths below answer from *files and the environment*, not only from values: the
# marker module claims and releases files in a directory, the materialization module compares
# two trees. A row therefore describes a world — a scratch directory the probe builds and
# removes, the environment variables a row sets — and the mouth reports what the module did
# to it. The same world-building is written in `probe.mjs`; the table is the only shared text.
# A call that raises answers `{"raises": true}` rather than a message: what Python raises
# (a `KeyError`, a `UnicodeDecodeError`) is the language's, and the table pins only that the
# twin refuses too. A row marked `nonroot` relies on file modes, which root ignores: it is left
# out of the answer when the probe runs as root, on both sides.
# ---------------------------------------------------------------------------------------


@contextmanager
def _environment(changes: dict[str, str | None]) -> Iterator[None]:
    """Set (a ``None`` value: unset) environment variables for the block, then restore every one."""
    saved = {name: os.environ.get(name) for name in changes}
    try:
        for name, value in changes.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _answered(call: object) -> dict:
    """What a call answers in table form: ``{"value": …}``, or ``{"raises": true}`` when it raised."""
    try:
        return {"value": call()}  # type: ignore[operator]
    except Exception:  # noqa: BLE001 — any refusal is the same answer; the language owns its type
        return {"raises": True}


def _skipped_as_root(case: dict) -> bool:
    """A ``nonroot`` row is not asked of a process that file modes do not bind."""
    return bool(case.get("nonroot")) and os.geteuid() == 0


def _marker_digest(data: dict, identity: str) -> str:
    """The marker hash as the probe's own oracle computes it (hashlib), not through the module."""
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[: data["name_sha256_tail"]]


def _marker_labelled(data: dict, names: list[str], identities: list[str]) -> list[str]:
    """Marker file names with each hash replaced by the identity that made it: ``kind@identity``."""
    labels = {_marker_digest(data, identity): identity for identity in identities}
    prefix = data["name_prefix"]
    shown = []
    for name in names:
        stem, _, digest = name.rpartition("-")
        if name.startswith(prefix) and digest in labels:
            shown.append(f"{stem[len(prefix) :]}@{labels[digest]}")
        else:
            shown.append(name)
    return shown


def _marker_listing(folder: Path) -> list[str]:
    """The folder's file names, sorted by code point; a folder that is not there lists nothing."""
    try:
        return sorted(entry.name for entry in folder.iterdir())
    except OSError:
        return []


def _marker_step(module: types.ModuleType, data: dict, world: dict, step: dict) -> list:
    """One step of a marker sequence; answers are the claim results and the listings, in order."""
    folder, directory, identities = world["folder"], world["directory"], world["identities"]
    op = step["op"]
    if op == "claim":
        return [module.claim_diagnostic_marker(step["kind"], step.get("identity"), directory=directory)]
    if op == "release":
        module.release_diagnostic_markers(
            step["prefix"], step.get("identity"), keep_kind=step.get("keep_kind"), directory=directory
        )
        return []
    if op == "ls":
        return [sorted(_marker_labelled(data, _marker_listing(folder), identities))]
    if op == "outside":
        return [sorted(set(_marker_listing(world["scratch"])) - {"dir"})]
    if op == "plant":
        (folder / step["name"]).write_bytes(b"")
    elif op == "plant_dir":
        (folder / f"{data['name_prefix']}{step['kind']}-{_marker_digest(data, step['identity'])}").mkdir()
    elif op == "age":
        names = _marker_listing(folder)
        (name,) = [
            n
            for n, label in zip(names, _marker_labelled(data, names, identities), strict=True)
            if label == step["label"]
        ]
        moment = time.time() - step["seconds"]
        os.utime(folder / name, (moment, moment))
    else:
        raise ValueError(f"unknown marker step {op!r}")
    return []


def _marker_world(case: dict, steps: list[dict]) -> tuple[Path, dict]:
    """A scratch directory holding ``dir/`` (unless the row says it is missing) and who may live in it."""
    scratch = Path(tempfile.mkdtemp(prefix="akmon-probe-markers-"))
    folder = scratch / "dir"
    if not case.get("missing_dir"):
        folder.mkdir()
    identities = sorted({step["identity"] for step in steps if step.get("identity")})
    directory = None if case.get("default_dir") else folder
    return scratch, {
        "scratch": scratch,
        "folder": folder,
        "directory": directory,
        "identities": identities,
    }


def _marker_sequences(module: types.ModuleType, data: dict, table: dict) -> list[dict]:
    """Claim/release/age sequences over one scratch directory each (index base 4000)."""
    results = []
    for index, case in enumerate(table.get("sequence", [])):
        steps = case.get("steps", [])
        scratch, world = _marker_world(case, steps)
        answers: list = []
        env = {"TMPDIR": str(world["folder"])} if case.get("default_dir") else {}
        try:
            with _environment(env):
                tempfile.tempdir = None  # the stdlib keeps its answer for the process: ask afresh
                for step in steps:
                    answers.extend(_marker_step(module, data, world, step))
        finally:
            tempfile.tempdir = None
            shutil.rmtree(scratch, ignore_errors=True)
        results.append({"index": 4000 + index, "expected": case.get("expected"), "actual": answers})
    return results


def _marker_names(module: types.ModuleType, table: dict) -> list[dict]:
    """The file one claim leaves: its whole name, its mode under umask 022, nothing beside it (base 3000)."""
    results = []
    for index, case in enumerate(table.get("name", [])):
        scratch = Path(tempfile.mkdtemp(prefix="akmon-probe-markers-"))
        folder = scratch / "dir"
        folder.mkdir()
        previous = os.umask(0o022)
        try:
            module.claim_diagnostic_marker(case["kind"], case["identity"], directory=folder)
            names = _marker_listing(folder)
            mode = format(stat.S_IMODE((folder / names[0]).stat().st_mode), "o") if names else ""
            actual = {"names": names, "mode": mode, "outside": sorted(set(_marker_listing(scratch)) - {"dir"})}
        finally:
            os.umask(previous)
            shutil.rmtree(scratch, ignore_errors=True)
        results.append({"index": 3000 + index, "expected": case.get("expected"), "actual": actual})
    return results


def _marker_tempdirs(table: dict) -> list[dict]:
    """``tempfile.gettempdir()`` under each row's environment — the answer the JS twin must give (base 5000)."""
    results = []
    for index, case in enumerate(table.get("tempdir", [])):
        if _skipped_as_root(case):
            continue
        scratch = Path(tempfile.mkdtemp(prefix="akmon-probe-markers-"))
        try:
            for relative in case.get("dirs", []):
                (scratch / relative).mkdir(parents=True)
            for relative in case.get("files", []):
                (scratch / relative).write_bytes(b"")
            for relative, mode in case.get("chmod", {}).items():
                (scratch / relative).chmod(int(mode, 8))
            changes: dict[str, str | None] = {"TMPDIR": None, "TEMP": None, "TMP": None}
            changes.update(
                {name: value.replace("{{scratch}}", str(scratch)) for name, value in case.get("env", {}).items()}
            )
            with _environment(changes):
                tempfile.tempdir = None
                actual = tempfile.gettempdir().replace(str(scratch), "{{scratch}}")
        finally:
            tempfile.tempdir = None
            for relative in case.get("chmod", {}):
                (scratch / relative).chmod(0o700)
            shutil.rmtree(scratch, ignore_errors=True)
        results.append({"index": 5000 + index, "expected": case.get("expected"), "actual": actual})
    return results


def probe_markers(repo: Path, table: dict) -> list[dict]:
    """Marker naming, claiming, age-out and release, against the tree's common/markers."""
    module = _load_module(repo, "common/markers.py", "conform_markers")
    data = _data_document(repo, "common/markers.json")
    results = []
    for index, case in enumerate(table.get("kind", [])):
        actual = _answered(lambda case=case: module.marker_kind(case["stem"]))
        results.append({"index": index, "expected": case.get("expected"), "actual": actual})
    for index, case in enumerate(table.get("unidentified", [])):
        results.append(
            {"index": 1000 + index, "expected": case.get("expected"), "actual": module.unidentified_identity()}
        )
    for index, case in enumerate(table.get("state", [])):
        actual = _answered(lambda case=case: module.delegation_state_name(case["which"], case["identity"]))
        results.append({"index": 2000 + index, "expected": case.get("expected"), "actual": actual})
    results += _marker_names(module, table)
    results += _marker_sequences(module, data, table)
    results += _marker_tempdirs(table)
    return results


def _materialization_world(case: dict) -> tuple[Path, Path, Path]:
    """A scratch directory with the project (its ``.akmon`` copies) and the standard tree a row describes."""
    scratch = Path(tempfile.mkdtemp(prefix="akmon-probe-materialization-"))
    project, tree = scratch / "project", scratch / "tree"
    copies = project / case.get("aitna_dir", "_aitna") / ".akmon"
    project.mkdir()
    tree.mkdir()
    for base, prefix in ((copies, "project"), (tree, "tree")):
        files = {relative: text.encode("utf-8") for relative, text in case.get(prefix, {}).items()}
        files.update({relative: bytes.fromhex(hexed) for relative, hexed in case.get(f"{prefix}_hex", {}).items()})
        for relative, content in files.items():
            (base / relative).parent.mkdir(parents=True, exist_ok=True)
            (base / relative).write_bytes(content)
        for relative in case.get(f"{prefix}_dirs", []):
            (base / relative).mkdir(parents=True, exist_ok=True)
        for relative, mode in case.get(f"{prefix}_chmod", {}).items():
            (base / relative).chmod(int(mode, 8))
    return scratch, project, tree


def _materialization_stale(module: types.ModuleType, table: dict) -> list[dict]:
    """``stale_materialized`` over each row's project and tree (index base 6000)."""
    results = []
    for index, case in enumerate(table.get("stale", [])):
        if _skipped_as_root(case):
            continue
        scratch, project, tree = _materialization_world(case)
        copies = project / case.get("aitna_dir", "_aitna") / ".akmon"
        try:
            with _environment({"AITNA_ROOT": case.get("aitna_root")}):
                actual = _answered(lambda project=project, tree=tree: module.stale_materialized(project, tree))
        finally:
            for prefix, base in (("project", copies), ("tree", tree)):
                for relative in case.get(f"{prefix}_chmod", {}):
                    (base / relative).chmod(0o700)
            shutil.rmtree(scratch, ignore_errors=True)
        results.append({"index": 6000 + index, "expected": case.get("expected"), "actual": actual})
    return results


def probe_materialization(repo: Path, table: dict) -> list[dict]:
    """The generated banner, the copy format and the freshness check, against the tree's common/materialization."""
    module = _load_module(repo, "common/materialization.py", "conform_materialization")
    results = []
    for index, case in enumerate(table.get("marker", [])):
        results.append({"index": index, "expected": case.get("expected"), "actual": module.generated_marker()})
    for index, case in enumerate(table.get("banner", [])):
        with _environment({"AITNA_ROOT": case.get("aitna_root")}):
            actual = module.generated_banner()
        results.append({"index": 1000 + index, "expected": case.get("expected"), "actual": actual})
    for index, case in enumerate(table.get("markdown", [])):
        with _environment({"AITNA_ROOT": case.get("aitna_root")}):
            actual = module.materialized_markdown(case["input"])
        results.append({"index": 2000 + index, "expected": case.get("expected"), "actual": actual})
    for index, case in enumerate(table.get("text", [])):
        with _environment({"AITNA_ROOT": case.get("aitna_root")}):
            actual = module.materialized_text(case["name"], case["input"])
        results.append({"index": 3000 + index, "expected": case.get("expected"), "actual": actual})
    for index, case in enumerate(table.get("dirs", [])):
        results.append(
            {"index": 4000 + index, "expected": case.get("expected"), "actual": list(module.imported_dirs())}
        )
    for index, case in enumerate(table.get("dir", [])):
        with _environment({"AITNA_ROOT": case.get("aitna_root")}):
            actual = str(module.materialized_dir(Path(case["project_root"])))
        results.append({"index": 5000 + index, "expected": case.get("expected"), "actual": actual})
    results += _materialization_stale(module, table)
    return results


# ---------------------------------------------------------------------------------------
# The routing mouth (C104) is generic where the earlier ones are per family: `routing.py` has
# ninety-odd definitions, so a row names the function and its arguments as JSON instead of the
# probe growing a branch per function. A row is `{id, fn, args_json, expected_json}` plus the
# optional world keys below; `fn` is the Python public name (the JS mouth calls the camelCase
# export). Arguments are plain JSON with four constructors the mouth resolves first — an object
# keyed `$path` is a path (`Path` here, the string on the JS side); `$registry` is the tree's
# shipped registry.json with its `set` keys replaced, its `merge` object deep-merged and its
# `drop` keys removed; `$call` is another public function's answer to `args`/`kwargs`, one
# element of it when `pick` names an index; `$new` is a dataclass built from its snake_case
# `fields` — and every string may hold `{{dir}}`, the row's scratch directory. Keyword-only parameters ride
# in `kwargs_json`. The answer is JSON: a dataclass is an object keyed by its field names, a tuple
# an array, a `Path` its POSIX string, a raise `{"error": <class name>, "message": <first
# argument>}` (the first argument, not `str()`: Python's `str(KeyError(x))` is `repr(x)`, the
# quoting is the language's, the text is the owner's). Back in every string answer `{{dir}}`
# replaces the scratch path, `{{body:<agent>}}` an agent body of agents.json (the data file owns
# that prose; the table pins where it lands) and `{{registry_hash}}` the canonical hash of a
# `$registry` argument as the mouth's own oracle computes it (hashlib over the sorted compact
# JSON), so a shipped-registry edit does not move the table while the hashing stays pinned.
# A row answers its value, or `{"value": …, "tree": {…}}` when it names `tree` (the files under
# that scratch subdirectory afterwards: relpath → text, or → {text, mode} with `tree_modes`).
# World keys: `files` (relpath → text), `files_parts` (relpath → parts: a text, `{hex}` or
# `{repeat, times}` — for the bytes TOML cannot spell and the 64 KiB a tail-read block needs),
# `mtimes` (relpath → seconds in the past), `modes` (relpath → octal), `env` (name → value, `""`
# unsets; AKMON_CONTEXT_RECOMMENDED_MAX and AITNA_ROOT are unset and TMPDIR is the scratch
# directory unless a row says otherwise), `setup_json` (calls made first, answers dropped),
# `ordered` (an object answer becomes its [key, value] pairs: the order is pinned), `nonroot`.
# Expected and actual compare as canonical JSON, so `true` is not `1` and `1.0` is not `1`.
# ---------------------------------------------------------------------------------------

_ROUTING_BASE_ENV = ("AKMON_CONTEXT_RECOMMENDED_MAX", "AITNA_ROOT")


def _routing_deep_merge(base: dict, override: dict) -> dict:
    """The probe's own deep merge for ``$registry.merge`` (not the module's ``_deep_merge``)."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _routing_deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _routing_hash(registry: dict) -> str:
    """The registry hash as the probe's oracle computes it — what `{{registry_hash}}` stands for."""
    canonical = json.dumps(registry, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


_ROUTING_CONSTRUCTORS = ("$path", "$registry", "$call", "$new")


def _routing_registry(module: types.ModuleType, world: dict, change: dict) -> dict:
    """The shipped registry with a row's `set`/`merge`/`drop` applied; its hash is remembered."""
    registry = json.loads(json.dumps(world["registry"]))
    registry.update(_routing_arg(module, world, change.get("set", {})))
    registry = _routing_deep_merge(registry, _routing_arg(module, world, change.get("merge", {})))
    for key in change.get("drop", []):
        registry.pop(key, None)
    world["hashes"].add(_routing_hash(registry))
    return registry


def _routing_constructed(module: types.ModuleType, world: dict, value: dict) -> object:
    """The value one constructor object stands for (see the block comment above)."""
    if "$path" in value:
        return Path(_routing_arg(module, world, value["$path"]))
    if "$registry" in value:
        return _routing_registry(module, world, value["$registry"])
    if "$call" in value:
        args = _routing_arg(module, world, value.get("args", []))
        answer = getattr(module, value["$call"])(*args, **_routing_arg(module, world, value.get("kwargs", {})))
        return answer[value["pick"]] if "pick" in value else answer
    return getattr(module, value["$new"])(**_routing_arg(module, world, value.get("fields", {})))


def _routing_arg(module: types.ModuleType, world: dict, value: object) -> object:
    """One argument with its constructors resolved and `{{dir}}` filled, recursively."""
    if isinstance(value, str):
        return value.replace("{{dir}}", str(world["dir"]))
    if isinstance(value, list):
        return [_routing_arg(module, world, item) for item in value]
    if not isinstance(value, dict):
        return value
    if any(key in value for key in _ROUTING_CONSTRUCTORS):
        return _routing_constructed(module, world, value)
    return {key: _routing_arg(module, world, item) for key, item in value.items()}


def _routing_json(value: object) -> object:
    """An answer in table form: dataclasses, tuples, sets and paths as JSON values."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _routing_json(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, (list, tuple)):
        return [_routing_json(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_routing_json(item) for item in value)
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(key): _routing_json(item) for key, item in value.items()}
    return value


def _routing_text(world: dict, value: object) -> object:
    """Every string of an answer with the scratch path, agent bodies and registry hashes tokenized."""
    if isinstance(value, str):
        text = value.replace(str(world["dir"]), "{{dir}}")
        for name, body in world["bodies"]:
            text = text.replace(body, f"{{{{body:{name}}}}}")
        for digest in world["hashes"]:
            text = text.replace(digest, "{{registry_hash}}")
        return text
    if isinstance(value, list):
        return [_routing_text(world, item) for item in value]
    if isinstance(value, dict):
        return {_routing_text(world, key): _routing_text(world, item) for key, item in value.items()}
    return value


def _routing_tree(base: Path, *, with_modes: bool) -> dict:
    """The files under ``base``: relpath → text (or ``{hex}`` when not UTF-8), with modes on request."""
    tree: dict = {}
    if not base.is_dir():
        return tree
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        try:
            content: object = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = {"hex": raw.hex()}
        if with_modes:
            content = {"text": content, "mode": format(stat.S_IMODE(path.stat().st_mode), "o")}
        tree[path.relative_to(base).as_posix()] = content
    return tree


def _routing_world(scratch: Path, case: dict) -> None:
    """Write the row's files, then set the mtimes and modes it names."""
    contents = {relative: text.encode("utf-8") for relative, text in case.get("files", {}).items()}
    for relative, parts in case.get("files_parts", {}).items():
        data = b""
        for part in parts:
            if isinstance(part, str):
                data += part.encode("utf-8")
            elif "hex" in part:
                data += bytes.fromhex(part["hex"])
            else:
                data += part["repeat"].encode("utf-8") * part["times"]
        contents[relative] = data
    for relative, data in contents.items():
        (scratch / relative).parent.mkdir(parents=True, exist_ok=True)
        (scratch / relative).write_bytes(data)
    for relative, seconds in case.get("mtimes", {}).items():
        moment = time.time() - seconds
        os.utime(scratch / relative, (moment, moment))
    for relative, mode in case.get("modes", {}).items():
        (scratch / relative).chmod(int(mode, 8))


def _routing_call(module: types.ModuleType, world: dict, call: dict) -> object:
    """Call one public name; a module constant (not callable) answers its value."""
    target = getattr(module, call["fn"])
    if not callable(target):
        return target
    args = _routing_arg(module, world, call.get("args", []))
    kwargs = _routing_arg(module, world, call.get("kwargs", {}))
    return target(*args, **kwargs)


def _routing_answer(module: types.ModuleType, world: dict, case: dict) -> object:
    """The row's answer in table form, a raise included."""
    for setup in json.loads(case.get("setup_json", "[]")):
        _routing_call(module, world, setup)
    call = {"fn": case["fn"], "args": json.loads(case.get("args_json", "[]"))}
    call["kwargs"] = json.loads(case.get("kwargs_json", "{}"))
    try:
        value = _routing_json(_routing_call(module, world, call))
    except Exception as exc:  # noqa: BLE001 — every raise is an answer the table pins
        message = exc.args[0] if len(exc.args) == 1 and isinstance(exc.args[0], str) else str(exc)
        return {"error": type(exc).__name__, "message": _routing_text(world, message)}
    if case.get("ordered") and isinstance(value, dict):
        value = [[key, item] for key, item in value.items()]
    value = _routing_text(world, value)
    if "tree" not in case:
        return value
    tree = _routing_tree(world["dir"] / case["tree"], with_modes=bool(case.get("tree_modes")))
    return {"value": value, "tree": _routing_text(world, tree)}


def _routing_case(module: types.ModuleType, repo: Path, case: dict) -> object:
    """One row in its own scratch directory and environment, both restored afterwards."""
    scratch = Path(tempfile.mkdtemp(prefix="akmon-probe-routing-"))
    agents = _data_document(repo, "tools/model_routing/agents.json")
    world = {
        "dir": scratch,
        "registry": _data_document(repo, "tools/model_routing/registry.json"),
        "bodies": [(spec["name"], spec["body"]) for spec in agents["agent_specs"]],
        "hashes": set(),
    }
    changes: dict[str, str | None] = dict.fromkeys(_ROUTING_BASE_ENV)
    changes["TMPDIR"] = str(scratch)
    for name, value in case.get("env", {}).items():
        changes[name] = value.replace("{{dir}}", str(scratch)) if value != "" else None
    previous = os.umask(0o022)
    try:
        _routing_world(scratch, case)
        with _environment(changes):
            tempfile.tempdir = None
            return _routing_answer(module, world, case)
    finally:
        tempfile.tempdir = None
        os.umask(previous)
        for relative in case.get("modes", {}):
            with contextlib.suppress(OSError):
                (scratch / relative).chmod(0o700)
        shutil.rmtree(scratch, ignore_errors=True)


def probe_routing(repo: Path, table: dict) -> list[dict]:
    """The model-routing core, one public call per row, against the tree's tools/model_routing/routing."""
    module = _load_module(repo, "tools/model_routing/routing.py", "conform_routing")
    results = []
    for index, case in enumerate(table.get("case", [])):
        if _skipped_as_root(case):
            continue
        expected = json.loads(case["expected_json"])
        actual = _routing_case(module, repo, case)
        if json.dumps(expected, sort_keys=True) == json.dumps(actual, sort_keys=True):
            actual = expected
        elif expected == actual:  # Python calls `True == 1` and `1 == 1.0`; the table does not
            actual = {"strictly": json.dumps(actual, sort_keys=True)}
        results.append({"index": index, "id": case["id"], "expected": expected, "actual": actual})
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
    "markers": probe_markers,
    "materialization": probe_materialization,
    "routing": probe_routing,
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
