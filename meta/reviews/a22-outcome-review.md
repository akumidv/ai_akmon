# A22 outcome review

> **Point-in-time review.** This record summarizes the A22 material visible in this
> checkout. It does not change the task, evidence, decisions, or operative guidance.

## Verdict

A22 produced bounded, decision-relevant results; it did not produce evidence for a new
general interaction rule. The claim-calibration comparisons detected no benefit, the
decision-ground routing comparison stopped at its pre-registered qualification floor,
and the selected cold-resumption screen showed no observed pointer recovery gain. These
are different outcomes: a negative comparison, an incomplete comparison, and a small
screen with no observed gap. None establishes that the candidate behaviors are
equivalent or never useful.

The project records already dispose of the claim-calibration rule (ADR 0019 D01), stop
the current P3 packet before B/C (D07), and close the selected cold-resumption pilot
without a new rule (D08). A22 remains active because its broader completion condition
still calls for an owner disposition. The concrete remaining action is that disposition;
the owner can accept the existing recommendation to close this evaluation without a new
operative rule, or name a specific remaining question for a separately designed study.

## Original goal

A22's goal was to improve the whole collaboration between a project owner and agents:
put the owner's attention on decisions where their experience and judgment matter,
while agents handle routine investigation, evidence assembly, comparison, and authorized
repair. The bounded evaluation asked which minimal changes to guidance or examples help
agents establish decision grounds, obtain necessary owner input, verify outcomes, and
retain rationale. Decision quality had to be considered alongside owner and agent costs;
"no new rule" was an allowed result. See the [research brief](../../docs/design/attention-and-human-agent-collaboration.md#task-brief-and-direction)
and [comparison plan](../../docs/design/attention-frame-comparison.md#status-and-next-decision).

The overall acceptance condition was not simply to finish every planned experiment. It
was to reach an owner disposition on a bounded interaction change, an examples-only
outcome, or no new rule. The active task says that disposition remains open
([A22 task](../TASKS.md#active--blocked--deferred)).

## Results against the goal

| Branch | What was obtained | What it supports | What remains unknown |
| --- | --- | --- | --- |
| P1/T1 claim-calibration screen | The mechanics run exposed a weak design: some inputs carried answer cues and the no-tools subject could report checks but not execute them. The B-vs-C block then ran 18 cells with identical verdicts, but the design would produce that result whether or not the clause worked. Positive controls were not run. [T1 review](t1-mechanics.md) · [comparison record](../../docs/design/attention-frame-comparison.md#result-of-the-b-vs-c-block) | The packet needed better controls before behavior could be inferred. | T1 gives no valid candidate-benefit or no-benefit result. Its proposed P1 positive-control branches are not completed findings. |
| P2/T2 on Claude | The hardened claim-calibration comparison and two audits found no clause benefit. The akmon-versus-consumer delivery contrast is confounded by whether the cases concern akmon itself. The rubric has a documented reading fork; neither recorded nor literal readings establish benefit or equivalence. [M83–M85](../MEASUREMENTS.md) · [T2 synthesis](t2-audit-synthesis.md) | No reason to add the candidate clause from these results; project-match and scoring limits are explicit. | General delivery effects remain unresolved; sample size is too small to establish equivalence. The delivery/project-match question moved to A30. |
| P2/T3 on Codex | Clause and examples failed the pre-registered benefit margin across the recorded and alternate scoring readings. [M96–M97](../MEASUREMENTS.md) · [T3 review](t3-codex-p2.md) | Together with T2, supports the accepted disposition of no new claim-calibration rule (ADR 0019 D01). | Seven case pairs with three repeats detect only large effects; this is not proof of equivalence or universal ineffectiveness. |
| Decision-ground routing, P3 V3 | The complete A arm had 128/128 accepted calls and 32 complete cells, but the frozen qualification floor failed: five strata represented only three of four required case pairs. B/C was not run. [M176](../MEASUREMENTS.md) · [P3 qualification result](../../docs/design/attention-frame-comparison.md#result-of-p3-v3-a-qualification) | The packet correctly stopped at its pre-set gate; ADR 0019 D07 keeps the clause outside operative guidance. | P3 estimates neither benefit nor equivalence. A new comparison requires a distinct prospective design and authorization; adding repeats to this packet is not an open path. |
| Fresh-task/cold-resumption screen | A44, C98, and C33 each had both arms score 6/6, with no observed pointer recovery gain. A44 breached resource/model-routing controls; C98/C33 reader counts differed, so token deltas are not causal. [M177–M179](../MEASUREMENTS.md) · [ADR 0019 D08](../../docs/adr/0019-collaboration-guidance-from-a22.md#d08--close-the-cold-resumption-pilot-without-a-new-rule) | The owner closed this selected offline pilot without a standing resume-point rule or live transfer. | The small, selected set establishes neither equivalence nor saved owner attention. A new mechanism or experiment needs its own prospective scope. |

## Which branches are unclear

The evidence does not leave the branch statuses ambiguous; the remaining uncertainty is
about how broadly to generalize from them and whether to start new work.

1. **P1/T1 versus P2/T2/T3:** T1 is a withdrawn, non-informative mechanics screen, not
   an early negative result. P2/T2 and P2/T3 are the actual claim-calibration comparisons.
   Their no-benefit finding is bounded by low power; the T2 delivery arm also cannot
   isolate delivery from project match.
2. **P3 qualification versus effect test:** P3's A-only qualification completed but
   failed the required pair-coverage floor. This is not a failed clause comparison:
   there is no B/C effect result. Whether a new P3 design is worth its cost is a new
   owner choice, not a missing analysis of the stopped packet.
3. **Cold resumption:** the selected offline screen is disposed. Its equal answer scores
   do not establish equal effort or saved attention, and A44's cost data are invalid for
   a bounded arm comparison. Reopening it would require a distinct question and controls.
4. **Overall A22 disposition:** this is the outstanding A22 decision. The research
   document recommends closing the current evaluation without a further operative
   rule or C86 implementation, while preserving A30's delivery/project-match work and
   A32's remaining claim-evidence work as separate tasks. That recommendation is not
   yet the recorded overall A22 disposition
   ([proposed disposition](../../docs/design/attention-and-human-agent-collaboration.md#proposed-overall-a22-disposition--owner-choice-pending)).

Accordingly, A30 and A32 are not hidden A22 branches that need to be repeated here.
They own distinct unresolved questions. The broad research aspirations in the living
design (for example, further cognitive improvements and controlled adoption) also must
not be read as evidence that A22's three bounded comparison branches are unfinished.

## Folder structure change

The decision and design documents have moved from `meta/decisions/` and `meta/design/`
to `docs/adr/` and `docs/design/` under ADR 0023. A22's live designs and ADR 0019 are
present at the new paths; its task, measurements, reviews, and experiments remain under
`meta/`, as the layout decision specifies. Current A22 links in `meta/TASKS.md` use the
new locations. In this working tree, Git reports the old paths as deleted and `docs/`
as untracked while many files are modified; that makes a status/diff review noisy but
does not by itself indicate missing A22 evidence. Follow the current links and verify
content at the destination paths rather than interpreting the unstaged move as loss.

## Can anything else be done?

Yes, but the useful next step is small: make the overall A22 disposition explicit.
The existing evidence supports the current recommendation to close this evaluation
without a new interaction rule, while leaving A30 and A32 open under their own scopes.
No further run is needed to make that bounded disposition. If the owner instead wants
to pursue a remaining question, define that question, outcome measure, controls, cost
limit, and stop rule in a new prospective scope before any new probe or provider call.
Do not restart T1 or append work to terminal P2/P3 or the closed resumption pilot.

## Sources

- [A22 task record](../TASKS.md#active--blocked--deferred)
- [A22 research brief and proposed disposition](../../docs/design/attention-and-human-agent-collaboration.md)
- [Case comparison and P3 record](../../docs/design/attention-frame-comparison.md)
- [Accepted branch dispositions](../../docs/adr/0019-collaboration-guidance-from-a22.md)
- [Measurements M83–M85, M96–M97, M176–M179](../MEASUREMENTS.md)
