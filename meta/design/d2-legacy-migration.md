# A22 — lossless migration of legacy D2 records

## Status and resume point

Migration design and preserved reasoning for the accepted replacement in
[ADR 0016](../decisions/0016-decision-records-and-owner-acceptance.md). The repository cutover is
implemented under C94; this note remains the lossless classification source, not a live status
board or a second authority.

The inspected subject has parallel owner-controlled work. `meta/D2_LEDGER.md` has no
unstaged delta but does have staged changes relative to HEAD: the live/index view puts
D2-45, D2-46, D2-47, D2-48, D2-50 and D2-51 in Approved and D2-49 in Pending.
The examples below use that live/index view and say where linked artifacts disagree.
They are a dry-run, not a migration of unlanded state.

**Current execution:** the linked [cutover reference map](d2-cutover-reference-map.md) covers every
legacy ID and routes active machinery versus historical provenance. C94 applies that map to the
live tree while preserving parallel staged work. Old Approved or Verified choices are not
reapproved; unresolved evidence remains unresolved.

## Migration objective

Remove D2 as a separately maintained decision/approval/landing authority without
losing any of the useful work it accumulated:

- the exact accepted commitment and why it won;
- material costs, limits, rejected alternatives and replacement relations;
- unresolved design, implementation or evidence obligations;
- version-scoped measurements and their limitations;
- discoverability of old `D2-N` references and historical provenance.

The migration unit is a **semantic obligation**, not a Markdown row. One D2 row can
produce one accepted decision block, several task/evidence links, or no new decision
block at all. Several rows can also describe amendments to one decision family. A
row is not copied wholesale into an ADR.

Success means every material clause has exactly one current owner or an explicit
unresolved destination; no Pending content becomes accepted by migration; no old
exception silently becomes current again; and no implementation/evidence claim is
manufactured from owner acceptance.

## Destination model

| Source content in a legacy row | Authoritative destination |
| --- | --- |
| Accepted enduring commitment, rationale, alternatives, consequences | Addressable block in a thematic ADR |
| Open architecture fork or challenged premise | Living design open point, linked from the affected block |
| Implementation or remediation still to do | Task, under the normal code-flow completion contract |
| Test/conformance acceptance criteria | Task or specification owning that implementation |
| Versioned harness fact or quantitative observation | `MEASUREMENTS` and its evidence report |
| Review findings and experiment detail | Review/evidence artifact; linked, not copied |
| Supersession, expiry or narrowed applicability | Relationship on both affected decision blocks |
| Historical D2 ID | Legacy alias on the destination plus a frozen migration artifact/history |
| Landing SHA copied into D2 | Not copied into the new decision block; Git remains the timeline |

This table describes migration analysis, not a new mandatory form for ordinary work.
An ADR block should contain enough rationale to interpret its accepted meaning, but
it should link large measurements and test lists to their actual owners.

### State mapping

- **Verified:** carry the decision core as accepted without another owner round.
  Preserve its legacy alias and links. Do not copy the row's SHA into a new required
  field; the frozen old record and Git retain historical provenance.
- **Approved:** carry the decision core as accepted without a later `verify` state.
  Implementation and evidence obligations remain open or complete according to
  their own owners. `Approved` never means “implementation complete.”
- **Pending:** never promote automatically. Put an unresolved decision in design;
  put missing evidence or implementation in its task. If the row merely restates
  an already accepted split or protocol while waiting for evidence, preserve that
  accepted rationale separately and keep the evidence open.
- **Contradictory copies:** do not select whichever status is convenient. Identify
  the current authority and the precise semantic/gate difference. Correct stale
  navigation without ceremonial reapproval only when the accepted scope is already
  unambiguous; otherwise leave a migration exception for owner resolution.

The mapping does not infer acceptance from implementation, tests, an agent-authored
“owner choice” label or containment inside an Accepted file. Conversely, it does not
reopen a clearly Approved/Verified decision merely because its new carrier differs.

## Worked migration sample

### D2-44 — narrow accepted mission commitment

Current legacy disposition: Verified. It accepts the mission/priorities framing and
explicitly excludes the interaction protocol, report budgets, automatic reopening,
and model/effort routing changes.

- **Decision:** an addressable block in the human–agent collaboration/mission theme.
  Preserve the economic whole-lifecycle resource-allocation rationale and the
  exclusion boundary.
- **Work/evidence:** A22/C86 continue to own the unaccepted collaboration design and
  implementation. Product differentiation remains intent, not measured superiority.
- **History:** retain `D2-44` as a legacy alias; do not copy `0617402` into a new
  approval field.

This case demonstrates that a Verified row can migrate without reapproval while its
narrow scope prevents neighbouring research from inheriting acceptance.

