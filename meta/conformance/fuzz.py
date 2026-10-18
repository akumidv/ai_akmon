#!/usr/bin/env python3
"""Differential fuzzing of the hook payloads (C111, design node-consumers.md §5 gate 4).

The corpus pins what the standard means on the inputs someone thought of; this run asks the
other question — on inputs nobody wrote down, do the two permanent implementations still
behave as one (ADR 0020 D03)? It takes every hook scenario's payload (plus any recorded payload
under ``fuzz/seeds/``) as a seed, mutates it deterministically from ``--seed``, and runs each
mutated case through the Python and the Node hook on identical fresh fixtures — the same
fixture, the same project path, the same private tempdir — comparing the exit code, the
normalized stdout (as JSON when it parses), the normalized stderr, and the files the hook
created, changed or removed under the project and the tempdir.

A difference is either *known* — it matches an entry of ``fuzz.toml``, which names the
``DIVERGENCES.md`` row that accepts it — or *divergent*: a defect in one twin or a missing DV
row. Each divergent case is written as a **draft** scenario (the Python result as its
``[expected]``) under ``--emit``, never into ``scenarios/``: the Seed protocol's human review
decides whether it becomes a fix plus a scenario, or a DV row plus a ``fuzz.toml`` entry.

Usage:
    python3 meta/conformance/fuzz.py --cases N --seed S [--script NAME] [--emit DIR]
                                     [--time-budget SEC] [--jobs J] [--case I]

Exit 0 when no case diverged outside ``fuzz.toml``, 1 when one did, 2 on a usage error or a
missing prerequisite (``node``).
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import copy
import dataclasses
import fnmatch
import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CORPUS_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(CORPUS_ROOT))
sys.path.insert(0, str(CORPUS_ROOT.parents[1]))

from corpus import (  # noqa: E402
    REPO_ROOT,
    CorpusError,
    ExpectedSpec,
    FixtureSpec,
    RunEnv,
    RunSpec,
    Scenario,
    build_snapshot,
    load_scenarios,
    materialize_fixture,
)
from normalize import Ctx, normalize  # noqa: E402
from runner import (  # noqa: E402
    RunCtx,
    _command_for,
    _impl_version,
    _normalize_leaves,
    _toml_string,
    _toml_tables,
    _toml_value,
    json_text,
    run_ctx_for,
    scenario_env,
    seed_tmp_files,
    warmup_sync,
)

SEEDS_DIR = CORPUS_ROOT / "fuzz" / "seeds"
KNOWN_FILE = CORPUS_ROOT / "fuzz.toml"
DIVERGENCES_FILE = CORPUS_ROOT / "DIVERGENCES.md"
IMPLS = ("python", "node")
STREAMS = ("exit", "stdout", "stderr", "files")
#: A hook that has not answered in this long is recorded as a timeout (exit ``"timeout"``).
PROCESS_TIMEOUT = 60
#: The very long string a ``long-string`` mutation writes: at least 64 KiB.
LONG_STRING_BYTES = 64 * 1024
#: Payload keys whose values are paths: the ``path-like`` mutation targets them.
PATH_KEYS = frozenset({"cwd", "file_path", "transcript_path", "path", "notebook_path", "agent_transcript_path"})
BYTES_PLACEHOLDER = "@@akmon-fuzz-bytes@@"
#: A draft's file listing keeps a file's content only up to this size (a draft is read by a human).
DRAFT_FILE_LIMIT = 8 * 1024
#: How deep the mutations walk into a seed payload: a list or object nested deeper is held as its
#: raw JSON text, one leaf (a scenario may pin a payload thousands deep; the walks recurse).
SEED_WALK_DEPTH = 64


# --- JSON documents json.dumps cannot spell -----------------------------------------


@dataclass(frozen=True)
class Raw:
    """A literal JSON token written as is: ``-0``, ``1e309``, a nesting thousands deep."""

    text: str


@dataclass(frozen=True)
class Pairs:
    """A JSON object as an ordered list of members, so a key may repeat."""

    items: tuple[tuple[str, object], ...]


@dataclass(frozen=True)
class Bytes:
    """A string member whose content is raw bytes (invalid UTF-8) in the stdin."""

    raw: bytes


def dump_json(value: object, *, ascii_only: bool) -> str:
    """One JSON text for ``value``; :class:`Raw`, :class:`Pairs` and :class:`Bytes` spelled as they say."""
    if isinstance(value, Raw):
        return value.text
    if isinstance(value, Bytes):
        return f'"{BYTES_PLACEHOLDER}"'
    if isinstance(value, Pairs | dict):
        items = value.items if isinstance(value, Pairs) else tuple(value.items())
        members = (
            f"{json.dumps(key, ensure_ascii=ascii_only)}: {dump_json(item, ascii_only=ascii_only)}"
            for key, item in items
        )
        return "{" + ", ".join(members) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(dump_json(item, ascii_only=ascii_only) for item in value) + "]"
    return json.dumps(value, ensure_ascii=ascii_only)


def _bytes_nodes(value: object) -> list[bytes]:
    """The :class:`Bytes` leaves of a document, in serialization order."""
    if isinstance(value, Bytes):
        return [value.raw]
    if isinstance(value, Pairs):
        return [raw for _key, item in value.items for raw in _bytes_nodes(item)]
    if isinstance(value, dict):
        return [raw for item in value.values() for raw in _bytes_nodes(item)]
    if isinstance(value, list):
        return [raw for item in value for raw in _bytes_nodes(item)]
    return []


def encode_document(value: object, *, ascii_only: bool) -> bytes:
    """The stdin bytes of a document: UTF-8, ASCII escapes forced when a lone surrogate needs them."""
    text = dump_json(value, ascii_only=ascii_only)
    try:
        data = text.encode("utf-8")
    except UnicodeEncodeError:  # a lone surrogate has no UTF-8 spelling: only the \\ud800 escape carries it
        data = dump_json(value, ascii_only=True).encode("utf-8")
    for raw in _bytes_nodes(value):
        data = data.replace(BYTES_PLACEHOLDER.encode(), raw, 1)
    return data


# --- seeds ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Seed:
    """One fuzzing seed: a hook scenario (its script, args, fixture, env) and its payload."""

    name: str
    scenario: Scenario

    @property
    def script(self) -> str:
        """The hook the seed runs."""
        return self.scenario.run.script

    @property
    def payload(self) -> dict:
        """The seed's stdin document (``{}`` for a seed that sends none), bounded by :func:`_walkable`."""
        return {key: _walkable(item, 1) for key, item in (self.scenario.run.payload or {}).items()}


