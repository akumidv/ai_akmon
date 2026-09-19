# A22 — D2 cutover reference map and thematic boundaries

## Status and resume point

Implementation map for [ADR 0016](../decisions/0016-decision-records-and-owner-acceptance.md) and
[C94](../TASKS.md). It continues the [legacy migration](d2-legacy-migration.md) by separating references
that enforce the current D2 workflow from references that merely preserve decision
or evidence provenance. It also stress-tests actual thematic boundaries rather than
assuming each broad preliminary routing group should become one file.

The repository has parallel owner-controlled staged work; file counts describe the
inspected working tree and default ripgrep ignore rules unless stated otherwise.

Sections C1–C5 below preserve the **pre-cutover inventory** used to implement C94.
Their present-tense descriptions name the inspected baseline, not the repository's
post-cutover operative contract; the outcome is recorded at the end of this note.

**Accepted cutover:** use a compatibility tombstone at the old
ledger path, a frozen archive, and unique legacy aliases on current destination
owners. Replace the D2 workflow atomically, but retain old `D2-N` text in dated
evidence and history. Use several cohesive thematic ADRs, not one ADR per old row and
not one giant ADR per broad subsystem label.

**Execution rule:** validate every canonical alias and active dependency after the migration.
Old Approved/Verified rows do not receive another approval cycle; unresolved evidence remains
task-owned. Consumer-project migration remains outside C94.

## What the reference inventory establishes

A fixed-string source-tree search currently finds concrete `D2-N` references in
68 files: 41 Markdown and 27 non-Markdown files. Excluding the legacy migration note
itself leaves 40 Markdown files. A wider source-tree search for generic `D2`,
`D2_LEDGER` or `d2_ledger` reaches 87 files. These are scope counts, not 68 or 87
independent migration obligations: one historical report and one runtime hook have
very different cutover meaning.

The ignored installed tree under `.venv/lib/python3.11/site-packages/akmon/_tree/`
adds 25 Markdown and 21 non-Markdown copies with concrete IDs. Those are derived
delivery artifacts. They must be refreshed by package installation/build verification,
never edited or counted as additional source authorities.

The inventory therefore needs two axes:

1. **Does this reference control current behaviour or state?** If yes, it must be
   rewritten or retired as part of the atomic cutover.
2. **Does this reference preserve provenance?** If yes, it should usually retain the
   original ID and gain resolvable legacy navigation, not be rewritten as though the
   historical document had always used the new scheme.

## Cutover classes

### C1 — operative acceptance and workflow authority

These surfaces prescribe what the agent or owner must do. They cannot coexist
indefinitely with a contradictory replacement:

- `AGENTS.md`, `guardrails/_common.md`, `roles/architect.md` and
  `roles/engineer.md` express owner verification of architecture, math and data-shape
  changes;
- `pipelines/pre-commit.md` and `pipelines/tasks.md` prescribe the D2 ledger/check
  or name a D2-style record as the work carrier;
- ADR 0007 and `meta/design/d2-ledger.md` define the ledger, `add → approve → verify`,
  the manually copied commit hash and the warn-first path check;
- `meta/decisions/README.md` describes both the D2 lifecycle and ADR status rules
  that depend on it;
- `meta/D2_LEDGER.md` is the current acceptance/status authority.

The replacement must preserve meaningful owner control while changing its unit.
The proposed rule is: the owner accepts a clearly bounded consequential decision;
implementation then proves conformance to that decision in its task and evidence.
A material implementation delta returns to design and needs a new or replacing
decision. Merely landing unchanged implementation does not request the same
substantive acceptance again.

This means removing D2 does **not** mean removing the `Owner-verify` principle. The
principle changes from “move every sensitive row through a second status lifecycle”
to “expose and explicitly accept consequential decision scope, and expose later
material deltas.” Exact operative wording remains part of the future implementation
design.

### C2 — D2 runtime and tooling machinery

These surfaces implement the old workflow and are the highest-risk cutover set:

- `tools/d2_ledger/d2_ledger.py` and `meta/tests/test_d2_ledger.py` own the ledger
  parser, IDs, lifecycle commands and check behaviour;
- `hooks/d2-ledger-reminder.py`, `hooks/hook_core.py`, `hooks/codex-hook.py` and
  their tests own the sensitive-path reminder, pending/approved counts and session
  status;
- `hooks/model-routing.py` appends the D2 count to routing status;
- `bin/sync.py` generates D2 hook wiring, while `hooks/README.md` documents it;
- `src/akmon/_init.py` emits D2 into a new consumer's root `AGENTS.md`, while
  `BOOTSTRAP.md` explains why that directive must be present at session start;
