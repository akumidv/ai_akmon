# Anatomy of one gate — a worked example

A real gate, end to end: the top-down architecture audit **of akmon itself**, run with
akmon's own mechanism (session of 2026-07-05, recorded in
[meta/reviews/review-20260705.md](../meta/reviews/review-20260705.md)). Every step below
happened; quotes are from the session's gate artifacts. Gate artifacts live in the
consuming project's `_aitna/artifacts/gates/<stamp>-<slug>/` and are **gitignored**
(per-session process material, not repo content) — which is why this page inlines what it
cites instead of linking it.

The operative rules this example exercises: [MODEL.md §10](../MODEL.md#10-capability-tiers--model-routing)
(tiers, task kinds, the leverage principle) and the gate anchors in the
[review-flow](../pipelines/review-flow.md) / [design-flow](../pipelines/design-flow.md)
pipelines.

## 0. What a gate is

A **gate** is the point where a body of drafted work is judged as a whole before it
reaches the owner: the orchestrator assembles everything produced so far into a
**gate-pack**, and a clean-context **k-auditor** — pinned to the maximal available model —
judges it against a **yardstick**. The auditor drafts a verdict; the owner still decides.
This is the leverage principle in action: the strongest model spends a few thousand tokens
exactly where one missed contradiction would poison everything downstream.

## 1. Frame — the yardstick

First artifact written, *before* any analysis: `yardstick.md` — the owner's request
restated as acceptance criteria, plus explicit out-of-scope items. This audit's yardstick
had five criteria (goals-vs-implementation · isolation/abstraction/subagent economics ·
subagents↔roles↔pipelines wiring · consumer attachment · bottlenecks) and one owner-set
exclusion (the submodule-vs-vendored state of the local copy). Everything later — zone
plan, synthesis, verdict — is judged against this file, so scope cannot silently drift.

## 2. Fan-out — worker-tier zones

The orchestrator split the tree into **five zones** — R (roles+pipelines), H (hooks),
T (tools+registry), A (consumer attachment), M (meta: ADRs/backlog/prior gates) — and
delegated each to a **k-explorer** on the worker rung (haiku in that session). Five
parallel read-only sweeps returned conclusions with file:line citations; the orchestrator
window stayed lean (~337k tokens burned in subagents, near-zero in the main context).

Two mechanics matter here:

- **Delegation descriptions carry a `[zone:X]` marker.** The delegation-log hook records
  every spawn to a TSV at zero token cost; the coverage-map assembler later groups those
  log lines by zone. In this very session the orchestrator wrote `zone:R …` without
  brackets — the map degraded to "(unlabelled)" and had to be hand-assembled. The lesson
  became a backlog task (tolerant parsing + the convention stated where the orchestrator
  sees it); the take-away for you: **bracket the marker**.
- **Workers extract, the orchestrator calibrates.** Zone R flagged a "role docs contradict
  the registry" finding. The real state was subtler (partial restatement — drift-prone
  duplication, not contradiction); the orchestrator reframed it. Worker output is treated
  as reliable *extraction* with citations, never as final *judgement*.

## 3. Synthesis — the orchestrator's draft

The orchestrator (not a delegate — synthesis is never delegated) merged five zone reports
plus its own reading of the core surface into `analysis.md`: findings ranked, each with
evidence, an assessment per yardstick criterion, and a "what is genuinely strong — keep"
section. This is still a **draft**: it contains whatever blind spots the zones shared.

## 4. The gate-pack — assembled by code

`gate_pack.py` (a tool, not prose discipline) concatenated the pack: the yardstick, the
synthesis, and the **coverage map** — which zones were planned vs which delegations
actually ran, derived from the delegation log. The coverage map exists so the auditor can
see not only what was found but **where nobody looked**.

## 5. The audit — clean context, maximal model

A **k-auditor** was spawned with *only* the gate-pack — no session history, no
accumulated framing. The clean context *is* the mechanism: an auditor that shared the
orchestrator's context would inherit the orchestrator's blind spots. Its tool set is
read-only (no write tools) — isolation by construction, not by instruction. It returned a
structured verdict with four required parts, and every part earned its place:

- **Contradictions (4 found)** — e.g. two zones had reported *the same fact* (an
  in-flight rename's broken links) as two independent defects; the verdict merged them and
  flipped the framing from "migration unexecuted" to "migration in flight with incomplete
  propagation — worse, it actively generates broken state". It also caught the synthesis
  *under*-crediting a zone: the "over-flagged" example partially undercut itself.
- **Uncovered seams (6 found)** — the sharpest: *all five zones were static reads;
  nothing was executed*. Also two classic boundary gaps ("zone T checked the tools, zone A
  checked the attached result — nobody checked that the attach instructions produce that
  result").
- **Re-ranking deltas (7)** — one sub-bullet was promoted to a standalone major finding
  (a checker that had drifted from the data it checks — cheapest fix, widest blast
  radius); one live-observed nit was upgraded because it silently defeats the coverage-map
  mechanism itself.
- **Level verdict** — the explicit answer to "was the session's model rung enough, or
  must a piece be redone higher?" Here: *adequate at every rung; no redo* — with the
  evidence spelled out (every spot-checked worker citation reproduced exactly).

## 6. Execution evidence — closing the seam the audit found

The verdict's "nothing was executed" seam had a named task kind waiting for it:
`validate-loop`. A **k-validator** ran the meta test suite and the verification tools and
produced the single sharpest fact of the whole audit — **tests green (338 passed) while
`verify --strict` and the self-CI were red** — a split that is *statically invisible*: no
amount of reading files could have surfaced it. Static sweeps and execution runs are
complementary evidence classes; a gate that only reads is half a gate.

## 7. What the owner received

One synthesis + one independent verdict + the execution evidence, with the items only the
owner can verify listed explicitly (math/data/architecture verification never delegates —
see [guardrails/_common.md](../guardrails/_common.md) § Verify against reality). The
findings then became one review file and named backlog tasks — the gate's output is
durable artifacts, not a chat scroll.

## Take-aways

- **Write the yardstick first**; everything downstream is judged against it.
- **Fan out cheap, synthesize in the main session, audit clean and maximal** — the three
  rungs of the leverage principle, in order.
- **Mark every fan-out delegation with `[zone:X]`** so the coverage map assembles itself.
- **Treat worker reports as extraction, not judgement** — calibration is the
  orchestrator's job, and the auditor checks the orchestrator.
- **Add an execution leg** (`validate-loop`) — static reads cannot see a green-tests /
  red-verify split.
- **The auditor's clean context and read-only tool set are the guarantee** — prefer
  structural isolation over trusting instructions.