def _walkable(value: object, depth: int) -> object:
    """``value`` with every list or object at ``SEED_WALK_DEPTH`` levels held as a :class:`Raw` leaf."""
    if isinstance(value, dict | list) and depth >= SEED_WALK_DEPTH:
        return Raw(json_text(value))
    if isinstance(value, dict):
        return {key: _walkable(item, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [_walkable(item, depth + 1) for item in value]
    return value


def _recorded_seed(path: Path) -> Seed:
    """A seed from ``fuzz/seeds/<script>--<label>.json``: the payload on the base fixture, natively attached."""
    script, sep, _label = path.stem.partition("--")
    if not sep or not script:
        raise CorpusError(f"{path}: a recorded seed is named <script>--<label>.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CorpusError(f"{path}: a recorded seed is one JSON object (the hook payload)")
    scenario = Scenario(
        id=f"seeds/{path.stem}",
        ecosystem="shared",
        kind="hook",
        covers=(f"hook:{script}",),
        fixture=FixtureSpec(warmup="after"),
        env={},
        run=RunSpec(script=script, payload=payload),
        expected=ExpectedSpec(seeded=False),
    )
    return Seed(name=scenario.id, scenario=scenario)


def load_seeds(script: str | None = None, seeds_dir: Path = SEEDS_DIR) -> list[Seed]:
    """Every shared hook scenario and every recorded payload, optionally of one hook, in name order."""
    seeds = [Seed(name=s.id, scenario=s) for s in load_scenarios("hooks") if s.ecosystem == "shared"]
    if seeds_dir.is_dir():
        seeds.extend(_recorded_seed(path) for path in sorted(seeds_dir.glob("*.json")))
    if script:
        seeds = [seed for seed in seeds if seed.script == script]
    return sorted(seeds, key=lambda seed: seed.name)


@dataclass(frozen=True)
class Vocabulary:
    """The event and tool names seen across the seeds: what a ``swap-*`` mutation draws from."""

    events: tuple[str, ...]
    tools: tuple[str, ...]


def vocabulary(seeds: list[Seed]) -> Vocabulary:
    """The sorted ``hook_event_name`` and ``tool_name`` string values of every seed payload."""
    payloads = [s.payload for s in seeds]
    events = {p.get("hook_event_name") for p in payloads if isinstance(p.get("hook_event_name"), str)}
    tools = {p.get("tool_name") for p in payloads if isinstance(p.get("tool_name"), str)}
    return Vocabulary(events=tuple(sorted(events)), tools=tuple(sorted(tools)))


# --- mutations --------------------------------------------------------------------------

Path_ = tuple[str | int, ...]


def _member_paths(value: object, prefix: Path_ = ()) -> list[Path_]:
    """Every member path of a document (object keys and list indices), depth first."""
    paths: list[Path_] = []
    if isinstance(value, dict):
        for key, item in value.items():
            paths.append((*prefix, key))
            paths.extend(_member_paths(item, (*prefix, key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.append((*prefix, index))
            paths.extend(_member_paths(item, (*prefix, index)))
    return paths


def _get(doc: object, path: Path_) -> object:
    for step in path:
        doc = doc[step]  # type: ignore[index]
    return doc


def _set(doc: dict, path: Path_, value: object) -> None:
    parent = _get(doc, path[:-1])
    parent[path[-1]] = value  # type: ignore[index]


def _label(path: Path_) -> str:
    return ".".join(str(step) for step in path) or "<root>"


def _string_paths(doc: dict) -> list[Path_]:
    return [p for p in _member_paths(doc) if isinstance(_get(doc, p), str)]


def _pick_target(doc: dict, rng: random.Random, paths: list[Path_], fallback: str) -> Path_:
    """A member path to mutate: one of ``paths``, else a new top-level ``fallback`` member."""
    if paths:
        return rng.choice(paths)
    doc[fallback] = ""
    return (fallback,)


def _drop_key(doc: dict, rng: random.Random, _vocab: Vocabulary) -> str:
    keyed = [p for p in _member_paths(doc) if isinstance(p[-1], str)]
    if not keyed:
        return "drop-key:<none>"
    path = rng.choice(keyed)
    del _get(doc, path[:-1])[path[-1]]  # type: ignore[attr-defined]
    return f"drop-key:{_label(path)}"


UNKNOWN_KEYS = ("unknown_key", "__proto__", "constructor", "toString", "", "hook_event_name ", "Hook_Event_Name")


def _add_key(doc: dict, rng: random.Random, _vocab: Vocabulary) -> str:
    containers = [()] + [p for p in _member_paths(doc) if isinstance(_get(doc, p), dict)]
    where = rng.choice(containers)
    key = rng.choice(UNKNOWN_KEYS)
    _get(doc, where)[key] = rng.choice(("x", 1, True, None, [], {"a": 1}))  # type: ignore[index]
    return f"add-key:{_label((*where, key))}"


def _retype(doc: dict, rng: random.Random, _vocab: Vocabulary) -> str:
    path = _pick_target(doc, rng, _member_paths(doc), "hook_event_name")
    current = _get(doc, path)
    kind, value = rng.choice(
        (
            ("str", "1"),
            ("int", 1),
            ("int", 0),
            ("float", 3.5),
            ("bool", True),
            ("bool", False),
            ("null", None),
            ("list", []),
            ("list", [current]),
            ("object", {}),
            ("object", {"name": current}),
        )
    )
    _set(doc, path, value)
    return f"retype:{_label(path)}->{kind}"


def _empty_string(doc: dict, rng: random.Random, _vocab: Vocabulary) -> str:
    path = _pick_target(doc, rng, _string_paths(doc) or _member_paths(doc), "session_id")
    _set(doc, path, "")
    return f"empty-string:{_label(path)}"


def _long_string(doc: dict, rng: random.Random, _vocab: Vocabulary) -> str:
    path = _pick_target(doc, rng, _string_paths(doc) or _member_paths(doc), "session_id")
    unit = rng.choice(("x", "é", "\U0001f9ed", "a/", "line\n"))
    _set(doc, path, unit * (LONG_STRING_BYTES // len(unit.encode("utf-8")) + 1))
    return f"long-string:{_label(path)}"


UNICODE_EDGES = (
    ("astral", "\U0001f9ed"),
    ("replacement", "\ufffd"),
    ("max", "\U0010ffff"),
    ("combining", "e\u0301"),
    ("rtl", "\u202e\u05d0"),
    ("bom", "\ufeff"),
    ("line-separator", "\u2028"),
)


def _edit_string(doc: dict, rng: random.Random, insert: str) -> tuple[Path_, str]:
    """Put ``insert`` at the start, the end, or in place of a string member; returns (path, where)."""
    path = _pick_target(doc, rng, _string_paths(doc), "session_id")
    current = _get(doc, path)
    current = current if isinstance(current, str) else ""
    where = rng.choice(("start", "end", "whole"))
    _set(doc, path, {"start": insert + current, "end": current + insert, "whole": insert}[where])
    return path, where


def _unicode_edge(doc: dict, rng: random.Random, _vocab: Vocabulary) -> str:
    name, text = rng.choice(UNICODE_EDGES)
    path, where = _edit_string(doc, rng, text)
    return f"unicode-edge:{name}@{where}:{_label(path)}"


def _lone_surrogate(doc: dict, rng: random.Random, _vocab: Vocabulary) -> str:
    path, where = _edit_string(doc, rng, rng.choice(("\ud800", "\udfff")))
    return f"lone-surrogate:{where}:{_label(path)}"


CONTROLS = (("nul", "\x00"), ("escape", "\x1b[31m"), ("crlf", "\r\n"), ("tab", "\t"), ("del", "\x7f"), ("bell", "\x07"))


def _control_chars(doc: dict, rng: random.Random, _vocab: Vocabulary) -> str:
    name, text = rng.choice(CONTROLS)
    path, where = _edit_string(doc, rng, text)
    return f"control-chars:{name}@{where}:{_label(path)}"


BIG_NUMBERS = (
    ("beyond-2^53", 2**53 + 1),
    ("beyond-2^64", 2**64 + 1),
    ("neg-zero", Raw("-0")),
    ("neg-zero-float", Raw("-0.0")),
    ("overflow", Raw("1e309")),
    ("float-one", 1.0),
    ("exponent", Raw("1E+2")),
)


def _big_number(doc: dict, rng: random.Random, _vocab: Vocabulary) -> str:
    path = _pick_target(doc, rng, _member_paths(doc), "session_id")
    name, value = rng.choice(BIG_NUMBERS)
    _set(doc, path, value)
    return f"big-number:{name}:{_label(path)}"


def _deep_nest(doc: dict, rng: random.Random, _vocab: Vocabulary) -> str:
    path = _pick_target(doc, rng, _member_paths(doc), "tool_input")
    depth = rng.choice((64, 900, 1100, 5000, 100000))
    shape = rng.choice(("array", "object"))
    text = "[" * depth + "]" * depth if shape == "array" else '{"a": ' * depth + "1" + "}" * depth
    _set(doc, path, Raw(text))
    return f"deep-nest:{shape}-{depth}:{_label(path)}"


def _swap(doc: dict, rng: random.Random, key: str, names: tuple[str, ...]) -> str:
    choices = [name for name in names if name != doc.get(key)] or list(names) or [""]
    doc[key] = rng.choice(choices)
    return f"swap-{key.split('_')[-2]}:{doc[key]}"


def _swap_event(doc: dict, rng: random.Random, vocab: Vocabulary) -> str:
    return _swap(doc, rng, "hook_event_name", vocab.events)


def _swap_tool(doc: dict, rng: random.Random, vocab: Vocabulary) -> str:
    return _swap(doc, rng, "tool_name", vocab.tools)


PATH_LIKES = (
    "..",
    "../..",
    "/",
    "/etc/passwd",
    "relative/dir/file.md",
    "{{root}}/",
    "{{root}}/../outside.md",
    "{{root}}/with space/a b.md",
    "{{root}}/_aitna/TASKS.md/",
    "{{root}}//double//slash.md",
    "~/file.md",
    "C:\\Users\\x\\file.md",
)


def _path_like(doc: dict, rng: random.Random, _vocab: Vocabulary) -> str:
    paths = [p for p in _member_paths(doc) if isinstance(p[-1], str) and p[-1] in PATH_KEYS]
    path = rng.choice(paths) if paths else ("cwd",)
    _set(doc, path, rng.choice(PATH_LIKES))
    return f"path-like:{_label(path)}"


VALUE_MUTATIONS = {
    "drop-key": _drop_key,
    "add-key": _add_key,
    "retype": _retype,
    "empty-string": _empty_string,
    "long-string": _long_string,
    "unicode-edge": _unicode_edge,
    "lone-surrogate": _lone_surrogate,
    "control-chars": _control_chars,
    "big-number": _big_number,
    "deep-nest": _deep_nest,
    "swap-event": _swap_event,
    "swap-tool": _swap_tool,
    "path-like": _path_like,
}

INVALID_UTF8 = (
    ("lone-continuation", b"\x80"),
    ("ff", b"\xff\xfe"),
    ("truncated-sequence", b"\xc3\x28"),
    ("encoded-surrogate", b"\xed\xa0\x80"),
    ("beyond-10ffff", b"\xf4\x90\x80\x80"),
    ("overlong", b"\xc0\xaf"),
)
NON_JSON = (
    ("text", b"not json at all"),
    ("python-repr", b"{'hook_event_name': 'Stop'}"),
    ("xml", b"<payload/>"),
    ("nan", b"NaN"),
    ("bom", b"\xef\xbb\xbf{}"),
    ("array", b"[]"),
    ("number", b"1"),
    ("string", b'"PreToolUse"'),
    ("null", b"null"),
    ("two-documents", b"{} {}"),
)


def _invalid_utf8(doc: dict, rng: random.Random) -> tuple[object, str]:
    name, raw = rng.choice(INVALID_UTF8)
    path = _pick_target(doc, rng, _string_paths(doc), "session_id")
    _set(doc, path, Bytes(raw))
    return doc, f"invalid-utf8:{name}:{_label(path)}"


def _duplicate_key(doc: dict, rng: random.Random) -> tuple[object, str]:
    if not doc:
        doc = {"hook_event_name": "Stop"}
    key = rng.choice(list(doc))
    items = list(doc.items())
    twin = rng.choice(("", None, "duplicate", 0))
    items.insert(rng.choice((0, len(items))), (key, twin))
    return Pairs(tuple(items)), f"duplicate-key:{key}"


STDIN_MUTATIONS = ("invalid-utf8", "non-json", "truncate", "empty-stdin", "duplicate-key")
KINDS = (*VALUE_MUTATIONS, *STDIN_MUTATIONS)


@dataclass(frozen=True)
class Case:
    """One fuzz case: its seed, the mutations applied, and the exact stdin bytes (tokens unmaterialized)."""

    index: int
    seed: Seed
    mutations: tuple[str, ...]
    stdin: bytes
    document: object = None  # the mutated document when the stdin is its plain spelling, else None
    ascii_only: bool = True

    @property
    def kinds(self) -> tuple[str, ...]:
        """The mutation kinds of the case, without their details."""
        return tuple(label.split(":", 1)[0] for label in self.mutations)


def _stdin_stage(doc: dict, kind: str, rng: random.Random, *, ascii_only: bool) -> tuple[bytes, str, object]:
    """Apply one stdin-level mutation; returns (stdin, label, the document when still a plain one)."""
    if kind == "invalid-utf8":
        value, label = _invalid_utf8(doc, rng)
        return encode_document(value, ascii_only=ascii_only), label, None
    if kind == "duplicate-key":
        value, label = _duplicate_key(doc, rng)
        return encode_document(value, ascii_only=ascii_only), label, None
    if kind == "non-json":
        name, raw = rng.choice(NON_JSON)
        return raw, f"non-json:{name}", None
    if kind == "empty-stdin":
        name, raw = rng.choice((("empty", b""), ("blank", b" \n\t")))
        return raw, f"empty-stdin:{name}", None
    data = encode_document(doc, ascii_only=ascii_only)  # truncate
    cut = rng.randrange(1, len(data)) if len(data) > 1 else 0
    return data[:cut], f"truncate:{cut}/{len(data)}", None


def make_case(seed_value: int, index: int, seeds: list[Seed], vocab: Vocabulary) -> Case:
    """The ``index``-th case of a run seeded ``seed_value``: deterministic in both, independent of the others.

    The primary mutation kind cycles through every kind (so a bounded run covers each); the seed
    and up to two extra value mutations are drawn from the case's own ``random.Random``.
    """
    rng = random.Random(f"akmon-fuzz:{seed_value}:{index}")  # noqa: S311 — reproducible inputs, not secrets
    seed = rng.choice(seeds)
    primary = KINDS[index % len(KINDS)]
    doc = copy.deepcopy(seed.payload)
    extras = rng.sample(sorted(VALUE_MUTATIONS), rng.choice((0, 0, 1, 2)))
    value_kinds = [k for k in (primary, *extras) if k in VALUE_MUTATIONS]
    labels = [VALUE_MUTATIONS[kind](doc, rng, vocab) for kind in dict.fromkeys(value_kinds)]
    ascii_only = rng.random() < 0.5  # noqa: PLR2004 — an even split between \\u escapes and raw UTF-8
    if primary in STDIN_MUTATIONS:
        stdin, label, document = _stdin_stage(doc, primary, rng, ascii_only=ascii_only)
        labels.append(label)
    else:
        stdin, document = encode_document(doc, ascii_only=ascii_only), doc
    return Case(index, seed, tuple(labels), stdin, document, ascii_only)


# --- running one case on both implementations --------------------------------------------


@dataclass(frozen=True)
class Observed:
    """What one implementation did on one case, normalized."""

    exit: int | str
    stdout: str
    stderr: str
    effects: dict[str, str]  # changed path -> sha256 of the normalized content, or "<removed>"
    contents: dict[str, str] = field(default_factory=dict)  # changed text path -> normalized content


def _walk(base: Path, prefix: str, *, skip_git: bool) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for directory, dirnames, filenames in os.walk(base):
        if skip_git and Path(directory) == base and ".git" in dirnames:
            dirnames.remove(".git")
        for name in filenames:
            path = Path(directory) / name
            if path.is_file():
                found[prefix + path.relative_to(base).as_posix()] = path
    return found


def _state(proj: Path, run_tmp: Path, ctx: Ctx) -> dict[str, tuple[str, str | None]]:
    """Every file of the project (no ``.git``) and the tempdir: path -> (digest, normalized text or None)."""
    state: dict[str, tuple[str, str | None]] = {}
    for relative, path in {**_walk(proj, "", skip_git=True), **_walk(run_tmp, "{{tmp}}/", skip_git=False)}.items():
        data = path.read_bytes()
        try:
            text: str | None = normalize(data.decode("utf-8"), ctx)
        except UnicodeDecodeError:
            text = None
        digest = hashlib.sha256(text.encode("utf-8", "surrogatepass") if text is not None else data).hexdigest()
        state[normalize(relative, ctx)] = (digest, text)
    return state


def _effects(before: dict, after: dict) -> tuple[dict[str, str], dict[str, str]]:
    effects = {path: "<removed>" for path in before if path not in after}
    contents: dict[str, str] = {}
    for path, (digest, text) in after.items():
        if before.get(path, (None,))[0] != digest:
            effects[path] = digest
            if text is not None and len(text) <= DRAFT_FILE_LIMIT:
                contents[path] = text
    return effects, contents


@dataclass
class Template:
    """One seed's materialized project for one implementation: a pristine copy restored before each case."""

    scenario: Scenario
    run: RunCtx
    proj: Path
    pristine: Path
    tree: Path
    run_tmp: Path
    env: dict[str, str]


def build_template(seed: Seed, run: RunCtx) -> Template:
    """Materialize the seed's fixture once for ``run.impl`` (warmup sync and baseline commit included)."""
    scenario = seed.scenario
    tag = "fuzz-" + seed.name.replace("/", "-")
    run_tmp = run.work / f"tmp-{tag}"
    env = scenario_env(scenario, run, run_tmp)
    proj = run.work / f"proj-{tag}"
    run_env = RunEnv(snapshot=run.snapshot, repo=run.repo, work=run.work, version=run.version, impl=run.impl)
    proj, tree = materialize_fixture(scenario.fixture, run_env, tag, warmup_sync(scenario, run, env))
    pristine = run.work / f"pristine-{run.impl}-{tag}"
    shutil.rmtree(pristine, ignore_errors=True)
    shutil.copytree(proj, pristine, symlinks=True)
    return Template(scenario, run, proj, pristine, tree, run_tmp, env)


def _materialize_stdin(stdin: bytes, ctx: Ctx) -> bytes:
    """The case's stdin with the scenario tokens replaced by this run's host facts (as runner does)."""
    for token, raw in (("{{root}}", ctx.root), ("{{tree}}", ctx.tree), ("{{tmp}}", ctx.tmp)):
        if raw:
            stdin = stdin.replace(token.encode(), raw.encode())
    return stdin.replace(b"{{version}}", ctx.version.encode())


def run_case(case: Case, template: Template) -> Observed:
    """Restore the template's pristine project and a fresh tempdir, run the hook once, observe it."""
    shutil.rmtree(template.proj, ignore_errors=True)
    shutil.copytree(template.pristine, template.proj, symlinks=True)
    shutil.rmtree(template.run_tmp, ignore_errors=True)
    template.run_tmp.mkdir(parents=True)
    scenario, run = template.scenario, template.run
    ctx = run_ctx_for(scenario, run, (template.proj, template.tree, template.run_tmp), None)
    seed_tmp_files(scenario, template.run_tmp, ctx)
    before = _state(template.proj, template.run_tmp, ctx)
    command, _payload, extra_env = _command_for(scenario, template.tree, template.proj, ctx, run.impl)
    try:
        result = subprocess.run(
            command,
            cwd=template.proj,
            env={**template.env, **extra_env},
            input=_materialize_stdin(case.stdin, ctx),
            capture_output=True,
            timeout=PROCESS_TIMEOUT,
            check=False,
        )
        exit_code: int | str = result.returncode
        stdout, stderr = result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        exit_code, stdout, stderr = "timeout", exc.stdout or b"", exc.stderr or b""
    effects, contents = _effects(before, _state(template.proj, template.run_tmp, ctx))
    return Observed(
        exit=exit_code,
        stdout=normalize(stdout.decode("utf-8", "backslashreplace"), ctx),
        stderr=normalize(stderr.decode("utf-8", "backslashreplace"), ctx),
        effects=effects,
        contents=contents,
    )


# --- comparing --------------------------------------------------------------------------


def _as_json(text: str) -> object:
    """The parsed document of a JSON stdout, or a sentinel tuple when it is not one JSON document."""
    try:
        return json.loads(text)
    except ValueError:
        return ("<text>", text)


def differing_streams(python: Observed, node: Observed) -> tuple[str, ...]:
    """The observables on which two results differ: ``exit``, ``stdout`` (JSON-aware), ``stderr``, ``files``."""
    ctx = Ctx(root="", mount="", tree="", tmp="", version="")
    streams = []
    if python.exit != node.exit:
        streams.append("exit")
    if _normalize_leaves(_as_json(python.stdout), ctx) != _normalize_leaves(_as_json(node.stdout), ctx):
        streams.append("stdout")
    if python.stderr != node.stderr:
        streams.append("stderr")
    if python.effects != node.effects:
        streams.append("files")
    return tuple(streams)


# --- known divergences -------------------------------------------------------------------


@dataclass(frozen=True)
class Known:
    """One ``fuzz.toml`` entry: a divergence signature the DV row ``dv`` accepts."""

    dv: str
    reason: str
    scripts: tuple[str, ...] = ("*",)
    streams: tuple[str, ...] = STREAMS
    mutation: str | tuple[str, ...] = "*"  # one glob, or several (any matches)
    stdin_regex: str = ""
    python_stdin_errors: str = ""

    def matches(self, case: Case, streams: tuple[str, ...], host: dict[str, str]) -> bool:
        """Whether the case's divergence is this entry's: script, streams, mutation, stdin and host condition."""
        if self.python_stdin_errors and host.get("python_stdin_errors") != self.python_stdin_errors:
            return False
        if not any(fnmatch.fnmatchcase(case.seed.script, pattern) for pattern in self.scripts):
            return False
        if not set(streams) <= set(self.streams):
            return False
        patterns = (self.mutation,) if isinstance(self.mutation, str) else self.mutation
        if not any(fnmatch.fnmatchcase(label, pattern) for label in case.mutations for pattern in patterns):
            return False
        return not self.stdin_regex or re.search(self.stdin_regex, case.stdin.decode("utf-8", "replace")) is not None


KNOWN_FIELDS = frozenset(f.name for f in dataclasses.fields(Known))


def _dv_ids(divergences: Path) -> set[str]:
    return set(re.findall(r"^\| (DV\d+) \|", divergences.read_text(encoding="utf-8"), flags=re.MULTILINE))


def load_known(path: Path = KNOWN_FILE, divergences: Path = DIVERGENCES_FILE) -> list[Known]:
    """The ``[[known]]`` entries of ``fuzz.toml``; refused when one names no DV row or holds an unknown field."""
    if not path.is_file():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    rows = _dv_ids(divergences)
    known = []
    for index, entry in enumerate(data.get("known", [])):
        extra = set(entry) - KNOWN_FIELDS
        if extra:
            raise CorpusError(f"{path}: known[{index}] has unknown field(s) {sorted(extra)}")
        if entry.get("dv") not in rows:
            raise CorpusError(f"{path}: known[{index}] names {entry.get('dv')!r}, no row of {divergences.name}")
        if not entry.get("reason"):
            raise CorpusError(f"{path}: known[{index}] carries no reason")
        bad = set(entry.get("streams", ())) - set(STREAMS)
        if bad:
            raise CorpusError(f"{path}: known[{index}] names unknown stream(s) {sorted(bad)}")
        known.append(
            Known(**{k: tuple(v) if isinstance(v, list) else v for k, v in entry.items()})  # type: ignore[arg-type]
        )
    return known


def host_facts(env: dict[str, str]) -> dict[str, str]:
    """The host conditions a ``fuzz.toml`` entry may depend on: the error handler of Python's stdin."""
    result = subprocess.run(
        [sys.executable, "-c", "import sys; print(sys.stdin.errors)"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return {"python_stdin_errors": result.stdout.strip()}


# --- draft scenarios --------------------------------------------------------------------


def _plain(value: object) -> bool:
    """Whether a document has a corpus (TOML) spelling: no null, no special token, no surrogate, int64 numbers."""
    if isinstance(value, dict):
        return all(isinstance(k, str) and _plain(k) and _plain(v) for k, v in value.items())
    if isinstance(value, list):
        return all(_plain(item) for item in value)
    if isinstance(value, str):
        return not any(0xD800 <= ord(ch) <= 0xDFFF for ch in value)  # noqa: PLR2004 — the surrogate block
    if isinstance(value, bool):
        return True
    if isinstance(value, int):
        return -(2**63) <= value < 2**63
    return isinstance(value, float) and math.isfinite(value)


def payload_toml(case: Case) -> str | None:
    """The ``[run.payload]`` section of a case, or ``None`` when the corpus schema cannot carry its stdin."""
    doc = case.document
    if not isinstance(doc, dict) or not doc or not _plain(doc):
        return None
    block = _toml_tables(doc, "run.payload")
    try:
        if tomllib.loads(block).get("run", {}).get("payload") != doc:
            return None
    except tomllib.TOMLDecodeError:
        return None
    return block


def _fixture_toml(fixture: FixtureSpec) -> list[str]:
    defaults = {"name": "base", "branch": "main", "attach": "native", "repo": False, "git": True}
    lines = ["[fixture]"]
    for name, default in defaults.items():
        value = getattr(fixture, name)
        if value != default:
            lines.append(f"{name} = {_toml_value(value)}")
    if fixture.warmup != ("after" if fixture.attach == "native" else "none"):
        lines.append(f"warmup = {_toml_string(fixture.warmup)}")
    collections = {name: getattr(fixture, name) for name in ("files", "tmp_files", "tree_files")}
    collections.update({name: list(getattr(fixture, name)) for name in ("remove", "tree_remove", "tags")})
    lines.extend(f"{name} = {_toml_value(value)}" for name, value in collections.items() if value)
    return lines if len(lines) > 1 else []


def _expected_toml(python: Observed) -> list[str]:
    lines = ["[expected]", f"exit = {python.exit if isinstance(python.exit, int) else -1}"]
    lines.append(f"stderr = {_toml_string(python.stderr)}")
    parsed = _as_json(python.stdout)
    if isinstance(parsed, dict) and _plain(parsed):
        lines.append(_toml_tables(parsed, "expected.stdout_json"))
    else:
        lines.append(f"stdout = {_toml_string(python.stdout)}")
    files = {path: text for path, text in python.contents.items() if not path.startswith("{{tmp}}/")}
    if files:
        lines.append("[expected.files]")
        lines.extend(f"{_toml_string(path)} = {_toml_string(text)}" for path, text in sorted(files.items()))
    removed = sorted(p for p, d in python.effects.items() if d == "<removed>" and not p.startswith("{{tmp}}/"))
    if removed:
        lines.append(f"file_absent = {_toml_value(removed)}")
    return lines


def _comment(text: str) -> str:
    return "\n".join("#   " + line for line in (text or "<empty>").splitlines()[:20])


def draft_scenario(case: Case, seed_value: int, results: dict[str, Observed], streams: tuple[str, ...]) -> str:
    """A candidate scenario for a divergent case, in the corpus format, marked as a draft for human review."""
    python, node = results["python"], results["node"]
    script = case.seed.script
    scenario_id = f"hooks/fuzz-{script}-s{seed_value}-c{case.index}"
    payload = payload_toml(case)
    header = [
        "# DRAFT — a differential-fuzz candidate (C111). Not corpus spec: per README § Seed protocol a",
        "# human reads the Python result below as a spec, token by token, then either fixes the twin that",
        "# is wrong and keeps this as a scenario (drop this header and the [fuzz] table), or records a",
        "# DIVERGENCES.md row plus a fuzz.toml entry and deletes this file. Removing [fuzz] is the act",
        "# of review: the corpus loader refuses a scenario file that still carries it.",
        f"# reproduce: python3 meta/conformance/fuzz.py --seed {seed_value} --case {case.index}",
        f"# seed scenario: {case.seed.name}; mutations: {', '.join(case.mutations)}",
        f"# differs on: {', '.join(streams)}; node result: exit {node.exit}",
        "# node stdout:",
        _comment(node.stdout),
        "# node stderr:",
        _comment(node.stderr),
    ]
    if payload is None:
        header.append(
            "# The corpus schema cannot carry this stdin (no raw-stdin field, or a value TOML has no spelling"
        )
        header.append("# for): its exact bytes are [fuzz].stdin_base64 — a schema gap for the reviewer to decide.")
    elif not case.ascii_only and not case.stdin.isascii():
        header.append("# The fuzz stdin spelled non-ASCII text as raw UTF-8; the runner sends json.dumps' \\u escapes.")
    lines = [
        *header,
        f"id = {_toml_string(scenario_id)}",
        'ecosystem = "shared"',
        'kind = "hook"',
        f"covers = [{_toml_string('hook:' + script)}]",
        "",
        "[fuzz]",
        f"seed = {seed_value}",
        f"case = {case.index}",
        f"mutations = {_toml_value(list(case.mutations))}",
        f"differs = {_toml_value(list(streams))}",
        f"stdin_base64 = {_toml_string(base64.b64encode(case.stdin).decode())}",
        "",
        *_fixture_toml(case.seed.scenario.fixture),
    ]
    if case.seed.scenario.env:
        lines.extend(["[env]", *(f"{k} = {_toml_string(v)}" for k, v in case.seed.scenario.env.items())])
    lines.extend(["", "[run]", f"script = {_toml_string(script)}"])
    if case.seed.scenario.run.args:
        lines.append(f"args = {_toml_value(list(case.seed.scenario.run.args))}")
    if payload is not None:
        lines.append(payload)
    lines.extend(["", *_expected_toml(python)])
    return "\n".join(lines) + "\n"


# --- the run ----------------------------------------------------------------------------


@dataclass
class Outcome:
    """One case's verdict: agree, known (with its DV) or divergent, and both results."""

    case: Case
    verdict: str
    streams: tuple[str, ...] = ()
    dv: str = ""
    results: dict[str, Observed] = field(default_factory=dict)


class Workers:
    """Private work directories, one per worker: each holds the templates of the seeds it runs.

    A seed belongs to one worker (:func:`buckets`), so its fixture is materialized once per
    implementation in the whole run, and both implementations of a case run at the same paths.
    """

    def __init__(self, root: Path, snapshot: Path, versions: dict[str, str], count: int) -> None:
        self._templates: dict[tuple[int, str, str], Template] = {}
        self.runs: dict[tuple[int, str], RunCtx] = {}
        for worker in range(count):
            work = root / f"w{worker}"
            work.mkdir(parents=True)
            for impl in IMPLS:
                self.runs[worker, impl] = RunCtx(
                    repo=REPO_ROOT, snapshot=snapshot, work=work, version=versions[impl], impl=impl
                )

    def run(self, case: Case, worker: int) -> dict[str, Observed]:
        """Run the case on both implementations in the worker's directory (the same paths for both)."""
        results = {}
        for impl in IMPLS:
            key = (worker, case.seed.name, impl)
            if key not in self._templates:
                self._templates[key] = build_template(case.seed, self.runs[worker, impl])
            results[impl] = run_case(case, self._templates[key])
        return results


def seed_of(seed_value: int, index: int, seeds: list[Seed]) -> Seed:
    """The seed :func:`make_case` draws for this case (its first draw), without building the case."""
    return random.Random(f"akmon-fuzz:{seed_value}:{index}").choice(seeds)  # noqa: S311 — reproducible inputs


def buckets(seed_value: int, indices: tuple[int, ...], seeds: list[Seed], jobs: int) -> list[list[int]]:
    """The case indices of each worker: a seed's cases all go to the worker of that seed."""
    owner = {seed.name: position % jobs for position, seed in enumerate(seeds)}
    lists: list[list[int]] = [[] for _ in range(jobs)]
    for index in indices:
        lists[owner[seed_of(seed_value, index, seeds).name]].append(index)
    return lists


def judge(case: Case, results: dict[str, Observed], known: list[Known], host: dict[str, str]) -> Outcome:
    """Classify one case's two results against the known-divergence table."""
    streams = differing_streams(results["python"], results["node"])
    if not streams:
        return Outcome(case, "agree", results=results)
    entry = next((k for k in known if k.matches(case, streams, host)), None)
    if entry is not None:
        return Outcome(case, "known", streams, entry.dv, results)
    return Outcome(case, "divergent", streams, results=results)


def timed_out(outcome: Outcome) -> bool:
    """Whether either implementation hit :data:`PROCESS_TIMEOUT` on this case."""
    return any(result.exit == "timeout" for result in outcome.results.values())


def slim(outcome: Outcome) -> Outcome:
    """An agreeing outcome without its stdin and results: a long run keeps only what a report reads."""
    if outcome.verdict != "agree":
        return outcome
    return Outcome(dataclasses.replace(outcome.case, stdin=b"", document=None), "agree")


@dataclass(frozen=True)
class Plan:
    """What one fuzz run does: its seed, the case indices, the budget and the parallelism."""

    seed: int
    indices: tuple[int, ...]
    script: str | None = None
    time_budget: float | None = None
    jobs: int = 1


def run_fuzz(plan: Plan, emit: Path) -> tuple[list[Outcome], int]:
    """Run the plan; returns every finished outcome and how many cases the time budget left unrun."""
    seeds = load_seeds(plan.script)
    if not seeds:
        raise CorpusError(f"no shared hook seed runs script {plan.script!r}")
    vocab = vocabulary(seeds)
    known = load_known()
    versions = {impl: _impl_version(REPO_ROOT, impl) for impl in IMPLS}
    deadline = time.monotonic() + plan.time_budget if plan.time_budget else None
    with tempfile.TemporaryDirectory(prefix="akmon-fuzz-") as raw:
        work = Path(raw)
        snapshot = build_snapshot(REPO_ROOT, work)
        workers = Workers(work / "workers", snapshot, versions, plan.jobs)
        host = host_facts(scenario_env(seeds[0].scenario, workers.runs[0, "python"], work))

        def drain(worker: int, indices: list[int]) -> list[Outcome | None]:
            done: list[Outcome | None] = []
            for index in indices:
                if deadline is not None and time.monotonic() > deadline:
                    done.append(None)
                    continue
                case = make_case(plan.seed, index, seeds, vocab)
                outcome = judge(case, workers.run(case, worker), known, host)
                if outcome.verdict == "divergent" and timed_out(outcome):
                    # A timeout on a loaded host is noise as often as a finding: one rerun decides.
                    outcome = judge(case, workers.run(case, worker), known, host)
                done.append(slim(outcome))
            return done

        with concurrent.futures.ThreadPoolExecutor(max_workers=plan.jobs) as pool:
            parts = pool.map(drain, range(plan.jobs), buckets(plan.seed, plan.indices, seeds, plan.jobs))
            done = [outcome for part in parts for outcome in part]
    outcomes = sorted((o for o in done if o is not None), key=lambda o: o.case.index)
    for outcome in outcomes:
        if outcome.verdict == "divergent":
            emit.mkdir(parents=True, exist_ok=True)
            name = f"fuzz-{outcome.case.seed.script}-s{plan.seed}-c{outcome.case.index}.toml"
            text = draft_scenario(outcome.case, plan.seed, outcome.results, outcome.streams)
            (emit / name).write_text(text, encoding="utf-8")
    return outcomes, len(done) - len(outcomes)


def _short(text: str, limit: int = 160) -> str:
    flat = text.replace("\n", "\\n")
    return flat if len(flat) <= limit else flat[:limit] + "…"


def report(outcomes: list[Outcome], plan: Plan, emit: Path, unrun: int) -> int:
    """Print the divergent signatures and the summary line; returns the exit code."""
    divergent = [o for o in outcomes if o.verdict == "divergent"]
    groups: dict[tuple[str, tuple[str, ...], str], list[Outcome]] = {}
    for outcome in divergent:
        key = (outcome.case.seed.script, outcome.streams, "+".join(sorted(set(outcome.case.kinds))))
        groups.setdefault(key, []).append(outcome)
    for (script, streams, kind), members in sorted(groups.items()):
        first = members[0]
        py, node = first.results["python"], first.results["node"]
        where = f"{script} on {','.join(streams)} after {kind or 'no mutation'}"
        print(f"DIVERGENT {where}: {len(members)} case(s), e.g. case {first.case.index}")
        print(f"  mutations: {', '.join(first.case.mutations)}")
        print(f"  python: exit {py.exit} stdout {_short(py.stdout)!r} stderr {_short(py.stderr)!r}")
        print(f"  node:   exit {node.exit} stdout {_short(node.stdout)!r} stderr {_short(node.stderr)!r}")
        if "files" in streams:
            print(f"  files python {sorted(py.effects)} node {sorted(node.effects)}")
    known = [o for o in outcomes if o.verdict == "known"]
    tally: dict[tuple[str, str, tuple[str, ...]], int] = {}
    for outcome in known:
        key = (outcome.dv, outcome.case.seed.script, outcome.streams)
        tally[key] = tally.get(key, 0) + 1
    for (dv, script, streams), count in sorted(tally.items()):
        print(f"KNOWN {dv} {script} on {','.join(streams)}: {count} case(s)")
    scripts = len({o.case.seed.script for o in outcomes})
    budget = f" · {unrun} unrun (time budget)" if unrun else ""
    drafts = f" · drafts in {emit}" if divergent else ""
    print(
        f"fuzz: {len(outcomes)} cases · {scripts} scripts · "
        f"{sum(o.verdict == 'agree' for o in outcomes)} agree · {len(known)} known"
        f"{' (' + ', '.join(sorted({o.dv for o in known})) + ')' if known else ''} · "
        f"{len(divergent)} divergent · seed {plan.seed}{budget}{drafts}"
    )
    return 1 if divergent else 0


def main(argv: list[str] | None = None) -> int:
    """Parse the CLI, run the fuzz cases on both implementations, and report."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cases", type=int, default=100, help="how many cases to run (default 100)")
    parser.add_argument("--seed", type=int, default=0, help="the run's seed: every case derives from it")
    parser.add_argument("--case", type=int, action="append", default=[], help="run only this case index (repeatable)")
    parser.add_argument("--script", help="fuzz only the seeds of this hook")
    parser.add_argument("--emit", help="where divergent cases' draft scenarios go (default: a fresh temp dir)")
    parser.add_argument("--time-budget", type=float, help="stop starting new cases after this many seconds")
    parser.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1), help="parallel workers")
    args = parser.parse_args(argv)
    if shutil.which("node") is None:
        print(
            "fuzz: prerequisite missing — the node binary is not on PATH (node >= 22); the differential run "
            "compares the Python and the Node hooks, so it cannot run without it",
            file=sys.stderr,
        )
        return 2
    indices = tuple(args.case) if args.case else tuple(range(args.cases))
    plan = Plan(args.seed, indices, args.script, args.time_budget, max(1, args.jobs))
    emit = Path(args.emit) if args.emit else Path(tempfile.mkdtemp(prefix="akmon-fuzz-drafts-"))
    try:
        outcomes, unrun = run_fuzz(plan, emit)
    except CorpusError as exc:
        print(f"fuzz: {exc}", file=sys.stderr)
        return 2
    return report(outcomes, plan, emit, unrun)


if __name__ == "__main__":
    raise SystemExit(main())