- `bin/verify.py`, `meta/self_ci.py` and their fixtures recognize D2 as an always-on
  directive or contract marker;
- consumer configuration uses `[d2_ledger] sensitive_paths` and the
  `_aitna/D2_LEDGER.md` path.

This is not a comment-only migration. Retiring the ledger while leaving the reminder,
counter, generated wiring or verifier expectations alive would create a permanently
false warning or a broken consumer contract. Conversely, deleting all sensitive-path
machinery would also be an automatic design decision: a path advisory may still be
useful if it asks whether an accepted design is being changed, rather than demanding
a new ledger row. The replacement must choose and test that behaviour explicitly.

### C3 — current decision, task and evidence dependencies

These references do not necessarily implement D2, but some use a D2 state as a live
prerequisite. They need semantic rerouting rather than global substitution:

- `meta/TASKS.md` contains active gates and copied D2 states;
- ADRs 0004, 0005, 0006, 0012, 0013 and 0014 use D2 rows as operative decision or
  readiness owners;
- `meta/design/model-routing.md`, `meta/design/codex-runtime-contract.md`,
  `meta/design/stage1-hardening-contracts.md`, the code-rules design and the update
  design contain current owner/gate wrappers;
- current evidence reports for F4/F6 contain live D2-23/D2-49 prerequisites.

Each live dependency must resolve to exactly one of three things:

- an accepted decision block;
- a task state or dependency;
- a versioned evidence condition.

No document should continue to ask whether an already accepted decision has landed.
Likewise, an accepted decision block must not claim that unfinished code or missing
measurement now exists.

### C4 — implementation provenance and regression labels

Many code comments and tests cite a D2 ID because it is the shortest route to the
rationale. These references are not acceptance state. Examples include D2-46 in the
delegation nudge, D2-45 in adapter crash behaviour, D2-39 in record-reader tests and
D2-29/D2-47 in the expired-exemption regression.

At cutover, current implementation comments should point to stable accepted blocks
while retaining a legacy alias where useful. Tests must preserve the actual property:
an expired exemption stays expired, a partial replacement stays partial, and measured
literal limits do not broaden. Synthetic `D2-1`/`D2-99` fixture strings remain valid
only if the old parser is deliberately retained as a compatibility surface; they do
not become new decision records.

`hooks/hook_core.py` is the most concentrated risk: it contains current semantics
from D2-10, D2-17, D2-19, D2-21, D2-26, D2-45 and D2-46 as well as the generic D2
reminder/counter implementation. It must be migrated clause by clause, not assigned
to one umbrella ADR and mechanically relabelled.

Existing consumer `AGENTS.md` content is hand-owned: D2-36 explicitly prevents
realign from rewriting it wholesale. Updating the source initializer therefore fixes
new attachments but does not migrate existing consumers. The eventual release needs
an explicit, owner-visible instruction/change notice for replacing the old directive;
silently regenerating the root file is not an available migration mechanism.

### C5 — dated evidence, archive and research

`CHANGELOG.md`, `meta/TASKS_ARCHIVE.md`, dated reviews, measurement rows, session-cycle
analysis and alternatives research are historical records. Their original D2 IDs and
then-current states are evidence. Bulk replacement would falsify that evidence and
make older conclusions appear to have been written under a later process.

Keep their text. Make each legacy ID discoverable through the compatibility layer,
and change only a genuinely live wrapper or broken link. Installed package copies
inherit the eventual source release and are not edited in place.

## Compatibility form for old links and grep

The current best candidate has three pieces:

1. Move the exact old ledger to a clearly frozen archive after the migration snapshot
   is settled. It remains historical evidence and accepts no new rows or transitions.
2. Leave a short tombstone at `meta/D2_LEDGER.md`. Existing file links still resolve,
   but the page cannot plausibly be mistaken for a current Pending/Approved queue.
3. Give every migrated ID one canonical marker, for example
   `Legacy-ID: D2-43`, on its current decision/task/evidence destination. A check makes
   the marker unique and resolvable. The tombstone explains the fixed-string lookup.

The marker is navigation, not another status registry. An accepted row normally
resolves to its accepted decision block; a Pending evidence row such as D2-49 resolves
to the living task/evidence owner, not an accepted ADR. If one old row decomposes into
several destinations, its one canonical marker names the primary semantic owner and
links the secondary obligations. Do not copy a status onto every destination.

