# A22 P3 V3 clean-restart proposal

**Status: owner decision required. NOT SEALED. NOT AUTHORIZED FOR DISPATCH.** This proposal
starts a new, independently identified P3 execution epoch. It does not retry, repair, reclassify,
or reuse the V2 `q1461` attempt. No provider call may occur under this proposal until its
implementation, seal, static preflight, owner acceptance, and exact-scope dispatch authorization
are complete.

## Decision requested

Accept or reject this material accounting change: V3 gets a fresh **5,000,000-token Codex
observed-usage ceiling for V3 provider calls only**. The known 153,614-token V2 debit and
`q1461`'s unresolved usage remain visible in the V2 history but do not consume this V3 ceiling.
They are not erased or reclassified; the combined V2-plus-V3 P3 usage may exceed 5,000,000
tokens. V3's ceiling is therefore a new-epoch budget, not a continuation of the previously
accepted P3-wide ceiling. Qwen remains without an aggregate token ceiling, with complete
per-call usage records and the same fixed experiment schedule.

The request covers a fresh technical source exchange on A, one fresh one-shot route check for
each scorer route against that exchange, and then a new qualification starting at A. It does not
authorize dispatch by itself. Acceptance must name the new accounting boundary, the subscription
stop thresholds below, the selected scorer conditions, and the phases authorized. The V2 proposal
records owner-accepted protocol direction, but the V2 approval record remains default-deny and its
retry-evidence policy is `UNSELECTED`; neither authorizes V3 calls.

## Why a clean restart

The V2 `q1461` record is terminal: its Codex process failed during local app-server startup,
stdout and parsed events are empty, and the ledger says `missing_usage`. That does not prove zero
provider usage. The V2 ledger blocks further calls while that unknown remains. Preserve its
attempt, call reservation, failure artifacts, approval, seal, and ledger unchanged. Do not retry
q1461 under its existing IDs or use it as the V3 source exchange.

The V2 route-check runner and subject driver are tied to q1461 as the route-check source, and the
single-packet builder accepts sources through the existing sealed map and run verifier. V3 needs
its own source selection and accounting path. The V2 5,000,000-token rule covered prior and future
Codex P3 usage, including the known 153,614-token prior debit. The V3-only ceiling requested here
changes that rule and requires explicit owner acceptance; an accepted V2 plan does not carry that
acceptance forward.

## V3 run sequence

1. **Technical source exchange.** Generate a fresh, opaque V3 run ID, subject-attempt ID, and
   provider-call IDs. Run the sealed `P3-01` / arm `A` / strongest-tier / repeat-1 cell as a new
   `technical` attempt. It has no parent or origin link to q1461. It must complete both subject
   turns and pass model, event, transcript, rollout, and correlated-usage checks. Any failed or
   usage-unknown call is terminal in V3; do not retry or substitute it. A later new attempt would
   require a separately accepted amendment and new IDs. This attempt is mechanics/source evidence
   only: it is not a scored run, does not fill the first qualification cell, and cannot be counted
   again in the qualification map. Keep source IDs and q1461 history in evaluator-only provenance;
   show scorers no run, arm, tier, model, or qualification label.
2. **Fresh route checks.** Build two fresh opaque scorer packets from the verified V3 source
   exchange. Codex and Qwen receive the same blinded packet content and scorer prompt, with no
   source run ID, arm, tier, model, or qualification label. Candidate pins are Codex CLI 0.156.1 /
   `gpt-6-astra` and Qwen CLI 0.24.7 / `qwen3.8-27b`; these are recorded in V2 but do not become
   V3-approved conditions until frozen and explicitly accepted in the V3 approval. Qwen uses
   default thinking, not the altered thinking-disabled condition. Each route gets one process, one
   correlated usage record, no observed retry/error marker, no observed tool use, and a complete
   valid TSV. The V3 approval must explicitly select `OBSERVED_NO_RETRY`, which is observable
   evidence only and does not prove that hidden transport retries never occurred. A route failure
   blocks qualification and does not authorize a replacement call.
