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
3. **Design** — propose the structure; decide **point by point**. For anything
   load-bearing, frame the design space before recommending: include the realistic
   options (including the status quo when viable), the evaluation criteria, trade-offs,
   best-practice principles involved, risks, and revisit-if conditions. Do not present a
   single option as inevitable.
4. **Confirm recording** *(gate)* — before mutating design docs, ADRs, requirements, or
   backlog files, get explicit owner confirmation that the findings should be recorded.
   This gate is already satisfied when the request itself is an edit command ("write",
   "add", "update", "record", "make the change").
5. **Record** — update the **living design concept** (not an ADR yet): the structure, the
   **open-point register** (decided / leaning / pending with rationale), and **concrete**
   examples (signatures, call sites, data shapes). Move dead-ends to a **rejected
   register** with *why* + *revisit-if* — **never delete them**.
6. **Iterate** — revisit on new constraints; a rejected branch may revive. Repeat 3–5
   until the open points are resolved.
7. **Consolidate** — a coherence pass across the whole concept; **then** fold the locked
   decisions into an **ADR** (the options, the choice, the rationale, the consequences).
8. **Align** *(gate)* — get **explicit owner agreement** on any architecture / data-model
   / math-shaping decision *before* it is written as a requirement. Plausibility and
   passing examples are not agreement.
9. **Hand off** — a task in the **design backlog**; an implementation task in
   `_forge/TASKS.md` (goal + design link) only **once the design is locked**.

## Gates (must hold to advance)

- **After Survey:** the current design is confirmed against code, not memory; names
  checked for collisions.
- **Before Record:** load-bearing recommendations have alternatives, evaluation criteria,
  and a stated rationale for the chosen option, unless the change is explicitly too small
  for alternatives to be material.
- **Before Record:** the owner has explicitly agreed to write/update the relevant design,
  backlog, requirement, ADR, or process file unless the original request was already an
  edit command.
- **Before Consolidate→ADR:** the open-point register has no blocking `pending`; dead-ends
  are in the rejected register, not deleted.
- **Before a requirement (Align):** the owner has explicitly agreed to load-bearing
  decisions.
- **At Hand off:** the design is locked and linked; an ADR exists for every non-trivial
  decision.

## Artifacts

- **Living design concept** — durable, multi-session, resumable by a cold agent (hub +
  "how to resume"; a folder when it grows). The live source until decisions lock.
- **Rejected-branches register** — why + revisit-if.
- **ADR(s)** — the locked decisions only. Order them by **number**, not a date; **no dates** in
  design docs or ADRs (the commit history is the timeline — see [tasks](tasks.md) §No dates).
- **Design backlog** — separate from the implementation backlog; same index format and the same
  no-dates rule ([tasks](tasks.md)).

## Done

A locked, linked design with alternatives/trade-offs and recommendation rationale; an ADR
per non-trivial decision; the updated requirement(s); and an implementation task in
`_forge/TASKS.md`. Code is **not** part of this pipeline — it is [code-flow](code-flow.md).