This form is preferable to leaving the full ledger at its old path because a frozen
table headed Pending/Approved/Verified still looks operative. It is preferable to a
manually maintained second mapping table because unique aliases can be checked where
the meaning now lives. A generated navigation index remains an option only if direct
aliases prove insufficient for multi-owner rows.

The exact archive path, marker syntax and validation command remain proposed. Their
selection belongs to the replacement contract, not this inventory pass.

## Candidate thematic ADR boundaries

The preliminary legacy routing used large subsystem groups only to prove coverage.
The groups below are reading and change-coherence boundaries. A block is the unit of
acceptance and replacement; a file is the unit of nearby context. Neither should be
derived from the number of old rows.

### Packaging is at least two topics

#### Topic P — carrier, runtime and declaration semantics

Candidate blocks:

| Block | Legacy material | Boundary |
| --- | --- | --- |
| Supported carriers and source ownership | D2-12, D2-25, surviving D2-35 clauses | Which carriers exist, what is source versus materialization, package as dev dependency |
| Executable/runtime surface by carrier | D2-13 clauses, D2-26, D2-33, D2-35 | What executes from the package or mounted tree and what is deliberately not copied |
| Shared root and record-reader ownership | surviving D2-26, D2-32, D2-33, D2-39 | Project-root/runtime-root ownership and strict versus lenient record reading |
| Supported Python and manifest semantics | D2-34, D2-43, relevant D2-13 clauses | Runtime floor, TOML pin parsing and the user-visible `unreadable` outcome |

D2-35 only replaces runtime-root/materialization premises. It must not erase the
shared reader/utility ownership in D2-26/D2-33. D2-32 likewise contains accepted
notice/silence behaviour after two pre-acceptance branches were replaced.

#### Topic L — consumer alignment, release and update lifecycle

Candidate blocks:

| Block | Legacy material | Boundary |
| --- | --- | --- |
| Version and release consistency | D2-31, relevant D2-51 clauses | Owners of version order, final-release selection and changelog/tag consistency |
| Attach, sync and realign boundaries | D2-36, surviving D2-25 clauses | What each operation may align, own or deliberately leave to the consumer |
| Explicit update and rollback | D2-51 | Target selection, per-carrier operation, rollback disclosure and never-commit rule |

This is a better split than one ever-growing “packaging” ADR: carrier/runtime choices
and update/release workflow evolve for different reasons and have different tests.
They retain explicit cross-links because `update` invokes the carrier-specific
realignment contract.

### Model routing is several coupled topics, not one file

| Topic/block cluster | Legacy material | Important edge |
| --- | --- | --- |
| Provider/model selection and diversity | D2-1, D2-5, relevant D2-6 | Separate declared binding from evidence that a vendor/model route actually exists |
| Gate pack, audit and coverage | D2-2, D2-3, D2-6, D2-7 | D2-3 accepts architecture but does not prove the C17 implementation complete |
| Role/orchestrator detection and delivery | D2-4, D2-37 | Codex delivery remains task/evidence-limited; do not infer parity |
| Delegation nudge and unattended posture | D2-8, D2-9, D2-10, D2-11, D2-46 | D2-46 replaces counts, thresholds and read ask eligibility/consumption; D2-11 still escalates an ask that is actually formed |
| Context budget and pressure delivery | D2-38, D2-42 | D2-42 replaces bands/delivery/reset, while the recommended-budget premise survives |
| Transcript retrieval strategy | D2-50 | Performance implementation supports routing but does not redefine selection policy |

D2-27/D2-40 belong primarily to vendor host-trust diagnostics, not merely because
their result is printed by model-routing status. D2-15/D2-16 belong to agent identity
and overlay compatibility. Keeping these out of a generic routing file prevents
physical call sites from dictating decision context.

### Hook work separates safety protocol from vendor integration

#### Topic H — hook survivability and bounded execution

| Block | Legacy material | Non-decision owner kept separate |
| --- | --- | --- |
| Crash-open protocol and fail-closed gate | D2-20 F3, D2-45 | C87 implementation and versioned vendor observations |
| Bounded input-envelope protocol | D2-20 F6 | D2-23 concrete caps/evidence and C52 implementation |
| Timeout derivation protocol | D2-20 F4/F5 | D2-49/N6 concrete timings and literals |
| Capability exemption expiry | D2-29, D2-47 | C90 regression evidence; old exemption remains visibly expired |

D2-23 and D2-49 do not become peer accepted ADR blocks merely because their rows
exist. D2-23's accepted envelope results route to evidence/readiness; D2-49 remains
open evidence work. The durable protocol stays in the accepted survivability blocks.