3. **Fresh A qualification.** After both route checks pass, start the A qualification grid from
   its first cell under fresh V3 IDs. Run all 8 cards × 2 tiers × 2 repeats (32 subject runs),
   score each output once on each independent route, and seal a new qualification map from the two
   complete scorer datasets. Continue only if at least four strata qualify and every case pair is
   represented. Then run B and C twice in each qualifying stratum, up to 64 further scored runs.
   A practical benefit requires at least three fewer failed C runs than B under both scorers, with
   no pair showing at least two more C failures under both scorers. Otherwise the result is
   inconclusive or worse, never equivalence. Preserve all other preregistered P3 stop conditions.
   V3's planned ceiling remains 96 scored subject runs, at most 24 technical/defect attempts,
   and 120 subject attempts total. Before qualification, run the packet's mechanics controls:
   one two-turn A and one two-turn C control for each subject model, recording exact pins, effort,
   input limit, session/resume behavior, fixed second turn, scratch path, rollout, model identity,
   and event checks. The P3-01/A/strongest technical source may satisfy the matching A control
   once, but never counts twice or becomes scored data. C controls and the other A control are
   separate `technical` attempts. All controls count within the 24 technical/defect allowance and
   120 total. Preserve the sealed packet's 40,000-token per-turn input limit and predeclared
   C-only 50,000-token exception; use the exception only for C. V2 attempt counts remain
   separately reported; the V3 limit is not a claim that the historical V2 attempts did not occur.
   Freeze the subject pins from the packet proposal: Codex CLI 0.156.1 / `gpt-6-astra` at
   `medium` for strongest and Codex CLI 0.156.1 / `gpt-5.6-luna` at `medium` for mid. Verify the
   actual model identity and stop on mismatch.

Scoring schedule: each unique scored subject output receives exactly one accepted reading from
each of the two fixed independent scorer routes. The matrix contains 32 A qualification outputs
and up to 64 B/C comparison outputs, for at most 96 scored outputs, 96 accepted readings per
scorer (Codex 96 and Qwen 96), and 192 accepted readings total. The allowance of up to 24
technical/defect subject attempts does not add scored outputs or accepted readings. Route checks
and mechanics controls are unscored and excluded from accepted-reading counts. Failed scorer
attempts remain in the call ledger and are not accepted readings; an authorized repair may produce
the one accepted reading for its affected output, but cannot create a second accepted reading for
that output. No other scorer retries, uncontrolled scoring, or adjudication calls are allowed.

This V3 schedule is a material owner choice that changes V2's wording of exactly 120 accepted
readings per model. V3 adopts the 96-per-scorer maximum because it matches the unchanged 96-output
subject grid; it does not preserve V2's extra 24 readings per model. The owner must explicitly
accept this schedule before V3 is sealed or dispatched. Keep V2's separate ceiling of 240 total
scorer passes, including failed, defective, route-check, and preflight passes. That is an upper
bound on all scorer calls, not a target or permission to fill unused passes with accepted readings.
Preserve the V2 observed scorer limits: at most 20,000 input tokens per call on both routes and
at most 1,000 output tokens per Codex call. These are post-call checks and do not prevent a single
provider call from exceeding its allowance or the remaining aggregate budget. Keep the Qwen
2,000-token output setting, but do not call it a hard provider cap; if Qwen does not return
correlated usage or a valid complete response, stop that route. Require complete TSV shape,
blinding, model identity, correlated usage, and zero observed tool activity for both route checks.

## V3 Codex token accounting

The V3 append-only ledger starts with `v3_codex_tokens_used = 0` and a 5,000,000-token limit.
It counts every V3 Codex provider call exactly once: source turns, route checks, qualification and
comparison readings, and failed or defective calls with known usage. The ledger carries the V2
proposal/seal/approval/ledger hashes and q1461's `UNKNOWN_USAGE` disposition as historical
references only. It must expose these separately from V3 debit and state plainly that V2 exposure
is excluded by this newly proposed budget boundary. Never convert q1461 to zero or silently add
an estimate to the V3 total. If any V3 Codex call lacks correlated usage, retain it as
`UNKNOWN_USAGE` and lock all further V3 provider dispatch until independently correlated evidence
resolves it; the new-epoch boundary does not permit an unknown V3 call to be ignored.

