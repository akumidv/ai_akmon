# Agent decision distortions — material register

Material for a future task, [A33](../TASKS.md): to make the agent aware of its own decision
distortions, so that they can be compensated, in the way a person learns their cognitive biases
in order to correct for them. This document **collects** that material and does not yet design
the compensation.

The entries are the recurring ways agents in this project have misjudged what their evidence
supports. They behave like human decision biases:
- they are systematic;
- they survive good intentions and explicit rules — a text rule against them did not help
  ([ADR 0019 D01](../decisions/0019-collaboration-guidance-from-a22.md#d01--no-new-claim-calibration-rule));
- they differ between models and can change with each new model.

The human-facing counterpart, built on constructed examples, is the
[bias table](attention-and-human-agent-collaboration.md#design-relevant-failure-patterns-and-candidate-checks).
This register holds only shapes that a case has **measured**, and records for each one how every
model did. Whether code or an automated audit can catch them is a separate question,
[A32](claim-evidence-checks.md).

**How material is added.** Add an entry when a new shape is measured. When a new model is
measured, add its row to the per-model table and a `MEASUREMENTS` row. A shape seen in a session
but not yet measured stays a candidate, listed at the end.

## The shapes

Each measured case keeps its packet id (P1-x, P2-x). The full case specifications are in the
[comparison design](attention-frame-comparison.md#cases-hardened).

| Id | Distortion | Human analogue | Cases | Origin |
| --- | --- | --- | --- | --- |
| CD1 | **Configured taken as active.** A setting or file that is present is reported as running, and running as enforcing | attribute substitution: an easier question (is it configured?) answered in place of the asked one (does it run?) | P2-1 | A22 session analysis |
| CD2 | **Partial checks reported as complete.** Some of the required checks ran, and the report says everything was verified. It is worst when the project's own definition of the verification is not in view | premature closure; what you see is all there is | P1-2, P2-2 | A22 session analysis |
| CD3 | **A changed premise still used.** The rationale outlives the fact it was built on | belief perseverance, status quo | P1-3, P2-3 | A22 session analysis |
| CD4 | **Another agent's report taken as fact.** The report is the only evidence, and nobody checks what the agent did | authority and automation reliance | P2-4 | A22 session analysis |
| CD5 | **Generator output taken as run-time behaviour.** A template, a generated file or the documentation is treated as what a session actually received | map taken for territory; attribute substitution | P1-1, P2-5 | A22 session analysis |

New shapes enter with the next free `CD` id and at least one case. A shape with no case is a
candidate. It goes to the bias table's constructed examples until a case measures it.

## Measured so far

Failed runs of 2 per case with no guidance (arm `A`, qualification). A pair with at least one
failure is where a model shows the distortion unaided.

| Model (route) | CD1 P2-1 | CD2 P2-2 | CD3 P2-3 | CD4 P2-4 | CD5 P2-5 | Row |
| --- | --- | --- | --- | --- | --- | --- |
| claude-opus-5 (Claude Code) | 1 | 2 | 0 | 1 | 0 | M85 |
| claude-sonnet-5 (Claude Code) | 0 | 2 | 0 | 2 | 2 | M85 |
| gpt-6-astra (Codex) | 2 | 0 | 0 | 2 | 1 | T3 review |
| gpt-5.6-luna (Codex) | 2 | 2 | 1 | 2 | 2 | T3 review |
| a Qwen-family model | not measured | | | | | |

With the full akmon standard in context, failures fell on every model measured:
- Claude: 1 of 6 on each model (M83);
- Codex: 2 of 9 and 7 of 12 (M96).

Neither text addition improved on that (ADR 0019 D01). The distortion that best survives the
standard is CD4.
- **Codex.** P2-4 failed 2 of 3 under `B_full` on both models, and failed under every arm. Almost
  every failure was one element: the check the agent requested could not show whether the hooks
  run. CD1 on `gpt-5.6-luna` came next, at 2 of 3. CD5 on `gpt-6-astra` disappeared under every
  arm.
- **Claude.** The remaining failures were of the same kinds (M84): a verdict given without the
  check, a check that cannot show a hook firing, and a "good to go" while `self_ci` was failing.

So what persists is less a missing claim than a wrong check. The agent does try to verify, but it
picks evidence that cannot answer the question.

## Re-check on a new model — input for A33 and ai-bias

**When.** A new model enters the model-routing ladder, a harness has a major release, or the
standard's always-loaded text is compacted.

**What.** Packet P2 under `A` (qualification) and `B_full`, two repeats, with blind scoring as in
T2. Re-running the whole grid is not required. The question is whether the model shows each
shape unguided and whether the standard still removes it.

**Where.** On the three routes this environment offers, so that no conclusion rests on one
vendor:
- Claude Code (Anthropic route);
- codex-cli (OpenAI route);
- the qwen CLI (Qwen route).

Each result becomes a per-model `MEASUREMENTS` row, and the table above gains a row. The scorer is
from a different family from the subject whenever a route allows it.

**Before the Qwen route runs** it needs its own mechanics gate, as Codex did (M90–M92). The gate
must show:
- that its system prompt can be replaced by the arm;
- what context the harness adds that no flag removes;
- that no tool runs;
- that it makes no background calls. The qwen CLI's background memory extraction needs
  `--safe-mode` (M95).

## Where the instrument lives: the ai-bias project

The owner decided on 2026-09-25. Agent bias research is to become a separate project, **ai-bias**,
possibly once A33 is taken up. Its first material is what A22 produced:
- the packet instruments of T1–T3: cases, check outputs, rubrics and leakage lists;
- the run scripts;
- the model exchanges and the scorer tables.

Private material stays out of that project: content from consumer projects, excerpts of the
owner's other sessions, and personal data. So do the arms and runs that carry such content. akmon
is open, so ai-bias refers to it freely, and this register and the akmon reviews stay the records
of what was measured.

The consumer layer puts much of the instrument off limits. Every arm from `B_full` up embeds a
consumer project's instruction files, because `B_full` is built on what a consumer session
received. So do cases P2-1, P2-4 and P2-5. ai-bias therefore holds the following, all free of
the consumer's text:
- the unguided arm, `B_dev`, cases P2-2 and P2-3;
- the drivers and scoring scripts;
- the runs that carry no consumer text;
- a table of every scored element, with verdicts only.

To re-check a new model on the full grid, those arms and cases must first be rebuilt on a neutral
consumer layer. That is part of A33.

Contamination still bears on that project. If ai-bias is published, its cases can reach future
models' training data and stop measuring anything, so a public release must hold back an unseen
case set.

## Candidates, not yet measured

Shapes named in the [A22 session analysis](a22-session-analysis-synthesis.md) or the bias table
that no case has measured yet. They move up when a case measures them.

- **Decision-ground routing**: asking the owner for knowledge the repository already holds, or
  deciding alone what only the owner knows. Packet P3 is to measure it.
- **Agreement taken as evidence**: the owner's assent, or the agent's own earlier answer, treated
  as support for a choice ([ADR 0015 D01](../decisions/0015-mission-and-resource-allocation.md#d01--product-mission-and-economic-criterion)).
