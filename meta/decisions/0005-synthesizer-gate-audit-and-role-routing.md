# 0005 — Synthesizer gate audit, dynamic reasoner, plan-draft, role routing rights

- **Status:** Accepted (extends [0004](0004-model-routing-capability-tiers.md); implementation phased — C15–C20).
- **Owner:** akuminov@gmail.com
- **References:** design source [`meta/design/model-routing.md` §9–11](../design/model-routing.md)
  (rationale, decided register §9.7/§10.4, rejected branches §9.8, prior-art comparison §11) ·
  [MODEL.md § Capability tiers](../../MODEL.md) · [d2-ledger design](../design/d2-ledger.md) (§2.5
  attachment unit) · pipelines [review-flow](../../pipelines/review-flow.md) /
  [design-flow](../../pipelines/design-flow.md) (gate anchors) · backlog
  [A5, C15–C20](../TASKS.md).

## Context

ADR 0004 tiered *delegated* work, but the orchestrator's own synthesis — the
highest-leverage artifact of a review/architect session — remained the one unaudited node
(motivating evidence: an `io → options` layering inversion in the first consumer, invisible
to every per-module finding, caught only by a whole-graph look). Three further gaps: the
reasoner tier was statically pinned to the top rung (expensive, sometimes unavailable,
often above a bounded draft's needs); second-opinion diversity was defined by *vendor*
rather than by *model priors*; and the decomposition plan — the artifact the later audit's
coverage map derives from — was itself unchecked (circular blindness). The framework's goal
function is quality per unit of **tokens + owner attention**; only tokens had a mechanism.

## Decision

1. **Guiding principle — quality investment ∝ artifact leverage** (error cost + inherited
   operation/evolution cost): the higher the leverage, the stronger the model, the fresher
   the context, the closer to the owner the check. Named in MODEL.md; the tier gradient
   already embodies it.
2. **New tier `synthesizer`, pinned to the maximal available rung** — runs the new
   `synthesis-verify` task kind: a clean-context audit of the *whole* collected gate
   material (contradictions, uncovered seams from the coverage map, re-ranking deltas, an
   explicit could-not-verify list), delivered as generated agent **`k-synthesizer`**
   (read-only tools; input = a gate-pack, never session history; report → file + chat
   digest + D2-ledger attachment).
3. **The session model is the owner's level hypothesis; the synthesizer checks it** — its
   report includes a level verdict (did the task exceed the hypothesis; which piece to redo
   higher, or `/model` up). Advisory. The static init-time floor warning is demoted to a
   weak prior; consequently the **orchestrator floor is relaxed**: with the synthesizer on,
   review/architect-dominant sessions may orchestrate below the top rung.
4. **`reasoner` becomes dynamic:** default = the orchestrator's rung, with per-task-kind
   floors as registry data; escalate on the existing ladder signals. The synthesizer safety
   net makes the cheaper default acceptable.
5. **`second-opinion` requires *model* diversity, not vendor branding:** preference ladder
   as registry data — another vendor's model → the same vendor's *different* model → never
   the same model as author or auditor.
6. **New task kind `plan-draft` (tier reasoner, own matrix row)** — decomposition drafts
   (zone plan, risks, ordering) are delegable on leverage signals; *adopting* a plan, route,
   or synthesis is never delegated (the precise invariant reading). The synthesizer gains a
   **pre-fan-out plan-check anchor**: always for gate-qualifying work (structural criterion:
   zone plan names ≥2 zones), minimal pack (yardstick + zone plan), checking the plan
   against the *goal* — closing the coverage-map circularity.
7. **Gate-pack protocol — one packaging, N executors:** artifacts + Frame yardstick +
   coverage map (assembled from the delegation log by code; zone labels from the §10.3 zone
   plan) + an opt-in dependency-graph excerpt for architecture-review gates. Consumed by the
   synthesizer subagent and the second-opinion CLI (replaces the free-form `--prompt-file`).
8. **Triggers:** count floor (3 findings / 2 options, registry data, telemetry-tuned) OR
   structural trigger (≥2 independently-decomposed zones); orchestrator override both ways,
   a skip above the floor is silent-but-logged; one bounded loop-back re-round, then owner.
   Anchors: review-flow Calibrate, design-flow Consolidate (post-fan-out) + the plan check
   (pre-fan-out). Verification depth scales with gate criticality; diversity axes stay
   distinct — adversarial prompts / synthesizer context / second-opinion priors.
9. **Roles become orchestration contracts** with routing rights as registry data
   (`role_task_kinds`): review routes analysis kinds only (never an edit), architect adds
   design-fork/quant-derivation (doc-sync post-Record only), engineer routes realization
   kinds but never design-fork (a design gap goes back to architect), learn/release get
   their rows. Enforcement advisory via the delegation hook; doc rule + registry data ship
   first, the machine-readable active-role marker lands with the hook check (C20).
   `review` routing `debug-deep` stays legitimate: diagnosis is analysis, the fix is not.
10. **Owner attention is the second budget:** the synthesizer report attaches to the D2
    ledger entry (one place: change + rationale + audit + disagreement), and the stats
    digest gains attention metrics (D2 pending/verified, decisions per session).

## Consequences

- Registry deltas (C15): `synthesizer` selection policy (pinned max), `synthesis-verify` +
  `plan-draft` rows, dynamic-reasoner policy + per-kind floors, second-opinion diversity
  ladder, `role_task_kinds`; generated `k-synthesizer` joins the bootstrap set.
- Gate-pack builder + plan-check pack (C16), coverage map from the delegation log (C17),
  doc deltas — MODEL.md leverage principle, flow anchors, roles one-paragraph deltas,
  floor-warning demotion (C18), attention metrics (C19), role-matrix hook check (C20).
- The strongest model concentrates at three low-token, high-leverage points (plan draft on
  signal · plan check before spend · whole audit after); fan-out execution stays cheap;
  orchestration runs on the owner's hypothesis model.
- Rejected branches (v1 no-new-tier, static top-rung reasoner, vendor-only diversity,
  mandatory-at-every-gate, judgment-only trigger, raw transcripts, other-vendor-as-
  synthesizer) stay on record in the design §9.8 with revisit-if conditions.