### D2-43 — accepted decision discovered in an ordinary task

Current legacy disposition: Verified; C84 is archived as done. The enduring choice
is to parse the manifest as TOML and expose `unreadable` as a distinct result with
defined `verify`/`init` behaviour.

- **Decision:** a packaging-theme block, preserving alternatives, error semantics
  and costs. Whether parsing and the new outcome are one indivisible commitment is
  decided from their rationale, not from their sharing one task.
- **Work/evidence:** archived C84 and its code/test anchors retain implementation
  history. The test list is not duplicated into the ADR block.
- **History:** the block carries legacy alias `D2-43`; Git and the frozen old row
  retain the old landing pointer.

This is the key task-origin case: a significant decision gets durable ownership,
while the task remains the unit of implementation.

### D2-45 — accepted amendment with unfinished implementation state

Current legacy disposition: Approved. [ADR 0013](../decisions/0013-hook-survivability-and-crash-posture.md)
already contains the substantive F3 amendment: the guard moves to C87, Claude emits
an owner-visible notice and Codex reports failure through its exit behaviour.

- **Decision:** assign the existing amendment a stable block identity rather than
  copying D2-45 into another theme. Preserve the separate owner-gated conditions
  for any future move from crash-open to fail-closed.
- **Work:** C87 owns implementation and close-out. Its unresolved Claude
  `SessionStart` terminal-visibility observation remains visible, but does not make
  the accepted crash contract Pending again.
- **Evidence:** M69–M71 and the C87 report keep their version and channel limits.

Under the candidate there is no later D2 verify. Task closure still needs ordinary
implementation/conformance evidence; removing bookkeeping does not remove checking.

### D2-46 — accepted measured policy amendment

Current legacy disposition: Approved. The accepted core changes the delegation
nudge: tool-kind weights, grace, thresholds, no ask carried by a read, and no shell
command-text classifier.

- **Decision:** an addressable block in the delegation/model-routing theme, linked
  as an amendment to the legacy D2-8 policy.
- **Work:** C88 owns code, compatibility and task completion.
- **Evidence:** the replay report and measurements keep the sampled populations and
  residual read-only-shell limitation. They do not become a universal claim that
  the thresholds improve every consumer.

The block records the rule and decisive evidence; it does not inline the entire
replay or treat measured implementation progress as a new approval status.

### D2-47 — expiry is a relationship, not deletion

Current legacy disposition: Approved. It removes D2-29's temporary crash-posture
exemption after measurements became available.

- **Decision:** mark the old exemption block superseded/expired and link the new
  unexempted rule from both directions. Preserve why the temporary exception once
  existed; do not leave D2-29 discoverable as a current unconditional allowance.
- **Work:** C90 owns removal and regression evidence.
- **Evidence:** retain vendor/version and fixture-shape limits of the measurements.

This case prevents migration from flattening history into only the latest text.

### D2-48 — one acceptance scope, several thematic blocks

The live/index ledger places D2-48 in Approved, while [ADR 0014](../decisions/0014-code-rules-catalog-and-language-profiles.md)
still labels the whole ADR Proposed and says D2-48 Pending. This is migration
exception M1 below, not permission to choose a status silently.

The row's semantic content naturally separates into related blocks: placement,
profile kinds, standard ruff configuration, project-declared check runner,
initialization choice, and akmon's own configuration/size boundary. If their recorded
owner acceptance covered one coherent set, that single acceptance can migrate to
several independently addressable blocks; the file count does not multiply owner
approvals. The withdrawn custom linter and its reason remain part of the rationale.

C89 and C91 keep their implementation slices and evidence. C91 eliminating the
exception list is implementation progress under the size rule, not automatically
a new architecture decision.

### D2-23 and D2-49 — the counterexample to copying rows