Before a call, record a quota snapshot and a V3 token-ledger snapshot. After a call, record the
correlated provider usage and a fresh quota snapshot before any next call. For the first five V3
provider calls, also persist one subscription-quota checkpoint after each call. After call five,
continue checkpoints at least every **10 minutes while dispatch is active**, and never let an
active dispatch or idle run go more than **30 minutes** without a checkpoint. A call boundary
always triggers a checkpoint even when less than ten minutes have passed. The snapshot records
UTC time, provider/route, five-hour and weekly usage percentages and reset times when exposed by
the source, source/version, freshness, and raw redacted response hash. Do not store credentials.

**Proposed stop thresholds, for explicit owner acceptance:** stop all new Codex dispatch at
**80% used in the five-hour window** or **90% used in the weekly window**. Stop Qwen dispatch at
the same thresholds only if a corresponding trustworthy Qwen subscription-quota signal is
available; otherwise Qwen remains governed by its fixed schedule and per-call usage completeness.
Both routes stop on missing, stale, malformed, or semantically uninterpretable quota telemetry
where that telemetry is required to apply a threshold. Both routes stop on missing or
uncorrelated per-call usage. If a threshold is reached during a live call, signal the operator
stop, terminate the active provider process using the existing stop control, preserve the attempt
as failed/uncertain, charge any known usage, and do not retry. A checkpoint failure is itself a
stop condition, not permission to continue until the next interval.

The parent-reported snapshot at **2026-10-15 07:15:49 UTC** was 0% used in both Codex windows.
That is neither a current baseline nor independently captured evidence, and it does not reconcile
q1461. The 2026-10-13 quota pilot observed coarse counters that did not map cleanly to remaining
percentages. Static preflight may validate the telemetry adapter and threshold logic only against
synthetic and preserved fixtures. After owner approval, a separate live, no-provider-call
readiness check must capture the current quota source, used percentages, reset windows, source and
freshness immediately before each authorized phase. If stable, interpretable percentages and
reset information are unavailable, or the current snapshot is missing, stale, or uninterpretable,
deny dispatch. The old parent-reported snapshot is not current evidence.

## Conditions and prerequisites before dispatch

### Implementation

- Add a V3 driver/ledger/route-check path with an explicit epoch ID and output directory. It must
  never append to or rewrite the V2 ledger or its attempt artifacts.
- Generate V3 run IDs, attempt IDs, provider-call IDs, packet IDs, and qualification-map IDs from
  fresh entropy. Reject any collision with V2 or prior V3 records. V3 source resolution accepts
  only the newly registered technical A source and verifies its sealed cell, case/arm hashes,
  model pin, two-turn transcript, rollout, usage evidence, and packet-source hashes. It must
  reject q1461 and any V2 exchange as a source.
- Bind every reservation and completion to the V3 epoch, exact V3 proposal/seal/approval hashes,
  route, provider-call ID, and correlated per-call usage. Enforce the V3-only 5,000,000 observed
  token ceiling before subsequent dispatch, checkpoint before/after calls, and retain every failed
  call. As the route has no enforceable hard per-call total cap, document that one call may
  overshoot the remaining V3 budget; stop further dispatch immediately when observed use reaches
  or exceeds the ceiling.
- Add the quota telemetry adapter and append-only checkpoint record. Test stale/missing telemetry,
  threshold crossings, concurrent stop, checkpoint ordering, and recovery after process failure
  using synthetic fixtures only. Qwen must retain its default-thinking settings and route-specific
  correlation; do not copy Codex quota percentages to Qwen.
- Prepare an isolated writable Codex home, app-server state, temporary directory, and runtime
  path. A no-model check must perform create/write/fsync/read/delete checks and prove that sealed
  project inputs remain read-only and no writable target resolves into the sealed source tree.
