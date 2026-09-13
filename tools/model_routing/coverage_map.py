#!/usr/bin/env python3
"""Assemble the coverage map from the delegation log (design §9.4 + §10.3, C17).

Which zone/module each fan-out worker was *dispatched to*, derived **from the delegation log
by code, not by the orchestrator** — the map costs one tool run, not tokens per gate. §9.4
says "actually checked"; the log cannot support that. It records the observed dispatch
request and makes no launch or completion claim (F21/A), so a delegation the harness
refused or aborted still reads as coverage. Read a covered zone as "someone was sent
there", and the uncovered list — the output the gate leans on — as the sound half. Each
fan-out delegation carries a ``[zone:LABEL]`` marker in its description (parsed at log-write
time by ``routing.delegation_log_line`` into a zone column); this tool groups the in-scope
entries by zone and, given the Decompose/Survey zone plan (§10.3), flags the *uncovered
seams* — planned zones no worker touched.

Scope: the log is one append-only file across sessions, so an assembly run names its scope —
``--session`` (the self-describing key) or an explicit ``--all-sessions`` — optionally narrowed
by ``--since``/``--until``. There is no unscoped default: the union of every session lets one
round's worker cover a zone another round never touched, and the uncovered list is exactly the
output the gate cannot afford to under-report. The printed summary names the session set either
way. Time bounds compare instants, not strings: a bare date covers its whole day, a bound with no
offset is read in local time (the zone the log writer stamps in), and a row whose timestamp is not
ISO fails a time-scoped run rather than being silently kept or dropped.
``session_id`` is the finest key that exists today, so two fan-out rounds inside one
session assemble as one map — narrow them with ``--since``/``--until``. This docstring
previously said a ``gate_id`` refinement "rides on the C20 session-state marker": there is
no such marker. C20 reads the active role from the transcript instead (D2-4), and the
design row that promised the marker (§10.4 decision 1) was never reconciled with it. A
finer key, whenever one is built, changes only the key — not the scope-by-key shape here.

Output feeds ``gate_pack.py --coverage-map <path>`` (closing its C17 stub).
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

# The tree root, so the shared ``common`` package resolves: it holds the single owner of
# project-root discovery (C73) and is reachable at the same tree-relative depth from the
# mounted tree and from the materialized ``<AITNA_ROOT>/.akmon/`` copy alike.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import routing  # noqa: E402

from common.project_root import aitna_root, resolve_project_root  # noqa: E402

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


def build_coverage_map(entries: Iterable[routing.DelegationEntry], zone_plan: list[str] | None = None) -> str:
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


def _aware(value: datetime) -> datetime:
    """``value`` as an instant: an offset-less value is read in local time."""
    return value if value.tzinfo is not None else value.astimezone()


def _parse_bound(text: str, *, end_of_day: bool) -> datetime:
    """A ``--since``/``--until`` bound as an instant; ``ValueError`` when it is not ISO.

    A bare date is the whole day — its first instant as a lower bound, its last as an upper one.
    Compared as strings instead, ``--until 2026-09-02`` sorted before every offset-bearing stamp
    of that day and dropped all of them.
    """
    text = text.strip()
    try:
        day = date.fromisoformat(text)
    except ValueError:
        return _aware(datetime.fromisoformat(text))
    return _aware(datetime.combine(day, datetime.max.time() if end_of_day else datetime.min.time()))


def _in_scope(
    entry: routing.DelegationEntry, session: str | None, since: datetime | None, until: datetime | None
) -> bool:
    """Whether ``entry`` is in the run's scope; ``session`` None is the explicit all-sessions run.

    Raises ``ValueError`` when a time bound is set and the row's timestamp is not ISO: such a row
    cannot be placed in time, and keeping or dropping it would both be a guess.
    """
    if session is not None and entry.session_id != session:
        return False
    if since is None and until is None:
        return True
    moment = _aware(datetime.fromisoformat(entry.timestamp.strip()))
    return (since is None or moment >= since) and (until is None or moment <= until)


def _describe_scope(session: str | None, entries: list[routing.DelegationEntry]) -> str:
    """The session set a run covered — named for the all-sessions run too, since it is a choice."""
    if session is not None:
        return f"session {session}"
    seen = sorted({entry.session_id or "-" for entry in entries})
    return f"all sessions ({len(seen)}: {', '.join(seen)})" if seen else "all sessions (none in scope)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, help="Project root. Defaults to cwd or a parent with AGENTS.md.")
    parser.add_argument("--log", type=Path, help="Delegation log. Defaults to <root>/.claude/model-routing.log.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--session", help="Scope to this session_id (the self-describing round key).")
    scope.add_argument(
        "--all-sessions",
        action="store_true",
        help="Union every session in the log — explicit, because it can hide a zone one round left uncovered.",
    )
    parser.add_argument(
        "--since", help="Include entries at or after this ISO date/date-time (a bare date: from its start)."
    )
    parser.add_argument(
        "--until", help="Include entries at or before this ISO date/date-time (a bare date: through its end)."
    )
    parser.add_argument("--zone-plan", type=Path, help="Zone-plan file (§10.3) — enables uncovered-seam detection.")
    parser.add_argument(
        "--out", type=Path, help="Output path. Defaults under <AITNA_ROOT>/artifacts/gates/ (gitignored)."
    )
    parser.add_argument("--stdout", action="store_true", help="Also print the coverage map to stdout.")
    args = parser.parse_args(argv)

    bounds: dict[str, datetime | None] = {}
    for flag, text, end_of_day in (("--since", args.since, False), ("--until", args.until, True)):
        try:
            bounds[flag] = _parse_bound(text, end_of_day=end_of_day) if text is not None else None
        except ValueError:
            parser.error(f"{flag} {text!r} is not an ISO date or date-time")

    root, root_notice = resolve_project_root(args.project_root)
    if root_notice:
        print(root_notice, file=sys.stderr)
    log_path = args.log or (root / routing.DELEGATION_LOG_REL)
    if not log_path.is_file():
        parser.error(f"delegation log not found: {log_path}")

    try:
        entries = [
            entry
            for entry in routing.parse_delegation_entries(log_path.read_text(encoding="utf-8").splitlines())
            if _in_scope(entry, args.session, bounds["--since"], bounds["--until"])
        ]
    except ValueError as exc:
        parser.error(f"a delegation-log row cannot be placed inside --since/--until ({exc}); no map written")
    zone_plan = parse_zone_plan(args.zone_plan.read_text(encoding="utf-8")) if args.zone_plan else None
    coverage = build_coverage_map(entries, zone_plan)

    # The default lands under the *configured* dev layer, like every other generated artifact:
    # the literal this replaced wrote the map into `_aitna/` even when the project's dev layer is
    # somewhere else, i.e. into a directory the project does not read (same defect as gate_pack's).
    default_name = f"coverage-{time.strftime('%Y%m%d-%H%M%S')}.md"
    out = args.out or (aitna_root(root) / "artifacts" / "gates" / default_name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(coverage + "\n", encoding="utf-8")
    try:
        rel = out.relative_to(root)
    except ValueError:
        rel = out

    print(f"coverage-map entries={len(entries)} zones={len({e.zone or _UNLABELLED for e in entries})}")
    print(f"scope: {_describe_scope(args.session, entries)}")
    print(f"map: {rel}")
    if args.stdout:
        print("")
        print(coverage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
