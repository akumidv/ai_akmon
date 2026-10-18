#!/usr/bin/env python3
"""Recorded fuzz seeds from real hook payloads (C121, ``fuzz/seeds/README.md``).

The differential fuzz run (``fuzz.py``) mutates the payloads of the hook scenarios; a recorded
seed adds a payload the harness really sent, so the run starts from shapes nobody wrote down.
Recording is two steps with a human between them and the commit:

``tee`` wraps a hook command where a developer wires it (their untracked
``.claude/settings.local.json``): it copies the stdin bytes to ``DIR/<script>--<n>.json`` and then
runs the command on the same bytes, its stdout, stderr and exit code passed through unchanged. A
recording failure never changes what the hook does: the copy is skipped silently, and so is a
``DIR`` inside the repository (raw captures are private material and are never committed).

``scrub`` turns those raw captures into seeds: paths under the project become ``{{root}}``,
paths under the tempdir ``{{tmp}}``, any other path under the home directory a neutral one;
ids become fixed neutral ones; free text (prompts, messages, tool output, file contents) a short
placeholder — the keys, types and nesting stay. One seed is kept per distinct (script, shape). A
capture it cannot scrub — not one JSON object, or a home path outside the project inside a longer
string — is skipped with a line. A dry run lists what it would write; ``--apply`` writes it.

Usage:
    python3 meta/conformance/fuzz_record.py tee --out DIR [--script NAME] -- <hook command...>
    python3 meta/conformance/fuzz_record.py scrub --raw DIR --project-root P [--apply]
                                                  [--seeds-dir D]

Standard library only: ``tee`` runs on every hook call, before anything else is installed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SEEDS_DIR = Path(__file__).resolve().parent / "fuzz" / "seeds"
#: Members whose whole subtree is free text: every string leaf in it becomes the placeholder.
FREE_TEXT_KEYS = frozenset(
    {
        "prompt",
        "message",
        "tool_response",
        "content",
        "old_string",
        "new_string",
        "new_source",
        "description",
        "last_assistant_message",
        "custom_instructions",
        "summary",
        "reason",
        "text",
        "pattern",
        "query",
    }
)
PLACEHOLDER = "scrubbed"
#: The neutral spelling of a home-directory path outside the project.
NEUTRAL_HOME_PATH = "/home/user/elsewhere"
#: Exit status of a hook command that could not be started (the shell's "command not found").
NOT_STARTED = 127
_LABEL_UNSAFE = re.compile(r"[^a-z0-9]+")


# --- tee -------------------------------------------------------------------------------


def script_name(command: Sequence[str]) -> str:
    """The hook a command runs: the stem of its ``.py``/``.mjs`` file, else the word after ``hook``."""
    for index, arg in enumerate(command):
        if arg.endswith((".py", ".mjs")):
            return Path(arg).stem
        if arg == "hook" and index + 1 < len(command):
            return command[index + 1]
    return Path(command[-1]).name if command else "hook"


def _inside(path: Path, roots: Sequence[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def record(stdin: bytes, out: Path, script: str, private_roots: Sequence[Path]) -> Path | None:
    """Write ``stdin`` to the next free ``out/<script>--<n>.json``; ``None`` when it is not recorded.

    Best effort by contract: a failing write, or an ``out`` inside one of ``private_roots`` (the
    repository), records nothing and raises nothing — the hook runs the same either way.
    """
    try:
        target_dir = out.resolve()
        if _inside(target_dir, [root.resolve() for root in private_roots]):
            return None
        target_dir.mkdir(parents=True, exist_ok=True)
        taken = [p.stem.rpartition("--")[2] for p in target_dir.glob(f"{script}--*.json")]
        number = max((int(n) for n in taken if n.isdigit()), default=0)
        for _attempt in range(100):  # a parallel hook may take the same number: try the next one
            number += 1
            target = target_dir / f"{script}--{number}.json"
            try:
                with target.open("xb") as handle:
                    handle.write(stdin)
            except FileExistsError:
                continue
            return target
    except OSError:
        return None  # a recording failure never changes the hook's behaviour
    return None


def tee(stdin: bytes, command: Sequence[str], out: Path, script: str, private_roots: Sequence[Path]) -> int:
    """Record ``stdin``, then run ``command`` on it with stdout and stderr inherited; its exit code."""
    record(stdin, out, script, private_roots)
    try:
        result = subprocess.run(list(command), input=stdin, check=False)
    except OSError as exc:
        print(f"fuzz_record tee: cannot run {command[0]!r}: {exc.strerror}", file=sys.stderr)
        return NOT_STARTED
    return result.returncode if result.returncode >= 0 else 128 - result.returncode


# --- scrub -----------------------------------------------------------------------------


class UnscrubbableError(ValueError):
    """A capture the scrubber cannot make neutral; the message says why."""


@dataclass(frozen=True)
class Places:
    """The host directories a capture's paths are rewritten against."""

    root: str  # the project: becomes {{root}}
    tmps: tuple[str, ...]  # the tempdirs: become {{tmp}}
    home: str  # the home directory: any other path under it becomes NEUTRAL_HOME_PATH


