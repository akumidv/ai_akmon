#!/usr/bin/env python3
"""The pairing gate (ADR 0020 D03; design node-consumers.md §5 gate 3).

Every consumer-executable ``.py`` — the population is the five ``CODE_ROOTS`` imported from
``coverage.py``, so the roots have one owner — has its ``.mjs`` counterpart under ``js/``, or
an exemption in ``pairing.toml`` with a reason and the owning task that ports it. The path the
counterpart is checked at is the mirrored layout of the design (§4): ``X/Y.py`` → ``js/X/Y.mjs``,
with the package mapping to the package — ``src/akmon/cli.py`` is ``js/akmon/cli.mjs``, the npm
``bin``. The exemption list shrinks as the port lands (C104 hooks, C105 CLI, C107 update,
C108 tools); an exemption that matches nothing is a failure, and so is one that has become
unnecessary — matching only files whose port has already landed — because a list that keeps
covering a ported file no longer says what is outstanding.

The gate reads names, not intent, so a placeholder counterpart is credited as a port unless told
otherwise: a ``[[stub]]`` entry in ``pairing.toml`` names a ``js/`` ``.mjs`` that only announces
the missing port. The ``.py`` behind it is then treated as unported — it stays in the exempt count,
and still needs the exemption that keeps its gap green — so the report cannot make an outstanding
port look done.

Usage: python3 meta/conformance/pairing.py [--tree REPO]
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Literal

CORPUS_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(CORPUS_ROOT))
sys.path.insert(0, str(CORPUS_ROOT.parents[1]))

from corpus import REPO_ROOT, CorpusError  # noqa: E402
from coverage import CODE_ROOTS  # noqa: E402

from common.findings import Finding, exit_code, print_findings  # noqa: E402


def _js_rel(rel: str) -> str:
    """The ``.mjs`` counterpart of one repo-relative ``.py`` path, relative to ``js/``."""
    return rel.removeprefix("src/").removesuffix(".py") + ".mjs"


def _read_config(path: Path) -> dict:
    """Parse ``pairing.toml``; a malformed file or an unknown table is refused, like ``coverage.toml``."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise CorpusError(f"{path}: pairing.toml is not valid TOML ({' '.join(str(exc).split())})") from exc
    unknown = set(data) - {"exempt", "stub"}
    if unknown:
        raise CorpusError(f"{path}: unknown tables {sorted(unknown)}; pairing.toml holds only [[exempt]] and [[stub]]")
    return data


def _entries(data: dict, table: str, path: Path) -> tuple[dict[str, str], ...]:
    """One table's entries, each carrying the ``path``, ``reason`` and ``task`` the gate quotes."""
    entries = data.get(table, [])
    if not isinstance(entries, list):
        raise CorpusError(f"{path}: [[{table}]] must be an array of tables")
    for entry in entries:
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(key), str) and entry.get(key).strip() for key in ("path", "reason", "task")
        ):
            raise CorpusError(f"{path}: [[{table}]] entry {entry!r} needs path, reason and task strings")
    return tuple(entries)


def load_exemptions(path: Path | None = None) -> tuple[str, ...]:
    """The ``[[exempt]]`` globs of ``pairing.toml``, in file order."""
    path = path or CORPUS_ROOT / "pairing.toml"
    return tuple(entry["path"] for entry in _entries(_read_config(path), "exempt", path))


def load_stubs(path: Path | None = None, repo: Path | None = None) -> frozenset[str]:
    """The ``[[stub]]`` counterparts of ``pairing.toml``, each a ``js/``-relative ``.mjs`` that exists.

    A placeholder is named by its exact path, once: a typo or a duplicate would quietly retire the
    entry that keeps a stub out of the paired count, so the gate refuses both.
    """
    path = path or CORPUS_ROOT / "pairing.toml"
    repo = repo or REPO_ROOT
    stubs = [_stub_path(entry["path"], repo, path) for entry in _entries(_read_config(path), "stub", path)]
    duplicated = sorted({stub for stub in stubs if stubs.count(stub) > 1})
    if duplicated:
        raise CorpusError(f"{path}: duplicate [[stub]] entries {duplicated}")
    return frozenset(stubs)


def _stub_path(stub: str, repo: Path, path: Path) -> str:
    """One validated ``[[stub]]`` path: a ``.mjs`` whose file is really under ``js/``."""
    if not stub.endswith(".mjs"):
        raise CorpusError(f"{path}: [[stub]] path {stub!r} must name a .mjs relative to js/")
    if not (repo / "js" / stub).is_file():
        raise CorpusError(f"{path}: [[stub]] path {stub!r} names no file under js/ of {repo}")
    return stub


