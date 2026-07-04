#!/usr/bin/env python3
"""Build the gate-pack markdown consumed by both gate executors.

One structured input package per gate (design §9.4), replacing free-form
``--prompt-file`` text: the auditor subagent (the orchestrator pastes the pack text
into an ``Agent`` call) and the second-opinion CLI (step 4) both read the same document.
Provider-neutral markdown, deterministic given its inputs (§11: "runnable as one
deterministic script").

Two pack kinds:
- ``full`` — post-fan-out audit pack: artifacts + yardstick + coverage map (+ optional
  decisions register / dependency-graph excerpt), ending in the k-auditor output
  contract (§9.3 item 4).
- ``plan-check`` — the pre-fan-out anchor (§9.3 item 5): yardstick + zone plan only, no
  artifacts, checking the plan against the goal rather than against its own coverage map.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

# Role -> the question the pack asks its executor (design §9.4: "roles and tiers stay
# orthogonal" — the role determines the pack's contract and question, the tier only the
# model).
ROLE_QUESTION: dict[str, str] = {
    "review": (
        "What contradicts across these findings? Which zone or seam is uncovered by the "
        "fan-out?"
    ),
    "architect": (
        "Do the locked decisions cohere? Do the options assume mutually compatible things?"
    ),
}

_PLAN_CHECK_QUESTION = "Does the plan cover the stated goal? Which zones or seams are obviously missing?"


def _require_known_role(role: str) -> None:
    if role not in ROLE_QUESTION:
        known = ", ".join(sorted(ROLE_QUESTION))
        raise ValueError(f"unknown role {role!r}; known roles: {known}")


def build_full_pack(
    gate: str,
    role: str,
    yardstick: str,
    artifacts: list[tuple[str, str]],
    *,
    decisions: str | None = None,
    coverage_map: str | None = None,
    dep_graph: str | None = None,
) -> str:
    """Assemble the post-fan-out audit pack (design §9.4).

    ``artifacts`` is a list of ``(name, text)`` pairs — findings-with-evidence (review) or
    options-with-trade-offs (architect). ``decisions`` (architect's decisions register),
    ``coverage_map`` (assembled from the delegation log by code — this builder only embeds
    it; C17), and ``dep_graph`` (opt-in per gate, §9.7 #3) are each optional sections.
    """
    _require_known_role(role)
    lines = [
        f"# Gate-pack — {gate}",
        "",
        f"role: {role}",
        "kind: full",
        f"Question: {ROLE_QUESTION[role]}",
        "",
        "## Yardstick (acceptance condition)",
        "",
        yardstick,
        "",
        "## Artifacts",
        "",
    ]
    if artifacts:
        for name, text in artifacts:
            lines.append(f"### {name}")
            lines.append("")
            lines.append(text)
            lines.append("")
    else:
        lines.append("_No artifacts supplied._")
        lines.append("")

    if decisions is not None:
        lines.append("## Decisions register")
        lines.append("")
        lines.append(decisions)
        lines.append("")

    lines.append("## Coverage map")
    lines.append("")
    coverage_sentinel = "_Coverage map not provided (assemble via coverage_map.py)._"
    lines.append(coverage_map if coverage_map is not None else coverage_sentinel)
    lines.append("")

    if dep_graph is not None:
        lines.append("## Dependency-graph excerpt")
        lines.append("")
        lines.append(dep_graph)
        lines.append("")

    lines.append("## What to return")
    lines.append("")
    lines.append("- Contradictions between independently-correct findings/options")
    lines.append(
        "- Uncovered seams — derived from the coverage map (zones no worker checked, "
        "boundaries between zones)"
    )
    lines.append("- Re-ranking / recommendation deltas")
    lines.append(
        "- Level verdict (§9.2): does the material suggest the task exceeded the "
        "session's level hypothesis? If so, name the specific piece to redo on a higher "
        "rung."
    )
    lines.append('- An explicit "could not verify" list')
    lines.append(
        "- If this pack lacks what the audit needs (no coverage map, no yardstick), "
        "return the precise gap instead of a diluted verdict."
    )
    return "\n".join(lines).strip() + "\n"


def build_plan_check_pack(gate: str, role: str, yardstick: str, zone_plan: str) -> str:
    """Assemble the minimal pre-fan-out pack (design §9.3 item 5).

    Yardstick + zone plan only, no artifacts and no coverage map: the plan is checked
    against the stated goal, not against its own coverage map.
    """
    _require_known_role(role)
    lines = [
        f"# Gate-pack — {gate}",
        "",
        f"role: {role}",
        "kind: plan-check",
        f"Question: {_PLAN_CHECK_QUESTION}",
        "",
        "## Yardstick (goal)",
        "",
        yardstick,
        "",
        "## Zone plan",
        "",
        zone_plan,
        "",
        "## What to return",
        "",
        "- Does the plan cover the stated goal (the yardstick above)?",
        "- Which zones or seams are obviously missing from the zone plan?",
        "- Check the plan against the goal, not against its own coverage map.",
    ]
    return "\n".join(lines).strip() + "\n"


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def _find_project_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "_aitna" / "akmon").exists():
            return candidate
    return start


def _report_path(root: Path, gate: str, kind: str) -> Path:
    safe_gate = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in gate).strip("-") or "gate"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / "_aitna" / "artifacts" / "gates" / f"{safe_gate}-{kind}-{stamp}.md"


def _digest(text: str, limit: int = 1200) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[:limit].rstrip() + "\n...[truncated; see full pack]"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, help="Project root. Defaults to cwd or a parent with AGENTS.md.")
    parser.add_argument("--gate", required=True, help="Verify gate name, e.g. design-align or code-verify.")
    parser.add_argument(
        "--role",
        required=True,
        choices=sorted(ROLE_QUESTION),
        help="Gate role — determines the pack's question (tier only determines the model).",
    )
    parser.add_argument("--kind", choices=("full", "plan-check"), default="full", help="Pack kind.")
    parser.add_argument("--yardstick", type=Path, required=True, help="File with the acceptance condition / goal.")
    parser.add_argument(
        "--artifact",
        type=Path,
        action="append",
        default=[],
        help="Artifact file (repeatable; full only) — named by its filename.",
    )
    parser.add_argument("--decisions", type=Path, help="Decisions register file (architect full).")
    parser.add_argument("--coverage-map", type=Path, help="Coverage map file (full).")
    parser.add_argument("--zone-plan", type=Path, help="Zone plan file (required for --kind plan-check).")
    parser.add_argument("--dep-graph", type=Path, help="Dependency-graph excerpt file (opt-in, §9.7 #3).")
    parser.add_argument("--out", type=Path, help="Output path. Defaults under _aitna/artifacts/gates/.")
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Also print the full pack, so the orchestrator can paste it into the k-auditor Agent call.",
    )
    args = parser.parse_args(argv)

    if args.kind == "plan-check" and args.zone_plan is None:
        parser.error("--zone-plan is required for --kind plan-check")

    root = (args.project_root or _find_project_root(Path.cwd())).resolve()
    yardstick_text = args.yardstick.read_text(encoding="utf-8")

    if args.kind == "plan-check":
        zone_plan_text = args.zone_plan.read_text(encoding="utf-8")
        pack = build_plan_check_pack(args.gate, args.role, yardstick_text, zone_plan_text)
    else:
        artifacts = [(path.name, path.read_text(encoding="utf-8")) for path in args.artifact]
        decisions_text = args.decisions.read_text(encoding="utf-8") if args.decisions else None
        coverage_map_text = args.coverage_map.read_text(encoding="utf-8") if args.coverage_map else None
        dep_graph_text = args.dep_graph.read_text(encoding="utf-8") if args.dep_graph else None
        pack = build_full_pack(
            args.gate,
            args.role,
            yardstick_text,
            artifacts,
            decisions=decisions_text,
            coverage_map=coverage_map_text,
            dep_graph=dep_graph_text,
        )

    out = args.out or _report_path(root, args.gate, args.kind)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(pack, encoding="utf-8")
    try:
        rel = out.relative_to(root)
    except ValueError:
        rel = out

    print(f"gate-pack kind={args.kind} role={args.role}")
    print(f"pack: {rel}")
    print("")
    print(_digest(pack))
    if args.stdout:
        print("")
        print(pack)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
