# 0010 — Alternatives adoption: the A11 verdict set

- **Status:** Accepted (all 7 themes of the alternatives plan; detailed per-theme rationale
  lives in the walkthrough record, which stays the detail owner; each downstream lock —
  A12/A13/A14/A16 — gets its own ADR when it locks). Owner-verify point: D2-14.
- **Owner:** akuminov@gmail.com
- **References:** plan [`meta/reviews/alternatives/plan-akmon-from-alternatives-20260718.md`](../reviews/alternatives/plan-akmon-from-alternatives-20260718.md)
  (weakness→source why-record, §5 decisions, §6.0 priority view) · rationale
  [`walkthrough-a11-20260717.md`](../reviews/alternatives/walkthrough-a11-20260717.md)
  (per-theme essence / as-is / solution / alternatives / recommendation + owner verdicts) ·
  archived backlog entry [A11](../TASKS_ARCHIVE.md) and the carriers named below (live in
  [`meta/TASKS.md`](../TASKS.md)) · ledger row D2-14 · descriptive pattern
  [`roles/architect.md`](../../roles/architect.md) § Describe a change essence-first.

## Context

Four independent reviews of alternative agent-standard ecosystems (ponytail, Superpowers /
OpenSpec / wshobson, in two review waves) converged on a set of akmon weaknesses (W1–W24)
and candidate adoptions. The plan organized them into phases (P0–P4) with four open owner
decisions (D1–D4). A11 walked all 7 themes of the plan's §6.0 priority view with the owner,
one theme per session step, each presented in the fixed descriptive order (essence → as-is
pros/cons → solution solves/drawbacks → alternatives → explicit recommendation with
grounds) and grounded in the repo's actual code and backlog, not in the reviews' summaries.
Every theme received an owner verdict; this ADR folds the verdict set into one decision.

## Decision

All 7 themes are **accepted**, with the amendments below; the four open decisions are
closed. The walkthrough record owns the full rationale per theme; the plan file remains the
weakness→source why-record.

1. **Behavioral evaluation** (P3.1→P3.2+P3.3 / W1 W3 W13) — accepted as planned: layered
   evaluation with a control arm (deterministic static always-on → LLM judge on risk →
   statistics for promotions only), baseline-must-fail for guardrail authoring, evidence
   classes in PROMOTE. Carriers: A14 → C42.
2. **Vendor delivery proof** (P0.1/P0.2→P3.4 / W2 W4 W9 W10) — accepted: probe-first on
   live paths, Claude → Codex order, matrix re-run deferred to P3.4; probes are akmon
   dev-side (`meta/`), re-run on every release touching `hooks/`/`bin/sync.py`. Carrier: N2.
3. **Delegation contracts** (P2.4/P2.5/P2.6/P2.8 / W17 W18 W19 W24) — accepted as one
   architect pass inside A13, with two scope amendments: a **smallness boundary** for the
   dispatch packet, and P2.6 cost heuristics marked **provisional** until C42 data.
4. **Change-state lifecycle** (P2.7 / W21) — accepted as its own architect pass inside A13,
   with two scope constraints: the change manifest is **links-only** (never duplicates the
   canonical owners), and A13 names a **triviality boundary** (what must carry a manifest).
   OpenSpec's semantics (delta → archive-merge → dependency invalidation) without its
   folders — the parallel tree stays a §4 non-goal.
5. **Review/handoff discipline** (P2.1/P2.2 / W11 W12) — accepted with the **seam
   amendment**: the A13 lock states explicitly that the dispatch packet's scope field
   (P2.4) never constrains what a reviewer may flag — the reviewer-independence clauses
   outrank the packet.
6. **Deterministic hardening** (P0.3/P0.4/P1.1–P1.7/P2.3 / W5–W8 W20 W22 W23) — accepted:
   the P0.3/P0.4 inventory rides N2 (decisions in A12 — see Amendments); one A12 pass locks
   the seven P1.x shapes; C40 lands them
   with the uniform acceptance **every check fails on a seeded violation**; caps numbers
   are picked as akmon's own and marked provisional; P2.3 (`akmon-defer:` — ceiling *and*
   trigger mandatory) rides A13.
7. **Owner attention & new carriers** (P1.4/Phase 4 / W14–W16) — accepted: `akmon status`
   observability-only (must read *actual* state, not declared); Phase 4 stays gated on
   Phase 3 measurement, each P4.x entering through its own ADR when its gate opens.

**Decisions closed:**

- **D1 (mutable enforcement levels) — resolved: mutability rejected**, P4.4 closed with the
  [pny/codex] 4.1 rationale (mutable intensity makes the active contract ambiguous — a
  structural objection no measurement changes). The "soften a hook" need is served by the
  declared path: C42 data → fix or unwire via sync, visible in `akmon status`. Revisit-if:
  real consumer demand for per-project softening that unwiring cannot express.
- **D2 (SubagentStart timing) — resolved: probe-first confirmed**; P0.1 gates P4.1.
- **D3 (fresh vs forked subagent context) — parked**: resolved by measurement inside C42's
  harness; P2.4 stays silent on isolation until then.
- **D4 (built-in subagent types vs `k-*`) — resolved: decided per vendor by the N2/P0.1
  comparison-arm data; `k-*` stays the contract until the data lands.**

Every accepted theme carries a pilot acceptance criterion (recorded per theme in the
walkthrough record) — acceptance is falsifiable, not declared.

**Amendments (backlog review, accepted by the owner):**

- **Role seam in stage 0:** N2 (review) keeps probes and the *as-is* inventory (invariants,
  the de-facto source/generated boundary, always-loaded volumes); the *decisions* — support-
  matrix dimensions, OS contract, boundary declaration, numeric caps — lock in A12
  (architect). Review measures the existing; architect constructs contracts.
- **Matrix-as-data gets a design lock:** P3.4's capability-matrix-as-code (schema, ownership,
  README generation, `sync.py` consumption) is a new source-of-truth architecture — carried
  as its own A-task (A16) + C-task (C44), not as a rider on C42/N1; N1 keeps the live
  evidence rerun.
- **A15 gate made satisfiable:** the gate is C42 + N2 + the **N1 Claude/Codex** rerun; the
  Gemini/Copilot cells split into a demand-driven N3 and gate nothing.
- **Split at lock time:** A13's contracts and A15's ADRs may lock one at a time, each
  spawning its own C-id — umbrella tasks do not serialize independently lockable work.

## Consequences

- The execution order is fixed: N2 (probes + inventory) unblocks A12/A15/A16 inputs; A12→C40
  (deterministic hardening), A13→C41 (pipeline & delegation contracts, two passes: the
  delegation-contracts pass and the lifecycle pass), A14→C42 (behavioral evaluation),
  A16→C44 (matrix as data) each produce their own ADR at lock time — this ADR records
  direction-acceptance, not the detailed contracts.
- akmon commits to measurement-before-mechanism as its adoption spine: no new delivery
  surface (SubagentStart injection, plugin carrier, MCP transport) before the gating
  measurement exists; an honest matrix re-run may reduce the ✅ count — accepted as honesty
  over optics.
- The descriptive pattern used for the walkthrough (essence-first, five steps) is itself
  codified in `roles/architect.md` and `roles/review.md` (truncated at the analysis seam)
  and applies to all future owner-facing change descriptions.
- Rejected mechanisms are recorded with revisit conditions in the walkthrough record's
  per-theme Alternatives sections (e.g. the OpenSpec parallel tree, LOC-based simplicity
  metrics, mutable enforcement levels) — a later pass may revive them only through their
  named revisit-if.
