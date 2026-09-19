# A22 — thematic ADRs with addressable decisions

## Status, task and resume point

Preserved comparison behind the accepted thematic-block form in
[ADR 0016](../decisions/0016-decision-records-and-owner-acceptance.md). It refines
[decision work and D2](decision-workflow-and-d2-register.md), which owns the workflow
investigation and session evidence. C94 owns the repository cutover; A22/C86 remain the broader
attention-aware design and implementation work.

The owner proposes dropping D2 and keeping related decisions in a thematic ADR:
stable subsection codes let a grep hit recover the surrounding topic, and let an
agent combine relevant blocks from several topics for a complex task. The goal is
less context reconstruction and better joint reasoning, not fewer files by itself.

**Accepted result:** use the thematic carrier for a coherent subject,
with separately addressable significant decisions inside it. Keep individual ADRs
as a valid small-topic or split-out form, not a competing workflow. Neither form
has a second authoritative D2 register.

**Implementation outcome:** the [legacy migration sample](d2-legacy-migration.md) decomposes
accepted decisions, evidence and open work, including the mixed D2-23/D2-49 case.
Its [cutover reference map](d2-cutover-reference-map.md) classified operative versus
historical references and supplied cohesive topic/block boundaries. C94 resolves the
two migration exceptions, preserves compatibility through the tombstone/archive plus
unique aliases, and does not ask the owner to approve unchanged history again.

## Existing shape and the actual choice

[ADR 0012](../decisions/0012-stage1-contracts-and-vocabulary.md) already names F-blocks.
Its final Consequences entry deliberately links F9/F10/F16 to their design owner
instead of duplicating them. [ADR 0014](../decisions/0014-code-rules-catalog-and-language-profiles.md)
groups six numbered decisions, but their names are not stable subsection codes and
its file-level status does not express separate acceptance scopes. These are
source-document observations, not a fresh approval or implementation audit.

The choice is **physical grouping**, not whether to preserve a decision's identity,
rationale or owner acceptance. Both alternatives must preserve those. Both can
remove D2. Removing D2 does not logically depend on selecting compound ADRs.

| Criterion | Thematic ADR, coded decision blocks | Individual ADRs, thematic navigation |
| --- | --- | --- |
| Understand a related set | One local reading context; common problem stated once | Follow links or assemble the set; shared context can still have one owner |
| Refer to one commitment | Needs a stable block identifier and boundary | File identity normally supplies the boundary |
| Change one commitment | Replace the affected block; protect neighbours and shared premises | Replace a record; still check constraints in other records |
| Parallel editing | More likely to touch the same file or shared introduction | Better physical isolation, though contradictory decisions remain possible |
| Complex cross-topic task | Assemble relevant blocks and their constraints | Assemble relevant files and their constraints; no inherent semantic disadvantage |
| Reading cost | Fewer jumps for a cohesive topic; can over-fetch history/unrelated clauses | Less local over-fetch; can under-fetch context or repeat it across records |
| Growth and history | Topic may become a hard-to-navigate specification or chronology | File collection may become a hard-to-navigate catalogue |
| Additional mechanism | Block identity, scope and replacement convention | Topic navigation and cross-record links |

These are inspectable trade-offs, not measured time or token savings. A fair
comparison gives individual ADRs a usable topic view; comparing a curated thematic
file to an unindexed pile of files would predetermine the answer.

