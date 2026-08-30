"""The capability-matrix vocabulary checker (C57, design §7).

A capability claim records **six independently required axes** — `documented`, `delivered`,
the complete `vendor / version / event / matcher` route coordinate, the observed normal-path
`effect`, the `crash-posture`, and the `evidence` behind the claim. A glyph cannot carry six
answers, which is why the legacy README grid is replaced rather than parsed: `✅` compresses
"documented", "delivered" and "measured" into one mark, and a reader cannot tell which of the
three it is asserting.

Two rules bind the axes to each other:

* an `ask` or `deny` effect requires every route coordinate to be **measured** — an enforcement
  claim over an unmeasured route is the exact thing this file exists to stop. The same claim
  over an unmeasured *crash posture* is a **warn**: those numbers come from C52's measurement
  campaign behind the D2-23 gate, and holding C57 behind an unrelated campaign is what §7
  forbids. It still fails `--strict`, so the debt stays visible;
* a **measured** row must cite evidence, and a row that measures nothing must cite none.
  Requiring a citation only in free prose is rejected: a pattern cannot tell evidence from
  decoration.

**Scope.** Only rows inside the marked region of top-level ``CAPABILITIES.md`` are matrix rows.
There is no fallback — not to a legacy README table, not to a matrix under ``meta/``. Outside
that region, an `enforced`/`enforces`/`✅`/`⚠️` claim standing next to a vendor or harness event
is a second authority and is rejected wherever it appears in the shipped documentation.
"""

from __future__ import annotations

import re
from pathlib import Path

from findings import Finding

MATRIX_FILE = "CAPABILITIES.md"
REGION_BEGIN = "<!-- akmon:capability-matrix:begin -->"
REGION_END = "<!-- akmon:capability-matrix:end -->"

#: The six axes, in the order the lock declares them.
AXES = ("documented", "delivered", "route", "effect", "crash-posture", "evidence")
#: The complete route coordinate. An `ask`/`deny` claim needs all four measured.
ROUTE_COORDINATES = ("vendor", "version", "event", "matcher")
#: Closed vocabularies. The lock pins these two and leaves the other axes' spelling to C57.
EFFECTS = ("none", "advisory", "ask", "deny")
CRASH_POSTURES = ("fail-open", "fail-closed", "unmeasured")
#: The explicit "no measurement stands behind this coordinate" value.
UNMEASURED = "unmeasured"

# --- the bare-claim scan -------------------------------------------------------------------
#
# Shipped documentation only. `meta/` is maintainer material, and `guardrails/` runtime prose is
# C53's F7/F8 surface — scanning it here would make two owners for one rule.
_SHIPPED_DOC_GLOBS = ("*.md", "roles/*.md", "pipelines/*.md", "profiles/*.md",
                      "skills/**/*.md", "tools/**/*.md", "examples/*.md")

_FORBIDDEN_CLAIM_RE = re.compile(r"\benforced\b|\benforces\b|✅|⚠️")
# Vendors are matched as **proper nouns**, case-sensitively: a lowercase `claude` inside
# `.claude/skills/` is a filesystem location, not a claim about a vendor's behaviour.
_VENDOR_RE = re.compile(r"\bClaude(?: Code)?\b|\bCodex(?: CLI)?\b|\bGemini\b|\bCopilot\b"
                        r"|\bAnthropic\b|\bOpenAI\b")
_HARNESS_EVENT_RE = re.compile(
    r"\bSessionStart\b|\bSubagentStart\b|\bSubagentStop\b|\bPreToolUse\b|\bPostToolUse\b"
    r"|\bUserPromptSubmit\b|\bPreCompact\b|\bNotification\b|\bStop\b"
)
# The one allowance the lock names: a threshold attributed to akmon's own in-process checker
# stays valid prose. Attribution must be adjacent to the claim, not merely somewhere in the
# block, or any page that mentions `sync.py` would buy itself an exemption.
_OWN_CHECKER_RE = re.compile(
    r"(?:enforced|enforces)[^.\n]{0,40}?`?(?:verify|sync|self_ci|validate)\.py`?"
)


def _blocks(text: str) -> list[tuple[int, str]]:
    """Contiguous non-blank runs, with the 1-based line number each one starts at.

    Adjacency is per block rather than per line because the claim and the mechanism it leans on
    are routinely one line apart — a blockquote that says "enforced" and names `PreToolUse`
    three lines later is one claim, and a line-scoped rule would not see it.
    """
    blocks: list[tuple[int, str]] = []
    current: list[str] = []
    start = 1
    for number, line in enumerate(text.splitlines(), start=1):
        if line.strip():
            if not current:
                start = number
            current.append(line)
            continue
        if current:
            blocks.append((start, "\n".join(current)))
            current = []
    if current:
        blocks.append((start, "\n".join(current)))
    return blocks


