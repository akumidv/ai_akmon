# 0019 — Collaboration guidance changes from the A22 evaluation

- **Status:** Accepted
- **Owner:** akuminov@gmail.com
- **References:** [A22](../TASKS.md) · [comparison design](../design/attention-frame-comparison.md) ·
  [T2 evidence](../reviews/t2-grid-20260922.md) · [T2 audits](../reviews/t2-audit-synthesis-20260923.md) ·
  [T3 evidence](../reviews/t3-codex-p2-20260924.md) · M83–M85, M96–M97 in
  [MEASUREMENTS](../MEASUREMENTS.md) · [ADR 0015](0015-mission-and-resource-allocation.md)

## Context

[ADR 0015](0015-mission-and-resource-allocation.md) accepts the mission but leaves every concrete
interaction change to its own decision block, backed by evaluation. A22 evaluates candidate
changes one at a time. This ADR holds its outcomes. The first one concerns *claim calibration*.

### The problem

An agent states a material claim, but its evidence is about a different subject from the claim.
The A22 session analysis found five recurring shapes, and packet P2 turned each one into a case:

| Case | What goes wrong |
| --- | --- |
| P2-1 | *configured* is reported as *active*: a hook present in settings is taken to run and to enforce |
| P2-2 | three of five checks ran, and the report says everything was verified |
| P2-3 | a premise changed, and the rationale built on it is still used |
| P2-4 | another agent's report is taken as fact, without looking at what that agent did |
| P2-5 | a generator's output (a settings file, documentation) is taken as what a session received at run time |

### The candidates

The owner could choose among three outcomes: adopt a rule, add worked examples only, or add no new
rule. Two candidates were tested:

- **The clause**, one paragraph added to the standard:

  > When a report states a material claim — a runtime or harness fact, a causal diagnosis, or the
  > completion of a check — name the subject actually examined and how it was established:
  > observed now, a recorded measurement at the version it names, a template or generator input,
  > or another agent's report. If that evidence covers a different subject, version or scope than
  > the claim, either examine the claim's own subject or narrow the claim to what was examined and
  > name the missing prerequisite. A stated limitation does not license the unchecked claim or an
  > action that assumes it.

- **The examples**: two worked episodes from this project's records and no rule. In C61 a report
  was checked against the live rendering and corrected. In C62 a diagnosis was measured rather
  than argued.

### How it was tested

- **Two-turn cases.** Each case gives the agent a task and a menu of checks. In turn 1 the agent
  may request one check. In turn 2 it receives the check's output and answers. A case is failed
  when the agent asserts the claim without the evidence that supports it.
- **Guidance given to the agent (arms):**
  - `A` — no standard;
  - `B_full` — the full akmon standard in context, the reference;
  - `C` — `B_full` + the clause;
  - `E` — `B_full` + the examples;
  - `C_E` — `B_full` + both.

  Each arm differs from the one it is compared with by exactly one addition.
- **Qualification.** Only case × model pairs that `A` fails enter the grid. A case the model
  already handles without guidance measures nothing.
- **Scoring.** A blind scorer sees neither the arm nor the clause. A run fails if any checklist
  element fails. A literal re-reading of two ambiguous elements was scored as well. On Codex, a
  second scorer from another model family re-scored every run.
- **Fixed in advance.** The margin was fixed before T3 ran: an addition counts only if its arm
  fails at least 3 fewer runs of 21 than the reference, under every reading.

### What was found

| Trial | Vendor | Runs per arm | `A` | `B_full` | `C` | `E` | `C_E` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T2 | Claude | 12 | 10 | 2 | 3 | — | — |
| T3 | Codex | 21 | 17 of 21 (a floor, see below) | 9 | 11 | 11 | 14 |

The table gives failed runs. `A`'s T3 count is biased upward because qualification admitted only
the pairs `A` failed. On two models the standard cut failures from 7 of 9 to 2 of 9, and from
10 of 12 to 7 of 12.

- **The standard in context works.** On both vendors, the full standard cuts failures sharply
  compared with no guidance.
- **The additions do not.** No reading on either vendor puts the clause ahead of the standard by
  more than one run, and none puts the examples ahead at all. On Codex, the arm with both
  additions failed the most. That is not counted as harm, because the second scorer reverses
  that gap.
- **What this means.** The standard already carries this behaviour. The failures that remain under
  it are not fixed by more text of this kind.
- **Limits.** Three repeats of seven pairs detect a large effect, not a small one. The result is
  *no benefit detected*, not proof of zero effect. On Codex, every arm carried the harness's own
  context, which could have damped any addition equally. Positive controls were not run. Those are
  cases where the right move is to proceed on the evidence given, and they would show what the
  clause costs. Once no benefit was found, that cost no longer bore on the choice.

## Accepted decision block

### D01 — No new claim-calibration rule

`Decision-ID: ADR-0019/D01`

Neither the candidate clause nor the worked examples is added to the standard, its guardrails,
roles or pipelines. The existing standard in context remains the guidance for claim calibration,
because it measurably changes this behaviour and neither addition improved on it on either
vendor. C86 implements nothing for claim calibration.

The block covers claim calibration only. Decision-ground routing, the owner-facing pilot and
cold resumption are separate A22 steps and still open. The block makes no choice about
non-textual means of catching the remaining failures, such as a deterministic check or an
automated audit. That question is open design work.

## Rejected alternatives

- **Adopt the clause.** Rejected: it added no detected benefit over the standard on two vendors,
  and it costs always-loaded context for every session.
- **Add the examples only.** Rejected on the same evidence. The examples arm did no better than
  the reference on Codex.
- **Run more repeats before deciding.** Rejected: the pre-registered design sized the trials to
  detect an effect worth adopting. A smaller effect than that would not repay a permanent
  addition to always-loaded text.

## Reconsider when

- A trial with more power, or cases from a consumer's own project ([A30](../TASKS.md)), shows a
  text addition ahead of the standard by a pre-registered margin.
- The standard's text that currently carries the behaviour is removed or compacted, and the
  behaviour degrades measurably as a result.
