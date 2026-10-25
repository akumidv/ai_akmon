# A22 fresh-task and cold-resumption pilot

The offline screen covers [A44](../reviews/a22-cold-resumption-codex-gpt-6-sol-pilot.md),
[C98](../reviews/a22-c98-cold-resumption-codex-gpt-6-sol-pilot.md) and
[C33](../reviews/a22-c33-cold-resumption-codex-gpt-6-sol-pilot.md). Both arms
recovered each case (M177–M179). A44 breached its resource controls; C98 and
C33 used automated descendant-inclusive gates and simple-model readers.
No pointer corrected an observed recovery failure. The owner accepted
[ADR 0019 D08](../decisions/0019-collaboration-guidance-from-a22.md#d08--close-the-cold-resumption-pilot-without-a-new-rule):
close this pilot branch without a standing resume-point rule or live transfer.
A22's broader disposition remains open.

## Question and boundary

Can an agent starting fresh recover a task's goal, accepted rationale, material
limits and next authorized action from akmon's existing records without asking
the owner to repeat settled ground? Does a compact, link-based resume point
improve that recovery without hiding changed premises or creating routine intake?

This follows the [P3 qualification stop](../decisions/0019-collaboration-guidance-from-a22.md#d07--stop-the-current-p3-comparison-at-its-qualification-floor). P3 supplied no B/C comparison; its decision-ground routing clause is not a treatment in this pilot. The pilot concerns continuity on fresh work, not a second reading of P3 or a claim that a shorter report is inherently better.

## Smallest useful comparison

Use two conditions on the same authorized task state:

- **Current practice:** the agent receives the normal repository entry point and the task request, then reads the relevant task, decision and evidence records as needed.
- **Resume point:** the same inputs plus one short pointer assembled only from those records. It names the goal, accepted choice and reason, unresolved material issue, evidence limit, and next authorized action, with links to the owning records. It gives no new authority or private answer key. The pointer is an evaluation input, not a new standing report or source of truth.

The first deliverable was one complete cold-resumption comparison on a held-out task state. The later C98 and C33 cases tested changed evidence and acceptance boundaries. A live transfer check would use one genuine fresh owner-facing task and a new session boundary only if an offline recovery gap warranted it; none was observed here.

## Case selection and controls

Prepare at least one case each for discovery, implementation handoff and acceptance. Use facts the subject has not seen in a previous A22 trial. Each case has an inspectable task record, an accepted decision or explicit absence of one, a material limit, and one next action. Include a same-premise control, where accepted rationale should be reused, and a changed-premise control, where only the affected choice should reopen. A concise handoff must not become false completion. The [paired traces](attention-frame-comparison.md#paired-traces-for-a-pilot) and [pilot acceptance questions](attention-frame-comparison.md#pilot-acceptance-questions) supply the case shapes; exact dossiers and answer keys must be frozen before any model call.

Do not ask the owner to re-answer a known question merely to create a measurement. The live task is selected prospectively from normal work after the offline cases, with the owner's intended outcome and authority boundary recorded before the pause. A second reading of the same learned case is a mechanics check, not independent evidence of benefit.

## Observations and decision rule

For each answer, retain the prompt, record versions, inspected sources, requested owner input, next action and correction. Judge whether it:

1. Restores the goal, accepted rationale and actual task state without inventing acceptance or completion.
2. Names the largest material limit and distinguishes a changed premise from a settled one.
3. Takes the next authorized step, or asks one focused owner question only when the missing ground is owner-only.
4. Avoids repeated intake, premature options and unsupported confidence.

Compare the two conditions on these observable failures before weighing effort. Record owner corrections and actual rework separately from hypothetical savings. Time, tokens and attention can be reported only where measured; an optional owner effort response is informal feedback, not a validated workload score. No single good continuation establishes a population effect or authorizes new guidance.

If current practice passes and the pointer adds no useful recovery, retain the smaller contract. If the pointer improves recovery without a material regression, propose the smallest reusable form and seek a separate operative decision. If both fail, revise the premise or the record quality before adding a skill, hook or questionnaire. Any material false closure stops a candidate from being recommended.

## Pilot disposition and continuation

The three offline pairs found no recovery advantage for a standing pointer.
Their small selected sample cannot prove equivalence or owner attention saved.
The owner accepted retention of ordinary repository discovery and closure of
this pilot branch without a new rule or live transfer. This closes the
cold-resumption branch only; A22's broader disposition and any other
interaction scope remain open.

For task-level continuation in this pilot, the [runner](../experiments/a22-resumption-pilot/run_c98_pair.py)
turns a frozen task case into a sequential two-arm run: it checks source and
packet hashes, clean HEAD, model routing, all descendant usage and stopping
gates before advancing. A planned next case that passes these controls can
run without another routine confirmation. Ask the owner for an open design
choice, missing owner-only ground, work affecting another project, or a new
experimental branch outside the agreed question. A failed gate stops the
dependent call and is reported with retained evidence.

## Alternatives and execution gate

- **Current practice only** is cheapest and may already recover enough context, but cannot measure the pointer's contribution.
- **A long handoff or mandatory questionnaire** may carry more detail, but adds owner and maintenance cost before a demonstrated gap. Keep it out of the first comparison.
- **Accepted disposition:** no standing pointer or live transfer on the completed offline screen; retain the existing records and report their limits.

For any new case, review exact dossiers, source and answer-key separation, model/harness pins, blinded evaluation, the session and token budget, stopping conditions, and any live task's authority before execution. Neither [ADR 0019 D07](../decisions/0019-collaboration-guidance-from-a22.md#d07--stop-the-current-p3-comparison-at-its-qualification-floor) nor the old P3 resource ceiling applies to a new pilot call. A22 stays active and C86 blocked until the owner accepts a final outcome and any implementation scope.