def _region_span(text: str) -> tuple[int, int] | None:
    """The one marked region, or ``None`` if there is not exactly one well-formed pair.

    Two ``begin`` markers make the boundary ambiguous, and a reader cannot tell which span is
    the matrix — so a second pair is not a second matrix, it is the absence of a single one.
    """
    if text.count(REGION_BEGIN) != 1 or text.count(REGION_END) != 1:
        return None
    begin = text.find(REGION_BEGIN)
    end = text.find(REGION_END)
    if end < begin:
        return None
    return begin, end + len(REGION_END)


def _shipped_docs(root: Path) -> list[Path]:
    paths: set[Path] = set()
    for pattern in _SHIPPED_DOC_GLOBS:
        paths.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(paths)


def check_bare_claims(root: Path) -> list[Finding]:
    """One finding per shipped-doc block that claims enforcement beside a vendor or event."""
    findings: list[Finding] = []
    for path in _shipped_docs(root):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(root).as_posix()
        if path.name == MATRIX_FILE:
            span = _region_span(text)
            if span is not None:
                # The marked region is where these claims belong; only the rest is scanned.
                text = text[: span[0]] + "\n" * text[span[0]: span[1]].count("\n") + text[span[1]:]
        for line, block in _blocks(text):
            claim = _FORBIDDEN_CLAIM_RE.search(block)
            if not claim:
                continue
            if not (_VENDOR_RE.search(block) or _HARNESS_EVENT_RE.search(block)):
                continue
            if _OWN_CHECKER_RE.search(block):
                continue
            findings.append(
                Finding(
                    "error",
                    "matrix.bare-claim",
                    f"claims {claim.group()!r} beside a vendor or harness event outside the "
                    f"marked matrix region",
                    f"{relative}:{line}",
                    f"Move this claim into the {MATRIX_FILE} matrix, or qualify it there and "
                    f"drop the bare claim here.",
                )
            )
    return findings


def _parse_rows(region: str, *, line_offset: int) -> tuple[list[dict], list[tuple[int, str]]]:
    """Claim blocks inside the marked region: a ``###`` heading plus its ``- key: value`` axes.

    One row is one *claim* — one capability on one vendor — because `vendor` is a route
    coordinate: a capability that behaves differently on two harnesses is two claims, not one
    cell with two readings.

    Returns the claims and the lines that fit no claim form, so the caller can reject them.
    """
    rows: list[dict] = []
    stray: list[tuple[int, str]] = []
    current: dict | None = None
    for number, line in enumerate(region.splitlines(), start=line_offset):
        stripped = line.strip()
        if not stripped or stripped in (REGION_BEGIN, REGION_END):
            continue
        if stripped.startswith("### "):
            current = {"title": stripped[4:].strip(), "line": number, "axes": {}}
            rows.append(current)
            continue
        if current is not None and stripped.startswith("- ") and ":" in stripped[2:]:
            key, value = stripped[2:].split(":", 1)
            axis = key.strip().lower()
            if axis not in AXES:
                # "Exactly six axes" is a closed list in both directions: an unknown key is a
                # seventh answer nothing reads, and a typo that would otherwise be invisible.
                stray.append((number, stripped))
                continue
            if axis in current["axes"]:
                # A repeated axis silently overwrote the earlier value, so a claim could carry
                # two contradictory readings and report whichever came last.
                stray.append((number, stripped))
                continue
            current["axes"][axis] = value.strip()
            continue
        # Anything else — prose, a smuggled glyph table, an axis line with no claim above it —
        # is silently invisible to every rule below unless it is reported here.
        stray.append((number, stripped))
    return rows, stray


def _parse_route(value: str) -> dict:
    coordinates: dict = {}
    for part in value.split(";"):
        if "=" not in part:
            continue
        key, coordinate = part.split("=", 1)
        coordinates[key.strip().lower()] = coordinate.strip()
    return coordinates


def _is_measured(axes: dict, route: dict) -> bool:
    """Whether the row asserts anything a probe or report had to establish.

    A settled `delivered` answer counts: "the wiring reaches the harness" — or measurably does
    not — is the claim readers act on, and letting it stand uncited is how a vendor grid drifts
    back into decoration. Only a row that settles nothing at all (`delivered` unmeasured, no
    crash posture, no boundary effect) is expected to cite nothing.
    """
    if axes.get("delivered") in ("yes", "no"):
        return True
    if axes.get("crash-posture") in ("fail-open", "fail-closed"):
        return True
    return axes.get("effect") in ("advisory", "ask", "deny")