[Nygard's original proposal](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
favours a small file per significant decision, stable numbering and retained
superseded records. Its strongest argument here is bounded reading and independent
history, not a mandatory file format. [arc42 section 9](https://docs.arc42.org/section-9/)
also permits sections, lists or tables and cautions against redundant text. A
thematic carrier is a local adaptation of these principles, not a demonstrated
improvement over the original practice.

## Minimal thematic structure

The topic states its purpose and scope, then contains decision blocks. A block
records the question/commitment, decisive premises, the choice and why alternatives
lost, material consequences, and when the reasoning needs reconsideration. Link
supporting research and implementation work instead of copying either into it.
Short decisions can express this in a few paragraphs; no mandatory field list for
every small clause is proposed.

An indivisible decision may have explanatory subclauses without separate IDs or
states. Give an independent ID to a commitment that can meaningfully be accepted,
replaced or referenced on its own. Indentation is not decision granularity.

### Addressing example — illustrative, not a renumbering of ADR 0014

```text
0014-code-rules-....md
  Topic: project checks and rule ownership
  ADR-0014-D03 — standard linter configuration
  ADR-0014-D04 — project-declared check runner
  ADR-0014-D05 — initialization of check commands
```

Prefer a stable numeric identity plus a readable title/keywords. A candidate full
token is `ADR-0014-D04`: unique across topics, usable with fixed-string search, and
not changed when a title or display order changes. The suffix identifies a decision,
not its current fourth position. Do not reuse a retired code. Semantic-only names
are easier to guess but more vulnerable to terminology changes; keep them in titles
and search terms rather than making a taxonomy part of identity.

The canonical heading or explicit anchor must retain the ID independently of title
changes; exact Markdown syntax and its checker remain implementation design. A
line number is a convenience, not a durable identity. If a topic is later split,
preserve existing IDs and leave a navigational pointer at old reference locations;
do not create another authoritative copy. Existing F-codes need compatibility,
not wholesale recoding merely to make historical documents uniform.

### Accepted record, not an approval queue

The simpler candidate keeps unresolved options and draft replacements in **design**
or the relevant task detail. ADR blocks capture accepted commitments. An open-work
link in the topic may make an in-flight change discoverable without presenting it
as a new accepted block. This uses the existing locked-ADR boundary and avoids
recreating Pending → Approved → Verified inside each section.

Once the owner explicitly accepts a clearly bounded proposition, record that scope
in its block; do not require the same substantive acceptance again merely to move
a row. No magic approval word, manually copied Git hash or landing transition is
proposed. Git can recover committed recording history; it cannot manufacture
missing owner acceptance. Ambiguous scope needs clarification, not inferred approval.

A block may identify that it is accepted, superseded or withdrawn. That is disposition,
not a prescribed workflow to traverse. Implementation status and test evidence stay
with work/evidence owners. A proposed-block variant is still possible, but has not
earned an additional state surface while design already carries the open work.

Adding a decision does not require approval of the entire topic again. If several
changes are inseparable, present and accept their explicit combined scope together;
independent IDs must not force separate owner turns. Editorial corrections do not
create a new decision. Material replacement gets a new decision ID and a visible
supersedes link, retaining the old rationale. The old decision remains in force
until replacement or explicit withdrawal, not merely because a draft challenges it.
Acceptance nevertheless does not prove present applicability: when new evidence
undermines a premise, expose that limit beside the decision and link the investigation.
Do not apply a known-invalid assumption while waiting for its replacement to be accepted.

## Three worked cases

### 1. Significant decision discovered during an ordinary task

The recorded C84/D2-43 case combines a manifest parsing correction with a new
`unreadable` outcome and its user-visible treatment. Sources:
[D2-43](../D2_LEDGER.md) and [C84 archive entry](../TASKS_ARCHIVE.md).
The new outcome is a contract decision, not just another patch attempt.

- **Thematic form:** place the enduring manifest/error-semantics decision under the
  packaging topic, with its rationale and costs. C84 links that block and retains
  implementation/check evidence. No second new D2 row.
- **Individual form:** give the same decision its own ADR and link it from packaging
  navigation and C84. Equally valid semantics; another file is the extra carrier cost.

Do not append the entire task or its test list to a broad packaging ADR. Decide
whether parsing and error semantics form one commitment from their actual rationale,
not from the fact that one task delivered both. This is a migration illustration,
not a proposal to silently move or reaccept the existing record.

### 2. Change initialization without reopening the runner

Use the illustrative D03/D04/D05 names above, not inferred live acceptance states.
Suppose a future task changes how initialization chooses commands. Its context
includes the runner contract and standard-configuration ownership. The agent reads
the theme, explains the proposed D05 delta, and checks it against D03/D04.

If the new initialization respects them, only the changed initialization commitment
needs acceptance. If it silently replaces a project's configuration, the proposal
conflicts with an existing constraint: redesign it or explicitly include that
constraint in the owner-facing change. A new D07 can supersede D05 after acceptance;
unchanged D03/D04 remain untouched. Keeping everything in one file helps visibility,
but does not itself perform this consistency check.

Individual records can provide the same check through links. They are preferable
if these subjects repeatedly evolve independently and retrieving the theme brings
mostly unrelated material; physical separation does not waive the dependency check.

### 3. Ordinary correction, no new decision record

Constructed example: a boundary comparison violates an already accepted limit, and
the fix restores that exact limit with a regression test. Record the task and its
verification, linking the governing decision when useful. Neither representation
needs a new ADR block, an ADR file, or a D2 entry. If the work reveals that the limit
itself should change, that newly exposed fork becomes design work instead.

## From a grep hit to a complex decision

Search is an entry point, not proof that all governing constraints were found.
Reading a matched line alone is insufficient; always expanding every match into
every complete ADR is also an unbounded context cost.

1. Find the decision by ID, domain terms, affected component or existing task links.
   Inspect its disposition, full rationale, topic scope and nearby constraints.
   For a cohesive small topic, reading the whole ADR is the natural default.
2. Follow relevant constraint and replacement links into other themes. Distinguish
   “constrained by” from “related background” in plain prose. A tag match does not
   establish a dependency, and an absent link does not establish independence.
3. Assemble a task-specific comparison: which accepted constraints apply, which
   premises changed, which options conflict, and the exact proposed decision delta.
   Check the set against the product goal and the current implementation/evidence.
4. Present the unresolved trade-off and decisive downside to the owner, with links
   to the full blocks. Let the owner challenge premises or describe a missing use
   case, not only select from the agent's menu. Unchanged constraints are context,
   not requests for approval. Mark unexamined areas and missing evidence honestly.

This assembled view is a working explanation, not another authority to maintain.
Material new rationale goes back to design or the accepted decision, not solely into
a disposable synthesis. Mechanical retrieval can be delegated; the orchestrator
owns the cross-topic reasoning and owner dialogue. Do not introduce a dependency
database, tag classifier or mandatory full-project reread just to enable this.

## Failure tests and boundaries

- **Shared-context drift:** a topic introduction changes from “preserve project
  configuration” to “akmon manages configuration,” while accepted blocks remain
  unchanged. This must be recognized as a material semantic change, not harmless
  editing. Keep decisive premises with their decision; a current topic overview
  cannot retroactively rewrite what was accepted. Later evidence challenges a
  premise visibly rather than silently replacing the historical rationale.
- **False containment:** reading all of the checks ADR misses a packaging constraint
  on where configuration can be materialized. The agent must follow the relevant
  cross-topic boundary; being in one thematic file is not sufficient coverage.
- **Approval multiplication:** one coherent owner choice adds two blocks and triggers
  two approvals plus a file-level approval. Reject that process: acceptance follows
  the presented semantic scope, not the number of storage objects.
- **Ever-growing topic:** readers repeatedly skip relevant clauses or spend most of
  their time on unrelated history. Split the topic or separate historical sections,
  preserving references and rationale. Do not impose a universal “seven decisions”
  cap; the cognitive research does not establish one.
- **D2 deleted, obligations lost:** an old row also contained missing measurements,
  an exception expiry or an implementation blocker. Map each obligation to its real
  task/evidence owner before retiring the old surface. An accepted ADR alone does
  not replace reminders, coverage or implementation verification.

The minimum later controls worth testing are unique/resolvable block references,
unambiguous active/replaced meaning, no material acceptance inferred from containment,
and preservation of legacy links and open obligations. Syntax checks cannot prove
rationale quality, semantic independence or genuine owner acceptance.

## Recommendation, rejected defaults and evaluation

Prefer **one coherent topic file containing small addressable decision records**.
Its expected benefit for this case is making related reasoning available together,
while preserving scoped acceptance and replacement. A single-decision ADR is the
smallest instance of the same convention; splitting is an escape hatch, not a
different approval system. Remove the separate D2 authority in the candidate, but
retain historical navigation and migrate its real obligations deliberately.

Do not select separate files as a universal default merely because the original
ADR convention uses them; retain them when independent evolution and reading make
them cheaper. Conversely, do not select a large topic file just to reduce file count.
Do not add Proposed states everywhere or a second status index before a demonstrated
need. Do not treat automatic acceptance or the removal of useful review as savings.

Compare both representations on the same three cases with the same information.
Check whether a reader can recover the purpose, exact current commitment, alternatives,
affected neighbours and open obligations, and correctly distinguish an editorial
change from a replacement. Track retrieval/reconstruction, avoidable owner questions,
agent effort and maintenance separately. A thematic carrier loses its preference if
it repeatedly hides changed premises or makes relevant context harder to retrieve
than the individual-record view. No behavioral comparison or runtime tests have run
for this note; the benefit remains a falsifiable design hypothesis.
