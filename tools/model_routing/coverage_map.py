#!/usr/bin/env python3
"""Assemble the coverage map from the delegation log (design §9.4 + §10.3, C17).

Which zone/module each fan-out worker actually checked, derived **from the delegation log
by code, not by the orchestrator** — the map costs one tool run, not tokens per gate. Each
fan-out delegation carries a ``[zone:LABEL]`` marker in its description (parsed at log-write
time by ``routing.delegation_log_line`` into a zone column); this tool groups the in-scope
entries by zone and, given the Decompose/Survey zone plan (§10.3), flags the *uncovered
seams* — planned zones no worker touched.

Scope: the log is one append-only file across sessions, so an assembly run is scoped by
``--session`` (self-describing key, written now) and optionally ``--since``/``--until``.
The ``gate_id`` refinement for multiple rounds in one session rides on the C20 session-state
marker; the scope-by-key shape here does not change when it lands.

Output feeds ``gate_pack.py --coverage-map <path>`` (closing its C17 stub).
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Iterable
from pathlib import Path

import routing

_UNLABELLED = "(unlabelled)"


def parse_zone_plan(text: str) -> list[str]:
    """The named zones the fan-out was split by — one per line.

    Blank lines and ``#`` comments are dropped; a leading ``- ``/``* `` bullet is stripped.
    Order preserved, duplicates collapsed.
    """
    zones: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line[:2] in ("- ", "* "):
            line = line[2:].strip()
        if line and line not in zones:
            zones.append(line)
    return zones


def _worker(entry: routing.DelegationEntry) -> str:
    return f"{entry.subagent}/{entry.model}" if entry.model else entry.subagent


def build_coverage_map(
    entries: Iterable[routing.DelegationEntry], zone_plan: list[str] | None = None
) -> str:
    """Render the coverage map markdown embedded into a gate-pack.

    ``entries`` are already scoped to the fan-out round (the CLI does the filtering). With a
    ``zone_plan``, planned zones with no worker surface as *uncovered seams* and worked zones
    absent from the plan as *off-plan*.
    """
    entries = list(entries)
    if not entries:
        return "_No delegations in scope._"

    # Group by zone, preserving first-seen order; distinct workers per zone, total count.
    order: list[str] = []
    workers: dict[str, list[str]] = {}
    counts: dict[str, int] = {}
    for entry in entries:
        zone = entry.zone or _UNLABELLED
        if zone not in workers:
            order.append(zone)
            workers[zone] = []
            counts[zone] = 0
        counts[zone] += 1
        who = _worker(entry)
        if who not in workers[zone]:
            workers[zone].append(who)

    # No "## Coverage map" heading: the gate-pack owns that section header and embeds this
    # body under it (standalone --stdout still reads fine, leading with the table).
    lines = ["| zone | workers | count |", "|------|---------|-------|"]
    for zone in order:
        lines.append(f"| {zone} | {', '.join(workers[zone])} | {counts[zone]} |")

    if zone_plan is not None:
        labelled = {z for z in order if z != _UNLABELLED}
        uncovered = [z for z in zone_plan if z not in labelled]
        off_plan = [z for z in order if z != _UNLABELLED and z not in zone_plan]

        lines += ["", "### Uncovered zones (planned, no worker)"]
        if uncovered:
            lines += [f"- {z}" for z in uncovered]
        else:
            lines.append("_All planned zones have at least one worker._")

        if off_plan:
            lines += ["", "### Off-plan zones (worked, not in the zone plan)"]
            lines += [f"- {z}" for z in off_plan]
        if _UNLABELLED in workers:
            lines += ["", f"_{counts[_UNLABELLED]} delegation(s) carried no `[zone:…]` marker — unattributable._"]

    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def _find_project_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "_aitna" / "akmon").exists():
            return candidate
    return start


def _in_scope(entry: routing.DelegationEntry, session: str | None, since: str | None, until: str | None) -> bool:
    if session is not None and entry.session_id != session:
        return False
    if since is not None and entry.timestamp < since:
        return False
    if until is not None and entry.timestamp > until:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, help="Project root. Defaults to cwd or a parent with AGENTS.md.")
    parser.add_argument("--log", type=Path, help="Delegation log. Defaults to <root>/.claude/model-routing.log.")
    parser.add_argument("--session", help="Scope to this session_id (the self-describing round key).")
    parser.add_argument("--since", help="Include entries with timestamp >= this (ISO, same format as the log).")
    parser.add_argument("--until", help="Include entries with timestamp <= this (ISO, same format as the log).")
    parser.add_argument("--zone-plan", type=Path, help="Zone-plan file (§10.3) — enables uncovered-seam detection.")
    parser.add_argument("--out", type=Path, help="Output path. Defaults under _aitna/artifacts/gates/ (gitignored).")
    parser.add_argument("--stdout", action="store_true", help="Also print the coverage map to stdout.")
    args = parser.parse_args(argv)

    root = (args.project_root or _find_project_root(Path.cwd())).resolve()
    log_path = args.log or (root / routing.DELEGATION_LOG_REL)
    if not log_path.is_file():
        parser.error(f"delegation log not found: {log_path}")

    entries = [
        entry
        for entry in routing.parse_delegation_entries(log_path.read_text(encoding="utf-8").splitlines())
        if _in_scope(entry, args.session, args.since, args.until)
    ]
    zone_plan = parse_zone_plan(args.zone_plan.read_text(encoding="utf-8")) if args.zone_plan else None
    coverage = build_coverage_map(entries, zone_plan)

    out = args.out or (root / "_aitna" / "artifacts" / "gates" / f"coverage-{time.strftime('%Y%m%d-%H%M%S')}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(coverage + "\n", encoding="utf-8")
    try:
        rel = out.relative_to(root)
    except ValueError:
        rel = out

    print(f"coverage-map entries={len(entries)} zones={len({e.zone or _UNLABELLED for e in entries})}")
    print(f"map: {rel}")
    if args.stdout:
        print("")
        print(coverage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