def _segment(prefix: str) -> str:
    """A regex for the directory ``prefix`` as a whole path: not the start of a longer name."""
    return re.escape(prefix.rstrip("/")) + r"(?=/|$|[^\w.-])"


def scrub_string(text: str, places: Places) -> str:
    """``text`` with project and tempdir paths tokenized; a home path outside them neutralized or refused.

    The most specific directory wins: the prefixes apply longest first, so a project under the
    tempdir is ``{{root}}``, and a tempdir under the home directory is ``{{tmp}}``.
    """
    rules = [(places.root, "{{root}}"), *((tmp, "{{tmp}}") for tmp in places.tmps), (places.home, None)]
    for prefix, token in sorted(rules, key=lambda rule: len(rule[0].rstrip("/")), reverse=True):
        if not prefix.rstrip("/"):
            continue
        if token is not None:
            text = re.sub(_segment(prefix), token, text)
        elif re.fullmatch(_segment(prefix) + r"\S*", text):
            return NEUTRAL_HOME_PATH  # the whole value is one path under the home directory, outside the project
        elif re.search(_segment(prefix), text):
            raise UnscrubbableError(f"a home path outside the project inside a string: {text[:80]!r}")
    return text


def _free_text(value: object) -> object:
    """``value`` with every string leaf replaced by the placeholder, its keys and other leaves kept."""
    if isinstance(value, str):
        return PLACEHOLDER
    if isinstance(value, dict):
        return {key: _free_text(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_free_text(item) for item in value]
    return value


def scrub_value(value: object, places: Places, key: str | None = None) -> object:
    """One payload member scrubbed: ids neutral, free text placeholder, paths rewritten, shape kept."""
    if key is not None and key in FREE_TEXT_KEYS:
        return _free_text(value)
    if key is not None and key.endswith("_id") and isinstance(value, str):
        return f"{key[:-3].replace('_', '-')}-recorded"
    if isinstance(value, str):
        return scrub_string(value, places)
    if isinstance(value, dict):
        return {scrub_string(k, places): scrub_value(item, places, k) for k, item in value.items()}
    if isinstance(value, list):
        return [scrub_value(item, places, key) for item in value]
    return value


def shape(value: object) -> object:
    """The key/type shape of a document: object keys and nesting kept, every leaf its type name."""
    if isinstance(value, dict):
        return {key: shape(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [shape(item) for item in value]
    return type(value).__name__


def shape_key(script: str, payload: object) -> str:
    """A short stable digest of (script, shape): the dedup key and the seed name's suffix."""
    text = json.dumps([script, shape(payload)], sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]


def seed_name(script: str, payload: Mapping, digest: str) -> str:
    """``<script>--<event>-<tool>-<digest>.json``: what the seed is, in its file name."""
    parts = [payload.get("hook_event_name"), payload.get("tool_name"), digest]
    label = "-".join(_LABEL_UNSAFE.sub("-", p.lower()).strip("-") for p in parts if isinstance(p, str) and p)
    return f"{script}--{label}.json"


def scrub_capture(path: Path, places: Places) -> tuple[str, dict]:
    """(script, scrubbed payload) of one raw capture ``<script>--<n>.json``; ``UnscrubbableError`` when it cannot."""
    script, sep, _number = path.stem.rpartition("--")
    if not sep or not script:
        raise UnscrubbableError("not named <script>--<n>.json")
    try:
        payload = json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UnscrubbableError(f"not a JSON document ({type(exc).__name__})") from exc
    if not isinstance(payload, dict):
        raise UnscrubbableError("not one JSON object")
    try:
        scrubbed = scrub_value(payload, places)
    except RecursionError as exc:
        raise UnscrubbableError("nested too deep to walk") from exc
    if not isinstance(scrubbed, dict):  # scrub_value keeps an object an object; this only narrows the type
        raise UnscrubbableError("not one JSON object")
    if places.home.rstrip("/") and places.home.rstrip("/") in json.dumps(scrubbed, ensure_ascii=False):
        raise UnscrubbableError("the home directory survived the rewrite")
    return script, scrubbed


@dataclass(frozen=True)
class Plan:
    """What a scrub would do: the seeds to write (name -> payload) and one line per capture."""

    seeds: dict[str, dict]
    lines: tuple[str, ...]


def _existing_shapes(seeds_dir: Path) -> dict[str, str]:
    """The (script, shape) digests of the seeds already in ``seeds_dir``, to the file holding each."""
    shapes: dict[str, str] = {}
    for path in sorted(seeds_dir.glob("*--*.json")) if seeds_dir.is_dir() else ():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # a broken seed is fuzz.py's to refuse, not the scrubber's
        shapes[shape_key(path.stem.partition("--")[0], payload)] = path.name
    return shapes


def plan_scrub(raw: Path, places: Places, seeds_dir: Path) -> Plan:
    """Scrub every capture under ``raw`` and keep one seed per (script, shape) not already in ``seeds_dir``."""
    seen = _existing_shapes(seeds_dir)
    seeds: dict[str, dict] = {}
    lines: list[str] = []
    for path in sorted(raw.glob("*.json"), key=lambda p: (p.stem.rpartition("--")[0], _ordinal(p))):
        try:
            script, payload = scrub_capture(path, places)
        except UnscrubbableError as exc:
            lines.append(f"skip {path.name}: {exc}")
            continue
        digest = shape_key(script, payload)
        if digest in seen:
            lines.append(f"same shape {path.name}: as {seen[digest]}")
            continue
        name = seed_name(script, payload, digest)
        seen[digest] = name
        seeds[name] = payload
        lines.append(f"seed {name}: from {path.name}")
    return Plan(seeds, tuple(lines))


def _ordinal(path: Path) -> int:
    number = path.stem.rpartition("--")[2]
    return int(number) if number.isdigit() else 0


def write_seeds(plan: Plan, seeds_dir: Path) -> list[Path]:
    """Write the plan's seeds into ``seeds_dir``, one indented JSON object per file."""
    seeds_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, payload in plan.seeds.items():
        target = seeds_dir / name
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(target)
    return written


# --- CLI ---------------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    tee_parser = sub.add_parser("tee", help="record a hook's stdin, then run the hook on it")
    tee_parser.add_argument("--out", required=True, help="the raw-capture directory, outside the repository")
    tee_parser.add_argument("--script", help="the hook's name in the capture file name (default: from the command)")
    tee_parser.add_argument("hook", nargs=argparse.REMAINDER, help="-- then the hook command")
    scrub_parser = sub.add_parser("scrub", help="turn raw captures into seeds (a dry run unless --apply)")
    scrub_parser.add_argument("--raw", required=True, help="the raw-capture directory")
    scrub_parser.add_argument("--project-root", required=True, help="the project the captures were made in")
    scrub_parser.add_argument("--apply", action="store_true", help="write the seeds (default: list them)")
    scrub_parser.add_argument("--seeds-dir", default=str(SEEDS_DIR), help="where seeds go (default: fuzz/seeds/)")
    return parser


def _run_tee(args: argparse.Namespace) -> int:
    command = args.hook[1:] if args.hook[:1] == ["--"] else args.hook
    if not command:
        print("fuzz_record tee: no hook command after --", file=sys.stderr)
        return 2
    private = [REPO_ROOT]
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        private.append(Path(os.environ["CLAUDE_PROJECT_DIR"]))
    stdin = sys.stdin.buffer.read() if sys.stdin is not None else b""
    sys.stdout.flush()
    return tee(stdin, command, Path(args.out).expanduser(), args.script or script_name(command), private)


def _run_scrub(args: argparse.Namespace) -> int:
    raw = Path(args.raw).expanduser()
    if not raw.is_dir():
        print(f"fuzz_record scrub: no raw-capture directory {raw}", file=sys.stderr)
        return 2
    tmps = {tempfile.gettempdir(), str(Path(tempfile.gettempdir()).resolve()), "/tmp"}  # noqa: S108 — a path to rewrite
    root = Path(args.project_root).expanduser().resolve()
    places = Places(root=str(root), tmps=tuple(sorted(tmps)), home=str(Path.home()))
    seeds_dir = Path(args.seeds_dir)
    plan = plan_scrub(raw, places, seeds_dir)
    for line in plan.lines:
        print(line)
    if args.apply:
        written = write_seeds(plan, seeds_dir)
        print(f"fuzz_record scrub: wrote {len(written)} seed(s) into {seeds_dir}; review them before committing")
    else:
        print(f"fuzz_record scrub: dry run, {len(plan.seeds)} seed(s) would be written; --apply writes them")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse the CLI and run ``tee`` or ``scrub``; the process exit code."""
    args = _parser().parse_args(argv)
    return _run_tee(args) if args.command == "tee" else _run_scrub(args)


if __name__ == "__main__":
    raise SystemExit(main())
