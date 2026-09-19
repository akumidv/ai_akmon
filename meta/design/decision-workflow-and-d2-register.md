# A22 — decision work, accepted decisions, and implementation evidence

## Status and resume point

This is the design and evidence trail behind the accepted replacement in
[ADR 0016](../decisions/0016-decision-records-and-owner-acceptance.md). The owner authorized the
full Akmon cutover; [C94](../TASKS.md) owns migration implementation. A22/C86 still own the broader
attention-aware interaction protocol, which this workflow change does not accept by implication.

The [research concept](attention-and-human-agent-collaboration.md) owns the broader
human-attention, cognition, dialogue, and economic rationale. D2 is now the primary
applied case, not the boundary of that mission. The [earlier slice proposal](attention-collaboration-plan.md)
is retained to explain the change of direction, not as a competing current plan.

**Resume here:** the [worked carrier comparison](thematic-adr-comparison.md) now
recommends thematic ADRs with stable decision-block identities and no separate D2
authority, retaining individual records as a small-topic/split-out form. It compares
task-origin decisions, independent amendments and a mundane no-record correction.
The accepted replacement is ADR 0016. The [legacy migration sample](d2-legacy-migration.md)
now tests task-origin decisions, amendments, expiry and mixed evidence gates without
changing historical statuses, and supplied thematic routing for every legacy D2
ID. Its [cutover reference map](d2-cutover-reference-map.md) now separates operative
machinery from historical provenance and records the topic boundaries C94 applied.
The machine-checked alias map completes row-by-row lookup. Mandatory SHA bookkeeping
is retired. Do not ask again for the applied obstacle or reapprove the mission block. No comparative
behavioral pilot has run, so the broader interaction design remains unevaluated.

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

The owner subsequently sharpened three points. First, Git can reveal when an
acceptance record entered history, so copying its commit into a separate field and
running verify is potentially redundant. Second, D2 also arises from ordinary tasks;
it is not simply an ADR index. Third, recording every question would create noise.
Alternatives now include significant decisions linked from tasks or ADRs, or thematic
ADRs with identifiable decision subsections and their own acceptance state, discovered
through keywords/tags. These are attributed design directions, not a final selection.

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

The owner's request for other sessions produced a separate
[cross-session evidence note](decision-review-session-cycles.md): additional Codex
and Claude episodes, their proposed correspondences, and the boundary between a
shared subject and a proven cross-model handoff. The original sample below is retained.

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

## Selected separation

Three different questions need distinct ownership, not three new forms to fill:

| Question | Owning artifact | What should happen there |
| --- | --- | --- |
| What do we need to understand or decide? | Design task and its living concept | Problem, future use, inspectable facts, owner-only knowledge, alternatives, unresolved risks, and the next useful investigation or dialogue |
| What was accepted, on what grounds? | One owning decision record in an ADR or task detail; optional navigational index | Exact accepted scope, rationale, consequences, and links to related/replacing decisions; no implementation-progress stages and no duplicated acceptance authority |
| Does the result meet the accepted intent, and what was checked/landed? | Implementation or verification task, linking its evidence | Conformance, behavioral limitations, version/diff, follow-ups, and integration status; no implied redesign or repeated acceptance of unchanged intent |

A plain specification check belongs to review/verification unless it exposes an
unresolved product or design choice. A missing measurement is investigative work,
not something the owner can make true by selecting an option. Neither requires a
new parallel registry. Task index rows remain small pointers to the owning detail.

### Acceptance and later changes

Accepted behavior: recognize **unambiguous explicit acceptance of a specific scope**
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

The selected model removes D2 as a second index beside ADRs, tests, and task state.
The owning thematic ADR block holds stable identity and rationale; a unique
`Legacy-ID` alias preserves lookup for old IDs. Task-origin decisions remain
representable: for example, D2-43's former anchors name package-pin code/tests and
C84, while its durable choice now belongs to ADR 0009 D08. Small local corrections
still remain task work rather than forcing every clarification into a new ADR.

