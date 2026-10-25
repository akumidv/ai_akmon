# 0021 — The athlos: bounded work, deferred handoff, and its adjudication

- **Status:** Accepted for **D01–D07**. The owner approved *athlos* as the name of the bounded labor
  and the handoff shape, and ruled that **`zone` stays** as the frame word (D04). The owner
  accepted an interim in which the head session launches every worker until the wait-cost probe
  measures a delegating holder (D06). The adjudication surface is a catalog of **viewpoints** — one
  mechanism with several kinds of assignment — with an offered launch (D07). A holder that has
  handed its work on is retired: by policy now, by forced termination after measurement (D05). The
  empty reserves of ADR 0008 §4 stay unbound (§ Consequences). No request is open. Implementation
  has not started, and two carriers this record first assumed are now measured absent
  (§ Consequences).
- **Owner:** akuminov@gmail.com
- **Amends:** [0006/D03](0006-orchestrator-detection-corridor-context-pressure.md#d03--recommended-context-budget-and-pressure-delivery)
  in the advice text of the pressure notice only. The sensor, its budget and its delivery channel stand.
- **References:** [MODEL.md](../../MODEL.md) § capability tiers (the orchestrator row is never
  delegated — and the orchestrator is the judge) · [0004/D01–D04](0004-model-routing-capability-tiers.md)
  (tiers, task-kind matrix, ladder) · [0005](0005-synthesizer-gate-audit-and-role-routing.md) (gate-pack
  audit, the surface the counter-briefs reuse) · [ADR 0008 §4](0008-mythological-naming-aitna-akmon-kyklopes.md)
  (the naming reservoir this record draws on and widens) ·
  [design: the design athlos and its counter-briefs](../design/design-athlos-counter-briefs.md) ·
  [pipelines/tasks.md](../../pipelines/tasks.md) (entry format, the `deferred` status) ·
  [design §12–§13](../design/model-routing.md) (pressure, delegation axes) ·
  [MEASUREMENTS.md](../MEASUREMENTS.md) M68–M71 (hook delivery and crash posture, both vendors) ·
  live tasks [A21](../TASKS.md) (task boundary, two axes), [A24](../TASKS.md) (auditor on designs),
  [A39](../TASKS.md) (local work plan per task), [C29](../TASKS.md) (keeping raw output out of the
  main context), [A46](../TASKS.md) and [A47](../TASKS.md) (the open scope this record leaves to
  them), [N15](../TASKS.md) (the wait-cost and retirement probe) and [N4](../TASKS.md) (whether
  dispatch completion is observable).

## Context

The owner asked for a way to set a batch of work aside and pick it up in another session, for
advice on keeping context short, and for the pressure notice to offer that step *before* it offers
`/compact`. Three measured facts decide the shape, and all three have to be faced rather than
wished away.

**A pre-cost warning does not exist on the routes akmon uses.** `UserPromptSubmit` — the only hook
that fires before the model answers — runs *after* the owner has already submitted the prompt, and
its notice is seen by the owner and never by the model (M69). Every failure path on both vendors is
fail-open: a hook that exits non-zero is reported as failed and the action goes ahead anyway (M70,
M68, M71). So "offer the cheaper exit before the expensive one" cannot be built as an earlier
warning; it can only be built as *what the existing notice says*, plus what the session wrote down
while context was still cheap.

**The task boundary and the fill are separate axes, and 0006/D03 says so.** The sensor knows a share
of a recommended one-task budget and nothing about which task a session carries; A21 keeps task
identity on the explicit-pick axis. A handoff mechanism belongs to neither sensor.

**A bounded labor needs a name that is not a frame and not a doer.** The existing vocabulary carries
the *frame* — a `zone` is a bounded slice of an approved plan, already parsed, labelled and
coverage-tracked — and the *doer*, the `k_*` delegate, a Kyklops. What had no word was the thing
between them: the bounded piece of work itself, which outlives whichever session, and whichever
delegate, is currently carrying it. Continuing one long-lived child to preserve its recall turns that
child into an unbounded session; flattening everything to avoid this trades away the concurrency the
owner needs. The named labor is the third member, not a synonym for either of the other two.

## Decision

1. The handoff unit is a **work package** — one bounded batch a fresh session can carry alone — and
   it is written *during* work, at a labor boundary or before waiting, never by waking a large old
   session to ask for it (**D01**).
2. Deferral leaves a backlog line with status `deferred` and a resume prompt **composed from the
   record's own fields**; the owner opens the next session (**D02**).
3. The pressure notice names the package **before** `/compact`; the sensor's arithmetic is untouched
   (**D03**).
4. An **athlos** is a bounded labor with an acceptance condition, named by the pair (task id, zone).
   It outlives the session and the delegate carrying it; the holder is an assignment, not a tier
   (**D04**).
5. Live handles and write ownership **do not migrate by implication**, and a holder that has written
   its record is retired rather than resumed; a successor verifies, and an unverifiable handle is a
   blocker rather than completed work (**D05**).
6. The head session launches every worker; a holder decomposes and consolidates but does not spawn.
   This is an interim until the wait-cost probe measures the alternative (**D06**).
7. The adjudication surface is one mechanism with a catalog of viewpoints, launched on the owner's
   word or offered above a threshold of the role's own result (**D07**).

## Alternatives considered

- **Warn before the prompt is sent.** No measured owner channel exists before the prompt is in
  flight (M69), and enforcement over an unmeasured route is the exact claim this repository's
  capability lock exists to stop. Kept as a probe, not as a rule.
- **Compact by default at the info level.** Keeps the history that caused the pressure and leaves no
  artifact a fresh session can act on.
- **Naming the labor after its frame, or after its doer.** Both were tried and rejected here: the
  frame word is already loaded (406 live uses, one of them a delegation-ledger column), and the doer
  word is the `k_*` delegate — which a labor outlives. A coined or borrowed third word was rejected
  for the reason [0008](0008-mythological-naming-aitna-akmon-kyklopes.md) gives: names come from the
  locked cluster, by lookup, not invention.
- **A permanent second orchestration tier.** Would put a judge below the session that is already the
  judge; the owner ruled that the **head session is the judge** and the viewpoints are its instruments,
  not a court of appeal. The middle holder's authority is bounded by **D06**.
- **Handoff text in a commit message or in the approved plan.** Couples working state to landed
  history. The alternative — keeping task-local state out of the tracked tree — is what A39 *names*
  as its own rule and what C150 has to build here; neither the ignore rule nor its check is in the
  tree yet (measured, § Consequences), so this bullet argues the shape, not a standing guard.

## Consequences

- **Carriers, when implementation is authorized:** `tools/model_routing/agents.json`
  (`context_pressure.info` / `.warn` text) and `tools/model_routing/routing.py::context_pressure_notice`
  for D03; the deferral helper as a new `tools/` entry point behind `akmon tool`; one shared
  ignore-and-link check for the local root with A39's plan directory. No registry numeric change, so
  no local-config invalidation beyond the notice text itself.
- **The viewpoints are a design-doc surface with an accepted shape.** [D07](#d07--viewpoints-one-mechanism-a-catalog-of-positions-one-control)
  accepts the mechanism, the catalog model and the launch rule; the catalog, the thresholds, the
  cost and the A24 overlap stay in
  [design/design-athlos-counter-briefs.md](../design/design-athlos-counter-briefs.md) and task
  **A46**. Nothing in this record arms an offer: only the explicit launch is live until a pilot sets
  the thresholds.
- **A prose/mechanism gap this record only partly closes.** `MODEL.md` keeps orchestration never
  delegated and [design §13.3](../design/model-routing.md) records a measured delegate with no
  `Task` tool, yet three of the six generated specs carry no tool cap and
  `hooks/vocabulary.json` maps `Task`/`Agent` to the `subagent` capability — so today a *mechanical*
  delegate could nest while the read-only ones cannot. Which way to close it is
  **A47**'s open scope. Under [D06](#d06--the-head-launches-every-worker-interim) the head launches
  every worker, so the prose stands and this record changes no cap; closing the mechanism side (withholding `subagent` from the three
  uncapped specs) is A47's, and a delegating holder (option **B**) would need a block in the 0004
  theme, not here.
- **The empty [ADR 0008 §4](0008-mythological-naming-aitna-akmon-kyklopes.md) reserves stay reserves.**
  0008 reserved some mythological names for future things, and nothing carries them yet; no athlos
  work depends on binding them, and `V1`'s on-disk rename is still open, so binding names now means a
  second migration. Binding `Hephaistos`, `keraunos`, `sphyra` and `physa` would be a naming sweep
  across shipped docs and generated surfaces, against an always-loaded chain that was measured at
  **320/320 lines** (cap since raised, ADR 0012 D-CAP). One note for whoever later wants a personal
  name for a brief: 0008 already assigns Brontes / Steropes / Arges to **smith tiers**, so spending
  them on brief roles would give one name two owners — which is also why the viewpoints are named by
  what they do (`advocate`, `critic`), not by a reserve name.
- **Both implementations move together.** ADR 0020 binds Python and JavaScript to one conformance
  corpus: `js/tools/model_routing/*` and the corpus scenarios change in the same step as the Python
  side. A divergence is registered, never shipped silently.
- **Consumer surface — measured impossible when written, and the carrier is unnamed.** This record first
  promised one always-on pointer in the generated instruction block. It could not be kept then: the
  shipped always-loaded chain sat **exactly on its cap** — `meta/checks/always_loaded.py` reported
  `akmon-shipped: lines=320/320 bytes=20886/21000`, and C56 makes an overage a `self_ci` **error** — so
  one more line broke akmon's own CI. The owner has since raised the cap (ADR 0012, amendment D-CAP),
  so room now exists; whether a pointer is worth a line is no longer blocked by it. The generator of that block was also not located in
  `bin/sync.py` or `src/akmon/_init.py`, which only *checks* the surface. Delivery is therefore **not**
  an always-on line: the notice and the `akmon tool` helper carry the mechanism, and any pointer waits
  on the reduction work of C60 or on an owner raise of the cap — a decision of its own, not a detail
  this record may spend.
- **Untouched:** 0006/D03's budget, ratios and per-episode throttle; A21's two axes; C29's prevention
  axis; the `zone` label grammar and the delegation-ledger column that already carries it; D2 and D5.
- **No savings are claimed here.** No token figure, ratio or achievable reduction is asserted by this
  decision; a package written early is a recoverability and quality claim first, and a cost claim
  only once measured on a comparable run. Two extra reasoner-tier briefs are a **added** cost, and
  they buy quality, not speed.

## Addressable accepted decision blocks

### D01 — The work package and when it is written

`Decision-ID: ADR-0021/D01`

*Superseded in part by [ADR-0022/D01](0022-local-layer-index-and-plans.md#d01--the-local-layer-and-the-raw-material-home): the package record is `<DEV>/local/handoff/<id>-<name>/HANDOFF.md`, not `local/packages/<task-id>/`; the ignore rule and the guard are C155 and C156, not one C150 step.*

The unit of handoff is a **work package**: one bounded batch a fresh session can take on alone, with
its own resume record at `<AITNA_ROOT>/local/packages/<task-id>/HANDOFF.md` — under the local root
A39 names, beside the plan it links and never copies. The batch's raw material sits in the same
directory; nothing in it is tracked. **The keeping-out is C150's to build, not a standing fact:** the
ignore rule and the tracked-link check are absent from the tree as measured (`.gitignore` and
`src/akmon/init.json` name no `local/` path, and no code reads one), so a package written today would
surface as untracked noise in the owner's `git status`. C150 therefore ships the directory contract
and its guard in one step, never the record alone.

The record is written while context is cheap: at an athlos boundary, at completion, or before waiting
on an owner answer or an external result. It is never produced by waking a large session to ask for
a handoff — that request pays for the history it is trying to escape. Its fields are fixed: goal and
acceptance; approved scope and open questions; repositories, branches, revisions and owned
uncommitted paths; checks run and their outcome; what remains unverified; next action; the resume
prompt. Facts and evidence, never transcript, logs, secrets or customer payloads.

Reconsider when a fresh session still has to read the old conversation to find its next action: that
is a falsification of the field set, not a reason to write a longer record.

### D02 — Backlog line and composed resume prompt

`Decision-ID: ADR-0021/D02`

*Superseded in part by [ADR-0022/D03](0022-local-layer-index-and-plans.md#d03--the-local-index-and-keys): the `deferred` line is appended to the local index, not to the project backlog.*

Deferring appends **one** line to the project backlog in the
[backlog format](../../pipelines/tasks.md) with status `deferred` — the entry is the index, the
package is the detail, and the detail link points at the record. A short multi-line note is not a
substitute for the package.

The resume prompt is emitted from the record's own fields by the tool that writes it, so it cannot
drift from the state it describes, and it names the paths to read rather than summarizing the
conversation. The owner opens the next session: an assistant clears no context of its own, takes no
runtime handle on the owner's behalf, and does not claim a transfer it has not verified.

### D03 — The pressure notice names the package before `/compact`

`Decision-ID: ADR-0021/D03`

Amends the advice text of [ADR-0006/D03](0006-orchestrator-detection-corridor-context-pressure.md#d03--recommended-context-budget-and-pressure-delivery)
and nothing else. Both levels name the order **defer the package → `/compact`**, with `/new` still
the new-task path at the warn level. The sensor, the recommended one-task budget, the ratios, the
per-episode throttle and owner-only delivery as `systemMessage` stand exactly as accepted; no new
event, no new channel, and no claim to warn before the owner's prompt is already in flight.

A package written earlier makes the notice a reminder of a step already taken rather than a rescue
attempt at the moment of pressure. That is the whole of the mechanism — the value is in the timing
of D01, not in a louder warning.

### D04 — An athlos is the labor, not its frame and not its doer

`Decision-ID: ADR-0021/D04`

An **athlos** (ἆθλον, pl. *aethla*) is one bounded labor of an approved plan: a piece of work with
its own acceptance condition, named by the pair (task id, zone) — the zone names where the work
lands, the athlos names the work itself. It is carried by a session and executed by `k_*` delegates,
and it outlives both: a completed agent id is not a fresh context, and a live one is not the labor
either.

Holding an athlos is an **assignment**, not a capability tier and not a sixth role: the holder works
under the role the zone belongs to and routes execution through the existing matrix. Today the parent
launches that athlos's worker assignments, because `MODEL.md` keeps orchestration undelegated.
**Whether a holder may delegate is bounded by [D06](#d06--the-head-launches-every-worker-interim):**
nothing in this block grants it — an accepted identity is not an accepted authority. Where nesting
stays unavailable the contract is unchanged and only the launcher differs, so no athlos is written
to assume a holder that cannot exist yet.

Continuing a long-lived holder to preserve its recall is not a property of an athlos; it is the
failure this block names. Independent athla rotate independently: a dependency blocks dependent work
only, and lifecycle discipline never becomes a global serialization barrier.

#### Why the frame word stays

The owner ruled that `zone` stays; the labor and the frame are now two words, which is what the
original complaint asked for. The measurement that settled it: `zone` is not prose but mechanism —
`routing.parse_zone`, the `[zone:LABEL]` marker parsed at log-write time into a **column of the
delegation ledger**, `coverage_map.py` grouping on it, the convention restated in every generated
fan-out brief, and the same spelling carried by the JavaScript twin and the conformance corpus (406
live whole-word uses). A rename is a data-format change shipped to every consumer, not a sweep.
`wave` was rejected on measurement too: 44 live uses already mean *a batch of tasks in a plan*
(`stage1-hardening-contracts:28,996`, the A11 walkthrough) — a different thing in the same document
set.

### D05 — Handles and ownership do not migrate by implication; a handed-off holder is retired

`Decision-ID: ADR-0021/D05`

A successor session treats a predecessor's live agents and processes as **unverified**: it re-reads
the record, checks the checkout against it, and acts only on what it can observe. Before a session is
replaced, its writers are accounted for — nested workers included, since replacing a holder does not
hand over its children.

**A holder that has written the record handing its work on is retired, not resumed.** A cold agent
that is continued pays for its whole context again, so a fresh session started from the record is the
cheaper successor and the safer one: nothing it relies on lives only in the old holder. Retirement has
two tiers, and only the first is promised:

- **Policy, now.** The successor starts work only after the source holder's stop is observed and its
  children are accounted for; otherwise it reports a blocker. Where a vendor offers no observable
  stop, the successor says so instead of assuming one.
- **Enforcement, after measurement.** Forcibly ending the source holder and its children is built
  only on a mechanism the wait-cost and retirement probe ([N15](../TASKS.md), with [N4](../TASKS.md))
  has measured per vendor. No such mechanism is claimed here.

Unresolved write ownership blocks a second writer. A handle that cannot be reconnected is reported as
a blocker and never recorded as completed work, and no replacement authorizes switching branches,
cleaning a checkout or stopping an active writer to make the handoff convenient.

#### Alternatives considered for this block

Trusting a predecessor's live handle by implication was replaced by retirement of the holder that
handed work on: restarting an agent is expensive and a new session is cheaper, so the handing-off
holder is ended rather than carried over. The retirement options:

| | Option | What it costs |
|---|---|---|
| **A** | Retire by policy — the successor does not start until the source's stop is observed, else a blocker | Buildable now; no force, only a refusal to proceed |
| **B** | Forced termination by a mechanism | Needs a per-vendor stop and a way to invoke it; unmeasured (N4, N15) |
| **C** | A now, B after the probe (accepted) | Two steps; no capability claimed before it is measured |

### D06 — The head launches every worker (interim)

`Decision-ID: ADR-0021/D06`

Option **A** of the alternatives below is accepted. The holder of an athlos decomposes it, lists the worker
assignments and consolidates what comes back; the head session is the only launcher, so the
never-delegated row of `MODEL.md` stands as written and this block adds no authority. Parallelism is
kept: the head launches the listed workers concurrently.

Two costs are accepted rather than hidden. A batch costs the head one more round-trip. And a zone has
**no living lead**: between batches its memory is the athlos record plus a short, fresh holder call
over the returned results — a document and a call, not a resident agent.

This is an interim, not a verdict against option **B** (a holder that spawns, capped). B stays a
candidate until [N15](../TASKS.md) measures what a holder pays to wait for its workers and resume;
adopting it would need a block in the 0004 theme, a new `task_kind` row, and caps and corpus moved in
both implementations (ADR 0020). One thing this block does **not** do: it does not remove
`subagent` from the three uncapped specs, so the mechanism side of the prose/caps gap stays open under
[A47](../TASKS.md) — the option table below says "no cap change", and that holds only for this
decision, not for A47.

Reconsider when N15 shows a waiting holder re-reads its context at no more than the cost of the second
fresh call, and the spawn right and the completion signal are visible on the vendors in use.

#### Alternatives considered for this block

The owner finds **B** the more interesting option but fears that a holder waiting for its workers
loses its cache and re-reads its context at full price, so B waits on the [N15](../TASKS.md)
measurement. The owner ruled the middle holder **necessary** (parallelism — sequential zone work is
often very slow) and ruled that the **head session is the judge**; what was open is only *who presses
the launch button*.

Measured starting point, which makes "just forbid it" dearer than it looks: three of the six
generated specs (`k_mechanic`, `k_validator`, `k_implementer`) carry `tools: null` = **all tools**,
and `hooks/vocabulary.json:13-14` maps `Task`/`Agent` to the `subagent` capability — so a mechanical
worker can already nest today while `k_auditor` and `k_reasoner` cannot. The gap runs in **both**
directions.

| | Option | What it means | What it costs |
|---|---|---|---|
| **A** | Head launches everything (accepted) | `MODEL.md` stands as written; the holder thinks, lists and consolidates, the parent spawns | No new authority, **no registry or cap change**, no conformance move. One extra round-trip per batch |
| **B** | Holder spawns, capped | A named delegating position; `subagent` granted to it and **withheld** from the three mechanical specs | An ADR-0004-theme amendment to the never-delegated row; a new `task_kind` row (the registry hash moves, so every local config re-inits once); caps rewritten in both implementations plus their corpus |
| **C** | Holder spawns, uncapped | Status quo formalized | Cheapest to write, and it leaves a *validator* able to spawn while an *auditor* cannot — the inversion this record exists to remove. Not recommended |
| **D** | Deferred | Decide nothing; prose keeps contradicting caps | Free today, expensive later: the next implementation task reads whichever of prose or caps it opened first |

**Why A — and it is not the timid choice.** Under A the holder still does the part that genuinely
needs a fresh context — decompose its own athlos, route, consolidate, batch questions upward — and
the parent performs the one mechanical act it is already the sole holder of. Parallelism survives
because the parent launches the listed workers concurrently; what A gives up is a latency of one
round-trip, not concurrency. A also leaves D2, D5 and the caps untouched, so it is the only option
that ships without a consumer-visible change. B becomes right when a measured case shows the
round-trip is the bottleneck — no such measurement exists in the tree.

### D07 — Viewpoints: one mechanism, a catalog of positions, one control

`Decision-ID: ADR-0021/D07`

The adjudication surface is **not a fixed pair**. A **viewpoint** is a position a fresh-context delegate takes over one gate-pack: advocate and
critic first, then further positions as the catalog grows — for example a review slice (reuse of
other libraries, security), a client that works strictly in sequence, one that interrupts and
restarts, an attacker. A viewpoint starts as a prompt in a catalog; whether it later becomes a pipeline
or a subagent is not decided here.

The mechanism and its control are the same for every viewpoint: one pack, positions returned with
`file:line` evidence, none of them deciding, the head judging (D04 stands). Viewpoints over one pack
are independent of each other, because contradicting views are the point; the pack carries the
project's evidence map by construction (the A32-E1 defect, M98).

**Launch.** The owner can always name an athlos and a set of viewpoints. Beyond that the offer is
driven by the *result of the role's own work*, not by a structural anchor (that route measured silent,
C98): for `architect`, weak or few arguments, or many options that need pruning; for `review`, the
same over findings; for `engineer`, never. The offer is made to the owner before any spend, and
viewpoints are launched by the head under D06. A structural trigger is a later option, after the owner
has reviewed practice.

**Not decided here, by design:** the thresholds that make arguments "weak" or options "many" —
a pilot sets them against the design doc's falsifier — and the viewpoint catalog itself. Until the
pilot, only the explicit launch is live.

#### Alternatives considered for this block

A fixed advocate/critic pair with a trigger was the earlier shape; it was replaced by the catalog
described above. Its pilot-first reasoning carries over: A32-E1 put three fresh-context auditors over ~200
scored exchanges and **none met its thresholds** — recall 0.28 / 0.58 / 0.23, false flags
0.22 / 0.44 / 0.22, with the auditors lacking the project's evidence map (M98). Fresh-context
viewpoints inherit that defect by construction, which is why the pack carries the evidence map and a
viewpoint earns a standing rule only after beating the no-viewpoint baseline on this repository's own
design athloi.

**Launch.** The explicit launch (A) exists under every option. B is accepted now; C is a possible
later step after practice is reviewed.

| | Option | What it costs |
|---|---|---|
| **A** | Explicit only — the owner names the athlos and the viewpoints | Nothing to build; never offered, so it is used only when the owner remembers |
| **B** | Offered when the role's own result crosses a threshold (accepted) | Needs thresholds that nothing yet measures; a pilot sets them |
| **C** | Structural trigger | The anchor route measured silent here (C98); a possible later step after practice is reviewed |

**Membership.** One mechanism with a catalog was accepted.

| | Option | What it costs |
|---|---|---|
| **A** | One mechanism, one control, a catalog of viewpoints collected from the start (accepted) | A `task_kind` row for a viewpoint, a viewpoint field on `gate_pack` (both implementations, ADR 0020), and a catalog that must be curated |
| **B** | Fixed advocate and critic, others later | Cheapest; builds the mechanism around a pair that the owner expects to outgrow |

**Idea sources.** Testing a decision may include comparing it with alternatives; the kinds of
assignment are not limited to two.

| | Option | What it costs |
|---|---|---|
| **A** | One mechanism, several kinds of assignment: test a decision (including against alternatives), and generate options from a source (the product's own history, competing products, public write-ups, a filtered brainstorm) (accepted) | The catalog holds assignments of more than one kind; generation needs a filter before its output reaches the owner |
| **B** | Testing only; idea gathering stays a separate procedure | Two mechanisms and two controls, against the owner's wish for one; the sources are described only in [the alternatives README](../reviews/alternatives/README.md) |

**Name.** The position is called a *viewpoint*; the working word was *stance*. A plain word was
chosen because the position is named in every sentence, in flags and in the catalog, and it has to fit
testing and generating alike. The word is renamed in the athlos documents only.