D2-23 is Approved in the live/index ledger and D2-49 is Pending. Their purpose is to
split F4/F6 envelope evidence from later F5 timeout-budget work so N6 can measure
inside an accepted envelope. [ADR 0013's amendment](../decisions/0013-hook-survivability-and-crash-posture.md)
already explains the split.

Do **not** copy D2-49 into an accepted-only ADR. The split rationale can be an accepted
decision, but D2-49 also asks for an entry-to-class table, timings, formula, literals,
units and live validation that do not yet exist. Those are N6 evidence and C52 gates.
Copying the row would either claim nonexistent evidence or rebuild a Pending/Verified
queue inside the ADR.

D2-23 also needs decomposition:

- enduring cap/support choices, if not already owned, belong in the relevant ADR block;
- version-scoped F4/F6 results stay in measurements/reviews;
- N6/C52 prerequisites stay in tasks;
- stale “not ready” prose is reconciled as a copy/gate issue, not silently treated as
  proof that the accepted envelope is invalid.

This pair shows why one legacy D2 row may yield zero or one new decision blocks plus
several links, rather than one migrated row.

## Migration exceptions exposed by the sample

### M1 — D2-48 status disagreement

The ledger says Approved; ADR 0014 says Proposed/Pending. Before cutover, establish
which content and acceptance scope the live/index change represents, then make the
ADR blocks authoritative and remove the copied status language. This should not ask
the owner to decide the design again if the exact acceptance is already clear. It
must not treat a staged row as landed history.

**Candidate resolution:** after the parallel change lands unchanged, treat its
Approved scope as accepted and align the identified ADR blocks without a new approval
round. If it does not land or its scope changes, retain the affected content in design.

### M2 — D2-23 gate disagreement

The ledger says D2-23 Approved. N6 is active and describes the envelope as verified,
while ADR 0013 still says both D2-23/D2-49 are Pending and says N6 begins after D2-23
is Verified. The semantic question is whether N6 is authorized to work inside the
accepted caps, not which word should be copied to three files.

Reconcile that prerequisite explicitly before migration. Under the candidate, its
future form should be a task dependency on an accepted envelope/evidence package,
not an ADR approval state followed by a landing state.

**Candidate resolution:** D2-23's Approved state establishes semantic acceptance;
the exact F4/F6 package being present in committed history establishes availability
for N6. Make that a task/evidence readiness condition, not a second owner decision.
Until the staged package lands and contradictory evidence prose is reconciled, do
not claim that current committed history satisfies it.

## Whole-ledger preliminary routing — retained migration input

This was the coverage map for all legacy IDs, not the final ADR-block layout. It groups
rows by the topic that should own their durable meaning. Individual rows still need
semantic partitioning, and a destination may retain only a clause rather than the
whole row.

| Destination topic | Legacy IDs covered | Migration treatment |
| --- | --- | --- |
| Model routing, gate packs and delegation | D2-1–D2-11, D2-37, D2-38, D2-40, D2-42, D2-46, D2-50 | Form addressable policy blocks; preserve runtime/evidence limits and the partial replacements below |
| Vendor integration, hook/capability contracts and findings | D2-15–D2-23, D2-27–D2-30, D2-45, D2-47, D2-49 | Reuse ADR 0011–0013 blocks where they own the rule; route measurements and unfinished work separately |
| Packaging, attach/update and shared runtime ownership | D2-12, D2-13, D2-25, D2-26, D2-31–D2-36, D2-39, D2-43, D2-51 | Fold into identifiable packaging/release/runtime blocks without flattening partial supersession |
| Alternatives-adoption decision set | D2-14 | Existing ADR 0010 owns the decision set; preserve remaining measurement work instead of making another umbrella block |
| Skills delivery and authoring | D2-41 | One thematic skills-contract destination, retaining migration and validator limits |
| Project mission and resource economics | D2-44 | Narrow accepted mission block; A22/C86 remain outside its accepted scope |
| Code rules, profiles and project checks | D2-48 | Several related blocks in the ADR 0014 theme with one recoverable acceptance scope |
| Retired D2 lifecycle itself | D2-24 | Preserve ADR 0007 and the former lifecycle as superseded history after the accepted cutover |

All IDs D2-1 through D2-51 are represented in this table; the non-contiguous ranges
are intentional. The grouping is not a claim that every listed decision belongs in
one physical file. A topic can split while stable decision identities remain.

### Row-level exceptions the grouped view must not hide

- **D2-3:** the row is in Verified but explicitly limits acceptance to architecture
  and says C17 cannot be implementation-verified before C76 closes. Migrate the
  architecture block and preserve C76; never derive task completion from the section.
- **D2-8/D2-10/D2-11/D2-46:** D2-10 is a diagnostic record superseded by D2-11;
  D2-46 replaces D2-8's counting, thresholds and the rule that the same ask has no
  tool-category exemption: a read now never carries or spends the ask. It does not
  replace the nudge's existence/purpose or D2-11's escalation when an ask is actually
  formed. Preserve the causal evidence without reviving the rejected posture.
- **D2-13 and D2-34:** their row prose still says a landing SHA is pending despite
  their presence in Verified with hashes. Treat that as stale lifecycle prose, not
  an unresolved semantic choice.
- **D2-20/D2-23/D2-49:** D2-20 is the stable umbrella protocol and explicitly excludes
  concrete F4–F6 results. Do not let the umbrella's acceptance absorb missing F5
  evidence or reproduce three records of the same status.
- **D2-22:** the bounded fail-quiet policy is temporary while C36(a) remains open.
  Its expiry condition must be visible from the accepted block and task; it is not
  an unconditional permanent rule.
- **D2-26/D2-33/D2-35:** D2-35 replaces only their package runtime-root and
  materialization premises. Their shared-reader/shared-utility ownership decisions
  survive. Whole-row supersession would discard still-current rationale.
- **D2-29/D2-47:** the former exemption is historical and expired; the old block must
  point to that expiry so a grep hit cannot mistake it for current permission.
- **D2-32/D2-33:** two D2-32 branches were superseded by D2-33 before acceptance.
  Preserve the accepted CLI-notice/hook-silence distinction rather than migrating
  crossed-out alternatives as current rules.
- **D2-37/D2-38/D2-42:** D2-42 replaces pressure bands, delivery and reset clauses,
  while the recommended-budget basis and unrelated orchestrator-delivery decisions
  survive. C81's Codex delivery and A21's task boundary remain separate work.
- **D2-27/D2-40:** D2-40 supplements the accepted delivery-diagnostic contract; C70
  still has task prerequisites and a newer-harness evidence limitation. Verified
  history is not proof of a currently complete task.
- **D2-48 and D2-51:** their linked ADR/design headers still say Pending while the
  live/index ledger says Approved. They remain reconciliation items M1 and the same
  class of stale copied status; neither requires inventing a new approval transition.

The full inventory also found several rows whose prose says “owner-approved” or
“landing SHA pending” inside the Verified section. This reinforces the central rule:
legacy section names and prose are evidence to reconcile, not a schema to reproduce.
A bounded fixed-string discovery pass over the inspected tree finds D2 references in
68 files: 41 Markdown files and 27 code/test files. That is a scope estimate, not a
count of independent obligations; it includes historical/research mentions and this
design. The [cutover reference map](d2-cutover-reference-map.md) now separates active
authority/tooling, current dependency, provenance and historical classes and proposes
the first topic/block boundaries. C94 completed the row-by-row destination validation;
the machine check in `meta/checks/decision_records.py` now enforces unique resolution.

## Planned migration sequence — completed by C94

1. **Freeze the subject after parallel work lands.** Inventory committed ledger rows,
   their sections, anchors and every inbound `D2-N` reference. Keep staged and
   committed states distinct during preparation.
2. **Partition each row.** Extract decision core, rationale/consequences, evidence,
   open work, and replacement/dependency relations. Flag contradictions and orphaned
   obligations; do not classify from status alone.
3. **Resolve one decision owner.** Reuse an existing ADR block when it already owns
   the commitment. Add a thematic block for an accepted task-origin decision only
   when no durable owner exists. Merge duplicated meaning without merging unrelated
   acceptance scopes.
4. **Route non-decision content.** Preserve measurements/reviews where they live and
   link tasks to them. Add a task only for a material obligation with no current
   owner; do not convert every historical `Verify:` bullet into backlog noise.
5. **Preserve legacy lookup.** Put `Legacy: D2-N` aliases on owning blocks/tasks as
   needed and retain a frozen historical ledger or generated migration map. It is
   navigation only: no status, rationale or new entries are maintained there.
6. **Validate losslessness.** Every old ID resolves; every material clause has one
   current owner or an explicit unresolved disposition; every active exception and
   expiry is correctly visible; no Pending choice is accepted; no Approved/Verified
   choice is reopened; no evidence or implementation state is invented.
7. **Cut over atomically after owner acceptance.** Align ADR conventions, design/code
   flows, tasks, hooks, CLI and tests in the C94 implementation. Archive or retire
   the active D2 surface only when no current guard still treats it as authority.

### Selected legacy carrier

A frozen old ledger preserves provenance cheaply but can look current. C94 therefore
moves the final snapshot to `meta/archive/D2_LEDGER.md`, leaves a compatibility tombstone
at the old path, and puts unique legacy aliases on destination owners. The machine check
derives resolution from those owners rather than maintaining a second status index.

## Accepted migration boundary

The owner did not reapprove each old Approved/Verified decision. ADR 0016 accepted:

1. thematic accepted-only decision blocks with stable identities;
2. the state/content mapping above, including no automatic promotion of Pending;
3. the lossless legacy/archive and obligation-preservation rule;
4. the resolved dispositions of genuine migration exceptions M1/M2;
5. removal of the active D2 workflow only after the atomic implementation cutover.

Implementation success is then checked separately: references resolve, tools and
hooks no longer prescribe the old lifecycle, tasks/evidence retain open obligations,
and normal project verification passes. That check is not another owner acceptance
stage and does not need a manually copied commit hash.

No behavioral comparison or runtime test was performed for this design note. The
sample establishes that lossless decomposition is possible and exposes two current
contradictions; it does not prove that the complete ledger has no additional category.
