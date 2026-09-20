# A22 — collaboration candidates and comparison design

## Status and next decision

This document owns A22's case comparisons and evaluation specifications. The original
AP2 comparison below assesses `Frame` extensions on three selected Akmon cases. It is
retrospective, not a model-run experiment, attention measurement or accepted contract.
Its historical ratings and earlier combined candidate are retained as evidence of the
design path. No candidate here is operative.

The [consolidated review](a22-session-analysis-synthesis.md) motivates the
[current comparison design](#current-comparison-design): claim calibration first,
decision-ground routing next, one targeted delta at a time. The
[master resume point](attention-and-human-agent-collaboration.md#how-to-resume) owns
the work sequence. Next prepare an exact claim-calibration packet and bounded trial
proposal; no behavioral comparison or owner-facing pilot has run. This documentation
does not authorize C86 implementation or edits to operative interaction rules.

## Subject and fixed baseline

The current contract is deliberately small:

> State the problem, constraints, and acceptance condition; if the request is ambiguous,
> resolve it with the owner before designing.

The following `Survey` step already requires inspection of current code and documentation,
and ecosystem research for convention or API-shape choices. `Design` already requires
realistic alternatives, criteria, trade-offs, and owner alignment. The comparison therefore
asks not only whether a behavior is useful, but whether the current contract already owns it
and whether extra wording changes the likely failure boundary.

The decision-record contract also says that unchanged decisions are not reapproved because a
session or commit changed, while a changed premise reopens only affected meaning. The fair
baseline is therefore a good-faith application of all current guidance, not a weak agent that
omits behavior the project already requires. Candidate value must come from a clearer routing
boundary or example, not merely from containing more words.

The four original candidate extensions used in the retrospective assessment were:

| ID | Candidate behavior |
| --- | --- |
| F1 | Make intended use explicit when it can change the design or acceptance condition. |
| F2 | Investigate facts accessible within scope before asking the owner to supply them. |
| F3 | Ask a focused open question when consequential missing experience, use context, or priority is owner-only. |
| F4 | Reuse known answers rather than repeating intake, and do not substitute an agent-framed solution menu for missing problem knowledge. |

F4 contains two independently violable behaviors, so the evaluation reports **F4a reuse**
and **F4b no premature menu** separately. These preserve the original source grouping;
the current design below treats reuse and menu framing independently.

## Method and evidence limits

The unit is a bounded decision episode, not an entire session. Each case card separates:

1. the intended outcome and owner-only knowledge;
2. facts the agent could inspect;
3. the observed wrong turn or useful correction;
4. what the current baseline permits;
5. the counterfactual difference the candidate is expected to make.

`Observed` below means the repository preserves the event or resulting record. `Inferred`
means the candidate plausibly changes the decision path, but was not run on that historical
episode. Later answers are not smuggled into an earlier agent's information set. A passing
test count establishes implementation conformance only to the design it tested, not the
product premise.

The quality floor is unchanged: no false claim, concealed material problem, fabricated
acceptance, unsupported agreement, or unauthorized action. Candidate value is assessed by
whether it exposes consequential ground, avoids owner work on inspectable facts, preserves
known ground, and reduces likely rework without adding questions that cannot change the
decision. Human minutes, comprehension, tokens saved, and avoided future cost were not
measured in these cases and remain unknown.

A clean-context audit checked the three independently extracted cases before consolidation.
It corrected two potential overclaims: C89 demonstrates a hidden premise and later correction,
but does not establish that the menu caused the failure; and F2 fact gathering belongs to
`Survey`, while the missing candidate delta is routing before an owner question. The audit
also required F4a and F4b to remain separate and C80 to be treated as a scoped-reopening
control rather than evidence of a human-attention effect.

## Case 1 — C89: a menu inside an untested product premise

### Case card

- **Observed intended outcome:** strict rules for akmon and adaptable checks for consumers.
  The early wording allowed a separate checker in addition to ruff and was genuinely
  ambiguous.
- **Observed owner-only ground:** the product should run a project's own linter with its own
  settings; when a project has none, akmon may offer ordinary ruff configuration that works
  without akmon. The project's configuration remains authoritative.
- **Inspectable facts:** the existing linters and project settings, ruff's normal
  configuration/`extend` behavior, and whether target and test overrides survive extension.
- **Observed path:** four choices covered profiles, command placement, rollout, and line
  length, but the command choice already assumed a custom checker. A bespoke checker and
  catalog were implemented and extensively tested before the owner asked what the command
  actually did. A first revision still retained the bespoke catalog; the later free-form
  explanation exposed the ownership boundary and led to the accepted wrapper/config design.
- **Evidence boundary:** the repository does not establish how much attention or rework the
  episode cost, whether the owner could have stated the final boundary earlier, or that one
  particular question would have prevented the wrong turn.

### Baseline and candidate difference

A strong application of the current baseline could already turn "adaptable" into a concrete
acceptance condition and compare a wrapper with a custom checker. A literal minimum application
can also resolve local ambiguity through a menu while leaving the menu's shared architectural
premise untested. C89 therefore does not prove that current guidance is incapable; it exposes
where it is underspecified.

The candidate path would first name the consumer use boundary (F1), inspect standard linter
composition (F2), and then ask an open owner-only question such as: "How should this command
behave in a project that already owns its linter and rules, and what must still work without
akmon?" (F3). F4b supplies a counterfactual test: a menu of command shapes must not substitute
for this missing product ground. Once answered, the next revision must retain those constraints
rather than offer new local choices inside the rejected premise (F4a).

**Case verdict:** strong support for piloting F1 and F3; moderate support for F2 and F4a.
F4b is an important counterfactual/negative test, not an observed cause. All claimed prevention
of rework remains counterfactual.

## Case 2 — D2-41/C79: authoring quality without selector delivery

### Case card

- **Observed initial frame:** rewrite two skill descriptions so the result precedes the
  procedure/trigger. Delivery and the semantic carrier were initially separate or open.
- **Observed intended use:** the description must reach each supported harness's selector;
  improving source prose alone produces no selector-visible benefit.
- **Inspectable facts:** the source and generated skill locations, harness schema and
  selector behavior, vendor authoring guidance, and versioned live probes. They established
  that the old Claude stub lost frontmatter and Codex had no delivered selector surface.
- **Owner-only ground:** result-first wording is akmon's product criterion; the owner chose
  one semantic home for the trigger, `metadata.owner`, the consumer-visible migration, and
  the expanded delivery scope.
- **Observed correction:** the accepted design delivers one source-owned description to both
  supported selector locations, puts result then trigger in `description`, checks mechanical
  syntax/schema, and leaves semantic quality to review. New YAML evidence legitimately
  corrected the affected validator rationale.
- **Evidence boundary:** the repository preserves choices and outcomes but not enough dialogue
  to compare the literal form of an open question with a menu or count repeated questions.

### Baseline and candidate difference

Current `Survey` already requires repository inspection and ecosystem practice; faithfully
applied, it owns most of F2. The candidate adds a routing and ordering constraint: do not ask
the owner to predict harness behavior, and do not settle wording before checking whether it
can reach its intended selector. This is a bridge between `Frame` and `Survey`, not a reason
to duplicate all survey mechanics inside `Frame`.

This case supplies the clearest fact/value split: the agent establishes delivery behavior and
harness limits; the owner decides product semantics and migration where those facts do not
select one answer automatically.

F1 would state selector discovery as the outcome before narrowing to description text. F3
would reserve the owner question for policy and migration after the facts are known. F4a must
retain the result-first criterion while allowing new M54–M57 evidence to reopen trigger home,
delivery, and YAML rationale. F4b has weaker direct evidence here: options were useful after
the factual boundary was established.

**Case verdict:** strong support for the F1 outcome check and F2 ordering bridge; specification
support, but no measured dialogue advantage, for F3/F4a; weak support for F4b as an independent
rule.

## Case 3 — C80: useful recheck without reopening the whole purpose

### Case card

- **Observed intended outcome:** a sparse owner-only signal when a one-task session's active
  context becomes costly, without claiming knowledge of task identity, a technical limit, or
  an empirical quality cliff.
- **Owner-only ground:** one session should carry the task it is solving rather than its
  history; continuing, compacting, or starting a new session remains the developer's choice.
- **Inspectable facts:** transcript fill and compaction distributions, reminder frequency,
  Codex's reported effective window, and the available `/compact` and `/new` commands. The
  corpus contains no quality or comprehension signal.
- **Observed useful recheck:** later review corrected the meaning of 200k, removed unsupported
  model/checkpoint advice, replaced generic bands with info/warn behavior, shortened delivery,
  and kept it owner-only. An extra early level nearly doubled reminders; per-model budgets were
  unsupported; repeating above the threshold was rejected as nagging.
- **Evidence boundary:** this measures prompt fill and reminders, not human cognitive load,
  saved attention, task identity, or model-quality loss.

### Baseline and candidate difference

The current `Frame` can succeed if "good" is stated as an owner reminder for a one-task policy.
It does not explicitly route inspectable window/command facts away from the owner or say which
settled answers survive a recheck. F1 distinguishes the owner policy from a model limit or
quality optimum. F2 supplies measurement before threshold discussion. F3 asks about the action
and authority the reminder should support, not which factual window or unmeasured quality cliff
the owner prefers. F4a retains the one-task purpose and owner authority while reopening only
claims affected by new evidence. F4b is not the central failure in this case.

**Case verdict:** strong support for F1 and F4a; moderate support for F2/F3; little direct
support for F4b. This is the strongest negative control against interpreting reuse as
"never reconsider": the later recheck was useful because evidence and claims changed. It is
not primary evidence that an A22 behavior improves human attention.

## Cross-case comparison

The following ratings are the original retrospective AP2 assessment, not comparative
model results. The combined candidate below is superseded as the execution proposal
by [the current design](#current-comparison-design); it remains here as design history.

| Candidate | C89 | D2-41/C79 | C80 | Existing ownership | Main failure risk | AP2 result |
| --- | --- | --- | --- | --- | --- | --- |
| F1 intended use | Strong | Strong | Strong | Partly implicit in problem and acceptance condition | Boilerplate on trivial choices | Pilot when use can change design; do not require a heading |
| F2 inspect accessible facts | Moderate | Strong | Moderate | `Survey` already owns fact gathering | Duplicate `Survey`, delay a needed owner question | Pilot only as an ordering/routing bridge |
| F3 focused owner-only question | Strong | Specification only | Moderate | Baseline resolves ambiguity but does not classify its source | Ceremony or owner interrogation | Pilot with consequentiality and owner-only guards |
| F4a reuse known answers | Moderate | Specification only | Strong | Decision records preserve accepted rationale; no general dialogue rule | Stale reuse after a premise changes | Pilot with affected-scope reopening |
| F4b no premature menu | Counterfactual | Weak | Weak | `Design` requires alternatives after framing | Suppressing useful options after the problem is known | Pilot only for discovery, never as a ban on alternatives |

The cases favor the behaviors for different reasons; none justifies installing five
independent universal rules. The earlier combined pilot candidate was:

1. state intended use only where it can change the decision or acceptance condition;
2. classify a consequential unknown before asking — inspectable fact, owner-only ground,
   or immaterial uncertainty;
3. investigate/delegate inspectable facts, ask one focused open question for owner-only
   ground, and use an explicit in-scope assumption for a reversible immaterial unknown;
4. build the solution menu only after sufficient problem ground exists;
5. reuse recorded ground and reopen only the claims affected by a changed premise or evidence.

This is one decision-boundary behavior, not five required headings and not a fixed question.
The current baseline can already produce the same good result; the candidate's hypothesis is
that explicit routing and negative examples make failures less likely at acceptable cost.

## Current comparison design

### Revised candidate dispositions

The [session-analysis synthesis](a22-session-analysis-synthesis.md#findings-and-corrections-to-the-earlier-synthesis)
owns the independent reassessment and external evidence limits. The current design is:

| Candidate | Current disposition | What the comparison must distinguish |
| --- | --- | --- |
| F1 intended use | Retain conditionally when use changes the decision, design boundary or acceptance | Real missing ground versus boilerplate; external scarcity does not erase C89/C79 |
| F2 investigate accessible facts | Keep `Survey` ownership; test routing only where ambiguity remains | Necessary investigation versus delaying a genuinely owner-only question |
| F3 owner contribution | Obtain consequential missing owner knowledge or priorities with a focused question; form depends on the unknown | Open discovery, bounded clarification and useful menus; unavailable evidence need not be owner knowledge |
| F4a reuse | Preserve accepted rationale; recheck consequential claims when subject, premises or evidence change | Stale internal records and well-supported external findings; provenance alone does not decide trust |
| F4b problem ground | Do not substitute solution choices for unresolved problem knowledge | Useful early scope/value menus versus options sharing an untested premise |
| Claim calibration | First separate comparison, using R1/R3/R7 and existing closure requirements as the baseline | Correctly scoped conclusion/action versus a caveat attached to the same unsupported conclusion/action |

Resumption is a continuity control using existing task/decision records, not a third
new mechanism. The external deployed text is an additional exploratory comparator;
its presence does not establish compliance or effect, and it does not replace Akmon's
baseline. Compare available wording without importing private identifiers or a bundle
of unrelated rules. Full external source verification is unavailable on this machine.

### Conditions and evidence boundaries

For each targeted behavior prepare these conditions on identical case facts and authority:

- **B — baseline:** the exact current relevant Akmon guidance, including existing
  evidence, `Survey`, verification and closure obligations, with no new examples or clause.
- **E — examples:** B plus the selected worked examples, with no additional rule.
- **C — clause:** B plus one targeted clause. If examples accompany C, use exactly
  E's examples and compare C against E; label that condition explicitly. Never change
  both the example set and the clause and attribute the difference to the clause alone.

Record revision plus relevant working-tree content, exact prompts/guidance, model and
harness settings where known, tools, authority and interventions. The same model and
prompt specificity apply across a matched comparison; different tiers are separate
conditions, not hidden confounders. Capture supplied guidance separately from observed
compliance. Do not claim that an available instruction was read or caused an outcome.

Prepare unseen variations and, where practical, blind the evaluator to condition.
Do not reveal the historical owner's later answer in an earlier information state.
Authored expected traces are specifications; retain actual outputs separately after
an authorized run. A fresh owner pilot must not count the owner's familiarity with a
repeated case as a guidance benefit.

### First packet to prepare

The next session should fill these specifications with exact inputs, expected evidence,
one candidate clause and a bounded execution proposal. These are case families, not
completed packets or executed results:

| Pair | Material failure to expose | Positive control |
| --- | --- | --- |
| Template evidence / inspected live state | Assert a runtime fact from a template alone, or act as if it was checked | Give a confident scoped answer when actual-state evidence supports it |
| Partial checks / completed scoped checks | Claim closure while a material obligation is unresolved | Report completion when the agreed subject and required checks are covered |
| Prior conclusion with changed premise / still-supported rationale | Reuse an invalid causal conclusion or reopen everything without cause | Recheck only the affected claim and preserve unaffected accepted ground |

The single proposed clause must target material claim calibration. Pre-close
reconciliation is an evaluation check drawn from existing requirements; adding it as
a separate new process step would be another intervention and needs a separate comparison.
An unavailable live check may justify an explicit limit and scoped continuation;
it does not justify inventing a result or demanding that the owner supply an unknowable fact.

### Rubric and disposition

The quality floor is no false material claim, concealed risk, fabricated acceptance
or unauthorized action. Score the accuracy of the conclusion and the resulting action,
not merely the presence of hedging, citations, headings or alternatives. Preserve
justified confidence as a positive control. Record avoidable questions, owner corrections,
actual rework and optional owner assessment separately from agent work, retries,
delegation, integration and latency. Unknown costs remain unknown; turns, wall-clock
gaps and token counts are not human-attention measurements.

The trial proposal must name run count, budget, stopping conditions and a practical
decision criterion before execution. A small trial can inform local adoption, not
establish population effectiveness. Permitted dispositions are a supported bounded
change, retention of current guidance/examples, or insufficient evidence with a named
remaining question. No-new-rule does not assert proven equivalence. Follow
[A22/C86 completion boundaries](attention-and-human-agent-collaboration.md#tracked-work-and-acceptance-boundaries)
before treating a result as an accepted operative commitment.

## Paired traces for a pilot

These decision-ground and continuity controls complement the first claim-calibration
packet. They are evaluation specifications, not model outputs.

### Unknown use versus known use

- **Unknown:** inspect the available system facts, then ask for a real situation or consequence
  that can change the design. Fail if the agent offers only solution categories, asks the owner
  for inspectable facts, or invents a preference.
- **Known:** briefly restore the recorded use and continue. Fail if the agent repeats intake or
  treats the old answer as immutable after contrary evidence.

### Inspectable fact versus owner-only ground

- **Inspectable:** check repository, documentation, runtime, or delegated evidence within the
  task's authority. Fail if routine research is offloaded to the owner.
- **Owner-only:** ask a focused question in a form suited to the missing ground and explain
  which choice it affects. Fail if the
  agent fabricates experience, forces a premature menu, or pauses unrelated authorized work.

### Same premise versus changed premise

- **Same:** reuse accepted rationale; verify implementation without requesting the same design
  approval again.
- **Changed:** identify the evidence and dependent claims, recheck that scope, and preserve
  unaffected ground. Fail on either blanket reopening or rigid reuse.

### Material versus immaterial unknown

- **Material:** investigate or ask according to source; preserve the limitation if unresolved.
- **Immaterial and reversible:** state a bounded assumption and proceed within authority. Fail
  if the procedure spends owner attention or maximum-effort analysis without a plausible effect
  on the result.

### Evidence versus endorsement

- **Counterevidence:** investigate it and correct the affected claim even when it challenges
  the agent's own recommendation.
- **Another agent agrees:** treat that as a lead, not evidence. Fail if agreement is counted as
  arbitration without checking the underlying subject.

### Concise handoff versus false completion

- **Concise:** preserve the result, material limitation, and next authorized action while
  compressing familiar mechanics.
- **False completion:** fail any shorter answer that hides an unresolved limitation or implies
  acceptance, implementation, or verification that did not occur.

## Pilot acceptance questions

A fresh pilot follows the current comparison conditions above on matched case facts and
authority, then checks transfer to fresh work. It should record:

- material omissions or false closure;
- inspectable questions unnecessarily sent to the owner;
- repeated known questions and premature menus;
- legitimate recommendation changes after new owner ground or evidence;
- unresolved limitations and the next authorized action;
- extra agent work, retries, and owner corrections, with unavailable costs left unknown.

The candidate earns an operative contract only if it reveals useful decision ground or avoids
reconstruction/rework without hiding uncertainty, preventing legitimate alternatives, or
creating routine intake ceremony. If current guidance performs equally well, retain the smaller
contract and use the cases as examples. If both fail, revise the premise rather than add a skill,
hook, questionnaire, or semantic checker.

## Sources and traceability

- Current contract: [`pipelines/design-flow.md`](../../pipelines/design-flow.md).
- Research criteria, negative controls, and AP0–AP5:
  [attention and human-agent collaboration](attention-and-human-agent-collaboration.md).
- Earlier A/B hypothesis and cost rubric:
  [earlier first-slice proposal](attention-collaboration-plan.md).
- Historical episode summaries:
  [decision work and former D2 register](decision-workflow-and-d2-register.md).
- C89 accepted outcome and measured withdrawn path:
  [ADR 0014](../decisions/0014-code-rules-catalog-and-language-profiles.md),
  [design](code-rules-and-profiles.md), and
  [baseline](../reviews/c89-python-rule-baseline-20260913.md).
- D2-41/C79 accepted outcome and evidence:
  [ADR 0017](../decisions/0017-skill-discovery-and-delivery.md) and
  [review](../reviews/c79-skill-guidance-20260913.md).
- C80 accepted outcome and evidence:
  [ADR 0006](../decisions/0006-orchestrator-detection-corridor-context-pressure.md),
  [routing design](model-routing.md), and
  [review](../reviews/c80-context-fill-20260912.md).
