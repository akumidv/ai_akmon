"""``akmon trust`` — accept, inspect and revoke the digests of a project's own grant files (C172).

ADR 0025 D04 and D05: a grant file a project declares takes effect only once the owner accepted
its content. The store, the digest and the log are ``common/grant_trust.py``'s; this module is the
command line over them. Imported lazily by ``akmon.cli``, as ``init`` is.

Acceptance happens at an interactive terminal and nowhere else: there is deliberately no ``--yes``
and no non-interactive path. The terminal check and the confirmation read both go through
:class:`TrustIO`, the one seam, so a test drives them without a pseudo-terminal.

The JavaScript twin is ``js/akmon/_trust.mjs``; the texts and exit codes are the same.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, TextIO

from akmon import _tree, cli

_SUBCOMMANDS = ("status", "diff", "accept", "revoke", "report")
_USAGE = (
    "usage: akmon trust status [PATH...] | diff [PATH...] | accept [PATH...] | revoke DIGEST-or-PATH | report\n"
    "  status   one line per grant file: state, short digest, path; exit 1 when any is not trusted\n"
    "  diff     each untrusted file against the last accepted version of the same path\n"
    "  accept   show each untrusted file, then ask at the terminal; refused when stdin is not a terminal\n"
    "  revoke   forget an accepted digest (a digest of at least 12 hex characters, or a file)\n"
    "  report   what the trust log records (ADR 0025/D05)\n"
    "PATH names grant files or directories; none names every file under <dev root>/grants/.\n"
)
_NOT_INTERACTIVE = (
    "akmon trust accept: acceptance needs an interactive terminal; stdin is not one (ADR 0025/D05: "
    "there is no non-interactive acceptance)"
)


@dataclass(frozen=True)
class TrustIO:
    """What the command touches of the process: environment, cwd, streams, the terminal check and the prompt."""

    environ: Mapping[str, str]
    cwd: Path
    out: TextIO
    err: TextIO
    interactive: bool
    ask: Callable[[str], str]


def process_io() -> TrustIO:
    """The real process: its environment, cwd and streams; interactive iff stdin is a terminal."""
    return TrustIO(os.environ, Path.cwd(), sys.stdout, sys.stderr, sys.stdin.isatty(), input)


class _Trust:
    """One run of ``akmon trust`` in the project the cwd belongs to."""

    def __init__(self, io: TrustIO) -> None:
        tree = _tree.embedded_tree_root()
        self.lib: ModuleType = cli._embedded_common_module(tree, "grant_trust")
        resolver = cli._embedded_common_module(tree, "project_root")
        self.io = io
        self.root, notice = resolver.resolve_project_root(None, io.cwd)
        self.rooted = notice is None
        if notice:
            io.err.write(notice + "\n")
        self.store = self.lib.resolve_store(io.environ, self.root)
        self.grants_dir = self.lib.grants_directory(self.root)

    def _say(self, line: str) -> None:
        self.io.out.write(line + "\n")

    def _targets(self, paths: Sequence[str]) -> list:
        """The grant files named by ``paths`` (the default set when none), each read once."""
        if not paths:
            files = self.lib.list_grant_files(self.grants_dir)
        else:
            resolver = cli._embedded_common_module(_tree.embedded_tree_root(), "project_root")
            files = []
            for given in paths:
                path = resolver.resolve_path(self.io.cwd / given)
                if path.is_dir():
                    files.extend(self.lib.list_grant_files(path))
                elif path.is_file():
                    files.append(path)
                else:
                    raise self.lib.GrantTrustError(f"{given}: no such file or directory")
        unique = list(dict.fromkeys(files))
        return [self.lib.load_grant(path, self.root) for path in unique]

    def _empty(self, paths: Sequence[str]) -> int:
        where = f"under {self.grants_dir.relative_to(self.root).as_posix()}/" if not paths else "in the given paths"
        self._say(f"akmon trust: no grant files {where}")
        return 0

    def status(self, paths: Sequence[str]) -> int:
        grants = self._targets(paths)
        if not grants:
            return self._empty(paths)
        untrusted = 0
        for grant in grants:
            state = self.lib.file_trust(grant, self.store).state
            untrusted += state != self.lib.TrustState.TRUSTED
            self._say(f"{state.value:<8} {grant.digest[: self.lib.SHORT_DIGEST_LENGTH]}  {grant.relative}")
        return 1 if untrusted else 0

    def _show(self, trust: Any) -> None:
        """What the owner reads before accepting: the change since the last accepted version, or the whole file."""
        grant, short = trust.grant, self.lib.SHORT_DIGEST_LENGTH
        if trust.state == self.lib.TrustState.NEW:
            elsewhere = self.lib.last_accepted_elsewhere(grant.relative, grant.project, self.store)
            if elsewhere is not None:
                self._show_against_other_project(grant, elsewhere)
                return
            self._say(f"=== {grant.relative}: new, no earlier version accepted; the whole file follows ===")
            text = grant.content.decode("utf-8", errors="replace")
            self.io.out.write(text if text.endswith("\n") or not text else text + "\n")
            return
        self._say(f"=== {grant.relative}: changed since {trust.previous[:short]} ===")
        before = self.lib.accepted_content(trust.previous, self.store)
        text = self.lib.unified_diff(
            before,
            grant.content,
            f"{grant.relative} (accepted {trust.previous[:short]})",
            f"{grant.relative} (now {grant.digest[:short]})",
        )
        self.io.out.write(text or "(the text is the same; only the final newline differs)\n")

    def _show_against_other_project(self, grant: Any, elsewhere: Any) -> None:
        """A file new to this project, as the change from the version another project accepted at its path."""
        short = self.lib.SHORT_DIGEST_LENGTH
        self._say(
            f"=== {grant.relative}: new in this project; last accepted in project {elsewhere.project} "
            f"as {elsewhere.digest[:short]}, the change since that version follows ==="
        )
        text = self.lib.unified_diff(
            self.lib.accepted_content(elsewhere.digest, self.store),
            grant.content,
            f"{grant.relative} (accepted in project {elsewhere.project}, {elsewhere.digest[:short]})",
            f"{grant.relative} (now {grant.digest[:short]})",
        )
        self.io.out.write(text or "(the text is the same; only the final newline differs)\n")

    def diff(self, paths: Sequence[str]) -> int:
        grants = self._targets(paths)
        if not grants:
            return self._empty(paths)
        shown = 0
        for grant in grants:
            trust = self.lib.file_trust(grant, self.store)
            if trust.state != self.lib.TrustState.TRUSTED:
                self._show(trust)
                shown += 1
        if not shown:
            self._say("akmon trust: every grant file is trusted; nothing to show")
        return 0

    def accept(self, paths: Sequence[str]) -> int:
        if not self.rooted:
            return 2  # no project root: the notice is printed, no grant is accepted for a guess (ADR 0022 D09)
        if not self.io.interactive:
            self.io.err.write(_NOT_INTERACTIVE + "\n")
            return 2
        grants = self._targets(paths)
        if not grants:
            return self._empty(paths)
        declined = 0
        for grant in grants:
            trust = self.lib.file_trust(grant, self.store)
            if trust.state == self.lib.TrustState.TRUSTED:
                self._say(f"{grant.relative}: already trusted")
                continue
            self._show(trust)
            if self._confirmed(f"accept {grant.relative}? [y/N] "):
                event = self.lib.accept(grant, self.store)
                self._say(f"{grant.relative}: accepted {event.digest[: self.lib.SHORT_DIGEST_LENGTH]}")
            else:
                declined += 1
                self._say(f"{grant.relative}: not accepted")
        return 1 if declined else 0

    def _confirmed(self, prompt: str) -> bool:
        try:
            answer = self.io.ask(prompt)
        except EOFError:
            return False
        return answer.strip().lower() in ("y", "yes")

    def revoke(self, reference: str) -> int:
        if not self.rooted:
            return 2  # no project root: the notice was printed, and nothing is revoked (ADR 0022 D09)
        if len(reference) >= self.lib.SHORT_DIGEST_LENGTH and set(reference) <= set("0123456789abcdef"):
            digest = self.lib.resolve_digest(reference, self.store)
        else:
            grants = self._targets([reference])
            if len(grants) != 1:
                raise self.lib.GrantTrustError(f"{reference}: revoke names one file, not {len(grants)}")
            grant = grants[0]
            if self.lib.is_accepted(grant.digest, self.store):
                digest = grant.digest
            else:
                digest = self.lib.last_accepted(grant.relative, grant.project, self.store)
                if digest is None:
                    raise self.lib.GrantTrustError(f"{grant.relative}: no accepted version to revoke")
        event = self.lib.revoke(digest, self.store)
        self._say(f"revoked {digest[: self.lib.SHORT_DIGEST_LENGTH]} ({event.path})")
        return 0

    def report(self) -> int:
        report = self.lib.trust_report(self.store)
        median = "-" if report.median_seconds is None else f"{report.median_seconds:.1f}"
        self._say(f"accepts: {report.accepts}")
        self._say(f"re-accepts: {report.reaccepts}")
        self._say(f"revokes: {report.revokes}")
        self._say(f"untrusted digests sighted: {report.untrusted_digests}")
        self._say(f"sighted digests later accepted: {report.accepted_after_sighting}")
        self._say(f"median seconds from sighting to acceptance: {median}")
        return 0


def _usage_error(io: TrustIO, message: str) -> int:
    io.err.write(f"akmon trust: {message}\n{_USAGE}")
    return 2


def _argument_problem(command: str, rest: Sequence[str]) -> str | None:
    """What is wrong with the arguments of ``command``, or ``None`` when they can be run."""
    if command == "revoke" and len(rest) != 1:
        return "revoke takes exactly one DIGEST or PATH"
    if command == "report" and rest:
        return "report takes no arguments"
    option = next((argument for argument in rest if argument.startswith("-")), None)
    return None if option is None else f"{command} takes no options; got {option!r}"


def _run(session: _Trust, command: str, rest: list[str]) -> int:
    if command == "revoke":
        return session.revoke(rest[0])
    if command == "report":
        return session.report()
    if command == "status":
        return session.status(rest)
    if command == "diff":
        return session.diff(rest)
    return session.accept(rest)


def main(argv: Sequence[str], io: TrustIO | None = None) -> int:
    """Run ``akmon trust <subcommand>``; ``io`` is the process unless a test hands in a fake."""
    io = io if io is not None else process_io()
    if not argv:
        io.err.write(_USAGE)
        return 2
    if argv[0] in ("-h", "--help"):
        io.out.write(_USAGE)
        return 0
    command, rest = argv[0], list(argv[1:])
    problem = f"unknown command {command!r}" if command not in _SUBCOMMANDS else _argument_problem(command, rest)
    if problem is not None:
        return _usage_error(io, problem)
    try:
        return _run(_Trust(io), command, rest)
    except (OSError, RuntimeError, ValueError) as exc:
        io.err.write(f"akmon trust: {exc}\n")
        return 2