def check_matrix(root: Path) -> list[Finding]:
    """The six-axis contract over the marked region of top-level ``CAPABILITIES.md``."""
    path = root / MATRIX_FILE
    target = MATRIX_FILE
    if not path.is_file():
        return [
            Finding(
                "error", "matrix.missing-file",
                f"top-level {MATRIX_FILE} is missing", target,
                f"Create {MATRIX_FILE} with one marked capability-matrix region.",
            )
        ]
    text = path.read_text(encoding="utf-8")
    span = _region_span(text)
    if span is None:
        return [
            Finding(
                "error", "matrix.missing-file",
                f"{MATRIX_FILE} carries no marked capability-matrix region", target,
                f"Wrap the matrix in {REGION_BEGIN} and {REGION_END}.",
            )
        ]
    begin, end = span
    line_offset = text.count("\n", 0, begin) + 1
    rows, stray = _parse_rows(text[begin:end], line_offset=line_offset)
    if not rows:
        return [
            Finding(
                "error", "matrix.missing-file",
                f"the marked region in {MATRIX_FILE} carries no capability claim", target,
                "Add the capability claims back to the region, or drop the region entirely "
                "rather than leaving an empty one that reads as a checked matrix.",
            )
        ]
    findings: list[Finding] = []
    for number, line in stray:
        findings.append(
            Finding(
                "error", "matrix.invalid-value",
                f"line is outside the claim grammar: {line[:60]!r}", f"{target}:{number}",
                "Inside the marked region write only '### <claim>' headings and their "
                "'- <axis>: <value>' lines.",
            )
        )
    for row in rows:
        findings.extend(_check_row(row, target))
    return findings


def _check_row(row: dict, target: str) -> list[Finding]:
    findings: list[Finding] = []
    axes = row["axes"]
    where = f"{target}:{row['line']}"
    title = row["title"]

    for axis in AXES:
        if axis not in axes:
            findings.append(
                Finding(
                    "error", "matrix.missing-axis",
                    f"{title}: axis {axis!r} is absent", where,
                    f"Add a '- {axis}:' line to this claim.",
                )
            )
    route = _parse_route(axes.get("route", ""))
    if "route" in axes:
        for coordinate in ROUTE_COORDINATES:
            if coordinate not in route:
                findings.append(
                    Finding(
                        "error", "matrix.missing-axis",
                        f"{title}: route coordinate {coordinate!r} is absent", where,
                        f"Add {coordinate}=<value> to this claim's route.",
                    )
                )
    effect = axes.get("effect")
    if effect is not None and effect not in EFFECTS:
        findings.append(
            Finding(
                "error", "matrix.invalid-value",
                f"{title}: effect {effect!r} is outside {' | '.join(EFFECTS)}", where,
                f"Set effect to one of {' | '.join(EFFECTS)}.",
            )
        )
    posture = axes.get("crash-posture")
    if posture is not None and posture not in CRASH_POSTURES:
        findings.append(
            Finding(
                "error", "matrix.invalid-value",
                f"{title}: crash-posture {posture!r} is outside {' | '.join(CRASH_POSTURES)}",
                where, f"Set crash-posture to one of {' | '.join(CRASH_POSTURES)}.",
            )
        )
    # A rule that reads an absent axis would report the same defect twice: the missing axis is
    # already named, and a derived complaint about it tells the reader nothing new. Every
    # relation below therefore runs only over a row that has the axes it needs.
    complete = all(axis in axes for axis in AXES)
    if complete and effect in ("ask", "deny"):
        for name in ROUTE_COORDINATES:
            if route.get(name) == UNMEASURED:
                findings.append(
                    Finding(
                        "error", "matrix.unqualified-effect",
                        f"{title}: effect {effect!r} claimed while {name!r} is {UNMEASURED}",
                        where,
                        f"Measure {name} before claiming {effect}, or lower the effect.",
                    )
                )
        if posture == UNMEASURED:
            # Warn, not error, and only for this coordinate. This is a **permanent** weakening
            # of the rule for every claim, not a suspension until C52 measures the two that
            # exist today: after C52 lands, a future ask/deny claim with no crash measurement
            # still passes a non-strict run. The trade the owner accepted (D2-29) is that §7
            # forbids holding C57 behind C52's measurement campaign, and `--strict` keeps the
            # debt failing somewhere rather than nowhere.
            findings.append(
                Finding(
                    "warn", "matrix.unqualified-effect",
                    f"{title}: effect {effect!r} claimed while 'crash-posture' is {UNMEASURED}",
                    where,
                    f"Record the measured crash posture from C52 before relying on {effect}.",
                )
            )
    if complete:
        evidence = axes["evidence"]
        measured = _is_measured(axes, route)
        if measured and not evidence:
            findings.append(
                Finding(
                    "error", "matrix.uncited-claim",
                    f"{title}: measured claim carries no evidence", where,
                    "Cite the probe or report behind this measurement.",
                )
            )
        elif not measured and evidence:
            findings.append(
                Finding(
                    "error", "matrix.uncited-claim",
                    f"{title}: nothing is measured, yet evidence is cited", where,
                    "Drop the citation, or record the measurement it belongs to.",
                )
            )
    return findings


def check_capabilities(root: Path) -> list[Finding]:
    """Both halves of §7's matrix contract, in the order a reader meets them."""
    return [*check_matrix(root), *check_bare_claims(root)]
