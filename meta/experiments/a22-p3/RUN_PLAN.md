# A22 P3 run plan — proposed, pending owner acceptance

**Status: NOT AUTHORIZED. This file is a proposal, not an executable command or spending
approval. No model calls may start until the owner accepts this plan and records the live
preflight result.**

## Proposed pins

| Route | Exact model pin | Effort / harness pin | Use |
| --- | --- | --- | --- |
| Subject, strongest | `gpt-6-astra` | `medium`; Codex CLI `0.156.1` | Strongest tier |
| Subject, mid | `gpt-5.6-luna` | `medium`; Codex CLI `0.156.1` | Mid tier |
| Blind scorer 1 | `gpt-6-astra` | `medium`; Codex CLI `0.156.1` | First fixed reading for every packet |
| Blind scorer 2 | `qwen3.8-27b` | Qwen CLI `0.24.7`; proposed `--max-tool-calls 0` | Independent second reading for every packet |

The subject models and scorer model are the recorded T3 pins. The locally installed Qwen CLI
reports `0.24.7` (verified for this proposal), while T3 used `0.24.4`; the Codex CLI reports
`0.156.1`. Qwen 0.24.7 help exposes `--max-tool-calls`; T3's Qwen tool behavior on 0.24.4 does
not establish the newer flag's effect. These version observations are not proof that the routes
remain available or that the model aliases resolve to the same backend. Verify executable path,
version, actual model identity, effort, and usage provenance before dispatch. Stop on any mismatch;
do not silently substitute a model.

## Proposed hard ceilings

- Subject ceiling: 120 subject runs, each with exactly two turns, hence at most 240 subject
  dispatches. Keep the existing 40,000 input-token per-turn cap and predeclare the existing
  C-only 50,000 exception before any C call. The four A/C subject preflight controls consume
  four of the 24 reserved mechanics/defect runs; they are inside, not above, the 120-run ceiling.
- Blind scoring ceiling: 240 total scorer passes across both scorers, including preflight,
  defects, and retries. Each pass has a 3,000 input-token cap and a 1,000 output-token cap.
  The resulting aggregate hard ceiling is 960,000 scorer tokens, below a 1,000,000-token budget.
  Before each pass, reserve 4,000 tokens from that budget; pre-count and reject packets over
  3,000 tokens. Require route-supported output limits and provider-reported usage in preflight.
  If either route cannot enforce and report these limits, do not dispatch it. The Qwen scorer
  must use `--max-tool-calls 0` and pass a no-tool mechanics control before scoring.
- Proposed aggregate scorer spend ceiling: USD 25, pending owner acceptance. The current driver
  has no billing integration, so this is a manual owner-controlled ledger and stop, not a
  machine-enforced limit. Before execution, record route-specific pricing, estimated total cost,
  and who will halt the scorer routes at the ceiling. If that control is unavailable, do not
  dispatch scorers.
- Do not adjudicate disagreements or make calls beyond these ceilings. Stop when any ceiling
  would be crossed; missing cells make the result incomplete.

## Mechanics preflight required before qualification

Run one unscored, two-turn control for each subject model and each of A and C. Confirm and retain
for every control: the exact model and CLI versions; effort `medium`; the rendered arm hash and
received instructions; the same session ID on resume; the fixed second turn; exact menu routing;
input counts within the declared caps; an out-of-repository scratch cwd on both turns; a unique
persisted JSONL rollout with that session ID; and a matching nonempty reply. Inspect returned and
persisted events for tool calls. Any recorded tool call, project material in context, identity
mismatch, missing rollout, or transcript mismatch fails preflight and stops the trial.

Run one synthetic blinded scoring packet through each scorer route. Both routes must return the
required TSV shape within their token caps, preserve packet blinding, record their actual model and
usage provenance, and record zero tool activity. These two passes count against both the 240-pass
ceiling and the proposed USD 25 scorer ceiling.

The T3 measurement M91 found that Codex did not expose its full tool list locally and retained
tool features despite disable flags. The subject driver detects tool events only after dispatch;
this limitation remains subject to explicit owner acceptance. M99 found Qwen's safe/plan mode did
not guarantee zero tool calls. The proposed Qwen `--max-tool-calls 0` setting must pass the scorer
mechanics control before use. The current driver checks returned and persisted events after each
subject dispatch and writes raw stdout/stderr, parsed events, and outcome metadata under `runs/`
before accepting or rejecting that dispatch. Keep those files for failed and interrupted attempts
as well as successes; every attempt marker consumes budget.

## Scoring isolation

Give each scorer only one blinded packet at a time and the frozen scorer prompt. Do not include
arm, tier, model, or qualification labels. Keep each scorer's raw TSV, route provenance, token
usage, and cost record. Require one row per applicable element, exact PASS/FAIL verdicts, and a
one-line evidence reason. Disagreements remain two readings; no adjudication call is allowed. Build
the B/C map with `python3 grid.py <scorer-1.tsv> <scorer-2.tsv>`; the importer checks both complete
readings against all 32 sealed A cells, verified records, exchanges, and their hashes before writing.

Owner acceptance must record the accepted pins, route-specific spend estimate and stop method,
the preflight outcome, and acceptance of M91/M99's tool-observability limitations before a model
call. Until those fields are accepted and recorded, the packet remains not authorized to run.
