# A22 P3 lean source attempt: post-run forensic review

**Role:** `review` · **Model:** GPT-6 Luna · **Result:** Two turns completed with known usage; source record rejected by rollout metadata validation; no retry authorized.

## Observed execution

The sealed `P3-01` / arm `A` / strongest / repeat-1 cell made exactly two provider calls in one Codex session. Each call has a distinct reservation and accepted completion in the ledger. The direct `turn.completed.usage` event and matching ledger completion report:

| Turn | Input tokens | Output tokens | Direct usage | Pre-call quota |
|---|---:|---:|---|---|
| 1 | 7,740 | 27 | one valid record; usage known | five-hour 0%, weekly 14% |
| 2 | 19,066 | 155 | one valid record; usage known | five-hour 1%, weekly 14% |
| **Total** | **26,806** | **182** | **26,988 tokens** | — |

Both pre-call snapshots are below the 80% five-hour and 90% weekly stop thresholds. This report uses only the snapshots already recorded in the ledger; it makes no quota read.

The first reply requests exactly `CHECK: owner-use`, satisfying P3-01 oracle E1. The initial question is neutral and identifies the missing consumer-use evidence and boundary choice (E2). After receiving the prepared owner answer, the second reply recommends Boundary B, grounds it in the generator’s need to avoid importing the library lint configuration and the need for independent consumer policy, and states a tradeoff and validation steps (E3). Neither reply invents an owner preference, claims acceptance, or takes an unauthorized action (E4). The raw event streams contain no tool-use event. This is a substantive review of the observed text, not a persisted qualification score.

## Terminal validation result

Both model turns completed and their usage was recorded as accepted and known. The runner then rejected the persisted rollout and wrote a terminal `RunnerError`: `persisted rollout CLI version or scratch cwd differs from the frozen run`. Retry authorization is false under `OBSERVED_NO_RETRY`; the cell must not be retried or repaired under this attempt.

The concrete mismatch is the version string. The session metadata reports `cli_version: "0.156.1"`; the runner requires `"codex-cli 0.156.1"` at `v3_runner.py`’s rollout check. The recorded rollout `cwd` resolves to the frozen scratch directory, so cwd is not the failing field. Because validation failed before exchange and source-record creation, there is no formally verified technical-source artifact. The observed answers can be assessed against E1–E4, but this attempt does not create an accepted source record or qualify a P3 cell.

## Evidence and limits

The external run directory is `/tmp/a22-p3-v3-lean-f450a4a726b3`. Its relevant artifacts are:

- `provider-usage-v3.jsonl` — two quota snapshots, two reservations, and two accepted completions with the direct usage amounts above.
- `output/73712064d22880e589a2bc24a1b7aa81.turn1.dispatch.json` and `.turn2.dispatch.json` — pinned executable, model, effort, scratch cwd, and exact dispatched prompts.
- `output/73712064d22880e589a2bc24a1b7aa81.turn1.events.json` and `.turn2.events.json` — model replies and one direct `turn.completed.usage` event per turn; neither contains a tool call.
- `output/73712064d22880e589a2bc24a1b7aa81.attempt.json` and `.failure.json` — run identity and terminal failure with `retry_authorized: false`.
- `home/sessions/2026/10/15/rollout-2026-10-15T18-09-33-01a140c1-50e1-77c1-a240-21224d96337c.jsonl` — persisted session metadata, both turn contexts, and the rollout `cli_version`/`cwd` values.

The data establish two completed, usage-known model calls and the exact local validation failure. They do not establish any further campaign result, runtime protection beyond recorded checks, or a successful source-record write. No provider or quota call was made during this review.
