# A22 P3 V3 launch readiness

**Role:** `review` · **Model:** GPT-6 Luna · **Result:** Not ready for full-campaign dispatch.

## Current review addendum

The source-phase approval authorizes only the V3 `technical_source` phase, and its source
preflight passed. One first-turn provider attempt completed and is terminal under the accepted
`OBSERVED_NO_RETRY` policy; there was no second turn and no retry. The runner marked the attempt
failed with usage unknown, so it is not a successful source result. See the
[`source-attempt report`](a22-p3-v3-source-attempt.md) for scope, approval, preflight, and runtime
evidence. The requested model label GPT-6 Luna remains explicit; the runtime artifacts separately
identify `gpt-6-astra` at medium effort.

The source-phase preflight and fresh quota snapshots cleared gates for that phase only. The full
campaign remains not ready: the source attempt does not clear the six full-campaign evidence gates
listed below or authorize route checks, scoring, or any later phase. Offline focused verification
covers implementation behavior, not those remaining gates. Codex CLI 0.156.1 is available by
standalone path; the default `PATH` resolves to 0.162.1. The `PATH` version alone does not
establish which executable was used for an earlier syntax review.

## Decision and current state

The owner accepted the first V3 technical-source cell, and the source-phase approval records that
phase-limited authorization. The operative full-campaign
[`owner-approval-v3.json`](../experiments/a22-p3/runs/owner-approval-v3.json) remains
default-deny: `owner_accepted=false`, both bound hashes are null, `authorized_phases` is empty,
`preflight_status` is `NOT_RUN`, and `dispatch_allowed=false`.

The operative candidate seal is
[`seal-v3.json`](../experiments/a22-p3/seal-v3.json), SHA-256
`58eea0362178111b0497e6fcd248dffb25b07dda295fa91de2d03205819cedde`. The separate source-phase
amendment seal is
[`source-phase-seal-v3.json`](../experiments/a22-p3/runs/source-phase-seal-v3.json), SHA-256
`c4977c962a4c216abdc57951c981a2691063657f8928f9201847045cd96e84a8`; it binds eight source
files and the operative seal hash. The source-phase approval and passed source preflight are
documented in the [source-attempt report](a22-p3-v3-source-attempt.md). The full-campaign static
preflight still reports `BLOCKED_STATIC_EVIDENCE`, `launch_ready=false`, and
`dispatch_allowed=false`. Its synthetic quota, token-ceiling, stop-control, runtime-write,
ID-collision, and q1461-source-rejection checks pass. Six additional proofs remain blocked:

1. An authoritative immutable hash manifest for the V2 artifacts.
2. A runtime manifest proving writable targets are isolated and sealed inputs are read-only.
3. A V3 qualification map proving the technical source is excluded from scored data.
4. Full-campaign checks that scorer payloads stay blinded and scorer routing is correct.
5. All four A/C-by-subject-model mechanics controls, with their pins and limits.
6. A V3 route-check implementation that marks route checks as unscored.

The current preflight does reconcile the 96-reading-per-scorer schedule with the 240-pass ceiling
arithmetically. The approval still has `schedule_accepted=false`; arithmetic is not owner
acceptance. The separate source-only amendment proposal is at
[`V3_PHASED_SOURCE_AMENDMENT_PROPOSAL.md`](../experiments/a22-p3/V3_PHASED_SOURCE_AMENDMENT_PROPOSAL.md).
It describes a separately gated first technical-source phase. It has not changed the operative
plan or approval; the operative seal now binds final runner, resolver, and preflight sources.

## Runner and ledger evidence

The V3 runner and ledger now retain post-call quota checkpoints, including a threshold-crossing
checkpoint; stop the active process when a live quota stop fires; retain known usage when
available; and block later reservations after a stop or unknown-usage condition. The runner also
fails closed when the live quota checkpoint cannot be obtained. These controls do not establish
that current provider telemetry can supply stable, interpretable quota percentages and reset
windows; that remains a live readiness gate before any further separately authorized phase.

The source-phase acceptance gate verified the approval artifact against the exact amendment
decision. Its static preflight passed source-phase checks, and the fresh pre-call quota snapshot
was below the approved stop thresholds. Offline preflight exercises missing quota, unknown-usage
lock, token ceiling, and persisted-stop behavior. A synthetic two-turn integration completes
correlated usage and rollout checks and marks source provenance `evaluator_only`; the resolver
rejects other scopes. Custom quota readers are limited to synthetic injected tests while production
uses the sealed live adapter. The completed attempt still ended with unknown ledger usage; see the
source-attempt report. The initial and resumed Codex commands carry the same `-s read-only`,
`--ignore-user-config`, `--ignore-rules`, scratch working directory, and arm instruction file; a
regression test checks that symmetry.

The earlier focused source-phase, dispatch, preflight, quota-adapter, ledger, and runner regression
set passed 36 tests with Ruff. The current offline focused verification is 20 tests with Ruff;
these are distinct reported runs. They cover synthetic controls and implementation behavior, not
the six missing full-campaign evidence items or full-campaign launch readiness. The source phase
has passed preflight and consumed its one authorized attempt. The CLI versions available for the
current check are stated in the addendum above.

## Accounting and limits

The V3 proposal uses a new 5,000,000-token Codex epoch ceiling that excludes the known 153,614-token
V2 debit and unresolved `q1461` usage. This can make total V2-plus-V3 exposure exceed the earlier
P3-wide ceiling. Keep the V2 records as history; empty output and parsed events do not prove that
`q1461` used no provider tokens. The source-phase approval accepts this accounting boundary for
that phase only; it does not accept the full 96-reading schedule, later scorer routes,
qualification, or comparison.

The source/mechanics phase was approved and attempted once. Its attempt ended terminally with
unknown usage; it does not score an output, fill the A qualification cell, authorize a scorer
route, or authorize later campaign phases. Preserve the attempt and make no second-turn call or
retry under `OBSERVED_NO_RETRY`. Any further provider call requires a new owner decision and
approval bound to its exact phase and artifacts. The full-campaign approval remains default-deny.

## Dispatch posture

One V3 source-phase call was made under phase-limited approval and ended terminally. No second
turn or retry is authorized. Do not dispatch route checks or scored campaign work until their
separate full-campaign blockers are closed, live quota readiness is captured for that phase, and
the approval explicitly authorizes it. A route check remains mechanics evidence; it cannot
qualify P3.


## Tool and account isolation limit

The accepted proposal requires a no-tool check and makes a tool-using call terminal, but the pinned Codex CLI does not provide a reliable pre-call global no-tools control. The runner passes an allowlisted environment and read-only sandbox, then detects tool activity in returned and persisted events and terminates the attempt. That detects use after the model has seen the input; it does not prevent tool access. The provider process shares the invoking user identity and can read the external `CODEX_HOME/auth.json`. The runner rejects a symlinked home and requires a dedicated external directory containing only a private regular `auth.json`, with no pre-existing user config; this constrains configuration inheritance but does not hide the credential from the same-UID process. Treat these as residual exposure for any future source-call authorization; neither the preflight nor the tests prove pre-turn tool isolation.

Quota and model execution now bind the same resolved executable and external `CODEX_HOME`; the account/limit receipt stores only hashes. Production runner injection parameters for executor and quota-reader were removed. The current test set covers default-deny and rejects injected runner launch seams. The source attempt and unknown-usage outcome are recorded in the [source-attempt report](a22-p3-v3-source-attempt.md).
