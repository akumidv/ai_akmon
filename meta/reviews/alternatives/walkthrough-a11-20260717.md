# A11 walkthrough record — per-theme breakdown and owner verdicts

> **What this is.** The rationale record for
> [A11](../../TASKS_ARCHIVE.md) (archived): each theme of the
> [alternatives plan §6.0 priority view](plan-akmon-from-alternatives-20260718.md)
> is presented to the owner in the fixed descriptive order (essence → as-is with
> pros/cons → proposed solution with what it solves and its drawbacks →
> alternatives; `roles/architect.md` § Describe a change essence-first), and the
> owner's verdict + pilot acceptance criterion are recorded here. The plan file
> stays the weakness→source why-record; `meta/TASKS.md` carries execution state;
> **on A11 completion the verdict set is folded into one ADR** that links this
> record as its rationale.
>
> **Completed 2026-07-17:** all 7 themes accepted; the verdict set is folded
> into [ADR 0010](../../decisions/0010-alternatives-adoption-a11-verdicts.md).
>
> Route (7 themes, plan §6.0): 1 behavioral evaluation → 2 vendor delivery
> proof (D2, D4) → 3 delegation contracts (D3 parked) → 4 change-state
> lifecycle → 5 review/handoff discipline → 6 deterministic hardening →
> 7 owner attention & new carriers (D1). Started 2026-07-17.

---

## Theme 1 — behavioral evaluation: P3.1 → P3.2 (+P3.3) · W1 W3 W13

**Verdict: ACCEPTED (owner, 2026-07-17), as planned.**

### Essence

akmon is made of rules that are supposed to **change agent behavior** — guardrail
texts, roles, hooks, routing. Today we only verify that the *code of the rules is
correct* (a hook parses its payload, sync generates pointers), never that a *rule
actually changes behavior*: does an agent with the commit guard commit to main
less often than without it? Does the nudge raise the delegation share? This theme
introduces the instrument that measures it — "agent with rule vs agent without
rule" on the same task — and wires the result into the rule lifecycle: a new rule
is authored only after an observed failure without it, and promotion of a rule
into the shared layer requires a named evidence class instead of plausibility.
It puts ground under akmon's goal function ("quality per unit of tokens + owner
attention"): today a claim, after this a measured quantity.

### As-is (pros / cons)

No behavioral verification mechanism exists; the adjacent mechanisms are:

- `meta/self_ci.py`, `bin/verify.py`, 350 meta tests — deterministic checks of
  **code and structure** only.
- D2 ledger — manual owner verification of features (attention, not statistics).
- Delegation log (C17) already writes `ts·session_id·subagent·model·zone·description`
  — raw material for a "delegation share" metric, currently read by no one as a
  metric.
- PROMOTE step (`pipelines/learning.md` step 2): promotion test = "general +
  proven", where *proven* = "used more than once" — a **frequency** criterion,
  not an effect criterion.

**Pros of the status quo:** zero API cost for measurement; the deterministic
layer is fast and reliable; D2 keeps the owner in the loop.

