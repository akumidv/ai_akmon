# A22 — decision work, accepted decisions, and implementation evidence

## Status and resume point

This is the current first-case design for A22. It records the owner's reported
problem, a bounded session investigation, alternatives, and a proposed modification
plan. It does **not** replace the operative D2 lifecycle, accept an ADR, change a
ledger row, or authorize implementation. [TASKS](../TASKS.md) owns execution state:
A22 refines the design; C86 remains its gated implementation task.

The [research concept](attention-and-human-agent-collaboration.md) owns the broader
human-attention, cognition, dialogue, and economic rationale. D2 is now the primary
applied case, not the boundary of that mission. The [earlier slice proposal](attention-collaboration-plan.md)
is retained to explain the change of direction, not as a competing current plan.

**Resume here:** use the cases below to work through the proposed separation,
especially exact acceptance scope, material changes after acceptance, and ownership
of implementation evidence. Then prepare a small migration example without changing
live statuses. Do not ask again for the owner's applied obstacle or reapprove D2-44.
No comparative behavioral pilot has run, and this workflow is not yet locked.

## Owner problem and intended result

The owner reports that D2 review often becomes design work: understanding the original
problem, restoring alternatives, and redesigning the solution with an agent. Some
items also pass through another model's review. The owner describes two or three
cycles for an item, followed by approval and a separate verify/SHA step whose benefit
is unclear. That frequency is owner testimony, not a measured result of this sample.

The owner's proposed direction is to make D2 a register of **accepted decisions**,
not a queue of things to accept again. Open issues belong to design tasks, where
iteration has a purpose. This is more substantial than shortening a report or adding
a walkthrough skill.

The intended result is less avoidable reconstruction and administrative confirmation,
with better decisions before implementation and truthful verification afterwards.
Useful disagreement, a newly discovered defect, or a changed use scenario can justify
another pass. Fewer rounds alone would be an unsafe success criterion.

## As-is: guarantees and costs