### Verification and SHA

The accepted replacement removes the **mandatory manual D2 closure transition and
mandatory copied SHA**. Do not move the same clerical obligation into the implementation
task under a different name. Ordinary accepted records need a clear accepted scope
and preserved history, not another manually maintained commit field.

An on-demand Git check supports the owner's point on a real example. D2-44 first
appears on the inspected branch in `0617402` already under `## Approved`; `4c6acee`
still has it there. `bc52998` moves it to `## Verified` with `0617402` as the stored
commit. The acceptance-bearing snapshot was recoverable without that later field.
These hashes identify this research example, not mandatory metadata for future
decision records. Read-only commands used for the check included:

```bash
git log --format='%h %s' -S'D2-44' -- meta/D2_LEDGER.md
git show 0617402:meta/D2_LEDGER.md | awk '/^## / { section = $0 } /^\| D2-44 \|/ { print section; print $0 }'
```

Search must identify the acceptance of that decision in context, not the first
`approve` anywhere in a file. A count-based `git log -S` search can find introduction
but miss a later move with unchanged occurrence count; inspect the relevant diffs
and containing section. Git recovers committed recorded content, not an unrecorded
conversation or the original time of owner agreement. An incomplete checkout/export
may lack history. These limits call for honest reporting, not a routine SHA ceremony.

The first committed acceptance and the subject of an implementation review are
different facts. For a particular review, measurement, or test result, identify its
subject sufficiently to reproduce or assess it: an existing CI/PR reference, artifact,
commit, or relevant worktree/index diff as appropriate. Reuse that evidence location
instead of copying identifiers into every linked task/decision. A specific evidence
need can justify a version reference; it is not a blanket field requirement. One
decision can span several commits and one commit can implement several decisions.

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
| R2 — individual decision records with thematic navigation, no separate D2 workflow | Independent acceptance/replacement with a compact view by subject; fewer competing state owners | Must cover task-origin decisions, legacy IDs and links; a manually duplicated status index would recreate the problem |
| R3 — keep lifecycle and add a walkthrough skill first | Can assemble context for difficult existing decisions | Does not by itself fix acceptance/landing semantics or the hidden premise in C89; adds delivery and maintenance cost |
| R4 — thematic compound ADR with independently identified decision blocks | Related rationale stays together; no new file for every meaningful addition | A global Accepted status cannot cover independent new blocks; growing documents, coupled edits, anchors and partial replacement need care |

The earlier recommendation preferred R1 while deferring representation. The owner's
clarification makes representation part of the current problem, not an optional
later detail. **Previous comparison recommendation:** compare R2 and R4 against a thin R1, with
R0 retained as the no-migration baseline. Prefer one authoritative acceptance record
and thematic navigation; a separately maintained D2 registry has to earn its cost.
That was the comparison starting point. The [worked comparison](thematic-adr-comparison.md)
now prefers R4 for cohesive topics, with R2 as its small-topic/split-out form and no
separate D2 authority; ADR 0016 accepts that choice and C94 owns its migration. Defer R3
unless the examples expose a distinct repeatable need. Removing a transition alone
does not solve early problem framing.

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

## Significant decisions and thematic organization

### What deserves a durable decision record?

The candidate threshold is **a consequential commitment whose rationale a later
task or reviewer will need**, not the existence of two imaginable options. Record
choices that materially set product scope, shared contracts or semantics, substantial
risk/quality/cost trade-offs, hard-to-reverse commitments, or non-obvious departures
from established policy. A short change can qualify; a long discussion alone does not.
This threshold is a proposed refinement, not an exemption from the current guardrails.

An ordinary correction under an accepted contract is normally task work plus its
verification. A local reversible implementation detail need not become an ADR.
A measured fact belongs with its evidence. A still-open research question belongs in
design or the relevant task until it yields a decision. If a bug exposes a genuine
policy fork, record that fork's resolution, not every intermediate patch attempt.