**Cons:** the goal function is unprovable — not one first-party number (all four
reviews independently named this gap #1); every new guardrail is authored blind —
we never watched the failure it supposedly fixes; the forcing hooks (commit
guard, delegation nudge, C29) may be useless or harmful (alarm fatigue) with no
way to know; PROMOTE lifts unproven rules into the shared layer, from which they
spread to every consumer; negative results ("did not reproduce") vanish.

### Proposed solution (what it solves / drawbacks)

Three-layer evaluation with a control arm, each layer cost-tagged (synthesis of
the three architectures observed in the reviews: ponytail → Superpowers →
wshobson):

1. **A14 / P3.1 — the contract before code:** baseline/treatment arms; isolation
   checklist (fresh repo copy + fresh context per cell, excluded global settings,
   workspaces retained for rescoring — direct port of ponytail's lesson, whose
   baseline secretly ran under their own SessionStart hook and nearly published a
   false ~4%); metric axes (role/boundary compliance, delegation & routing, gate
   activation, correctness/safety, tokens/time/owner attention; LOC diagnostic
   only); **baseline-must-fail** for guardrail authoring; layers: deterministic
   static always (free) → LLM judge on risk (~4 calls) → statistics (50–100 runs,
   confidence intervals) **for promotions only**.
2. **C42 / P3.2 — harness `meta/benchmarks/`** + the two cheapest claims gated
   first: the commit guard stops a default-branch commit (binary, deterministic
   grader); the delegation nudge moves the delegation share (metric from the
   existing log). The grader is unit-tested without an API key (ponytail's
   pattern). Includes the D3 arm and the first W18 outcome numbers.
3. **P3.3 — evidence classes in PROMOTE:** contract/unit-verified · behaviorally
   demonstrated · no-regression-only · unproven hypothesis · model/harness-specific
   ceiling; promotion requires a named class; negative results are retained and
   labeled (ponytail's #217 rung, labeled *unproven* when the benefit did not
   reproduce, is the honesty model).

**Solves:** W1 — first first-party numbers for the goal function; W3 — isolation
adopted before the first benchmark, not after the first embarrassment; W13 — the
shared layer is protected from plausible-but-unproven rules; side effects — data
for routing calibration (W18) and D3 resolved by measurement, not opinion.

**Drawbacks kept/introduced:** the statistical layer costs real money and time
(headless session runs) — mitigated by promotions-only; the LLM judge is
subjective — mitigated by being the middle layer, with both first gates
deterministic; the harness is new code that itself needs maintenance (new surface
in `meta/`); results are model/harness-bound — the "model/harness-specific
ceiling" class records this honestly, but portability of conclusions is limited;
a 2-gate sample proves the pilot, not the whole system.

### Alternatives

1. **Status quo** (deterministic tests + D2). Zero cost, but W1/W13 remain
   forever; every next guardrail authored blind. Rejects the #1 convergent
   finding of all four reviews.
2. **Statistics for everything** (Monte Carlo per rule, wshobson scale). Maximal
   honesty, but measurement costs more than the measured — contradicts the goal
   function itself. Already rejected in the plan.
3. **LLM judge only, no control arm** (Superpowers style). Cheaper than
   statistics, but a judge without a baseline is ungrounded: it scores
   "compliance-lookalike", not a behavior delta. Absorbed as the *middle layer*;
   rejected as the foundation.
4. **External eval tool** (Promptfoo/Braintrust/Phoenix — already named in
   ROADMAP "Build vs buy"). Less own code, but a foreign arm/isolation model and
   a dependency ROADMAP itself forbids making load-bearing. Compromise shape:
   own thin stdlib harness as the contract, external runner as an option for the
   statistical layer; sub-decision deferred to A14.
5. **Manual owner verification of behavior** (extend D2 to sessions). Does not
   scale and spends exactly the resource — owner attention — the goal function
   economizes.

### Verdict detail

- **Accepted as planned** (layered model; alternatives 3 and 4 absorbed in part,
  1/2/5 rejected).
- **Pilot acceptance criterion:** a repeated baseline/treatment fixture catches
  ≥1 known policy failure (e.g., a default-branch commit without the guard) and
  reports variance and run cost.
- **Carriers:** one architect pass A14 on P3.1+P3.3 (design session in plan mode
  per P2.8, plan file promoted into `meta/design/`) → C42 for P3.2.
- **Deferred to A14** (named, not decided): fixture consumer (pinned alphavar vs
  synthetic mini-repo), statistical-layer budget, own runner vs external.

---

## Theme 2 — vendor delivery proof: P0.1, P0.2 → P3.4 · W2 W4 W9 W10 · decisions D2, D4

**Verdict: ACCEPTED (owner, 2026-07-17), per recommendations — D2 resolved
(probe-first), D4 resolved (per-vendor by data; `k-*` stays the contract).**

### Essence

akmon's headline claim — "LLM-agnostic, with real enforcement" — rests on
assumptions about what each vendor harness *actually delivers*: does a subagent
receive the guardrails, does the model pin hold, do our hooks see the child
session, what remains on hook-less vendors. Today part of the support matrix is
assumption, not observation. The theme: **before building any new mechanism**,
record from live experiments what actually arrives on each path
(vendor × carrier × subagent type) and declare an honest support/degradation
contract. Two open decisions attach: **D2** — build SubagentStart injection now
or probe first; **D4** — map roles onto the vendor's built-in subagent types or
keep generated `k-*`.

### As-is (pros / cons)

- README matrix (8 capabilities × 4 vendors): the Claude column is ✅ and
  reflects genuinely wired hooks; Codex is mixed ✅/❌ (generic subagent launch
  live-verified on 0.144.1; hook output contract schema-verified from binary
  strings — C28(b); **runtime enforcement unverified** — the C31 question
  class); Gemini/Copilot — ❓ throughout.
- Delivery for `k-*` is **by construction**: generated agent bodies embed
  distilled guardrails (no commits, escalation signals, artifacts in English) +
  a model pin in frontmatter (routing.py `AGENT_SPECS`). A **non-`k-*`**
  subagent (built-in Explore / Plan / general-purpose / fork) receives nothing
  akmon-specific unless the harness injects it — and nothing verifies what it
  actually receives. That is W4.
- The risk class has already bitten live: the delegation nudge false-fired
  *inside* child sessions (C28d) — child-session hook behavior was an assumption
  until it broke.
- OS/shell support is declared nowhere (W9); instruction-tier vendors have no
  minimal "what is guaranteed" contract (W10).

**Pros of the status quo:** honest ❓ beats a false ✅; the Claude path is wired
and partly e2e-verified (C22); zero probe time spent; N1 already tracks the gap.

**Cons:** the headline claim is unproven beyond Claude; W4 open — a built-in
subagent may silently run guardrail-free; D4 undecidable without data; every ❓
cell is a place a consumer silently loses enforcement; no degradation contract.

### Proposed solution (what it solves / drawbacks)

- **P0.1 — live probes** on Claude Code + Codex: record from the
  payload/transcript what each subagent type actually receives — guardrail-text
  presence, model-binding adherence, tool set, whether delegation-log/routing
  hooks observe the child. Includes the **D4 comparison arm**: built-in types
  (Explore / Plan / general-purpose / fork) vs `k-*`. Output: a reproduced-drift
  record or its absence.
- **P0.2 — declare the support dimensions**: plugin-tier / instruction-tier per
  vendor; OS/shell statement (POSIX-only acceptable if stated).
- **P3.4 (later, once P3.1 defines "delivered")** — matrix re-run from
  experiment: `documented / delivered / advisory / enforced` per cell; matrix
  kept as data with the README table generated; smoke tests where cheap.

**Solves:** W2 — the matrix becomes honest; W4 — drift proven or disproven
*before* mechanism; W9/W10 — degradation becomes a contract; unblocks P4.1 and
D4.

**Drawbacks:** probes are manual and point-in-time — a harness update
invalidates them (mitigation: the N1 rule — re-check on every release touching
`hooks/` or `bin/sync.py`; P3.4 automates the cheap part); the stage is
findings-only, no user-visible feature; probing built-ins leans on undocumented
internals that may shift; Codex/Gemini probes cost install/subscription time;
an honest re-run will likely *reduce* the ✅ count — honesty over optics.

### Alternatives

1. **Mechanism first** (override D2: build SubagentStart injection now). Faster
   if the drift is real; dead surface + a standing token tax if it is not — and
   probes are needed anyway to verify the injection itself. Rejected.
2. **Fill the matrix from vendor docs.** Cheap, but exactly the lie ponytail
   escaped by luck; violates akmon's own "from experiment, not docs" norm.
   Rejected.
3. **Deep on Claude only; declare the rest instruction-tier without probing.**
   Cheaper and matches the "deep on Claude/Codex + instruction-tier for the
   rest" non-goal — but Codex is already half-wired and precisely its cells
   bite (C28/C31/C39). Absorbed as ordering: Claude → Codex; Gemini/Copilot
   stay declared-only until demand.
4. **Automated smoke tests instead of manual probes, immediately.** The right
   end state, the wrong order — you cannot automate before the payload shapes
   are known. Absorbed as P3.4.

### Recommendation and grounds

**Probe-first, Claude → Codex order, matrix re-run deferred to P3.4** (the plan's
shape; alternatives 3 and 4 absorbed as ordering/end-state). Grounds: (a) the
one live incident we have (C28d nudge false-fire in child sessions) came from an
*assumed* delivery path — evidence that assumption, not absence of mechanism, is
the active failure mode; (b) concept 1 (probe-first) — a mechanism built on an
unreproduced gap is dead surface plus token tax, directly against the goal
function; (c) akmon's own honesty norm makes docs-sourced cells (alt. 2)
inadmissible; (d) Codex's half-wired state makes "Claude-only" (alt. 3) leave
the known-biting cells unproven.

**D2 — resolved: probe-first confirmed** (P0.1 gates P4.1). Grounds: same (a)+(b);
the owner retains the override right the plan named, and did not exercise it.

**D4 — resolved: decided per vendor by the N2/P0.1 comparison-arm data;
`k-*` stays the contract until then.** Grounds: the decision rule ("prefer
native only where measurably at least as effective — delivery proven + W18
outcome economics") is exactly the theme's probe output, so deciding before N2
would be deciding on assumption — the failure mode this theme exists to remove.

### Verdict detail

- **Pilot acceptance criterion:** a real CLI transcript proves the exact payload
  on one vendor × carrier × subagent path; plus the D4 arm — a probe record of
  what a built-in type receives vs `k-*`, at least for Claude Code.
- **Carriers:** N2 (P0.1–P0.4 stage 0, review role, findings only) → P3.4 rides
  N1 later.
- **Owner clarification (recorded as rationale):** the probes are akmon
  dev-side (`meta/` artifacts: probe records in `meta/reviews/`, matrix as repo
  data), like theme 1's `meta/benchmarks/` — consumers see only the results
  (honest matrix, declared degradation contract). Cadence is not one-off:
  re-probe on every release touching `hooks/`/`bin/sync.py` (N1 rule); P3.4
  folds the cheap part into `self_ci`/`release_check`.

## Theme 3 — delegation contracts: P2.4, P2.5, P2.6, P2.8 · W17 W18 W19 W24 · D3 parked

**Verdict: ACCEPTED (owner, 2026-07-17), per recommendations — all four as one
architect pass inside A13; D3 explicitly PARKED (P2.4 stays silent on isolation
until C42 measures it).**

### Essence

akmon's delegation surface has **routing** (which rung runs what: tiers,
task-kind matrix, registry) but no **task protocol**: what a dispatch must
contain, what shape the subagent's report takes, how the orchestrator reacts to
failure, how bulk content travels between contexts, and what economics pick the
model. Every session improvises these. The theme locks four contracts around
the existing routing: dispatch packet + bounded status vocabulary with
prescribed controller reactions (P2.4), file handoffs (P2.5), cost heuristics +
explicit model per dispatch (P2.6), design-session carrier in the host's plan
surface (P2.8). The context-isolation question (fresh vs forked) is **D3 —
parked** until C42 measures it.

### As-is (pros / cons)

- **The routing spine is real and partly enforced**: MODEL.md §10 (tiers,
  task-kind matrix, "delegation is the default", escalation ladder), registry
  `role_task_kinds`, delegation log (zero-token observability), delegation
  nudge (advisory → ask), corridor warnings, gate audits.
- **The report contract is half-built, delegate-side only**: generated `k-*`
  briefs carry an escalation signal ("stop and report what is undecided") — but
  there is no status vocabulary, and **controller reactions are defined
  nowhere**: what the orchestrator does on a blocked delegate is improvisation;
  no "never force the same model to retry without changes" rule.
- **Dispatch content is unspecified**: the guardrail demands "name the delegate
  per sub-step up front" but defines no packet fields. The anti-pattern is
  observed, not hypothesized: a real 42k-char dispatch, 99% pasted history
  (top3 reviews).
- **Context hygiene is one-sided**: k-explorer's brief demands "conclusions,
  not dumps" (delegate side); no rule on the dispatch side; no file-handoff
  convention. C29 catches the orchestrator's inline dumps, not dispatch
  payloads.
- **Economics are price-based, not outcome-based**: the registry encodes a
  floor (worker = lowest, mid rung for `implement-under-spec`) — token-price
  intuition. W18 evidence: the cheapest models take 2–3× the turns and cost
  *more*; a non-`k-*` dispatch without a stated model silently inherits the
  expensive session model.
- **W24**: design-first is session discipline, not mechanism; an approved plan
  evaporates in `~/.claude/plans` (wave-3 analysis).

**Pros of the status quo:** the spine is tested and works; briefs already carry
delegate-side discipline; the log gives free observability; the escalation
ladder exists.

**Cons:** delegation quality is session-dependent — the protocol lives in
heads, not in a contract; scope escapes and missing-context retries are
unmeasured; pasted bulk is a standing tax on the orchestrator's context; the
floor prices tokens, not outcomes; the design gate ignores the harness's
enforcement point.

### Proposed solution (what it solves / drawbacks)

One architect pass (inside A13) locks four contracts:

- **P2.4 — dispatch packet + report contract**: normative fields (goal,
  accepted design/task excerpt, constraints, allowed scope/tools, verification
  commands, owner boundary, expected report paths) + the
  `DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED` vocabulary with a
  **prescribed controller reaction per status** (incl. "never retry the same
  model without changes"). Silent on isolation until D3.
- **P2.5 — file handoffs**: briefs/reports/review packages travel as paths, not
  pastes; a subagent returns status + one-line summary + paths; payload sizes
  become measurable.
- **P2.6 — cost heuristics into routing policy**: mid-tier floor for reviewers
  and prose-driven implementers; **explicit model in every dispatch**; "turn
  count beats token price" as named policy; calibration deferred to C42 data.
- **P2.8 — design-session carrier**: the plan-mode plan file is promoted into
  `meta/design/`; in team mode the lead's teammate-plan approval is the same
  gate; instruction-tier fallback — the design concept file itself is the plan.

**Solves:** W17 — failure handling stops being improvisation; W19 — the
orchestrator's context stops absorbing ballast; W18 — the dispatch model is
explicit and the economics named (calibrated later by data); W24 — design-first
becomes mechanism where the harness offers one.

**Drawbacks:** the packet is per-dispatch overhead — for small tasks writing a
brief file can cost more than the task → A13 must name an explicit **smallness
boundary** or the packet becomes its own tax; the status vocabulary works only
as far as the delegate knows it — `k-*` get it by generation, built-ins do not
(couples to D4); heuristics before calibration are still heuristics — may
misprice until the first C42 numbers; P2.8 is Claude-first (fallback for the
rest); added contract text presses on the always-loaded caps (W23) — carriers
are pipelines/briefs, not the always-on guardrail.

### Alternatives

1. **Status quo** (routing + brief discipline). Cheap, but the observed
   anti-patterns (42k dispatch; C28d) show the missing piece is a protocol, not
   more routing. Rejected.
2. **Full Superpowers port** (mandatory fresh-context isolation, universal
   worktrees, forced TDD). Already rejected by the plan as bootstrap
   absolutism; isolation goes honestly to D3 measurement, not doctrine.
3. **Tooling first** (a dispatcher that builds packets in code). Premature —
   locks shapes before the contract is proven; contract as text now, tooling in
   C41+ if the pilot proves it. Rejected as ordering.
4. **Status vocabulary without prescribed reactions.** Half of W17's value is
   the controller-reaction table; without it improvisation stays. Only the full
   form absorbed.
5. **For P2.6 — wait for calibration** (no policy until C42 numbers). Leaves
   known-bad price intuition in place meanwhile; provisional heuristics from
   review evidence beat nothing. Rejected; heuristics land marked provisional.

### Recommendation and grounds

**Accept all four as one architect pass (A13 scope); park D3 explicitly**, with
two A13-scope amendments drawn from the drawbacks: a smallness boundary for the
packet, and a `provisional` mark on P2.6 heuristics until C42 data. Grounds:
(a) convergence — both wave-2 reviews independently rank the delegation
protocol top-tier ("a handoff protocol, not a role"); (b) the anti-patterns are
observed, not hypothesized (the 42k dispatch; C28d as the price of an
improvised delegation surface); (c) contracts are text-first — cheap to lock,
C41 implements the mechanical parts; (d) the one-pass grouping matches the
plan's dependency spine (P2.4/P2.5/P2.6/P2.8 share one architect pass) — four
separate lock sessions cost more owner attention.

### Verdict detail

- **Pilot acceptance criterion:** two representative tasks run on the packet;
  scope escapes, missing-context retries, and dispatch tokens measured; one
  A-stage design produced via plan mode and promoted into `meta/design/`.
- **Carriers:** A13 (one architect pass; scope amendments above) → C41.
- **D3 — PARKED (owner, 2026-07-17):** fresh vs forked subagent context is
  resolved by measurement inside C42's harness; until then P2.4 stays silent on
  isolation.

## Theme 4 — change-state lifecycle: P2.7 · W21

**Verdict: ACCEPTED (owner, 2026-07-17), per recommendation — own architect
pass inside A13, with two scope constraints: the change manifest is
links-only, and A13 names a triviality boundary (what must carry a manifest
and what must not).**

### Essence

A non-trivial change in akmon lives in six carriers at once: the task in
`meta/TASKS.md`, the design in `meta/design/`, an ADR, a D2-ledger entry, the
code, the tests. There is **no projection of the change**: answering "what
state is change X in" requires a manual sweep of all six. Design docs are
whole snapshots — an amendment means editing the entire document, with no
delta records; there is **no closing step** — when the work is done, nothing
systematically reconciles the design with what actually landed in code; there
is **no invalidation** — an upstream design change does not mark dependent
tasks/briefs stale. The theme adopts OpenSpec's lifecycle *semantics*
(delta → closing reconciliation → dependency invalidation) without its
*folders* (the parallel spec tree is already a §4 non-goal).

### As-is (pros / cons)

The live evidence is our own backlog:

- **7 entries marked "code-complete & D2-pending"** in TASKS.md right now
  (C16, C17, C18, C20, C31, C39, V2) — work finished in code, its
  cross-carrier reconciliation hanging; this *is* the uncleared
  reconciliation debt.
- `meta/design/model-routing.md` — **985 lines**, a living design absorbing
  §9–13 with statuses embedded; what of it is implemented vs drifted from
  code is discoverable only by reading it end to end.
- Task lines balloon into mini-documents (C28 spans dozens of lines) because
  the task is the only place where a change's fragments get stitched together.
- Meanwhile the "one owner per fact" discipline exists and works;
  `TASKS_ARCHIVE.md` and the CHANGELOG give closure for tasks/releases; git
  history is an honest changelog.

**Pros of the status quo:** not a single duplicating tree; fact owners are
named; cheap — zero process overhead on small edits.

**Cons:** a change's state is reconstructable only by a full sweep (a tax on
owner attention — against the goal function); design docs drift silently
after implementation; reconciliation debt accumulates (7 hanging) with no
forcing step; an upstream edit does not invalidate downstream — a stale brief
looks fresh.

### Proposed solution (what it solves / drawbacks)

**P2.7, its own architect pass** (per the plan's dependency spine — separate
from the delegation pass):

- **Delta semantics** for design changes: `ADDED / MODIFIED / REMOVED`
  against the current truth — a change describes its diff, not a rewritten
  snapshot.
- **A closing archive-merge step**: on closing a change — reconcile "what
  landed in code" with the design/ADR, bring the design to truth, move the
  delta to archive/history. Inside existing carriers.
- **A compact change manifest**: one record that **only links** the canonical
  owners (task, design §, ADR, D2 entry, code) — a projection, never a
  duplicate.
- **Dependency invalidation**: a changed upstream design/spec marks dependent
  briefs and audit packs stale.

**Solves:** W21 — a change gets a projection (one look instead of a sweep);
design drift is caught by the closing step, not by accidental review; the
"code-complete & D2-pending" entries get a forcing closure step; downstream
staleness becomes visible.

**Drawbacks:** the manifest is one more artifact per change — if content (not
links) ever lands in it, it is ready fuel for drift (mitigated by a hard
"links only" rule); the closing step is process weight on every non-trivial
change → as in theme 3, A13 must name a **triviality boundary** (a small edit
must not be obliged to carry a manifest); the dependency map behind
invalidation can itself rot — until a checker (C41) it is discipline, not
mechanism.

### Alternatives

1. **Status quo** (one-owner-per-fact + git history). Cheap, but 7 hanging
   reconciliations and a 985-line design doc are the observed price; the debt
   grows with every non-trivial change. Rejected.
2. **Full OpenSpec port** (a parallel `openspec/` tree with change folders).
   Already rejected by the plan (§4): a second source of truth, a second task
   list. We take the semantics, not the folders.
3. **Tooling first** (a manifest generator/checker). Premature before the
   semantics are locked; a checker goes to C41 if the pilot proves value.
   Rejected as ordering.
4. **Extend the D2 ledger** (hang change links on D2 entries). Cheaper, but
   D2 is owner verification, not a change projection; overloading it muddies
   its purpose. Partially absorbed: the manifest *links* the D2 entry as one
   of the owners.

### Recommendation and grounds

**Accept P2.7 as its own architect pass in A13, with two scope constraints:
the manifest is links-only, and a named triviality boundary** (what must
carry a manifest, what must not). Grounds: **(a)** the debt is observable in
our own backlog right now (7 × "code-complete & D2-pending", ballooning task
lines) — not a hypothesis from someone else's repo; **(b)** both wave-2
reviews converged on the lifecycle semantics *and* both rejected the parallel
tree — a rare case where "what to take" and "what not to take" agree
independently; **(c)** a links-only manifest is the only form compatible with
the already-operating "one owner per fact"; alternatives 2–4 either violate
it or invert the order (tool before contract).

### Verdict detail

- **Pilot acceptance criterion (§6.0):** one change manifest links the
  existing owners, detects a stale base (upstream changed — the manifest
  shows it), and adds no second source of truth.
- **Carriers:** A13 (own architect pass; scope constraints above) → C41 for
  any manifest tooling the pilot justifies.

## Theme 5 — review/handoff discipline: P2.1, P2.2 · W11 W12

**Verdict: ACCEPTED (owner, 2026-07-17), with the seam amendment — the A13
lock must state explicitly that the dispatch packet's scope field (P2.4)
never constrains what a reviewer may flag; the reviewer-independence clauses
outrank the packet.**

### Essence

Two seams of the build loop have no contracts. **First — before writing new
code**: the engineer has the "reuse over re-implementation" principle but no
*ordered decision procedure* (needed at all → project reuse → stdlib → native
facility → installed dependency → minimal expression → only then new code)
and no root-cause clause for bug fixes ("fix the shared source, not the named
symptom"). **Second — the review verdict**: it is single and blended — "meets
the spec" and "implementation is good" are never separated; over-engineering
findings have no named yardstick (the vacuum is filled by "more lines = bad"
intuition); there are no reviewer-independence clauses (nothing forbids the
dispatcher saying "don't flag this" or pre-rating severity); a material
finding does not force fix + re-review — closure rests on the
signal-triggered check (owner-verify only for math/data/architecture), so
worker success reports carry too much trust.

### As-is (pros / cons)

**Reuse** is named in three places, everywhere as a principle, nowhere as a
procedure: `guardrails/_common.md` § Reuse over re-implementation (three
preference bullets), `roles/engineer.md` ("Reuse, don't re-implement"),
`pipelines/code-flow.md` step 2 ("Reuse existing abstractions… stdlib-only
for dev tooling"). No root-cause clause exists anywhere — a grep of
roles/guardrails finds none. Non-negotiables are not carved out either: a
literal "simplify" has no fence around security/trust-boundary requirements.

**Review**: `review-flow` is solid analysis discipline — Frame with a
mandatory yardstick, Measure with evidence per finding, Calibrate severity +
the audit gate over coverage, Hand off with fix criteria. But: the verdict is
one — "works but ugly" and "clean but off-spec" produce reports of the same
shape; "Calibrate severity" ranks but gives no yardstick specifically for
simplicity findings; no independence clauses — and the theme-3 dispatch
packet has just created a legitimate channel where "don't flag X" could
land; Hand off routes findings, but the loop "material finding → fix →
re-review" is not gated.

**Pros of the status quo:** the value is named and cheap; review's analytic
skeleton is real (yardstick, evidence, audit gate); zero process weight.

**Cons:** a preference without an order is uncheckable — the delegate and
the reviewer do not share one yardstick; bug fixes may legally patch the
symptom; the blended verdict hides exactly the two signals the owner needs
separately; over-engineering is argued by taste; reviewer independence is
luck, not contract.

### Proposed solution (what it solves / drawbacks)

Both contracts are text into existing pipelines, inside the A13 pass:

- **P2.1 — solution ladder in `code-flow`** (Implement step): ordered rungs
  *needed at all → project reuse → stdlib → native facility → installed
  dependency → minimal expression → new code* + a **root-cause clause** for
  bug fixes; the ladder explicitly subordinate to the accepted task and the
  locked design; **non-negotiables carved out** — security / accessibility /
  trust-boundary / data-loss / explicit requirements are never traded for
  simplicity.
- **P2.2 — review contract in `review-flow`**: the **simplicity lens** — a
  five-tag vocabulary `delete / stdlib / native / yagni / shrink`, read-only
  (a tag names the finding, never constructs the fix), severity by
  boundary/risk, **never by LOC**; **two-verdict task review** — spec
  compliance ∥ implementation quality separately, a material finding forces
  fix + re-review (this also closes "worker success reports are taken on
  faith"); **reviewer-independence clauses ported verbatim** — never tell a
  reviewer what not to flag, never pre-rate severity, a plan contradiction
  goes to the owner.

**Solves:** W11 — reuse becomes a checkable procedure with one yardstick
shared by engineer and reviewer; symptom fixes lose legitimacy. W12 —
over-engineering gets a falsifiable vocabulary; "compliant but poor" and
"good but off-spec" become distinguishable; the reviewer cannot be silenced
through dispatch; material findings close the loop.

**Drawbacks:** the ladder is per-change overhead — seven rungs on a trivial
edit is theater → needs a proportionality note (the ladder is a mental
order; only a material choice gets documented); five tags risk turning
reviews into tag-hunting (a tag labels a real finding, not a quota);
two-verdict + forced re-review raise the loop cost per material finding;
**the theme-3 seam**: the dispatch packet's scope field must not become a
"don't flag" channel — requires an explicit sentence in A13 (scope limits
what the reviewer *reads*, never what it *may flag*); more contract text
presses on the caps (W23) — the carrier is pipelines, not the always-on
guardrail.

### Alternatives

1. **Status quo** (principle without procedure). Cheap, but the vacuum is
   filled by model taste; W11/W12 are convergent findings of both wave-2
   reviews. Rejected.
2. **Numeric limits** (LOC budgets, cyclomatic-complexity thresholds).
   Falsifiable but a false metric — punishes clarity; the plan itself fixes
   "never LOC". Rejected.
3. **A separate simplicity-review role** (dedicated pass). An extra dispatch
   per review; simplicity is a lens inside the same analysis, not a role.
   Absorbed as the lens/tag vocabulary.
4. **Deterministic first** (complexity linters, dead-code checkers). They
   catch a sliver (dead code, unused dependencies) and can judge neither
   yagni nor the spec/quality split; fine as later automation (C41+), not as
   the foundation. Partially absorbed.

### Recommendation and grounds

**Accept P2.1 + P2.2 as planned — inside the A13 pass, with one seam
amendment: the A13 lock states explicitly that the dispatch packet's scope
field (P2.4) never constrains what a reviewer may flag — the independence
clauses outrank the packet.** Grounds: **(a)** W12 is the most widely cited
weakness row in the plan (four independent sources: [pny/claude] §7.2-3,
[pny/codex] F3, [top3/claude] §1.2-1/-7, [top3/codex] gap 3); **(b)** the
ladder and the lens are two halves of one yardstick — the engineer builds by
the ladder, the reviewer measures by the tags — locking them together keeps
the vocabulary shared; **(c)** pure text, zero code, rides the already
accepted A13 pass — the cheapest theme on the route; **(d)** the
independence clauses are ported verbatim from a proven source and close the
hole theme 3 just opened (the packet as a potential pressure channel on the
reviewer).

### Verdict detail

- **Pilot acceptance criterion (§6.0, row 2):** on two pilot reviews, both
  the count of findings that escape to the final audit and the review-loop
  count drop.
- **Carriers:** A13 (same pass; the seam amendment recorded in its scope)
  → C41 for the pipeline text changes.

## Theme 6 — deterministic hardening: P1.1–P1.7, P0.3, P0.4, P2.3 · W5–W8 W20 W22 W23

**Verdict: ACCEPTED (owner, 2026-07-17), per recommendation — P0.3/P0.4 ride
the already-accepted N2 stage; one A12 pass locks the seven P1.x shapes
(P1.4 observability-only, its D1 half stays with theme 7); C40 lands them
with the seeded-violation acceptance; P2.3 goes in A13 where already
scoped.**

### Essence

The deterministic layer — hooks, `sync --check`, `verify`, `self_ci`,
`release_check` — is akmon's free enforcement: no LLM, no API key, every
run. Today it checks **structure** (pointers, fixture, wheel) but not the
failure classes already named or observed: a hook can freeze a session
(unbounded stdin read); guardrail prose and hook code drift apart with no
cross-check; deferred simplifications rot with no marker; versions drift
across manifests; an orchestrator that loses its place after compaction may
re-dispatch completed work; tooling prints prose neither an agent nor the
owner can act on cheaply; the source/generated boundary and numeric caps are
preached but neither declared nor checked. The theme is ten small
deterministic items: two declarations (P0.3 — the guardrail↔hook invariant
inventory; P0.4 — boundary + caps), seven cheap hardenings (P1.1–P1.7), one
marker semantics (P2.3 `akmon-defer:`). None needs an LLM; the acceptance is
uniform — **every check fails on a seeded violation**.

### As-is (pros / cons)

Verified against the code:

- **W8 (hook survivability):** `claude_adapter.load_payload()` is
  `json.load(sys.stdin)` — blocking, unbounded (the same class as
  ponytail's frozen-session issue #443); both adapters catch malformed JSON
  → no-op, but **no regression test locks it** (`test_adapters.py` has zero
  malformed cases); BOM is normalized nowhere (BOM'd JSON drops the codex
  adapter into `{"raw": …}`); the generated `sync.py` hook wiring carries
  **no `timeout` field**.
- **W5 (prose↔code drift):** `sync --check` catches pointer drift; nothing
  pairs a rule's wording in `guardrails/*.md` with the `hook_core.py`
  constants. No INVARIANTS list exists.
- **W6:** zero `akmon-defer` markers in code (grep: only the plan/reviews/
  TASKS mention it); deferred simplifications live in memory.
- **W7:** `release_check.py` summarizes CHANGELOG sections but has no
  pyproject ↔ latest-CHANGELOG-entry cross-check.
- **W20:** the delegation log (hook-side) records dispatches, but there is
  no orchestrator-facing *completion* ledger in `_aitna/` — after compaction
  the place in the work is reconstructed from recollection; Superpowers
  calls this "the single most expensive failure observed".
- **W22:** `verify`/`release_check` print prose; no
  `severity/code/message/target/fix` envelope, no exit-code table.
- **W23:** `sync.py` generates vendor files but "what may never be
  hand-edited" is undeclared; no numeric caps on always-loaded artifacts.

**Pros of the status quo:** the layer is real and reliable — 350 meta tests,
self_ci runs sync/check/verify on a fixture plus a wheel smoke; malformed
JSON is already caught; zero dependencies. The problem is **coverage**, not
quality — the named failure classes sit outside it.

**Cons:** the freezing stdin is the one item with *production*-incident risk
at a consumer; prose↔code drift silently undermines akmon's core promise
(the rule looks alive, the hook enforces the old wording); the rest are
accumulating taxes (post-compaction re-dispatch, manual prose parsing, an
unnamed generation boundary).

### Proposed solution (what it solves / drawbacks)

The ordering is already embedded in the accepted carriers:

- **P0.3 + P0.4 — declarations, no code** — already inside the N2 scope
  accepted in theme 2 ("guardrail↔hook invariant inventory; source/generated
  boundary + numeric always-loaded caps declared"). This theme only confirms
  their consumers: P1.2 and P1.7.
- **A12 — one architect pass** locks the seven P1.x shapes: the "hook never
  blocks" contract (bounded stdin, BOM normalization, `timeout` in wiring,
  regression tests for the no-op); the invariant canary in `self_ci` +
  doc gardening as the same sweep; the version cross-check in
  `release_check`; `akmon status` **observability only** (its D1 half —
  mutable levels — stays with theme 7); the execution ledger in `_aitna/`
  (one line per completed dispatch; "after compaction trust the ledger and
  `git log`, not recollection"); the shared diagnostic envelope as one
  module; boundary + caps checks consuming the N2 declarations.
- **C40 — implementation**; acceptance: every check fails on a seeded
  violation.
- **P2.3 — `akmon-defer:` semantics** rides A13 (already in its line):
  ceiling **and** trigger mandatory, a canonical TASKS.md ID, the grep
  harvest flags `no-trigger` rot — no parallel ledger.

**Solves:** W8 — the frozen-session class closed before the first incident;
W5 — a reworded rule with a stale hook is caught by the canary; W6 — a
deferred simplification gets a ceiling and a trigger; W7 — versions are
linked; W20 — after compaction there is a source of truth cheaper than
re-dispatch; W22 — every finding shows machine and owner a one-sentence
`fix`; W23 — the token-economy preaching becomes a checkable number.

**Drawbacks:** the INVARIANTS list is itself prose and can rot (the
mitigation is asymmetric: the canary fails *loudly* when a phrase
disappears — the rot is visible, unlike the status quo); the envelope is a
mini-format to maintain across three tools; the caps numbers are borrowed
(wshobson: ≤150 context lines, 8 KB skill), not measured — pick our own and
mark them provisional until C42 data; the ledger helps only if written —
discipline until automated; ten small items risk scattering — hence one A12
lock, not seven.

### Alternatives

1. **Status quo.** The frozen session is not a hypothesis but a live
   upstream incident (#443), and our stdin path is the same kind; every next
   consumer inherits the risk. Rejected.
2. **LLM-based drift checks** (a judge compares prose to code). Pays per run
   what the canary costs once; the deterministic layer exists precisely to
   avoid this. Rejected.
3. **External frameworks** (the pre-commit ecosystem, schema validators). A
   dependency for stdlib-scale work; akmon dev tooling is stdlib-only by
   rule. Rejected.
4. **Code first, no A12 lock.** The shapes (envelope fields, caps numbers,
   canary format) are contracts between three tools and the N2 declarations;
   one cheap lock beats three desynchronized implementations. Rejected as
   ordering; the carriers (self_ci/release_check) absorbed as-is.

### Recommendation and grounds

**Accept as planned: P0.3/P0.4 ride the already-accepted N2; one A12 pass
locks the seven shapes (P1.4 observability-only, D1 stays with theme 7);
C40 lands them with the seeded-violation acceptance; P2.3 in A13 where
already scoped.** Grounds: **(a)** the best risk/benefit in the plan — every
item deterministic, stdlib, zero new dependencies, zero API cost; **(b)** W8
is the only item on the whole route whose failure class has already
materialized upstream (ponytail #443), and our path
(`json.load(sys.stdin)`, unbounded) is identical in kind; **(c)** the
declarations are already inside the accepted N2 scope — the theme adds
nothing to stage 0, only confirms the consumers; **(d)** seeded-violation
acceptance makes the whole theme falsifiable — the §6.0 pilot criterion here
is literally a test.

### Verdict detail

- **Pilot acceptance criterion (§6.0, row 3):** the checks land in
  `self_ci`/`release_check` and fail on seeded violations.
- **Carriers:** N2 (P0.3/P0.4 declarations) → A12 (one lock, seven shapes)
  → C40 (implementation, seeded-violation acceptance); P2.3 → A13 → C41.

## Theme 7 — owner attention & new carriers: P1.4, Phase 4 · W14–W16 · decision D1

**Verdict: ACCEPTED (owner, 2026-07-17), per recommendation — P1.4 as locked
by theme 6 (status must read *actual* state); Phase 4 gates confirmed as
planned (each P4.x enters through its own ADR when its gate opens);
D1 resolved: mutability REJECTED, P4.4 closed with the [pny/codex] 4.1
rationale and a named revisit-if.**

### Essence

Two halves. **First — owner attention**: learning akmon's current state in a
project (version pin, active role, which hooks are actually wired, carrier)
costs a manual investigation — W14; the answer is an `akmon status` command.
**Second — new delivery surface**: three potential mechanisms/carriers
(P4.1 — guardrail injection via SubagentStart; P4.2 — a Claude Code plugin
as a third carrier; P4.3 — MCP as a transport for the standard itself, for
vendors with neither hooks nor pointer support), all **gated behind Phase 3
measurement** per the plan. The last open decision attaches here — **D1:
mutable enforcement levels** (`advise|nudge|enforce|off`): [pny/claude]
proposes them; [pny/codex] objects that mutable intensity makes the active
contract ambiguous. The observability half (status) is uncontested; the
mutable half (P4.4) awaited this verdict.

### As-is (pros / cons)

Verified against the code:

- **W14:** the v0.3.0 CLI is `init / sync / verify / path / version`
  (`init` is a "not implemented yet" stub); there is no `status`. State is
  assembled by hand: the pin from `.akmon.toml`, hook wiring from the
  vendor's settings.json, the active role shown nowhere.
- **W15:** install is BOOTSTRAP.md — a long agent-driven attach (§A with
  ~15 steps, ready prompts) vs ponytail's 2-command plugin install. The
  v0.3.0 packaging is a step in that direction, but attach stays manual.
- **W16:** vendors with neither hooks nor pointer support have no delivery
  channel at all — the matrix tail is unserved.
- **D1:** enforcement levels today are static and implicit: a hook is either
  wired by sync or not; "softness" does not exist.

**Pros of the status quo:** not one premature surface — a plugin without a
version check and an uninstall path is a documented trap ([pny/claude]
§3.3); injection without proven drift is dead surface (theme 2 already fixed
that); the two current carriers (tree + package) are simple; the active
contract is unambiguous — what is wired is what is enforced.

**Cons:** state investigation is an attention tax on every doubt — against
the goal function; install friction limits adoption of the standard; the
matrix tail is unserved; the unresolved D1 keeps P4.4 in limbo.

### Proposed solution (what it solves / drawbacks)

- **P1.4 — `akmon status`, observability only** — already accepted with
  theme 6 (shape locked in A12). One shape requirement: status must read
  the *actual* state (the real settings.json wiring, the real pin), not the
  declared one — otherwise it lies exactly where it should save attention.
- **Phase 4 — confirm the gates, build nothing**: P4.1 only if the N2
  probes reproduce the drift (D2 already resolved that way in theme 2);
  P4.2 (plugin) and P4.3 (MCP) only after Phase 3 measurement and on
  explicit demand, each entering through its own ADR (for the plugin: a
  mandatory uninstall path, and the P1.3 version cross-check becomes
  mandatory).
- **D1 — resolve now: mutability rejected**, P4.4 closed with the
  [pny/codex] 4.1 rationale. The legitimate need behind mutability — "this
  hook annoys/harms" — is served by the measured path: C42 shows harm → the
  hook is fixed or unwired via sync, i.e. a **declared** per-project choice
  visible in `akmon status`, not a runtime knob. Revisit-if: real consumer
  demand for per-project softening that unwiring cannot express.

**Solves:** W14 — cheaply and now; W15/W16 — when measurement and demand
justify them, with no dead surface; D1 closed — the contract stays
unambiguous.

**Drawbacks:** install friction (W15) consciously remains until Phase 4 —
the plan trades adoption speed for proof; Phase 4 behind the Phase 3 gate
may be quarters away; `status` is one more surface that must be kept honest
(mitigation: the same seeded-violation acceptance as theme 6 — a status
that shows what is not there is a failing test); the rejected D1 may return
on real demand — hence the explicit revisit-if.

### Alternatives

1. **Status quo** (no status command). The uncontested half of W14 keeps
   burning attention on every doubt. Rejected.
2. **Phase 4 now, plugin first** (for adoption). Inverts the plan's
   measurement-first spine; a plugin without the P1.3 check and an uninstall
   path is a documented trap. Rejected.
3. **Drop Phase 4 forever.** The matrix tail and install friction stay
   permanent while demand may materialize. Rejected — keep it gated, not
   buried.
4. **D1 — accept mutable levels** ([pny/claude]). The objection is
   structural, not empirical: mutable intensity makes "what is actually
   enforced here" session-dependent — directly against W14's own goal and
   against theme 2's honest delivery contract; no C42 data changes that.
   Rejected.
5. **D1 — park until C42** (like D3). Parking is for decisions awaiting
   *data*; here the objection is principled and the need already has a
   declared-path answer. Rejected in favor of an explicit rejection with
   revisit-if.

### Recommendation and grounds

**Accept: P1.4 as already locked by theme 6 (with the "read actual state"
requirement); confirm the Phase 4 gates as planned (each P4.x enters through
its own ADR when its gate opens); resolve D1 — mutability rejected, P4.4
closed with the [pny/codex] 4.1 rationale and a revisit-if.** Grounds:
**(a)** the theme's split matches D1's own split: the uncontested half
(observability) is already accepted and cheap, the contested half is
rejected on a structural argument that no future data affects — there is
nothing to park; **(b)** unambiguity of the active contract is what themes 2
(honest delivery matrix) and 6 (checkable invariants) already invested in; a
runtime intensity knob works against both; **(c)** gating Phase 4 on
measurement is the plan's spine (concept 1), accepted with themes 1–2 —
building carriers earlier would re-litigate accepted verdicts; **(d)** the
"soften a hook" need gets a legitimate channel (C42 data → fix or unwire,
declared), so rejecting mutability forbids nothing real.

### Verdict detail

- **Pilot acceptance criterion:** for P1.4 — inherits theme 6's acceptance
  (status fails on a seeded divergence between declared and actual state);
  for Phase 4 — criteria arrive with each P4.x ADR when its gate opens; for
  D1 — the closure is recorded in plan §5 with the revisit-if.
- **Carriers:** P1.4 → A12 → C40; P4.1 gate → N2 outcome; P4.2/P4.3 gates →
  Phase 3 measurement + demand, own ADR each; P4.4 → closed (D1).