The [existing D2 design](d2-ledger.md#1-problem) addressed a real failure: sensitive
changes mentioned in chat disappeared before owner verification. It made those
obligations visible. Its unit is a verification point, not an accepted decision;
`Pending → Approved → Verified` tracks acceptance separately from landing.
The [design's transition contract](d2-ledger.md#5-mechanism-resolved-gaps) deliberately
requires a post-landing move and a follow-up closure commit.

The present implementation has a narrower guarantee than the name `Verified` may
suggest. [`verify_entry`](../../tools/d2_ledger/d2_ledger.py) only moves an Approved
row and stores the caller's commit string. It rejects an unknown/unapproved ID, but
does not inspect Git, validate SHA syntax, match the approved content, run checks,
or authenticate approval. The [round-trip test](../tests/test_d2_ledger.py),
`test_add_approve_verify_round_trip_escapes_pipe_delimiters`, even uses `abc|123`.
This is source/test-fixture inspection, not a new runtime experiment.

Thus this value is an intended **provenance pointer**, not a cryptographic signature
or proof of correctness. With a correctly selected commit it identifies a snapshot;
the external verification work supplies its meaning. Nor does the command itself
require a second substantive owner judgment: it records landing. The current
process nevertheless gives that bookkeeping a separate transition and connects it
to task closure in [ADR 0007](../decisions/0007-d2-ledger.md).

Separation of design from implementation already exists in [design-flow](../../pipelines/design-flow.md)
and [code-flow](../../pipelines/code-flow.md). They require framing, alternatives,
owner alignment, and a return to design for material mid-build forks. A22 must
address failures to establish decision readiness as well as ledger semantics;
inventing those requirements again would not establish better behavior.

## Bounded session evidence

Session extraction was delegated and resumed after a temporary subagent usage limit.
Only existing local logs were read; external Claude/Codex applications were not run.
The two Claude episodes below and one adjacent Codex episode are qualitative cases,
not a complete session census, vendor comparison, or measurement of active attention.
Historical implementation/check claims are attributed session reports, not a fresh
audit of the code they described. The trace key is at the end of this document.

### D2-41 / C79: several different kinds of repetition

- **C:991,1077,1121–1166:** the original skills-description request became a D2 with
  unresolved checking and delivery boundaries. The agent initially put source
  gathering on the owner; the owner redirected that accessible research to the agent.
- **C:3958–4055:** walkthrough exposed that a description-only task could finish
  without affecting generated delivery. The owner explicitly stopped premature
  rewriting and asked for renewed analysis of the actual boundary.
- **C:4064:** the owner made five substantive choices about delivery, schema,
  descriptions, and checking. **C:4506** reported implementation following those
  choices but retained Pending pending a literal approval, while also exposing
  breaking consequences and an unresolved YAML issue.
- **C:4509,4518,4636:** another check corrected the agent's earlier factual claim
  about YAML handling and changed the validator rationale. **C:4638,4642:** explicit
  approval was then recorded, with verify deferred until the owner's commit.

This is not evidence that all later approval was redundant: important consequences
and facts changed after the initial choice. The failure to distinguish an accepted
scope, a new material delta, implementation conformance, and row movement makes
those different activities look like one repeatedly reopened D2.

### D2-48 / C89: local choices did not establish the intended product

- **C:6162,6902:** the need included strict rules for akmon and adaptable checks for
  consumers. The early wording also mentioned a separate check other than ruff; it
  was genuinely ambiguous, not an obvious requirement the agent simply ignored.
- **C:7142,7149:** four offered choices covered profiles, command placement, rollout
  order, and line length. The command choice already assumed a custom checker;
  choosing the recommendations did not test that assumption.
- **C:7795:** the agent reported a completed custom checker, its own rule catalog,
  1,599 passing tests, an ADR, and D2-48 Pending. **C:7797:** the owner asked what the
  command actually did and explained the intended wrapper over the project's linter.
- **C:7813–7821:** the first revision still retained a bespoke catalog. The owner's
  free-form explanation established that standard linter settings should work without
  akmon and that the project's configuration should take precedence.
- **C:8222:** the reported redesign removed the custom linter in favor of a standard
  configuration and project-declared checks. This is the episode endpoint, not a
  claim that D2-48 is still Pending today; the live ledger has since advanced.

The central issue was untested interpretation of future use before implementation.
A menu can produce agreement on details while excluding the architectural alternative
that matters. The number of tests did not validate the product premise. It is
plausible that earlier framing would have avoided rework; these logs do not prove
that counterfactual or quantify savings.

### Counterexamples to eliminating verification or version identity

**X:12481,12488,12672 — C80 / D2-42:** an initial Codex review found real contract and
implementation defects. The owner then requested a return to the underlying problem:
continuing a long task differs from changing tasks. The later report distinguished
prompt fill from task identity and rejected a false compact guarantee, alongside a
remaining behavioral defect. It also reported C70 already in HEAD while describing
separate D2 promotion, SHA, prerequisite, and task-closure bookkeeping.

**C:2439,2477,2674:** a later history inspection replaced initially suggested commit
pointers with versions reported to contain the relevant contract or corrected
implementation. This supports retaining a checked evidence baseline, not requiring
that baseline to be a second acceptance stage inside D2.

Direct Codex review of the selected D2-41/48 episodes was **not established**. The C80
example is adjacent evidence; it does not prove the claimed frequency of cross-model
cycles for every D2. Timestamp gaps are not owner attention measurements.

## Proposed separation

Three different questions need distinct ownership, not three new forms to fill:

| Question | Owning artifact | What should happen there |
| --- | --- | --- |
| What do we need to understand or decide? | Design task and its living concept | Problem, future use, inspectable facts, owner-only knowledge, alternatives, unresolved risks, and the next useful investigation or dialogue |
| What was accepted, on what grounds? | Decision record/ADR; D2 as its small navigational index | Exact accepted scope, rationale, consequences, and links to related/replacing decisions; no implementation-progress stages |
| Does the result meet the accepted intent, and what was checked/landed? | Implementation or verification task, linking its evidence | Conformance, behavioral limitations, version/diff, follow-ups, and integration status; no implied redesign or repeated acceptance of unchanged intent |

A plain specification check belongs to review/verification unless it exposes an
unresolved product or design choice. A missing measurement is investigative work,
not something the owner can make true by selecting an option. Neither requires a
new parallel registry. Task index rows remain small pointers to the owning detail.

### Acceptance and later changes

Proposed behavior: recognize **unambiguous explicit acceptance of a specific scope**
in ordinary language. Do not demand a magic `approve` word after the same decision
has already been clearly accepted. An exploratory preference, approval to investigate,
or choosing sub-options does not imply acceptance of a hidden larger design.

Prepare the coherent scope, material consequences, and remaining uncertainty before
asking for acceptance. Capture the owner's own rationale, not only an option label.
When the meaning is unclear, clarify that meaning; when the proposal changes
materially, show the changed premise, consequence, or authority and seek agreement
on the affected delta. Do not silently extend the earlier acceptance.

An accepted decision remains a historical fact. New counterevidence or changed goals
can create a linked design task and a replacement decision. Preserve the old record
and show which decision applies now; “no workflow stages” must not mean “never
challenge or supersede a decision.” A known invalid premise must remain visible while
replacement work is open, not be hidden by an accepted label.

D2 should not duplicate the complete ADR plus tests plus task status in a huge row.
The owning record holds the rationale; the index provides stable identity and a link.
The exact representation for small math/data-shape decisions and the relation between
existing D2 and ADR identifiers remain open. Do not create two authorities for one
acceptance fact merely to preserve two filenames.

### Verification and SHA

Remove the **mandatory manual D2 closure transition** in the candidate, not the
ability to establish what was tested or landed. Evidence belongs with the work it
supports: a commit where sufficient, plus the relevant working-tree/index diff or
other exact artifact identity when necessary. One decision can span several commits;
one commit can implement several decisions. A single per-decision hash is not a
universal verification subject.

The implementation-acceptance boundary still needs to be specified by risk and the
existing owner-verification obligations. Requested full reviews and material domain
checks are not removed. Reusing evidence requires checking its scope and freshness;
an implementation defect does not automatically invalidate the design, and passing
tests do not prove the product premise. Commit ownership remains with the owner.

### Dialogue and reporting at this boundary

Start with the problem and intended use, then compare alternatives against explicit
criteria. Investigate accessible facts through agents before escalating an uncertainty.
Ask an open, consequential question where only the owner can supply the missing
experience or priority; do not repeatedly ask for recorded context.

Challenge an agent's premise as seriously as the owner's factual claim. Prefer a
counterexample or a targeted check to another general opinion round. Clarify value
trade-offs with the owner instead of presenting them as empirically provable facts.
Additional model effort earns its cost when it can change the decision or expose a
material error; neither cheap iteration nor universal maximal review is the goal.

An owner-facing packet should expose the current question, known ground, recommended
choice and decisive alternative, material downside, and what remains unresolved.
Details and rejected branches stay linked. On resumption, lead with what changed and
what that changes in the recommendation; retain access to the full causal account.
This is a content criterion, not a new fixed-length form or a demand to reread every
section at every step. The cognitive research supports testing such structure, not
declaring a universal word count or a “seven items” interface law.

## Alternatives and external perspectives

| Option | Benefit | Cost / reason not to select by default |
| --- | --- | --- |
| R0 — existing lifecycle, better preparation and examples | Smallest migration; may address much of the premature design/late discovery | Keeps a separate landing transition and distributed closure metadata; compare honestly rather than assume it cannot work |
| R1 — separate decision work, accepted-decision index, and work evidence | Matches the owner's direction; makes each question explicit and removes manual D2 landing closure | Requires compatibility work and protection against lost open questions, detached evidence, and duplicate D2/ADR authority |
| R2 — ADR index only, retire D2 as a separate surface | Potentially fewer artifacts and no duplicate decision identifiers for new work | Must cover non-architectural D2 scopes, old IDs, links, and consumers; may be a representation of R1 rather than a different behavioral model |
| R3 — keep lifecycle and add a walkthrough skill first | Can assemble context for difficult existing decisions | Does not by itself fix acceptance/landing semantics or the hidden premise in C89; adds delivery and maintenance cost |

**Recommendation:** develop R1 and test it against R0. Resolve R2 as a representation
choice after checking existing references; retaining the D2 name is not an outcome.
Defer R3 unless the worked examples expose a distinct repeatable need. Do not assume
that deleting a transition solves early problem framing.

External practice supports rationale preservation but does not mandate this exact
separation. [Nygard's original ADR proposal](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
uses small records, preserves consequences and replaced decisions, and permits
proposed as well as accepted status. It is not evidence that ADRs universally lack
a lifecycle. [AWS's ADR process](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html)
explicitly retains a lifecycle and treats accepted records as immutable, superseded
by a new accepted record. These are real alternatives to an accepted-only index.
[MADR](https://adr.github.io/madr/) separates considered options and outcome and has an
optional Confirmation section about implementation compliance. This distinction is
useful here: confirmation means checks/review, not a second approval token or merely
a commit string. These are practitioner designs, not measured evidence of savings
in akmon; the proposed placement of work evidence is a local inference.

## Modification and evaluation plan

1. **Case readiness, within A22.** Use C89 for early framing, D2-41 for material
   post-choice deltas, and C80 for useful repeated review. Write paired walkthroughs
   under R0 and R1 from the same information available at each point. Later owner
   clarifications must not be smuggled into the earlier agent's knowledge. These are
   inspectable specifications until actual comparative runs are separately authorized.
2. **Decision boundary and ownership, within A22.** Settle acceptance wording/scope,
   record versus index, current applicability/supersession, implementation acceptance,
   and evidence ownership. Use a worked record and counterexample, not another broad
   questionnaire. Preserve the existing mission and product scope.
3. **Migration example before implementation.** Classify a few old rows without
   changing them: accepted decision, design question, missing measurement, or mixed
   record. D2-23 is a useful missing-evidence case; D2-45/46 mix choice, implementation,
   and limits; D2-47 includes expiry of an earlier exception. Do not automatically
   convert Pending to accepted or to design work. Preserve ID/links, attachments,
   supersession, and unresolved obligations; ambiguous provenance stays unresolved.
4. **Lock only the useful slice.** Compare the examples and any separately scoped
   pilot using the rubric below. Record the accepted replacement contract through
   the still-operative design/ADR/D2 process; this note cannot exempt itself. The
   transition should not require all historical D2 decisions to be accepted again.
5. **C86, only after lock and implementation authority.** Implement compatible record
   handling and align prose, CLI, reminders, and tests as one coherent migration.
   Do not land guidance that assumes a new schema while tools still enforce the old
   one. Maintain a readable legacy path; never silently promote old rows. The exact
   deprecation policy for commands is a remaining design choice.
6. **Assess and integrate.** Check conformance and observed behavioral usefulness,
   including costs and new failure modes. Retain, shrink, or remove the candidate
   according to results. Release and consumer realignment remain owner-controlled;
   unrelated applied development continues throughout.

### Later touch map — not this turn's edit scope

| Owning surface | Reason it may change |
| --- | --- |
| ADR 0007, `design/d2-ledger.md`, ledger header | Explicit replacement/compatibility contract, not silent rewriting of accepted history |
| `design-flow`, `code-flow`, `tasks`, `pre-commit`, relevant role/guardrail text | Decision readiness, implementation acceptance, task closure and removal of manual D2 landing bookkeeping |
| `tools/d2_ledger/d2_ledger.py` and its tests | Schema/CLI compatibility, stable IDs, no inferred acceptance, preservation of rationale/review links |
| `hooks/hook_core.py`, `hooks/model-routing.py`, wrappers and adapter tests | Old add/approve/verify advice and counts must not treat accepted decisions as an attention queue |
| Task-linked evidence and any affected status digest | Keep unresolved work visible without copying every task state or imposing owner time logging |

This map was checked against a checkout based on `4c6acee6450f0bb1ce9de72c58ec2a83a4556a63`
with parallel uncommitted changes. It is a routing aid, not a frozen test baseline or
current status board. Re-read relevant worktree and staged diffs before edits; hook,
findings, initialization, routing and task-archive work already overlaps these areas.
Do not rewrite carrier wiring or claim new harness capabilities from prose changes.

The earlier plan's [comparison baseline and cost rubric](attention-collaboration-plan.md#evaluation-amid-a-moving-project)
remain applicable, but R0/R1 replace its narrower A/B comparison. Evaluate accurate
scope and acceptance, visible limitations, useful challenge, and preservation of
open work as a quality floor. Count avoidable questions/context reconstruction and
use a short voluntary owner assessment; never infer attention from timestamp gaps.
Track total agent work, retries, integration effort and unknown costs separately.
Better up-front design can justify higher immediate cost; hypothetical avoided
rework is not measured savings. No tool correctness check alone proves that the
interaction has improved.

For executable C86 changes, regressions need unknown/unaccepted records, material
delta versus unchanged resumption, legacy/mixed records, ID/attachment preservation,
stale/missing evidence, and actual hook payload boundaries. Run the project's
pytest/ruff/self-CI/build suite and preserve the installed-wheel network prerequisite
distinction. No runtime tests or implementation comparisons were performed for this
research-note update.

## Trace key and open limits

- **C:** `/home/ai/.claude/projects/-home-ai-workspace-akmon/0abb18e2-bafb-4e68-9bdd-d78dea2a76b5.jsonl`.
  References above are physical JSONL lines. Owner decision anchors include UUID
  `a02400d5-ebd3-4d03-93df-40d502e3912c` (C:4064),
  `52f7356f-b761-4404-a23e-6ce08aa2417a` (C:7149),
  `7dad29bc-c756-456e-941b-3b2f9072f413` (C:7797), and
  `ed39b464-9eac-4db3-943e-dd5ccb23a001` (C:7821).
- **X:** `/home/ai/.codex/sessions/2026/08/21/rollout-2026-08-21T07-27-38-01a02337-ddb3-7cc0-96e6-4f98300905d1.jsonl`.
  X:12481 and X:12672 are assistant final reports; X:12488 is the intervening owner
  request. These are local trace pointers, not portable public evidence.

Open: the exact replacement schema/commands, small-decision record placement,
owner implementation-acceptance boundary, migration/deprecation details, and measured
usefulness/cost. The evidence supports redesigning the framing and record boundaries;
it does not establish one final protocol, universal time savings, or model superiority.

A bounded independent document/source check found stale current-plan ownership and
an AP4 exit condition that still required the old D2 closure stage for the replacement.
Both were corrected and specifically rechecked. That review did not independently
reinspect raw sessions or validate the proposed workflow's behavioral effectiveness.
