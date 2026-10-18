# A22 P3 V3 phase-gated source amendment proposal

**Status: proposal for owner decision. No seal change, approval, or provider dispatch is made by this note.**

## Decision requested

Choose whether to permit a separately sealed and approved first V3 phase limited to one fresh, two-turn Codex technical source exchange: `P3-01` / arm `A` / strongest tier / repeat 1. This phase would create source and mechanics evidence only. It would not score an output, fill the A qualification cell, authorize either scorer route, or authorize qualification or comparison.

The exact owner decision, if accepted, is:

> I accept the V3-only 5,000,000-token Codex accounting ceiling, including its exclusion of the known 153,614-token V2 debit and unresolved `q1461` usage from that ceiling while preserving both as separately reported V2 history. I accept the frozen technical-source conditions, the `OBSERVED_NO_RETRY` evidence limit, the 80% five-hour and 90% weekly stop thresholds, the requirement for fresh interpretable quota telemetry, and the named human stop operator recorded in the amended approval. I authorize only the `technical_source` phase for the exact amended proposal and seal. This does not authorize route checks, qualification, comparison, repair, retry, or any other provider call.

The owner must supply the named stop operator and accept the exact hashes before approval can be recorded. This scope accepts the new epoch boundary even though this first phase is small; it does not imply acceptance of the later 96-reading-per-scorer schedule or any full-campaign phase.

## Proposed phase boundary

The first phase is one attempt containing exactly two subject turns on the frozen Codex CLI/model/effort pins already specified for the technical source. The source must use fresh V3 epoch, run, attempt, and call identities; bind the frozen `P3-01` case and A-arm hashes; use the isolated out-of-tree runtime; and pass the runner's transcript, same-session, model identity, no-tool, rollout, per-turn input, and correlated-usage checks. The source remains evaluator-only provenance. No scorer packet is emitted in this phase.

The phase is terminal on any failed, interrupted, malformed, identity-mismatched, tool-using, quota-stopped, or usage-unknown call. Preserve the attempt and all available evidence. Do not retry or substitute a source under this authorization. Missing or uncorrelated usage locks all later V3 dispatch unless independently reconciled under a separately accepted procedure.

The source can count once as the matching A/strongest mechanics control in a later campaign, provided the amended campaign protocol says so. It cannot count as a qualification output or as both source and a second control. It establishes none of the other three A/C-by-subject-model mechanics controls.

## Seal and approval consequences

This note is not incorporated into the current V3 proposal or its candidate seal, and the current candidate seal does not authorize this amended phase boundary. If the owner selects this option, update the proposal with the phase split and phase-specific prerequisites, then create a new V3 seal over the amended proposal and all source, runner, ledger, admission, quota, and preflight code that can affect this phase. Preserve the current candidate seal as historical evidence; do not overwrite it in place.

Create a new default-deny approval bound to the new proposal and seal hashes. It must record the owner's explicit acceptance, the named stop operator, the accepted V3 accounting boundary and separate V2 reporting, frozen technical-source pins and limits, quota thresholds, `OBSERVED_NO_RETRY` limitation, and `authorized_phases: ["technical_source"]`. The approval's preflight state starts unrun and dispatch remains false until the phase-specific static checks pass. A later phase needs a new explicit owner decision and approval update bound to the relevant exact hashes; technical-source approval alone never opens it.

Acceptance evidence must point to an owner-provided authenticated transcript export outside the repository. The transcript is a JSON object with exactly `record_type: "p3_v3_owner_acceptance_transcript"`, non-empty `session_id`, `message_id`, and `owner`, and `text` equal byte-for-byte to the quoted decision above. The approval stores the transcript path, exact quote, and SHA-256 of the transcript bytes, along with the proposal, operative-seal, and amendment-seal hashes. The validator checks the artifact's schema, exact text, and actual bytes hash; it cannot independently authenticate the chat export's origin, so that provenance must be verified by the owner or reviewer. A template or synthetic test transcript is not acceptance evidence; no such owner transcript is present in the current workspace.

## Required checks before the first source call

The source-phase preflight should report its own result separately from full-campaign readiness and remain offline. It must:

1. Verify the new seal and every bound source hash, the frozen packet and arm hashes, the V2 immutable-history manifest, and the V3 epoch boundary. Confirm fresh IDs do not collide with V2 or prior V3 identities and that the resolver rejects `q1461` and all V2 exchanges.
2. Confirm the approval exactly binds the amended proposal and seal, accepts the V3-only budget boundary and V2 exclusion, names the stop operator, and authorizes only `technical_source`. Confirm the V3 ledger is bound to that approval and remains default-deny for every other phase.
3. Exercise synthetic missing-usage, unknown-usage lock, token-ceiling, stale/missing quota, threshold-crossing, and persisted stop-control cases. Verify the live adapter can obtain interpretable used percentages, reset windows, source/version, and freshness; require a fresh no-provider-call quota capture immediately before dispatch and a valid post-call capture before another call could be considered.
4. Verify all writable runtime targets resolve outside the repository and sealed source tree, and sealed inputs remain read-only. Require an explicit dedicated external `CODEX_HOME` containing only a private, regular `auth.json`; reject home symlinks and pre-existing user configuration. The actual source runner must enforce the two-turn/session, exact model and CLI pins, no-tool event checks, transcript and rollout correlation, input cap, and per-call usage checks before accepting the source. This directory contract does not prevent a same-UID provider process from reading its authentication file.
5. Prove technical source IDs and provenance remain evaluator-only and cannot be imported as scored qualification data. The source record and resolver must enforce the `evaluator_only` provenance scope; no scorer or qualification map may consume this source record. Confirm static checks make no network or provider calls.

The quota condition is a hard launch gate. Existing pilot evidence only shows coarse counters; it does not establish stable percentages or reset semantics. If current telemetry cannot supply the accepted threshold inputs with clear meaning, the first phase remains denied even after the other checks pass.

## Gates that remain for the full campaign

The source-only preflight is not a replacement for full V3 preflight. Before scorer route checks, implement and independently verify one-shot native runners for both Codex and Qwen; verify scorer model identity, correlated usage, blinded packet equality, TSV completeness, no observed tool use, and the selected `OBSERVED_NO_RETRY` criterion. A route check is mechanics evidence only and cannot qualify P3.

Before qualification, close the full preflight gaps: prove all four A/C-by-subject-model mechanics controls and their attempt accounting; reconcile the 96-reading-per-scorer schedule with the 96-output maximum and the 240-pass ceiling; verify all accepted subject/scorer pins and input limits; and prove source provenance cannot enter the sealed qualification map. The accepted reading schedule, new-epoch accounting boundary, Qwen aggregate policy, route conditions, and phase authorization must be explicit in the approval governing those later calls.

Before comparison, require the full accepted A qualification grid, its sealed map, and the preregistered qualification threshold and pair coverage. Preserve the original A/B/C outcome rule and all stop conditions. Missing cells, route failures, usage gaps, quota stops, or exhausted budgets leave the campaign incomplete; no phase can silently relax or replace those conditions.

## Current posture and limits

The current V3 approval record is default-deny. The current preflight and readiness review identify missing campaign evidence, and the quota pilot does not provide launch-grade percentage telemetry. The first source runner exists, but its existence and synthetic runner tests do not establish live readiness. No source call is authorized by this amendment proposal. If accepted, the adopted proposal and its new seal, approval, and phase-specific preflight must all be reviewed before the owner authorizes the single technical-source phase.
