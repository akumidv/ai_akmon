# A22 P3 V3 lean source protocol proposal

**Status: prospective proposal for owner decision. This note does not change a seal, approval, or dispatch authority.**

## Proposed operating rule

Keep the V3-only Codex accounting ceiling at 5,000,000 tokens and the quota stop thresholds at 80% used in the five-hour window or 90% used in the weekly window. Preserve the existing per-turn input cap.

Immediately before each new provider call, take one fresh, interpretable quota snapshot and reject dispatch if either threshold is met or exceeded. This is the sole quota gate for that call. Remove mid-call quota polling and post-call quota checkpoints; a quota snapshot is not required to close a completed call or consider the next call. The next call still requires its own fresh pre-call snapshot.

For the V3 Codex ledger debit, use exactly one unambiguous direct CLI `turn.completed.usage` record associated with the single reserved provider-call ID for that invocation. Its integer `input_tokens` and `output_tokens` are canonical for that call. Do not accept legacy token counters or reconcile usage against rollout totals. Missing, malformed, duplicate, or uncorrelated usage makes the attempt terminal with usage unknown; preserve its evidence and do not retry. Treat 5,000,000 tokens as an observed-use stop before subsequent dispatch, not as an absolute per-call charge cap. Before a new call, reserve the unchanged 40,000-token input cap against the remaining ceiling; deny dispatch if that reservation would exceed it. The CLI has no enforceable hard per-call total-token cap, so one admitted call may take observed use beyond the remaining budget or the 5,000,000-token ceiling; after observing usage at or above the ceiling, stop all subsequent dispatch.

Keep rollout/session/transcript checks for session identity, CLI/model/effort, instructions, turn count, and tool-use absence. They do not supply token counts. Enforce the existing 40,000-token per-turn input cap using the direct completed-turn usage record.

## Threshold crossing and authorization

A threshold can be crossed while a call is running because this protocol does not poll mid-call. That call remains the terminal attempt under its existing exact authorization; no later call is authorized by that authorization. A threshold-crossing call is not retried or repaired. Any further provider call requires a new explicit owner approval and seal bound to the exact amended proposal and implementation. This proposal itself grants no provider-call authority.

## Parser amendment relationship

This proposal supersedes the legacy fallback described in [the V3 usage parser amendment proposal](V3_USAGE_PARSER_AMENDMENT_PROPOSAL.md): a single direct record is canonical, with no legacy fallback or cross-source reconciliation. Do not rewrite prior attempts, ledgers, provider events, transcripts, or seals.

## Adoption boundary

If accepted, revise the operative V3 proposal, runner, ledger, preflight, and approval to implement this rule; produce new exact hashes and a new seal, then obtain separate explicit authorization before any provider call. Until that work and approval are complete, the current accepted protocol and default-deny posture remain in force.