This follows the direction, not a mandatory template, of
[arc42's significance guidance](https://docs.arc42.org/tips/9-1/): focus on important,
risky, costly, lasting or unusual choices instead of every development detail.
Akmon's existing [design-flow](../../pipelines/design-flow.md) already distinguishes
material changes from trivial local ones. The candidate must make that distinction
usable rather than attach a new record to every edit matching a sensitive path.

### Topic, decision, and task are different units

- **Design** is the workspace for a larger problem: evidence, scenarios, alternatives,
  related decisions and unresolved questions. It need not be created for every task.
- **A decision** has an identifiable scope, rationale, consequences and acceptance.
  It may arise during design or ordinary implementation. Significant enduring choices
  need durable ownership; a task-local choice can remain in the task's linked detail
  when that adequately preserves its scope and discoverability.
- **A thematic view** groups related decisions without granting them shared approval.
  It can be sections in one file, a topic page linking records, or a folder.
- **A task** owns the work to resolve or implement something, not another copy of all
  accepted decision states. Promotion from a task-local note to a durable ADR should
  preserve its history and leave a link, not create two competing current versions.

The existing repository already contains compound records: [ADR 0012](../decisions/0012-stage1-contracts-and-vocabulary.md)
has separately named F-points, and [ADR 0014](../decisions/0014-code-rules-catalog-and-language-profiles.md)
groups six choices about code rules, profiles, checks, initialization and configuration.
ADR 0012 also explains separating stable vocabulary from measurement-amendable ADR 0013
so timing changes do not disturb stable decisions. The issue is not whether a file
may contain related clauses, but which clauses can evolve independently.

Do not turn a Proposed ADR block into a second copy of the living design's research
queue. The design owns exploration; a draft decision block can state the bounded
proposition and link its rationale. Once accepted, the decision record owns the
accepted meaning and the design links to it. A change of carrier must not require
the owner to accept unchanged content again. Allowing such draft blocks is itself
part of the proposal: current design-flow says ADRs contain locked decisions only.

**Earlier mixed-status organization example, not a change to ADR 0014 or its live
status:** the [worked comparison](thematic-adr-comparison.md#accepted-record-not-an-approval-queue)
now prefers keeping proposals in design rather than adding a Proposed state to ADR
blocks by default. This earlier option is retained for comparison:

| Theme: project checks | Independent decision scope | Example state |
| --- | --- | --- |
| `checks.runner` | Run project-declared linters rather than implement a custom linter | Accepted |
| `checks.setup` | How initialization selects and records those commands | Proposed |
| `checks.rule-placement` | Place machine-checkable rules in standard tool configuration | Accepted |

If `checks.setup` changes, it must not reopen unchanged `checks.runner`. Conversely,
adding a Proposed block under a thematic file must not inherit acceptance from an
old file-level header. A file with independently evolving decisions cannot truthfully
use one authoritative Accepted/Proposed status for all of them. A genuinely indivisible
decision with explanatory subclauses can keep one status; do not split it artificially.
The example labels are not an adopted ID syntax or a new state-machine specification.

Statuses here describe decision disposition (for example proposed, accepted, rejected,
or replaced), not implementation progress. No obligatory Reviewed/Verified/Released
ladder is proposed. A changed accepted meaning needs explicit affected-scope handling;
editorial edits do not warrant automatic reapproval. A compound document remains
viable only while finding and checking the relevant block is easier than reconstructing
the entire topic. Split on independent evolution or difficult navigation, not a magic
word count.

[arc42 section 9](https://docs.arc42.org/section-9/) permits lists, tables, separate
decision sections, and local placement, while warning against redundant text. This
supports several carriers rather than a universal one-file-per-decision law.
[MADR's category decision](https://adr.github.io/madr/decisions/0010-support-categories.html)
chooses topic subfolders with local IDs but explicitly notes discoverability, identity
and extra-index costs. It is an alternative to tags, not evidence that tags must win.

### Keywords and tags help retrieval, not acceptance

Start by finding existing topics and their accepted constraints before drafting a
new decision. Reuse recognizable names; use links when a decision affects several
topics. A few useful keywords/tags can provide another retrieval route, but keyword
overlap alone does not justify merging decisions or appending under an accepted scope.
Do not require a tagging taxonomy or automatic classifier before trying the examples.
If an index is useful, keep it navigational or derive it from owning records; do not
manually synchronize status, rationale and hashes across it, ADRs and tasks.

A contrary provenance practice is worth retaining: [arc42 also recommends an explicit
decision timestamp](https://docs.arc42.org/tips/9-8/). Akmon currently uses Git history
instead of dates in design/ADR files. That is a local trade-off, not universal ADR
practice; exports without history may need an explicit provenance view. It does not
establish a need for manual commit-hash fields or a second verification transition.

## Modification and evaluation plan

1. **Case readiness, within A22.** Use C89 for early framing, D2-41 for material
   post-choice deltas, and C80 for useful repeated review. Write paired walkthroughs
   under R0 and R1 from the same information available at each point. Later owner
   clarifications must not be smuggled into the earlier agent's knowledge. These are
   inspectable specifications until actual comparative runs are separately authorized.
2. **Decision boundary and ownership — completed for the record carrier.** The
   significance threshold and task-origin/theme examples compared R1/R2/R4 and ADR 0016
   settled the acceptance unit, record versus index, independent amendments,
   implementation acceptance, and evidence ownership. Broader owner-facing interaction
   remains A22 work.
3. **Migration dry-run and reference map — completed.** The migration work classified
   old rows without changing their historical states: accepted decision, design
   question, missing measurement, or mixed
   record. D2-23 is a useful missing-evidence case; D2-45/46 mix choice, implementation,
   and limits; D2-47 includes expiry of an earlier exception. Do not automatically
   convert Pending to accepted or to design work. Preserve ID/links, attachments,
   supersession, and unresolved obligations; ambiguous provenance stays unresolved.
   Test one decision with no ADR, one compound topic with different acceptance scopes,
   and one mundane task that should create no decision record. Legacy links need a
   readable mapping, not a second required registry for every future decision.
4. **Lock only the useful slice — completed for the workflow.** The owner accepted the bounded
   D2-to-ADR replacement as ADR 0016 without reapproving historical decisions. This does not lock
   the broader A22 interaction behaviours.
5. **C94 implements the workflow cutover; C86 remains separate.** C94 aligns record
   handling, prose, CLI, reminders, and tests as one coherent migration. The old path
   is a compatibility tombstone, the final ledger is archived, and the retired commands
   are removed rather than emulated. Old rows are never silently promoted.
6. **Assess and integrate.** Check conformance and observed behavioral usefulness,
   including costs and new failure modes. Retain, shrink, or remove the candidate
   according to results. Release and consumer realignment remain owner-controlled;
   unrelated applied development continues throughout.

### Pre-cutover implementation touch map — retained as design history

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
remain applicable, but workflow R0/R1 and record-carrier R1/R2/R4 comparisons replace
its narrower A/B comparison. Evaluate accurate
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

Open for the broader A22 work: behavioral usefulness and cost, including whether the
accepted recording threshold and owner-facing presentation reduce avoidable attention
without hiding material uncertainty. ADR 0016 and C94 settle the decision-record carrier,
legacy lookup, command retirement, and implementation-acceptance boundary; they do not
establish a universal interaction protocol, universal time savings, or model superiority.

A bounded independent document/source check found stale current-plan ownership and
an AP4 exit condition that still required the old D2 closure stage for the replacement.
Both were corrected and specifically rechecked. That review did not independently
reinspect raw sessions or validate the proposed workflow's behavioral effectiveness.

The later Git/organization/session extension received a bounded consistency check
against explicit acceptance scope, corrected history, attribution limits, and removal
of mandatory SHA bookkeeping. It reported no material conflicts; this was not the
formal ADR acceptance gate or a full transcript audit.
