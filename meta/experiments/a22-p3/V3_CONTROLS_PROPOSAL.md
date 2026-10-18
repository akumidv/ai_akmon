# A22 P3 V3 remaining subject mechanics controls

**Status: operational proposal; provider dispatch is default-deny pending an exact
control seal and owner acceptance.** The accepted historical usage exception
and its [receipt](runs/v3-historical-usage-reconciliation-v1.json) are inputs,
not a call authorization.

Run exactly three fresh, unscored, two-turn `P3-01` technical subject controls
in this order: A/mid (`gpt-5.6-luna`), C/strongest (`gpt-6-astra`), C/mid
(`gpt-5.6-luna`). Codex CLI 0.156.1 and medium effort apply to each. The
verified M137 A/strongest source satisfies the fourth control once and remains
evaluator-only. Each new control has a fresh attempt and two fresh call IDs,
one isolated scratch and Codex home, a fixed menu reply for turn 2, exact
case/arm hashes, no observed tools/retries, one session/rollout with model and
effort checks, and one direct correlated usage record per call. Input caps are
40,000 for A and 50,000 for C. The controls count against the remaining 21
technical/defect attempts; none counts as a scored run or accepted scorer
reading. Any failed, unknown-usage, quota-stopped or malformed control is
terminal. Stop the phase without substitution, repair, retry or continuation.

Before every Codex call, recheck the sealed 74,257-token opening record and
the phase ledger, fetch fresh interpretable subscription telemetry and stop at
80% five-hour or 90% weekly use. Charge every completed call, even one later
rejected as a control. Unknown usage and an unresolved reservation lock the
phase. A completed call may exceed the pre-call reservation; record its usage
and stop immediately if it crosses the aggregate ceiling. Never report the
controls as passed after such an overshoot. The 5,000,000-token V3-only
ceiling includes the historical 7,766-token receipt; V2 history stays
separately reported. The owner of this chat session is the stop operator.
`OBSERVED_NO_RETRY` means only observable CLI/session
behavior, not hidden transport internals.

The operational seal must bind this proposal, runner, validators, frozen P3
case and A/C arms, the original receipt, opening accounting record, verified
source and route evidence hashes, and a fail-closed test. An offline preflight
must prove hash and accounting integrity, exact three-cell order and model
pins, write isolation, default-deny approval, quota/budget/unknown-usage
negative gates, and no provider process. The owner must then accept that
exact seal for `technical_controls` only. This phase does not authorize A
qualification, comparison, scorer calls, repair or additional source calls.
