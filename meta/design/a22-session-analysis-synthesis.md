# A22 — consolidated session-analysis review

> Preserved analysis record, saved at the owner's request beside the
> [independent audit prompt](a22-independent-cross-project-audit-prompt.md).
> This records the independent reassessment and its recommendations, not an accepted
> interaction contract or an experiment result. The [current plan and resume point](attention-and-human-agent-collaboration.md#how-to-resume)
> own subsequent work; [TASKS](../TASKS.md) owns execution state.

## Scope, provenance, and confidentiality

This review combines Akmon's retrospective A22 cases, an owner-supplied external
session audit, and a critical reassessment of the earlier model's synthesis. The
current working tree and staged/unstaged changes were distinguished. Selected local
session messages were checked against the existing evidence notes; this was not a
new census or a replay of all historical implementation checks.

The external audit and its reversible source map remain outside Akmon. Its raw
sessions and repositories are on another machine: this review can check the report's
reasoning and internal consistency, but cannot independently reproduce its extraction.
No private repository or project names, identifying paths, source-map entries, or
verbatim private transcripts are carried into this document. External references
below are section and anonymous case locators in that owner-held report; case IDs
identify claims in the report, not independently verified source records.

The external sessions do not overlap the original A22 sample, but share the owner
and related development practice. They test possible transfer of hypotheses; they
are not independent evidence about other users or population-wide productivity.

## Overall assessment

Keep the accepted mission in [ADR 0015/D01](../decisions/0015-mission-and-resource-allocation.md#d01--product-mission-and-economic-criterion).
Refine A22 around establishing consequential decision ground and matching material
claims to the evidence actually obtained. Retaining the ground across sessions
connects those two concerns. Fewer questions, shorter reports, more agents, or lower
token spend are not success criteria by themselves.

The earlier synthesis correctly favored a bounded pilot and restraint about new
machinery. Its treatment of the external baseline, F1 and F4b was too strong, and
its preferred F3 count was not sufficiently checked. The revisions below supersede
those recommendations, while preserving their rationale for later review.

## Findings and corrections to the earlier synthesis

### External instructions are a comparator, not efficacy evidence

The external audit's late exposure correction (§2.7) reports that 11 of 19 primary
cases had some related instructions available. Only four had the attention-specific
text; one of those four exposures is inferred from an unpreserved working copy.
Importability does not establish reading, compliance, or benefit. The exposure
strata were reconstructed after the outcomes were read, so the comparison is
exploratory rather than confirmatory.

The report's suggestions to transfer wording immediately or treat deployment as
partial pilot evidence (§12.2–12.3) exceed these limits. Its own §14 and §16 preserve
the missing compliance/effect evidence. Compare the text as an additional design
alternative; retain current Akmon guidance as the primary baseline. Do not import
an entire bundle of batching, stopping, default-action and authority rules merely
because it already exists elsewhere. Unavailable facts are not automatically facts
the owner knows, and an unanswered question does not authorize a consequential default.

### Preserve conditional intended-use discovery (F1)

The external sample gives limited support for making intended use an explicit step.
Akmon's C89 and C79 cases nevertheless show why product boundary and actual use can
change a solution. They must not disappear when the external cases are added.
Retain F1 when use changes the decision, design boundary, or acceptance condition;
do not require a heading or restrict the trigger to acceptance wording alone.
The local support is retrospective, not measured prevention of rework.

### Evaluate decision ground, not question format (F2/F3/F4b)

F2 fact gathering is already owned by `Survey`. Investigation in all 19 external
cases does not establish that instructions have no effect; it shows no demonstrated
need for another standalone F2 rule in this sample.

F3 should target consequential missing owner knowledge or priorities. Open questions
and bounded choices are alternative ways to obtain that ground; neither form wins
by definition. Do not delay an owner-only question behind irrelevant investigation,
or pause independent authorized work.

Current F4b already forbids substituting a solution menu for missing problem ground.
Useful menus, including scope clarification before investigation, do not refute that
rule. The external audit sometimes scores a stronger prohibition that A22 does not
propose. Tool calls before a menu do not establish the quality of the underlying
problem framing. Retain useful menus as negative controls against overrestriction.

### Reuse requires relevant evidence, not a source-location shortcut (F4a)

The external stale-diagnosis case (§6, P14) supports checking a consequential claim
before relying on it. It does not justify trusting every internal record or fully
re-deriving every external conclusion. Check subject, changed premises, freshness,
supporting evidence and consequence of error. Preserve unchanged accepted rationale;
new evidence reopens the affected claim, not every decision.

### Test claim calibration first, without assuming it is the remedy

The external audit reports three distinct failure episodes across two repositories:
an assertion about live state drawn from a deployment template (P10), an imported
diagnosis accepted without adequate verification (P14), and a premature completion
claim (P08). These motivate a first bounded comparison of claim calibration.

Local evidence also separates architecture acceptance from implementation checks.
The sampled messages behind [decision-review session cycles](decision-review-session-cycles.md)
support that distinction. Historical assistant reports remain reports, not fresh
verification of the old code. Repeated review can expose real defects; reducing the
number of review rounds indiscriminately would lose useful work.

[R1/R3/R7 and pre-close reconciliation](attention-and-human-agent-collaboration.md#truthful-and-proportionate-reports)
already specify much of the desired behavior, and AP2 already includes a false-closure
control. Test the incremental value of a targeted clarification. A disclaimer attached
to the same unjustified action does not pass; neither does unnecessary hedging when
the evidence is sufficient. The proposed intervention's benefit remains unmeasured.

### Reconcile counts before relying on them

External §9.1 lists four F3 clusters, while §14 lists five. P01 is explicitly scored
as support in its card and the matrix but omitted from the four-cluster list. Thus
the previous synthesis's preference for four as the reliable count was premature.
F1 also differs between its matrix and aggregate description. Rebuild the descriptive
counts from case-level definitions before reuse; do not choose the smaller or larger
number as an adoption threshold. These counts are not effect sizes.

## Mission implementation and revised A22 problem statement

Proposed problem statement, now recorded for design refinement:

> Determine which minimal changes to existing guidance and examples help agents
> establish consequential decision ground, obtain the owner's necessary contribution,
> verify the result, and retain the rationale for later work. Assess decision quality
> alongside owner and agent costs, allowing an outcome that needs no new rule.

Three connected concerns organize the work:

1. **Decision ground:** investigate accessible facts, recover known constraints, and
   elicit only the missing owner knowledge or priorities that can change the action.
2. **Truthful result:** distinguish direct evidence, inference and unresolved checks;
   reconcile material causal and completion claims with the checked subject.
3. **Continuation:** recover the goal, accepted rationale, limitations and next action
   from existing records without repeating intake. Test the current `Record`/ADR 0016
   arrangement before proposing a new memory mechanism.

The ADR 0016/C94 workflow change is an implemented process change. Its human-attention
benefit has not been measured, and its completion does not accept the broader A22
protocol. README and ADR 0015 already distinguish the mission from a demonstrated
advantage. MODEL needs only clarity about whose routine effort is reduced. The older
`tokens + owner attention` expression in the routing design needs alignment with the
accepted treatment of distinct costs.

## Recommended modification map

This table preserves the review's recommendations; current progress is owned by the
linked plan and tasks, not by this historical table.

| Surface | Recommended change | Boundary |
| --- | --- | --- |
| [Main A22 design](attention-and-human-agent-collaboration.md) | Refine the brief, give one current resume point, separate completed workflow work from untested behavior | Keep research and rejected branches as history |
| [AP2 comparison](attention-frame-comparison.md) | Add the sanitized synthesis, revise F1–F4b interpretation, and specify separate claim-calibration and decision-ground comparisons | Historical cases remain retrospective; examples are not executed results |
| Main design AP0–AP5 | Compare individual changes, then apply surviving candidates on fresh tasks | Current guidance and examples-only remain viable outcomes |
| [A22/C86](../TASKS.md) and their detailed completion criteria | Permit owner-accepted no-new-rule disposition and distinguish insufficient evidence | C86 must not claim unperformed implementation shipped |
| [MODEL priority 1](../../MODEL.md#mission-and-priorities) | Agents carry routine investigation; reduce avoidable owner explanation and reconstruction | Preserve the accepted mission and factual independence |
| [Routing design §9.6](model-routing.md#96-owner-integration--attention-is-the-second-budget) and C19 | Separate costs; specify observable interaction events and voluntary owner assessment | Counts are not attention or decision-quality measurements |
| Earlier A22 plan and D2 evidence trail | Point to the current resume section | Do not restart the completed carrier redesign |
| Operative pipelines, guardrails and examples | After evaluation and acceptance, implement only the useful delta at its owning surface | No protocol, skill, hook, model binding or automatic approval is accepted by this report |

## Recommended evaluation sequence

1. Reconcile the evidence cards and aggregates; compare the available external
   wording without treating it as effective. If full text or source verification
   needs the other machine, name that gap and continue local case preparation.
2. Test material claim calibration first: indirect evidence, incomplete checks,
   and a justified confident conclusion. Assess the conclusion and action, not
   the presence of uncertainty vocabulary.
3. Test decision-ground routing separately: unknown/recorded use, inspectable fact/
   owner priority, consequential choice/reversible detail. Preserve both local and
   external cases and include useful early menus.
4. Distinguish the value of examples from the value of a rule. Hold case facts,
   authority and model conditions fixed; add one targeted instruction at a time.
   Use fresh variants rather than counting familiarity with a repeated owner case
   as improvement. Separate retrospective specifications from executed comparisons.
5. Apply surviving behavior on bounded fresh tasks and a cold-resumption case.
   Record material omissions, owner corrections, unnecessary questions, actual
   rework and optional owner assessment. Agent cost includes retries, delegation,
   integration and latency; unavailable costs remain unknown.

Each trial needs a scope, budget and stopping condition before execution. Possible
outcomes are a specifically accepted change, an accepted decision to retain current
guidance, or insufficient evidence with a named remaining question. No-new-rule is
an admissible decision, not a claim of proven equivalence. An inconclusive trial is
not successful completion of A22 by default.

## Adjacent work and deferred alternatives

C86 implements a selected result; it is not an obligation to invent a new protocol.
C19 remains deferred until observations prove useful enough to justify collection.
C56/C60 matter if the chosen surface adds always-loaded material; they are not
prerequisites for the design comparison. Corpus statistics do not become C82 harness
measurements without the relevant versioned evidence. Resource evaluation includes
the cost of checking and integrating delegated work, not merely the dispatch count.

External incidents involving secret access and global configuration merit a separate
bounded authority review if taken up. They do not widen A22. New skills, hooks,
questionnaires, persistent profiles, attention scores and automatic acceptance are
not justified by the reviewed evidence.

## Evidence navigation

- [Portable external audit prompt](a22-independent-cross-project-audit-prompt.md):
  research scope and original evidence discipline; not updated retroactively to fit results.
- Owner-held external audit: §2.7 exposure correction; §6 case cards; §7 and §9
  conflicting aggregates; §12 and §14 recommendation tension; §16 missing evidence.
- [Local AP2 cases and controls](attention-frame-comparison.md).
- [Local historical sample and limits](attention-and-human-agent-collaboration.md#historical-session-evidence).
- [Additional local review cycles](decision-review-session-cycles.md).
- [Accepted record model](../decisions/0016-decision-records-and-owner-acceptance.md)
  and [implementation archive](../TASKS_ARCHIVE.md) for C94.

The [current resume point](attention-and-human-agent-collaboration.md#how-to-resume)
is the entry for the next session; this report preserves why the plan changed.