#: What a population ``.py`` has on the js/ side: its port, a placeholder for it, or nothing.
Counterpart = Literal["port", "stub", "absent"]


def _counterpart(repo: Path, rel: str, stubs: frozenset[str]) -> Counterpart:
    """The counterpart state of one repo-relative ``.py``: ported, stubbed, or absent."""
    mirror = _js_rel(rel)
    if not (repo / "js" / mirror).is_file():
        return "absent"
    return "stub" if mirror in stubs else "port"


def _is_exempt(rel: str, exemptions: Iterable[str]) -> bool:
    """True when some ``[[exempt]]`` glob covers the file."""
    return any(fnmatch.fnmatch(rel, pattern) for pattern in exemptions)


def _covered(pattern: str, population: Sequence[str]) -> list[str]:
    """The population files one ``[[exempt]]`` glob covers."""
    return [rel for rel in population if fnmatch.fnmatch(rel, pattern)]


def _gap_finding(rel: str, counterpart: Counterpart) -> Finding:
    placeholder = "a stub .mjs placeholder under js/" if counterpart == "stub" else "no .mjs counterpart under js/"
    return Finding(
        "error",
        "pairing.gap",
        f"{rel} has {placeholder} and no pairing.toml exemption",
        rel,
        "Port the .mjs at the same relative path, or add an exemption with a reason and the owning task.",
    )


def _stale_findings(
    exemptions: Iterable[str], population: Sequence[str], counterparts: Mapping[str, Counterpart]
) -> list[Finding]:
    """An exemption is stale when it covers nothing at all, or only files the port already covers."""
    findings: list[Finding] = []
    for pattern in exemptions:
        covered = _covered(pattern, population)
        if not covered:
            findings.append(
                Finding(
                    "error",
                    "pairing.stale",
                    f"pairing.toml pattern {pattern!r} matches no consumer-executable .py",
                    pattern,
                    "Remove the pattern — the exemption list must not lie.",
                )
            )
        elif all(counterparts[rel] == "port" for rel in covered):
            findings.append(
                Finding(
                    "error",
                    "pairing.stale",
                    f"pairing.toml pattern {pattern!r} is fully superseded: every .py it covers already has its .mjs",
                    pattern,
                    "Remove the pattern — the port it covered has landed, so it no longer exempts anything.",
                )
            )
    return findings


def _ok_finding(total: int, paired: int, exempted: int, stubbed: int) -> Finding:
    return Finding(
        "ok",
        "pairing.ok",
        f"all {total} consumer-executable .py files paired ({paired} with their .mjs, {exempted} exempt, "
        f"{stubbed} of the exempt covered by a stub .mjs only)",
        "",
        "Keep the exemption list shrinking as the port lands.",
    )


def check_pairing(repo: Path | None = None, config: Path | None = None) -> list[Finding]:
    """The gate over the tree at ``repo`` (default: this repository), reading ``config`` for its lists.

    The findings are the gaps and stale exemptions, or one ok finding carrying the counts. ``config``
    defaults to this corpus's ``pairing.toml``. A counterpart that is a listed stub does not count as a
    port — the file behind it stays exempt, so it needs its own exemption and cannot inflate the paired
    count. An exemption is live only while it still covers something unported: a pattern matching no
    file, or only ported files, is stale.
    """
    repo = repo or REPO_ROOT
    population = sorted(
        path.relative_to(repo).as_posix()
        for root in CODE_ROOTS
        for path in sorted((repo / root).rglob("*.py"))
    )
    if not population:
        raise CorpusError(
            f"{repo}: no consumer-executable .py under {', '.join(CODE_ROOTS)}; the pairing population is empty"
        )
    exemptions = load_exemptions(config)
    stubs = load_stubs(config, repo)
    counterparts = {rel: _counterpart(repo, rel, stubs) for rel in population}

    findings: list[Finding] = []
    paired = exempted = stubbed = 0
    for rel in population:
        counterpart = counterparts[rel]
        if counterpart == "port":
            paired += 1
        elif _is_exempt(rel, exemptions):
            exempted += 1
            if counterpart == "stub":
                stubbed += 1
        else:
            findings.append(_gap_finding(rel, counterpart))
    findings.extend(_stale_findings(exemptions, population, counterparts))
    if findings:
        return findings
    return [_ok_finding(len(population), paired, exempted, stubbed)]


def main(argv: list[str] | None = None) -> int:
    """Parse the gate's CLI, run it against the tree, and print the findings."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tree", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    findings = check_pairing(Path(args.tree).resolve())
    print_findings(findings)
    return exit_code(findings)


if __name__ == "__main__":
    raise SystemExit(main())
