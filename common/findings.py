#!/usr/bin/env python3
"""The shared finding envelope every akmon check speaks (stage 1, P1.6).

One structure — ``severity · code · message · target · fix`` — used by ``bin/verify.py``,
``bin/sync.py --check``, ``meta/bin/validate.py``, ``meta/self_ci.py`` and (from C54)
``tools/release/release_check.py``, so a reader (and, from C59, a machine) meets one shape
rather than five. Stdlib-only and dependency-free
by contract: it ships in ``bin/`` and must import on the declared Python floor with no venv.

The five fields, and why each is load-bearing:

``severity``
    The closed vocabulary ``ok / warn / error``. For the three strict-capable adopters it
    decides the exit code through :func:`exit_code`: an error fails always, a warning fails
    only under ``--strict``. ``sync --check`` owns the recorded 0/1/2 exception.
``code``
    A stable dotted slug naming the *check* — ``pointers.stale``, ``caps.always-loaded``.
    One slug per rule, not per emitted finding: many findings share a code and are told
    apart by ``target``. A code is **never reused after its check is removed**, so the
    ``retired_codes`` record of ``common/findings.json`` names the slugs already spent and a
    live check that reaches for one is rejected here. Appending to that record when a check
    is deleted is process-owned;
    nothing can detect the omitted append, and this module does not pretend otherwise.
``message``
    What was observed, in the check's own words — one logical line, so the rendered stream stays one
    line per finding.
``target``
    The file or artifact the finding is about. May be empty when the finding is about the
    tree as a whole; whether it names the *right* artifact is review-owned. Like every rendered
    field, it contains no logical line separator.
``fix``
    What to do about it — required, non-empty, one sentence on one line. The mechanical
    heuristic rejects a terminator followed by whitespace and the compact uppercase form;
    residual natural-language sentence boundaries are review-owned so ordinary paths remain
    valid. A finding a reader cannot act on is a defect of the check, not of the tree, so the
    envelope refuses to carry one. That holds for ``ok`` too, where the sentence states the
    invariant to keep. Imperative mood is likewise review-owned.

Rendering is fixed at ``SEVERITY code target: message → fix`` — greppable by severity, by
code and by target, in that order. Serialization has exactly one owner,
:meth:`Finding.to_dict`; any consumer that serializes calls it rather than repeating the field
mapping, and no
adopter renders JSON publicly before ``akmon status`` (C59) introduces it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import InitVar, dataclass
from pathlib import Path
from typing import Any

from common import jsondata

#: A dotted slug: at least two lowercase ASCII segments, single hyphens only inside them.
CODE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*)+$")


def read_findings_data() -> dict[str, Any]:
    """The severity vocabulary, the retired-code record and the render skeleton (``findings.json``).

    Read once by whoever builds or prints a report and passed down; a function called
    without it reads the file itself (``common/jsondata.py``).
    """
    return jsondata.read(Path(__file__).parent / "findings.json")


def _or_read(data: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return data if data is not None else read_findings_data()


def retired_codes(data: Mapping[str, Any] | None = None) -> frozenset[str]:
    """Codes spent by checks that no longer exist.

    A slug listed here may never be issued again, so a consumer who greps their history is
    never shown two different rules under one name. Empty while no check has been removed;
    appending on deletion is process-owned (F14).
    """
    return frozenset(_or_read(data)["retired_codes"])


def severities(data: Mapping[str, Any] | None = None) -> tuple[str, ...]:
    """The closed severity vocabulary, ordered least to most severe (findings.json)."""
    return tuple(_or_read(data)["severities"])

# A sentence terminator followed by more text — the mechanical half of "one sentence".
# The uppercase lookahead catches the compact but still multi-sentence ``Do this.Then that.``
# form without rejecting dots inside ordinary paths such as ``meta/CONCEPT.md``.
_SECOND_SENTENCE_RE = re.compile(r"[.!?](?:\s+\S|(?=[A-Z]))")

# ``str.splitlines`` recognizes more separators than LF/CR. Any one of them would turn the
# canonical one-record-per-line rendering into multiple apparent findings.
_LINE_SEPARATOR_RE = re.compile(r"[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")
_LINE_SEPARATOR_ESCAPES = {
    "\n": r"\n",
    "\r": r"\r",
    "\v": r"\v",
    "\f": r"\f",
    "\x1c": r"\u001c",
    "\x1d": r"\u001d",
    "\x1e": r"\u001e",
    "\x85": r"\u0085",
    "\u2028": r"\u2028",
    "\u2029": r"\u2029",
}


def line_safe(value: str) -> str:
    """Escape logical line separators while preserving every other Unicode character."""
    return _LINE_SEPARATOR_RE.sub(lambda match: _LINE_SEPARATOR_ESCAPES[match.group()], value)


@dataclass(frozen=True)
class Finding:
    """One observation from one check. Invalid combinations never construct.

    ``data`` is the parsed ``findings.json`` the validation checks against — not a field: a
    carrier that builds many findings reads it once and passes it to each; without it the
    construction reads the file itself.
    """

    severity: str
    code: str
    message: str
    target: str
    fix: str
    data: InitVar[Mapping[str, Any] | None] = None

    def __post_init__(self, data: Mapping[str, Any] | None) -> None:
        data = _or_read(data)
        self._validate_severity(data)
        self._validate_code(data)
        self._validate_message()
        self._validate_target()
        self._validate_fix()

    def _validate_severity(self, data: Mapping[str, Any]) -> None:
        if self.severity not in severities(data):
            raise ValueError(f"severity must be one of {' | '.join(severities(data))}, got {self.severity!r}")

    def _validate_code(self, data: Mapping[str, Any]) -> None:
        if not isinstance(self.code, str) or not CODE_RE.fullmatch(self.code):
            raise ValueError(f"code must be a dotted slug like 'area.rule', got {self.code!r}")
        if self.code in retired_codes(data):
            raise ValueError(f"code {self.code!r} is retired and must not be reused by a live check")

    def _validate_message(self) -> None:
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError(f"message must be non-empty, got {self.message!r}")
        if _LINE_SEPARATOR_RE.search(self.message):
            raise ValueError(f"message must be one line, got {self.message!r}")

    def _validate_target(self) -> None:
        if not isinstance(self.target, str):
            raise ValueError(f"target must be a string (possibly empty), got {self.target!r}")
        if _LINE_SEPARATOR_RE.search(self.target):
            raise ValueError(f"target must be one line, got {self.target!r}")

    def _validate_fix(self) -> None:
        if not isinstance(self.fix, str) or not self.fix.strip():
            raise ValueError(f"fix is required and must be non-empty, got {self.fix!r}")
        if _LINE_SEPARATOR_RE.search(self.fix):
            raise ValueError(f"fix must be one line, got {self.fix!r}")
        if _SECOND_SENTENCE_RE.search(self.fix):
            raise ValueError(f"fix must be one sentence, got {self.fix!r}")

    def to_dict(self) -> dict[str, str]:
        """The sole canonical serialization: a JSON-safe mapping of exactly the five fields.

        Deterministic and non-mutating. There is no ``level`` key and no alias for one.
        """
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "target": self.target,
            "fix": self.fix,
        }


def render(finding: Finding, data: Mapping[str, Any] | None = None) -> str:
    """``SEVERITY code target: message → fix``; the ``target`` slot collapses when empty.

    The slot order and the arrow come from the data file's ``render`` skeleton; the upper-cased
    severity and the conditional target are code-side choices.
    """
    skeleton = _or_read(data)["render"]
    head = jsondata.fill(skeleton["head"], {"severity": finding.severity.upper(), "code": finding.code})
    if finding.target:
        head = jsondata.fill(skeleton["head_with_target"], {"head": head, "target": finding.target})
    return jsondata.fill(skeleton["line"], {"head": head, "message": finding.message, "fix": finding.fix})


def print_findings(findings: Iterable[Finding], *, quiet: bool = False) -> None:
    """Print each finding in canonical form; ``quiet`` drops the ``ok`` ones.

    One report, one read of ``findings.json``: the skeleton is read here and passed to every line.
    """
    data = read_findings_data()
    for finding in findings:
        if quiet and finding.severity == "ok":
            continue
        print(render(finding, data))


def exit_code(findings: Sequence[Finding], *, strict: bool = False) -> int:
    """The shared exit contract: errors fail; warnings fail only under ``--strict``."""
    severities = {finding.severity for finding in findings}
    if "error" in severities or (strict and "warn" in severities):
        return 1
    return 0
