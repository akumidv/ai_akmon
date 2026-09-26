# Pipeline: design-flow

The cycle the [architect](../roles/architect.md) role follows to turn a change request
into an agreed, written design the [engineer](../roles/engineer.md) can implement.

> A pipeline is a **declarative, ordered cycle** — the steps and their gates, not a script.
> Roles reference a pipeline; agents follow it.

## When

Any **material** change: new capability, a change to architecture / data model / the
column dictionary, or anything math-shaping. A trivial, local change skips straight to
[code-flow](code-flow.md) — design-flow is for changes that need a decision on record.

For an **analysis-only** request, the pipeline stops at reporting findings and recommendations
unless the owner explicitly asks to write or update files — the always-on rule and its trigger
list live in [_common](../guardrails/_common.md) § Analysis before mutation. Backlog and
documentation conventions say **where** accepted work is recorded; they do not authorize
recording it before agreement.

## Steps (a loop, not a line — expect several passes)

1. **Frame** — state the problem, the constraints, and what "good" looks like (the
   acceptance condition). If the request is ambiguous, resolve it with the owner before
   designing.
2. **Survey** — read the relevant code and docs. Confirm the **current** design *as it
   is*, not as remembered — module names, layers, the data dictionary, the provider
   contracts drift. Check new names for **collisions** in `src/`. Cite what you read.
   - **For a convention / API-shape decision, survey beyond the repo:** check the prevailing
     **ecosystem practice** (language stdlib, widely-used libraries) and weigh it, rather than
     settling the convention from local code or taste alone. Record the practice you found and
     the rationale for following or departing from it (it becomes part of the decision record).
   - *Gate — plan check (pre-fan-out):* when the decomposition (zone plan) names **≥2 zones**,
     run a minimal `audit` pass (`k_auditor`) over a **plan-check pack**
     (the Frame yardstick + the zone plan) *before* spending the survey/design fan-out — it
     checks the plan against the **goal**, closing the circularity where the later audit's
     coverage map derives from an unchecked plan. Cheap (yardstick + plan, no artifacts).
   - *Tier:* the survey fan-out delegates to `worker` (`explore-search`); drafting the zone
     plan itself delegates to `reasoner` (`plan-draft`) — but *adopting* the plan and routing
     the fan-out stay with the orchestrator.
3. **Design** — propose the structure; decide **point by point**. For anything
   load-bearing, frame the design space before recommending: include the realistic
   options (including the status quo when viable), the evaluation criteria, trade-offs,
   best-practice principles involved, risks, and revisit-if conditions. Do not present a
   single option as inevitable. *Tier:* drafting options on a load-bearing fork delegates
   to `reasoner` (`design-fork`); the recommendation and the decision stay with the
   orchestrator and the owner.
4. **Confirm recording** *(gate)* — before mutating design docs, ADRs, requirements, or
   backlog files, get explicit owner confirmation that the findings should be recorded.
   This gate is already satisfied when the request itself is an edit command ("write",
   "add", "update", "record", "make the change").
5. **Record** — update the **living design concept** (not an ADR yet): the structure, the
   **open-point register** (decided / leaning / pending with rationale), and **concrete**
   examples (signatures, call sites, data shapes). Move dead-ends to a **rejected
   register** with *why* + *revisit-if* — **never delete them**.
6. **Iterate** — revisit on new constraints; a rejected branch may revive. Repeat 3–5
   until the selected scope's open points are resolved.
7. **Consolidate** — check the selected decision scope against the whole concept and its
   dependencies. Prepare the exact proposition, alternatives, rationale and consequences
   in the living design; do not put an unaccepted proposal into an accepted ADR.
   - *Gate — audit (post-fan-out):* when a trigger fires — a **count floor**
     (`architect_min_options`, registry data) or the **structural trigger** (the design
     fan-out spanned ≥2 independently-decomposed zones) — route an `audit` pass
     (`k_auditor`, clean context) over the **gate-pack** (the concept + the Frame
     yardstick + the coverage map) **before** folding into an ADR. It checks for
     contradictions between independently-correct options, uncovered seams between zones,
     re-ranking deltas, and a level verdict. Advisory; the skip above the floor is allowed but
     **stated** — on Claude the `gate-audit` hook counts the turn's options and holds the
     hand-off once at or above the floor (C25). One bounded **loop-back** re-round on a material
     gap, then the owner.
