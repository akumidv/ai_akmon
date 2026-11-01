---
name: learning
description: Runs the learning agent over this project's own recorded sessions since its last run — extracts owner corrections, repeated failures, hook denials, delegation drift and unrecorded decisions, turns them into proposals (memory notes, guardrail/profile/pipeline candidates, tasks), persists only what the owner confirms, then records the run. Use when the session-start reminder says a learning run is due, or when the owner asks to run learning, review recent sessions or learn from sessions.
metadata:
  owner: akmon
---

# learning

The procedural skill for the [`learning`](../../agents/learning.md) agent (role `learn`).
The agent reads the sessions of **the project it serves, recorded since its last run**, and proposes
what to keep. All *listing and bookkeeping* is code — the `akmon learn` command; the only model work
is reading the transcripts, and that runs **in a subagent**, never in the orchestrator.

> **Proposals first, persistence on confirmation.** Nothing reaches `memory/`, a task, a guardrail
> or a pipeline until the owner confirms it
> ([analysis before mutation](../../guardrails/_common.md#analysis-before-mutation)). **Never read
> another project's sessions** — `akmon learn sessions` lists this project's only, and the run
> stops at that list.

## When to use

- A session-start reminder said `[akmon] learning: N sessions and D days since the last learning run`
  (thresholds: 10 sessions or 7 days, changeable under `[learning]` in `<dev root>/.akmon.toml`).
- The release agent, or the hand-off that leads to integration, offered a run before a pull request
  and the owner chose to run it.
- The owner asks to run learning, review recent sessions or learn from them.

Declare `🧭 role: learn — <focus>` before starting.

## Steps

1. **See what is due.** `akmon learn status` (a Node project: `npx akmon learn status`) prints the
   sessions and days since the last run and the thresholds. Then `akmon learn sessions` lists this
   project's Claude transcripts (including those started in a directory inside it) and Codex
   sessions recorded in this project's root or inside it, modified since the last run — before the
   first run, since counting began — as kind, session id, modified time, size, path. `--all` lists
   every recorded session instead. Its **first line is the listing time**: keep it, step 6 passes
   it to `mark`.

   An empty list means there is nothing to learn from — say so and stop. If `status` counts
   sessions but the list is empty, the counted sessions could not be found (their transcripts moved,
   were deleted, or were written elsewhere): tell the owner that, and with the owner's agreement run
   `akmon learn mark --at <listing time>` so the reminder resets instead of firing every session.
2. **Delegate one read-only `summarize` pass per transcript batch** to `k_explorer`. Batch the list
   by size so one pass reads a few transcripts (a transcript is JSONL; the pass reads text and tool
   results, not raw dumps). Give each pass the same **extraction targets** and ask for evidence
   (session id plus a short quote), never a transcript digest:
   - **owner corrections and stated preferences** — "no, not that", "always/never …", a redo;
   - **repeated failures and retries** — the same command or fix tried again, a gate red twice;
   - **hook denials and nudges** — what a guardrail hook blocked or reminded, and whether the work
     changed because of it;
   - **delegation drift** — long undelegated stretches of mechanical work in the orchestrator;
   - **decisions taken in chat but not recorded** — a choice the owner made that no task, ADR or
     memory note holds.

3. **Synthesize proposals** (orchestrator, from the passes' returns only), per
   [learning](../../pipelines/learning.md) and [memory-distill](../../pipelines/memory-distill.md).
   Deduplicate against `memory/` and the backlog, then say **where each would land**:
   - a **memory note** (stays LOCAL — memory-distill);
   - a **guardrail / profile / pipeline candidate** (the promotion test: *general* and *proven*; it
     becomes a task, a contract change routes through the architect role);
   - a **task** in `TASKS.md` (an unrecorded decision, a repeated mechanic worth a tool or skill).
   Keep project-specific detail out of anything bound for akmon: knowledge flows one way up.

4. **Present to the owner** in chat: the proposals with their evidence and landing place, ending in
   one **`Needed from you`** block with a line per proposal (`D-LEARN-<TOPIC>` plus its gist) asking
   keep / drop / change.

5. **Persist only what the owner confirms** — write the confirmed memory notes, tasks and candidate
   records, and nothing else.

6. **Record the run.** `akmon learn mark --at <listing time from step 1>` sets `last_run` to that time
   and clears the counted sessions, so the reminder starts over and activity after the listing is not
   swallowed by this run (`akmon learn mark` alone stamps now). Mark when the owner has decided,
   including when they dropped every proposal; do **not** mark an abandoned run — the sessions stay
   due.

## Boundaries

- Reads this project's sessions only; writes nothing but what the owner confirmed and
  the run record (`<dev root>/.local/learning.json`, gitignored).
- Proposes promotions into akmon as tasks or PRs the owner reviews; it never copies up silently and
  never tags, pushes or bumps a pin.
