# T2 — what a governed session actually receives

> **Verdict:** one headless turn in the wired consumer, read back from its transcript, shows the
> session receives the consumer's `CLAUDE.md`, `AGENTS.md` and both `@`-imported akmon files —
> the materialized `guardrails/_common.md` and `profiles/python.md` — plus two hook-injected
> blocks, and **no stale-rules notice**. The materialized guardrails match the akmon release the
> consumer has installed; they differ only from akmon's unreleased source. So the gap between
> what akmon ships and what a session reads is release lag, not a sync or staleness-detector
> failure. Owned by A22 and [trial T2](../design/attention-frame-comparison.md#trial-t2--delivery-and-clause-comparison);
> row M81 in [MEASUREMENTS](../MEASUREMENTS.md).

## What was checked

The T2 rebuild brief predicted, from akmon's **source** `hooks/hook_core.py`, that the consumer's
SessionStart text is 1,146 characters and ends in a stale-rules warning. The consumer's real
hooks run `akmon hook …` from its installed package, which carries its own copy of the
guardrails. The question was what the real hooks inject and which guardrail text the session
actually reads.

## Method

- Claude Code 2.1.278, `claude -p --output-format json --model opus`, one turn, prompt on stdin
  asking for a one-word answer; working directory the consumer project, its own wiring untouched.
- What entered the context was read from the session transcript, never from the model.
- The consumer project was not modified: every file outside VCS metadata, the virtual
  environment and caches was hashed before and after (715 files, identical), and the three files
  its hooks write (`.claude/model-routing.log`, `.claude/model-routing.local.json`,
  `.claude/settings.local.json`) were copied with `cp -p` before the run and restored after.
- Marker strings were checked for uniqueness against each candidate source before use.

## What the transcript shows

| Entered the context | Observed |
| --- | --- |
| `instructions` attachment | Four project files — `CLAUDE.md`, `AGENTS.md`, `_aitna/.akmon/guardrails/_common.md`, `_aitna/.akmon/profiles/python.md` — plus the harness's own auto-memory index, each once |
| Guardrail copy | The materialized copy: its marker `**Enforced** (not just documented) by` is present, akmon source's `Runtime check: privilege.no-escalation` is absent |
| `AGENTS.md` | Loaded once, although `CLAUDE.md` imports it with `@AGENTS.md` |
| SessionStart `session-start-agent` | 909 characters: role declaration, DEVELOP/OPERATE rosters, delegation-by-default, memory-read rule. **No stale notice** |
| SessionStart `model-routing` | 702 characters: tier line, delegation routing, a missing-model-list warning, D2 ledger count |

## Why no stale notice

The installed package is akmon `0.4.0.dev0`. Its `stale_materialized` compares the consumer's
copy against the tree the hook runs from — the installed package — and returns nothing. Against
akmon's source tree the same function returns `guardrails/_common.md`. The source also reports
`0.4.0.dev0`, so the version string does not distinguish the two; only the content does.

Consequence for the brief's V2: the 1,146-character text with a stale warning is what akmon's
*source* would say about this consumer. A real session on the consumer receives the 909-character
text without it. The stale-detector is working as designed; the consumer is simply on an older
build of the same version string.

## Consequences for T2

- `B_del` is taken from this transcript: the four project files' content as the harness rendered
  it, and both hook blocks. The auto-memory index is the harness's per-user memory, not akmon
  guidance, and stays out of the arm.
- The `B_ship ≫ B_del` outcome, if it occurs, points at releasing and adopting akmon changes,
  not at `sync` or the staleness detector.

## Re-check of the analysis's unrecorded facts (2026-09-23)

The A22 analysis kept four working-tree facts that no record held. Re-run against akmon's source
at `e006489` and the consumer, pinned to akmon `bc52998` (installed `0.4.0.dev0`), all four
reproduce unchanged; none needs a record of its own.

| Fact | Reproduced | Disposition |
| --- | --- | --- |
| akmon's source `session_start_result` on the consumer: 1,146 characters ending in the stale-rules warning | yes | read above as release lag: the consumer's installed hooks inject 909 characters and no notice |
| delivered `guardrails/_common.md` 10,023 bytes against the source's 10,808: 22 lines only in the source, 12 only in the delivered copy, `## Role declaration` missing from it | yes | the same release lag; `B_ship` against `B_del` measured it (M83) |
| `sync` materializes `CLAUDE.md` (payload `@AGENTS.md` only), `.github/copilot-instructions.md`, `GEMINI.md`, `.codex/README.md`, `.codex/hooks.json` | yes | a fact about akmon's own code, recorded by `bin/sync.py` itself |
| the quote checker used on T1's hand-built fixture pairs quotation marks positionally and skips real quotations | yes | not reused: T2's arms are assembled and asserted by script ([Arms](../design/attention-frame-comparison.md#arms)) |

## What this does not establish

The headless path only. Interactive sessions were not probed. One consumer, in a dirty
mid-migration state, on one harness version.