#### Topic V — vendor hook boundary and observable capability

Candidate blocks cover target/path normalization (D2-17), measured versus guessed
payload keys (D2-18), route/matcher ownership (D2-19), event-scoped diagnostics and
temporary fail-quiet behaviour (D2-21/D2-22), host-trust query behaviour
(D2-27/D2-40), shared findings vocabulary (D2-28), and command-prefix/capability
ownership (D2-30). D2-15/D2-16 can remain in the existing naming/agent-identity topic
with a cross-link to vendor delivery.

This split keeps “what must happen when a hook crashes or exceeds its envelope” near
one another, while placing “what payload/route a particular harness actually exposes”
with versioned capability boundaries. Measurements may amend the latter without
reopening the safety objective unless they force a different trade-off.

## Row-by-row candidate destination

This table validates coverage against the more precise blocks above. “Primary” means
the canonical legacy lookup target, not that the old row can be copied whole. The
last column names a second owner or a qualification that must remain visible.

| Legacy ID | Primary destination | Secondary route or qualification |
| --- | --- | --- |
| D2-1 | Routing — provider/model selection and diversity | Implementation/evidence remain in C16 and routing tests |
| D2-2 | Routing — gate pack, audit and coverage | Gate-pack carriers remain implementation evidence |
| D2-3 | Routing — gate pack, audit and coverage | C17/C76 implementation qualification; legacy Verified is not task completion |
| D2-4 | Routing — role/orchestrator detection | Preserve the measured payload limitation |
| D2-5 | Routing — provider/model selection and diversity | Declared binding provenance is distinct from actual vendor capability |
| D2-6 | Routing — gate pack, audit and coverage | Cross-cutting kind vocabulary may be referenced by role routing |
| D2-7 | Routing — gate/auditor identity amendment | Preserve rename history; no active migration task implied |
| D2-8 | Routing — delegation nudge purpose and baseline | Counts, thresholds and the no-tool-exemption ask rule are replaced by D2-46 |
| D2-9 | Routing — delegation nudge applicability | Subagent early return remains current |
| D2-10 | Routing — delegation nudge historical gap | D2-11 owns the current unattended posture |
| D2-11 | Routing — delegation nudge unattended posture | Evidence remains version-scoped in capabilities/measurements |
| D2-12 | Packaging P — supported carriers/source ownership | Python floor replaced by D2-34; execution premises amended by D2-35 |
| D2-13 | Packaging P — executable/runtime surface | Split direct-agent guidance and capability clauses to their current contract owners |
| D2-14 | Existing ADR 0010 verdict set | Preserve theme-specific follow-up/measurement work; no new umbrella approval |
| D2-15 | Agent identity — cross-vendor notation | Existing ADR 0011 is the natural owner |
| D2-16 | Agent identity — overlay key compatibility | D2-22 owns temporary warning delivery |
| D2-17 | Vendor V — target/path normalization | Advisory classification, not containment |
| D2-18 | Vendor V — measured payload and unknown-key handling | Guessed keys remain explicitly unmeasured |
| D2-19 | Vendor V — route/matcher ownership and diagnostics | Keep event routing separate from path inference |
| D2-20 | Existing ADR 0012/0013 accepted block set | One unique legacy acceptance-scope marker must link both themes; concrete evidence excluded |
| D2-21 | Vendor V — event-scoped diagnostic behaviour | Temporary/follow-up clauses stay task-owned |
| D2-22 | Agent identity — overlay warning delivery | Explicit expiry on C36(a); not a permanent routing rule |
| D2-23 | F4/F6 evidence-readiness owner | Link accepted protocol in Topic H and N6/C52 work; do not claim F5 |
| D2-24 | Superseded ADR 0007 lifecycle history | No current decision block beyond the accepted replacement contract |
| D2-25 | Packaging P carrier boundary | Split attach/release residuals to lifecycle Topic L |
| D2-26 | Packaging P runtime/root/reader ownership | Runtime-root premise partly replaced by D2-35 |
| D2-27 | Vendor V — Codex host-trust diagnostic | C70 task and newer-version evidence limitation remain open |
| D2-28 | Vendor V — stable findings contract | Existing ADR 0012 F1/F2 owner; C51 is historical implementation |
| D2-29 | Hook H — expired crash-posture exemption | D2-47 must be visible from every lookup |
| D2-30 | Routing — second-opinion command-prefix ownership | Vendor/config validation is a cross-link, not the primary theme |
| D2-31 | Lifecycle L — version and release consistency | D2-51 reuses version-order/final-release semantics without replacing the block |
| D2-32 | Packaging P — shared root ownership | Preserve notice/silence distinction after pre-acceptance branches were replaced |
| D2-33 | Packaging P — shared utility/runtime ownership | Package materialization premise partly replaced by D2-35 |
| D2-34 | Packaging P — supported Python floor | Explicitly replaces only the older floor clause |
| D2-35 | Packaging P — executable/runtime surface by carrier | Link every partial supersession in D2-12/13/26/33 |
| D2-36 | Lifecycle L — attach, sync and realign boundaries | Mounted-mode and hand-owned artifact limits remain visible |
| D2-37 | Routing — role/orchestrator detection and delivery | D2-42 changes context-pressure delivery only; Codex work remains separate |
| D2-38 | Routing — context-budget premise/history | Bands, delivery and reset clauses replaced by D2-42 |
| D2-39 | Packaging P — shared record-reader ownership | Strict legacy-ledger reader may disappear only with the D2 tool |
| D2-40 | Vendor V — Codex host-trust diagnostic details | Supplements D2-27; does not close C70 by status inference |
| D2-41 | Skills delivery and authoring topic | Preserve consumer-breaking metadata migration and validator limits |
| D2-42 | Routing — current context budget/pressure delivery | A21 task boundaries and C81 Codex delivery remain separate |
| D2-43 | Packaging P — manifest and pin-result semantics | C84 implementation/test evidence remains in the task archive |
| D2-44 | Mission and resource-economics topic | A22/C86 interaction protocol remains unaccepted work |
| D2-45 | Hook H — crash visibility amendment | C87 implementation and unmeasured Claude SessionStart visibility stay separate |
| D2-46 | Routing — current delegation weights/grace/thresholds/read handling | Amends D2-8; D2-11 still governs an ask that survives tool eligibility |
| D2-47 | Hook H — exemption expiry/current crash posture | Capability regression evidence remains version-scoped |
| D2-48 | Code rules/checks thematic block set | One acceptance scope may link multiple blocks; C89/C91 work remains separate |
| D2-49 | N6/F5 open evidence owner | Pending stays in task/design/evidence, never an accepted ADR block |
| D2-50 | Routing — transcript retrieval strategy | C93 implementation and N6 baseline dependency remain task/evidence state |
| D2-51 | Lifecycle L — update and rollback | C92/live-consumer verification remain task/evidence state |