- Preserve the packet's two-turn/no-tools contract, out-of-repository scratch path, exact-id menu
  routing, rollout verification, 40,000-token per-turn limit, and C-only 50,000-token exception.
  Include all four A/C-by-subject-model mechanics controls in attempt accounting; one A/strongest
  source does not establish the other three controls.

### Seal, approval, and static preflight

1. Freeze this exact V3 proposal and the implementation sources; preserve the existing packet
   seal unchanged. Create a distinct V3 seal that binds proposal bytes, packet seal hash, driver,
   ledger, route runner, quota adapter, preflight sources, and frozen model/CLI/scorer settings.
2. Create a V3 owner-approval record bound to those hashes. It must explicitly accept the
   new-epoch 5,000,000 Codex ceiling and its exclusion of all unresolved V2 exposure, the separate
   reporting of the 153,614 known V2 debit and q1461 unknown status, the 80%/90% subscription stop
   thresholds, Qwen's uncapped aggregate policy, `OBSERVED_NO_RETRY`, the V3 attempt/scoring
   schedule, the named human stop operator, and authorized phases. V2 approval cannot authorize
   V3 dispatch.
3. Run no-network, no-model static preflight: verify exact seal and source hashes; verify immutable V2
   artifacts and the V3 epoch boundary; prove ID non-collision and rejection of q1461 as a V3
   source; validate synthetic missing-usage, quota-threshold, stale-snapshot, token-ceiling, and
   stop-control cases; verify the writable runtime manifest; prove technical source IDs cannot
   enter the scored qualification map; validate evaluator-only source provenance and scorer
   blinding; and confirm no network/model call occurs in static preflight. Also verify the four
   mechanics controls, subject-model pins, turn/input limits, the reconciled accepted-reading
   allocation, 240-pass ceiling, and separate unscored route-check treatment. If the 120-per-model
   schedule cannot be reconciled with the 96-output ceiling without changing the accepted V2
   protocol, stop and obtain an explicit owner decision before sealing V3.
4. Obtain explicit owner acceptance and dispatch authorization for the exact sealed V3 proposal
   after reviewing the resulting artifacts. Capture and pass a separate current quota snapshot
   after approval and immediately before dispatch; the 07:15:49 report cannot serve as that
   snapshot. Authorize the technical
   source, route checks, and qualification as distinct phases. Each phase rechecks approval,
   quota telemetry, dispatch control, and remaining V3 token budget immediately before its first
   provider call.

No static preflight or quota snapshot establishes experiment validity. The two route checks only
validate scorer mechanics; the A/B/C observations and preregistered outcome rule determine the
P3 result. Missing telemetry, a usage gap, a route failure, or a quota stop leaves qualification
incomplete and does not permit a retry.

## Alternatives considered

- **Reconcile q1461 and continue the V2 accounting epoch.** Preferred if uniquely correlated
  provider usage can be found: it preserves the accepted P3-wide ceiling. The available V2 record
  and the subscription-quota pilot do not provide that reconciliation, so this is not the current
  launch path.
- **Reserve a conservative maximum for q1461 and continue V2.** Rejected: the current Codex route
  has no demonstrated hard output cap, and the input/output checks are post-call. A numeric
  maximum would be invented rather than evidenced.
- **Stop P3 without another run.** Safest resource choice and always available. It produces no
  new route validation or qualification evidence.
- **V3 clean restart (recommended for a new launch).** Preserves q1461 as terminal/unknown,
  gives the new data independent identities and fresh route/A-source evidence, and makes the new
  budget boundary explicit. Its cost is substantive: it permits total V2-plus-V3 Codex usage to
  exceed the previously accepted P3-wide 5,000,000-token ceiling. Only explicit owner acceptance
  of that change can make this option eligible for dispatch.

## Decision and revisit conditions

Recommendation: choose **V3 clean restart** only if the owner accepts the separate V3 budget
boundary and the quota telemetry can support the specified thresholds. Otherwise keep q1461
terminal and stop dispatch; if q1461 is reconciled later, reconsider continuing under the V2
accounting boundary. A newly discovered route-enforced hard total-token cap may justify revisiting
the rejected conservative-reservation option. This proposal records no owner acceptance and grants
no authority to execute.
