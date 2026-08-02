# Three High-Value Sources for Improving Akmon

> **Document date: 2026-07-18. Evidence checked: 2026-07-18.** The document date
> follows the owner's requested dating. External projects evolve; links describe the
> reviewed upstream state, not a permanent capability claim.

## Frame

**Subject:** Akmon's AI-assisted development standard, especially role boundaries,
subagent orchestration, drift control, and token/owner-attention economics.

**Yardstick:** improve quality per unit of tokens plus owner attention while preserving
Akmon's defining constraints: one contract owner, explicit
`review → architect → engineer` boundaries, owner-owned decisions and landing actions,
LLM-agnostic policy, vendor-honest enforcement claims, and regression-verifiable rules.

This is a review, not a design decision. The adaptations below are candidate experiments
for an architect pass; they do not authorize changes to the operative standard.

## Why these three

The most useful trio is not simply the three repositories with the most stars. It is the
smallest set that covers three different failure surfaces:

| Project | Best contribution to Akmon | Primary gap addressed |
|---|---|---|
| [Superpowers](https://github.com/obra/superpowers) | Behavioral policy evals and a precise task/review handoff | A rule can exist and still not change agent behavior |
| [OpenSpec](https://github.com/Fission-AI/OpenSpec) | Change-local artifact graph and current/proposed state separation | Design, task, D2, implementation, and living contract can drift |
| [wshobson/agents](https://github.com/wshobson/agents) | Native multi-harness generation, round-trip checks, and tiered evaluation | Generated adapters and catalogs do not prove delivery or quality |

Spec Kit is a strong fourth candidate, but its specification pipeline overlaps OpenSpec.
BMAD and ECC provide broader catalogs, but their many personas and workflows would add more
taxonomy than Akmon currently needs. The selected trio has less overlap and more directly
testable mechanisms.

## Akmon baseline and observed weak spots

Akmon already has substantial strengths that should remain the frame rather than be
replaced:

- cognitive roles instead of persona proliferation;
- explicit owner authority and analysis/design/implementation boundaries;
- task-kind-to-tier routing, clean-context audit, gate packs, and coverage maps;
- one versioned shared standard with generated vendor delivery;
- deterministic checks, honest vendor capability accounting, and a learn loop;
- an explicit objective of quality per unit of tokens plus owner attention.

The local evidence also exposes six material gaps:

1. **Policy behavior is weakly evaluated.** `meta/self_ci.py` and structural tests can
   prove that an artifact exists or is wired, but Akmon's roadmap still leaves richer
   skill evaluation gates open ([ROADMAP O5](../../ROADMAP.md#o5-skill-contract--partially-done)).
2. **Delegation has routing but not a complete task protocol.** Akmon names task kinds,
   tiers, and delegates, but lacks one normative dispatch packet, bounded status vocabulary,
   and a required split between spec-compliance and implementation-quality verdicts.
3. **Engineer verification is less independent than review/design verification.** The
   engineer gate audit is signal-triggered rather than a consistent task-level contract;
   successful worker reports can therefore carry too much trust
   ([engineer role](../../../roles/engineer.md)).
4. **Change state is fragmented.** A non-trivial change may span `meta/TASKS.md`, a living
   design, an ADR, the D2 ledger, code, and tests. Multiple backlog entries are currently
   `code-complete & D2-pending`, demonstrating that implementation state and accepted
   architecture state are distinct and costly to reconstruct.
5. **Vendor delivery evidence is incomplete.** The capability matrix deliberately contains
   unknowns and task N1 requires live probes. Akmon is honest about this gap, but does not yet
   have a reusable round-trip certification harness per vendor × carrier × subagent path
   ([TASKS N1](../../TASKS.md)).
6. **Token economics are principled but not yet outcome-calibrated.** Akmon tracks context
   pressure and is developing token/attention telemetry, yet routing primarily encodes a
   model floor. It does not consistently compare total turns, input tokens, retries,
   review loops, latency, owner interventions, and escaped defects for a task.

## 1. Superpowers — make the operating rules behaviorally testable

### Strong concepts that fit Akmon

Superpowers treats process documentation as testable behavior: establish a failing
no-guidance baseline, add the skill, verify compliance, then close observed rationalization
loopholes. Its skill-writing guidance also distinguishes trigger metadata from the full
workflow because models may treat a descriptive summary as a shortcut and skip the body
([writing-skills](https://github.com/obra/superpowers/blob/main/skills/writing-skills/SKILL.md)).

Its subagent-driven workflow uses a fresh implementer context per task, a curated task brief,
independent task review, separate spec-compliance and code-quality verdicts, mandatory re-review
after material findings, and a whole-change review at the end
([subagent-driven development](https://github.com/obra/superpowers/blob/main/skills/subagent-driven-development/SKILL.md)).

It also makes an important cost correction: the cheapest token price may lose if a weak model
needs two or three times as many turns. Model choice is therefore based on task clarity,
integration complexity, judgment, and risk—not role name alone.

### Akmon gaps it can close

| Gap | Compatible adaptation | Evidence/metric |
|---|---|---|
| Structural checks do not prove compliance | Behavioral A/B fixtures for high-risk rules: role routing, analysis-before-mutation, owner-only landing, and policy delivery to subagents | Repeated fresh-context pass rate; failure/rationalization classes; variance |
| Delegation prompt quality is implicit | A minimal dispatch packet: task goal, accepted design/task excerpt, relevant global constraints, allowed scope/tools, verification commands, owner boundary, and expected report paths | Missing-context questions, retries, out-of-scope edits, dispatch tokens |
| Worker success reports are too easy to trust | Two independent verdicts: contract/spec compliance and implementation quality; material findings require fix and re-review | Escaped findings at final audit; review-loop count; false approvals |
| Model routing focuses on the rung | Measure total task cost: input/output/cache tokens, turns, retries, latency, review cost, and owner interventions | Quality-adjusted cost per completed task |
| Always-loaded instructions can grow | Trigger-only metadata plus progressive disclosure; measure routed payload sizes | Trigger recall/precision and total injected tokens |

### Role and subagent implications

No new top-level DEVELOP role is justified. The current role split is stronger than adding
`planner`, `tester`, `debugger`, or `code-reviewer` personas. These are task kinds or lenses:

- `architect` owns accepted task/design meaning;
- `k-implementer` receives the bounded dispatch packet;
- an independent reviewer can emit the two verdicts;
- `k-auditor` retains the whole-gate, clean-context seam check;
- the orchestrator alone routes, synthesizes, and talks to the owner.

The likely missing concept is therefore a **handoff protocol**, not a role.

### Do not copy wholesale

- automatic implementer commits or branch-finishing operations conflict with owner authority;
- mandatory worktrees are unsafe as a universal rule in dirty or constrained workspaces;
- one fresh implementer plus review loops for every atomic edit can cost more than it saves;
- universal TDD/design ceremony should be risk-triggered in Akmon;
- absolute context isolation should be tested against a cheaper forked-context arm.

## 2. OpenSpec — make change drift explicit and machine-checkable

### Strong concepts that fit Akmon

OpenSpec separates current capability specifications from proposed changes. A change groups
proposal, requirement/scenario deltas, design, and tasks, then applies the verified delta back
to the current specification. Its artifact dependencies form an explicit graph rather than a
collection discovered by search
([concepts](https://github.com/Fission-AI/OpenSpec/blob/main/docs/concepts.md),
[OPSX](https://github.com/Fission-AI/OpenSpec/blob/main/docs/opsx.md)).

Its verification vocabulary is particularly useful: **completeness**, **correctness**, and
**coherence**. The verifier asks whether tasks and scenarios are covered, implementation
matches intent, and design decisions are reflected in code. It also surfaces artifact/code
drift, although upstream verification remains advisory
([commands](https://github.com/Fission-AI/OpenSpec/blob/main/docs/commands.md)).

OpenSpec generates action-specific instructions from project context, artifact rules,
templates, and only the dependencies required for the current action. This is compatible
with Akmon's gate-pack and progressive-disclosure direction, but is not by itself proof of
token savings.

### Akmon gaps it can close

| Gap | Compatible adaptation | Evidence/metric |
|---|---|---|
| State is reconstructed from task/design/ADR/D2/code | Generate a compact change manifest that links the existing canonical owners instead of duplicating them | Broken/missing links; repeated reads; time to reconstruct readiness |
| Current and proposed contracts can blur | Record current contract reference/hash, proposed delta, promotion condition, and owner-verification state | Stale-base conflicts detected before implementation/closure |
| A changed upstream artifact does not invalidate downstream work explicitly | Dependency invalidation: a changed design/spec marks dependent task briefs and audit packs stale | Invalidated artifacts caught; unnecessary reruns; escaped stale assumptions |
| Verification is command-list oriented | Add completeness/correctness/coherence/drift axes to the audit yardstick | Findings by axis; false-ready rate |
| Gate packs are assembled from several inputs | Generate the resolved graph as a compact auditor pack with links and selected facts | Pack tokens, missing evidence, audit precision |

### Role and subagent implications

OpenSpec actions should feed Akmon's roles, not replace them:

- `review` checks the current state and proposal assumptions;
- `architect` owns proposal/spec/design synthesis and any return from implementation;
- `engineer` executes only ready, non-stale tasks;
- `k-auditor` checks completeness, correctness, coherence, and drift over the resolved graph;
- owner verification alone promotes proposed architecture to accepted current truth.

Again, the gap is not a missing role. It is a missing **change-state projection and
invalidation contract**.

### Do not copy wholesale

- do not add an `openspec/` tree beside Akmon's existing sources of truth;
- do not create a second task list or a second design owner;
- advisory verification must not weaken D2 and owner gates;
- fluid action order must not let an engineer silently redesign a load-bearing contract;
- archive history is not a substitute for Akmon's `CAPTURE → DISTILL → PROMOTE → PROPAGATE`
  learn loop;
- large repeated project context must pass an A/B token and behavior evaluation.

## 3. wshobson/agents — certify delivery without adopting a persona catalog

### Strong concepts that fit Akmon

wshobson/agents keeps a source-of-truth and generates harness-native artifacts instead of
claiming a lowest-common-denominator translation. Its documented matrix names concrete output
shapes and harness-specific limits; its `garden` check targets drift, dead links, and size caps
([README: multi-harness support](https://github.com/wshobson/agents#multi-harness-support),
[harness matrix](https://github.com/wshobson/agents/blob/main/docs/harnesses.md)).
The capability table is derived from a machine owner used by adapters and documentation. That
is more valuable to Akmon than copying a fast-changing inventory of plugins or agents.

The project also exposes two evaluation ideas relevant to Akmon:

- a layered plugin evaluation model: deterministic static checks, semantic LLM judgment,
  and repeated Monte Carlo reliability runs;
- round-trip recipes against real CLIs, which are closer to Akmon's required live harness
  evidence than generator-only tests
  ([plugin eval](https://github.com/wshobson/agents/blob/main/docs/plugin-eval.md),
  [round-trip results](https://github.com/wshobson/agents/blob/main/docs/round-trip-results.md)).

Its three-level skill loading—metadata always available, instructions on activation,
resources on demand—is a concrete progressive-disclosure pattern. Its hybrid model routing
also reinforces that planning, execution, and review can use different rungs
([architecture](https://github.com/wshobson/agents/blob/main/docs/architecture.md)).

### Akmon gaps it can close

| Gap | Compatible adaptation | Evidence/metric |
|---|---|---|
| Generated files can pass structural checks but fail at runtime | Vendor × carrier × path certification: main session, subagent, skill trigger, hook payload, and enforcement behavior | Exact transcript/payload assertions and reproducible CLI fixture |
| The README capability matrix is partly manual | A vendor-capability registry with `native/emulated/degraded/unsupported/unverified`, evidence class, harness version, probe date, test id, and enforcement semantics; generate the human table from it | Claim without current evidence fails verification |
| Adapter drift checks are scattered | One `garden`-style sweep for generated drift, dead links, unsupported fields, context caps, and unmaterialized dependencies | Deterministic failures per harness |
| Policy quality has one testing layer | Three depths: static on every change; bounded semantic eval for risky policy changes; repeated reliability runs for release candidates | Cost and pass-rate by depth |
| Progressive disclosure is conceptual | Explicit metadata/instructions/resources layers with payload budgets and trigger tests | Always-loaded bytes/tokens, activation accuracy, missing-resource rate |
| Routing has no empirical portfolio view | Aggregate task results by task kind × model tier, including turns and review defects | Cheapest adequate tier based on observed outcomes |

### Role and subagent implications

Akmon should resist the project's large agent catalog. Domain personas are useful as LOCAL
specializations or skills, but promoting them to SHARED roles would blur Akmon's cognitive
operation boundary. The reusable concepts are:

- role remains stable; task kind selects the delegate;
- skills provide routed knowledge; agents provide bounded execution;
- native adapters are generated from one semantic owner;
- each adapter earns a capability claim through live round-trip evidence.

### Do not copy wholesale

- catalog size is not coverage quality;
- named vendor models must not enter the LLM-agnostic policy layer;
- generated native artifacts still need live payload/enforcement verification;
- LLM-judge scores cannot replace deterministic invariants or owner decisions;
- 50–100-run evaluation is too expensive for routine documentation edits and needs risk gates;
- broad plugin installation increases discovery noise and always-loaded metadata.

## Consolidated findings and priority

| Priority | Finding | Best source | Route | Acceptance criterion for a pilot |
|---:|---|---|---|---|
| P0 | Akmon cannot yet prove that high-risk prose changes agent behavior | Superpowers + agents eval | Architect: behavioral-eval contract | A repeated baseline/treatment fixture catches at least one known policy failure and reports variance/cost |
| P0 | Vendor delivery and subagent-path enforcement lack reusable certification | wshobson/agents | Review N1, then architect | A real CLI transcript proves the exact policy/payload on one vendor × carrier × subagent path |
| P1 | Change readiness and architecture acceptance are fragmented | OpenSpec | Architect | One manifest links existing owners, detects a stale base, and adds no second source of truth |
| P1 | Delegation lacks a normative dispatch and review handoff | Superpowers | Architect | Two representative tasks use the packet; scope escapes and missing-context retries are measured |
| P1 | Token routing is not calibrated to total outcome cost | Superpowers + agents | Learn/review, then architect | Compare at least two model tiers using total turns/tokens/retries/review defects, not token price alone |
| P2 | Progressive disclosure lacks explicit budgets and trigger evals | Superpowers + agents | Architect | Measure always-loaded payload and trigger recall before/after, with no owner-boundary regression |

## Recommended experiment sequence

1. **Behavioral policy A/B.** Choose one high-risk invariant—owner-only landing or
   analysis-before-mutation—and run no-policy versus current-policy arms in fresh contexts.
2. **Live delivery round trip.** Trace that invariant from source through one generated
   adapter into a main session and a subagent transcript; assert exact payload and behavior.
3. **Dispatch packet pilot.** Run two independent implementation fixtures with explicit
   packet fields, bounded statuses, separate contract/quality verdicts, and mandatory re-review.
4. **Change projection pilot.** For one Akmon change, generate links to task, design/ADR,
   D2 points, affected contracts, scenarios, and verification evidence; detect stale inputs.
5. **Cost comparison.** Record total tokens, turns, retries, elapsed time, owner interventions,
   and defects found at each gate. Compare fresh context with a bounded inherited-context arm.
6. **Architect decision.** Only proven mechanisms enter a design/ADR and D2 ledger; rejected
   mechanisms and revisit conditions remain recorded.

## Conclusion

Akmon does not need more top-level roles. Its role model is already a differentiator. The
highest-value improvements are contracts around the roles:

1. behavioral evidence that policy changes agent behavior;
2. precise dispatch, status, and independent review handoffs for subagents;
3. a change-local projection connecting current state, proposed state, tasks, D2, and evidence;
4. live, native, round-trip certification of each vendor path;
5. outcome-based token economics that counts turns, retries, reviews, owner attention, and
   escaped defects.

Superpowers is the best source for behavior and handoff discipline, OpenSpec for change-state
and drift control, and wshobson/agents for native delivery and evaluation depth. Their catalogs
and ceremonies should not be copied; their strongest mechanisms should be tested inside
Akmon's existing ownership, role, and verification model.