8. **Align and record acceptance** *(gate)* — get **explicit owner agreement** on the
   coherent architecture / data-model / math-shaping scope before writing it as a
   requirement or accepted ADR block. Ordinary unambiguous acceptance is sufficient;
   no magic approval word, repeated per-block confirmation, or file-level approval follows.
   Record the accepted scope and the owner's rationale in its thematic ADR block(s).
   Plausibility and passing examples are not agreement. Clarify ambiguous scope; a new
   material delta needs acceptance only for the affected meaning.
9. **Hand off** — a task in the **design backlog**; an implementation task in
   `_aitna/TASKS.md` (goal + design link) only **once the design is locked**.

## Gates (must hold to advance)

- **After Survey:** the current design is confirmed against code, not memory; names
  checked for collisions.
- **Before Record:** load-bearing recommendations have alternatives, evaluation criteria,
  and a stated rationale for the chosen option, unless the change is explicitly too small
  for alternatives to be material.
- **Before Record:** the owner has explicitly agreed to write/update the relevant design,
  backlog, requirement, ADR, or process file unless the original request was already an
  edit command.
- **Before Consolidate→Align:** the selected scope has no blocking open choice; unrelated
  open work stays in design/tasks. Dead-ends are in the rejected register, not deleted;
  and — when a trigger fired (count floor or ≥2 zones) — the audit ran on the gate-pack
  (or the skip above the floor is logged),
  with one bounded loop-back re-round on a material gap.
- **Before a requirement (Align):** the owner has explicitly agreed to load-bearing
  decisions.
- **Before an accepted ADR block:** the owner has accepted its exact scope. A containing
  topic's acceptance cannot approve an added or changed block.
- **At Hand off:** the design is locked and linked; significant commitments have accepted
  ADR blocks, and implementation/verification work has a task owner.

## Artifacts

- **Living design concept** — durable, multi-session, resumable by a cold agent (hub +
  "how to resume"; a folder when it grows). The live source until decisions lock.
- **Rejected-branches register** — why + revisit-if.
- **Thematic ADRs** — accepted commitments only, grouped by subject with stable block IDs.
  A single-decision ADR is a valid small-topic form. Order ADRs by **number**, not a date;
  **no dates** in design docs or ADRs (see [tasks](tasks.md) §No dates).
- **Design backlog** — separate from the implementation backlog; same index format and the same
  no-dates rule ([tasks](tasks.md)).

## Decision blocks and later changes

Record a significant commitment whose rationale future work needs: a shared contract,
product boundary, consequential math/data choice, substantial risk/cost trade-off, or
hard-to-reverse departure. A routine correction under accepted rules does not need a
new decision record. The same threshold applies when a decision emerges during coding.

Use a stable canonical marker in the project's chosen decision-record namespace; for example,
`Decision-ID: DEC-0042/D03` can be referenced in prose as **decision 0042 D03**, with a readable
title and a durable anchor.
The suffix identifies the decision, not its display position; never reuse it. Retain a `Legacy-ID: D2-N`
alias only when migrating that historical identity. A title change or topic split keeps
the identity and a navigational pointer, not a second authoritative copy.

A block preserves the accepted scope, decisive premises, choice, rationale, material
consequences and reconsideration conditions. Link research and implementation evidence
instead of duplicating them. Common topic context must not silently change the meaning
of an unchanged block. Material replacement gets a new ID and an explicit supersession
link covering only the affected scope. Preserve the old rationale and make challenged
premises visible while replacement work is open; do not apply a known-invalid premise.

Implementation status, missing measurements and conformance checks belong to tasks and
their evidence, not to an ADR approval queue. Git supplies committed history on demand;
there is no mandatory copied SHA or separate post-landing verification transition.
An evidence reference identifies the subject actually checked, not proof of acceptance.

## Done

A locked, linked design with alternatives/trade-offs and recommendation rationale;
accepted ADR blocks for significant commitments; updated requirement(s); and an
implementation task in `_aitna/TASKS.md`. Code is **not** part of this pipeline — it is
[code-flow](code-flow.md).
