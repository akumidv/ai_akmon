# Experiments — the index

What akmon has tested, with what verdict, and where the facts are recorded. Read this, and grep
[`MEASUREMENTS.md`](../MEASUREMENTS.md), before designing an experiment: what was measured is not
measured again. Negative and refuted results are listed as findings.

Each line points to a results document in this folder. The raw materials of an experiment —
fixtures, runners, transcripts, per-run outputs — live in its task's ergon, not here
([ADR 0023/D07](../../docs/adr/0023-project-documents-layout.md#d07--an-experiment-leaves-its-results-in-the-tree-and-its-materials-in-its-ergon)).

| Experiment | Task | Question | Verdict | Recorded in |
|---|---|---|---|---|
| [c194-vocabulary](c194-vocabulary.md) | C194 | Do the words ergon/athlos/step cost a light-model agent work, against everyday and standard words? | No measured cost; standard *task* collides with the backlog's in 10/18 runs; a missing definition costs ~1.5× the tool calls; a one-line gloss in the entry file is the cheapest fully-right carrier | M221–M223, [merge record §12](../../docs/design/ergon-athlos-merge.md#12-the-vocabulary-measured), ADR 0029/D10 |
| [a22-p3](a22-p3.md) | A22 | Does a frozen decision-ground routing clause cut failed subject runs against the architect baseline? | **Not answered:** the no-guidance qualification arm ended FLOOR_FAILED (3 of 4 required pairs, 5 strata) and ADR 0019/D07 stopped the packet before B/C; operational negatives (gateway DNS, WebSocket 503, scorer formats, thinking exhausting output, input caps) recorded | M118–M176, [attention-frame comparison](../../docs/design/attention-frame-comparison.md), ADR 0019 |
| [a22-resumption-pilot](a22-resumption-pilot.md) | A22 | Does a record-derived resume pointer help a fresh session recover a paused task truthfully? | **No gain:** 6/6 in both arms on A44, C98, C33, no false closure; one case per pair, token ceilings breached | M177–M179, [resumption pilot](../../docs/design/a22-fresh-task-resumption-pilot.md), ADR 0019/D08 |
| [a32-e2-codex](a32-e2-codex.md) | A32, C113 | Does any auditor configuration reach recall ≥ 0.6 at ≤ 0.2 false flags on the frozen 161-exchange cohort? | **No E2 result:** the run stopped at 1,378/1,449 valid records; E1 before it was negative (recall 0.23–0.58, false flags 0.22–0.44) | M98, M99, M102, [claim-evidence checks](../../docs/design/claim-evidence-checks.md) |
| [c197-qwen-model-surface](c197-qwen-model-surface.md) | C197 | What model values does a Qwen Code agent accept, what does its transcript record, is an agent file re-read per launch, and is the served set discoverable? | Answered for Qwen Code 0.26.7: served ids and grades are accepted for a subagent; the transcript carries the model outside `message.model`; agent files are read per launch; the endpoint lists seven served ids | M225–M230 |
| [c197-stage-a-pilot](c197-stage-a-pilot.md) | C197 | What does one pass of the probe runner cost end to end, and does the two-case seed set separate the seven served ids? | **Cost measured, no separation:** 21 calls in 5 min 44 s, 8,792 + 14,315 recorded tokens; 13 of 14 fix attempts passed, the hunt item is one bit, every cell is n = 1 and fails the 30-item gate; the stage-B set is at least about 3.8–5.7 h sequential | none in MEASUREMENTS; the run's ledger is in `meta/.ergon/C197-model-measurement/materials/stage-a/` |
