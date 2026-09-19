"""Check the accepted ADR block identifiers and legacy D2 aliases.

The cutover keeps no D2 lifecycle. Old identifiers are navigation aliases only: each must
resolve exactly once from the current semantic owners (accepted ADRs or the live task index),
without consulting the frozen ledger or historical reports.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from common.findings import Finding

_DECISION_LINE = re.compile(r"^\s*`Decision-ID: (ADR-(\d{4})/D\d{2})`\s*$")
_LEGACY_LINE = re.compile(r"`Legacy-ID: ((?:D2-\d+)(?:,\s*D2-\d+)*)`")
_LEGACY_ID = re.compile(r"\bD2-(\d+)\b")
_EXPECTED_LEGACY = frozenset(range(1, 52))


def _owners(root: Path) -> list[Path]:
    decisions = sorted((root / "meta" / "decisions").glob("[0-9][0-9][0-9][0-9]-*.md"))
    tasks = root / "meta" / "TASKS.md"
    return [*decisions, *([tasks] if tasks.is_file() else [])]


def _location(root: Path, path: Path, line: int) -> str:
    return f"{path.relative_to(root).as_posix()}:{line}"


def _collect_records(root: Path) -> tuple[dict[str, list[str]], dict[int, list[str]], list[Finding]]:
    """Collect canonical identifiers and immediate file-ownership errors."""
    findings: list[Finding] = []
    decision_locations: dict[str, list[str]] = defaultdict(list)
    legacy_locations: dict[int, list[str]] = defaultdict(list)
    for path in _owners(root):
        file_number = path.name[:4] if path.parent.name == "decisions" else None
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if decision := _DECISION_LINE.match(line):
                identifier, declared_number = decision.groups()
                location = _location(root, path, line_number)
                decision_locations[identifier].append(location)
                if file_number is not None and declared_number != file_number:
                    findings.append(
                        Finding(
                            "error",
                            "decision.id-owner",
                            f"{identifier} is declared in ADR {file_number}, not ADR {declared_number}",
                            location,
                            "Move the block to its owning ADR or correct the Decision-ID prefix.",
                        )
                    )
            if legacy := _LEGACY_LINE.search(line):
                location = _location(root, path, line_number)
                ids = [int(match.group(1)) for match in _LEGACY_ID.finditer(legacy.group(1))]
                for legacy_id in ids:
                    legacy_locations[legacy_id].append(location)
    return decision_locations, legacy_locations, findings


def _duplicate_decision_findings(decision_locations: dict[str, list[str]]) -> list[Finding]:
    """Reject a block identifier with more than one current owner."""
    findings: list[Finding] = []

    for identifier, locations in sorted(decision_locations.items()):
        if len(locations) > 1:
            findings.append(
                Finding(
                    "error",
                    "decision.duplicate-id",
                    f"{identifier} is declared {len(locations)} times",
                    ", ".join(locations),
                    "Keep one canonical decision block for this Decision-ID.",
                )
            )
    return findings


def _legacy_findings(legacy_locations: dict[int, list[str]]) -> list[Finding]:
    """Require exactly one current owner for each frozen legacy identifier."""
    findings: list[Finding] = []

    for legacy_id in sorted(_EXPECTED_LEGACY):
        locations = legacy_locations.get(legacy_id, [])
        if not locations:
            findings.append(
                Finding(
                    "error",
                    "decision.legacy-missing",
                    f"D2-{legacy_id} has no canonical alias in current ADRs or meta/TASKS.md",
                    "meta/decisions, meta/TASKS.md",
                    f"Add exactly one `Legacy-ID: D2-{legacy_id}` at its current semantic owner.",
                )
            )
        elif len(locations) > 1:
            findings.append(
                Finding(
                    "error",
                    "decision.legacy-duplicate",
                    f"D2-{legacy_id} has {len(locations)} canonical aliases",
                    ", ".join(locations),
                    "Keep the alias only at the single current semantic owner.",
                )
            )

    for legacy_id, locations in sorted(legacy_locations.items()):
        if legacy_id not in _EXPECTED_LEGACY:
            findings.append(
                Finding(
                    "error",
                    "decision.legacy-unexpected",
                    f"D2-{legacy_id} is outside the frozen D2-1..D2-51 namespace",
                    ", ".join(locations),
                    "Use a Decision-ID for new decisions; do not extend the legacy namespace.",
                )
            )
    return findings


def check_decision_records(root: Path) -> list[Finding]:
    """Return findings for duplicate decision blocks or unresolved legacy aliases."""
    decision_locations, legacy_locations, findings = _collect_records(root)
    findings.extend(_duplicate_decision_findings(decision_locations))
    findings.extend(_legacy_findings(legacy_locations))

    if not findings:
        findings.append(
            Finding(
                "ok",
                "decision.records",
                "decision block IDs are unique and every D2-1..D2-51 alias resolves once from a current owner",
                "meta/decisions, meta/TASKS.md",
                "Keep decision blocks unique and legacy aliases canonical without recreating D2 status.",
            )
        )
    return findings