This assignment covers D2-1 through D2-51 exactly once as primary lookup targets.
It intentionally changes the preliminary routing for D2-30: the durable choice is
ownership of the second-opinion command prefix, so routing is primary and vendor
validation is secondary. It also exposes D2-13, D2-20, D2-25 and D2-48 as true
partition cases rather than forcing their whole rows into one block.

## Cross-topic migration tests

The thematic form is acceptable only if these cases stay recoverable:

- a grep for D2-35 shows exactly which D2-12/13/26/33 premises it replaced and which
  ownership decisions survived;
- a grep for D2-46 reaches both the current nudge thresholds and the still-operative
  unattended ask-to-deny rule it did not replace;
- a grep for D2-29 cannot expose the exemption without also exposing D2-47's expiry;
- D2-23 resolves to accepted evidence/readiness without claiming F5 completion, and
  D2-49 resolves to open work without being promoted by containment in ADR 0013;
- D2-3 resolves to accepted architecture and separately exposes the implementation
  qualification rather than deriving completion from legacy `Verified`;
- current code comments can cite stable blocks, while dated measurements and reviews
  retain their original IDs and versions;
- no current hook, CLI, generated pointer, verifier or pipeline still requires an
  active D2 ledger after cutover;
- an old link to `meta/D2_LEDGER.md` lands on an explicit migration explanation, not
  a missing file or a table that still looks live.

## Cutover outcome and remaining scope

C94 assigns exact ADR/block IDs, retires the sensitive-path reminder and D2 CLI, freezes the old
ledger under `meta/archive/`, and leaves a compatibility tombstone at the old path. ADR 0014 D01
and ADR 0013 D02 resolve the former M1/D2-48 and M2/D2-23 status contradictions; N6 retains the
unresolved timeout evidence formerly labeled D2-49.

Consumer migration and compatibility duration remain outside C94, as does implementation of the
broader A22/C86 interaction design. The original source counts and classification remain design
evidence, not measured reductions in attention or tokens; implementation verification is recorded
with C94 rather than inferred from this map.
