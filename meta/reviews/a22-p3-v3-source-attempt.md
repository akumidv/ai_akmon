# A22 P3 V3 technical-source attempt

**Role:** `review` · **Model label:** GPT-6 Luna · **Result:** one attempt completed at the provider boundary; runner marked it failed and ledger usage unknown. No retry.

## Scope and authorization

This report covers only the first V3 `technical_source` attempt, case `P3-01`, arm `A`, strongest tier, repeat 1. It does not evaluate a scored response or establish qualification, a route check, or a comparison result.

The source-phase approval records `owner_accepted=true`, authorizes only `technical_source`, accepts the V3-only 5,000,000-token Codex ceiling, the `OBSERVED_NO_RETRY` policy, and 80% five-hour / 90% weekly stop thresholds. It binds proposal `c163caa638f5d9dbc65dd405858408d5c01e0e91a399caa36ccac3e1520bd06a`, amendment proposal `bfc6452a9713089f8ee607ff87fb892932daf2f64cdc1598a39fd14d627b8f57`, amendment seal `3d0f931f47a54f0d101e99e63e33182b1f447704ff340e9f9257c7ea15f89667`, and operative seal `58eea0362178111b0497e6fcd248dffb25b07dda295fa91de2d03205819cedde`. The source-phase seal identifies packet seal `62ace0ce353ce059acd2ee442589d81912ffa61d6442787dc17aebd34728dd93` and the technical-source settings.

The runtime attempt and dispatch artifacts identify the configured model as `gpt-6-astra` at effort `medium`, matching the source-phase seal. That differs from the report's requested model label, GPT-6 Luna; this report preserves both values rather than treating them as equivalent.

## Gates and call

The captured source-phase preflight reports `PASSED_SOURCE_PHASE_PREFLIGHT`, no blockers, and passes its synthetic quota, token-ceiling, persisted-stop, runtime-write, usage-lock, and source-scope checks. Its top-level `launch_ready` and `dispatch_allowed` remain false for the full campaign; it expressly marks this as a source-phase-only run. Immediately before the call, the live Codex quota snapshot was fresh and showed 18% five-hour and 10% weekly usage, below the accepted 80% and 90% stop thresholds. The post-call snapshot showed 19% and 10%. The quota receipt records Codex CLI `0.156.1` and hashes for the account, executable, external home, and limit receipt; no account identifier is reproduced here.

One provider call was reserved and dispatched for `P3-01/A/strongest`, repeat 1 (run ID `b62745e38d8ae5547c8c004c4ff19cc4`; attempt ID `95e85fab70b5464fd4b520d321088003`). The command returned code 0. The event stream contains a completed assistant response:

> The missing first-consumer use could distinguish the boundaries. I’d check it before recommending A or B.
>
> CHECK: owner-use

The events and stdout contain `turn.completed` usage values of 7,737 input and 29 output tokens. The isolated rollout also contains a `token_usage_record` and a `token_count` event with matching values, totaling 7,766 tokens. The runner still failed to find **valid correlated token usage**: its parser accepts the expected `token_count` shape only when the required correlation is present, and this returned stream did not pass that check. The runner produced a terminal `RunnerError`; the attempt artifact has no accepted usage, and the ledger records `input_tokens=null`, `output_tokens=null`, and `usage_status=UNKNOWN_USAGE`. Thus the output telemetry is corroborated in the local session artifacts, while accounting for this provider attempt remains unknown in the authoritative ledger. The observed 7,766 total is not substituted into that ledger or treated as a successful accounting receipt.

The failure record sets `retry_authorized=false` and `terminal=true`. The attempt is therefore retained as one failed, unknown-usage attempt under `OBSERVED_NO_RETRY`; it is not repaired, repeated, or counted as a successful source result. No second turn was dispatched.

## Evidence and limits

The primary artifacts are in the isolated source-attempt directory:

- [approval](/tmp/a22-p3-v3-source-340ec9af6c43/owner-approval-v3-source.json) and [source-phase preflight](/tmp/a22-p3-v3-source-340ec9af6c43/source-phase-preflight-v3.json)
- [attempt record](/tmp/a22-p3-v3-source-340ec9af6c43/output/b62745e38d8ae5547c8c004c4ff19cc4.attempt.json), [failure record](/tmp/a22-p3-v3-source-340ec9af6c43/output/b62745e38d8ae5547c8c004c4ff19cc4.failure.json), [dispatch record](/tmp/a22-p3-v3-source-340ec9af6c43/output/b62745e38d8ae5547c8c004c4ff19cc4.turn1.dispatch.json), [events](/tmp/a22-p3-v3-source-340ec9af6c43/output/b62745e38d8ae5547c8c004c4ff19cc4.turn1.events.json), and [stdout](/tmp/a22-p3-v3-source-340ec9af6c43/output/b62745e38d8ae5547c8c004c4ff19cc4.turn1.stdout.txt)
- [usage ledger](/tmp/a22-p3-v3-source-340ec9af6c43/provider-usage-v3.jsonl) and [pre-call quota receipt](/tmp/a22-p3-v3-source-340ec9af6c43/preflight/runtime/q1461-source.json)
- [isolated rollout log](/tmp/a22-p3-v3-source-340ec9af6c43/home/sessions/2026/10/15/rollout-2026-10-15T14-31-35-01a13ff9-c46c-75c0-bea0-2db13a9cb475.jsonl), which contains the matching token-usage and quota events
- [source-phase seal](../experiments/a22-p3/runs/source-phase-seal-v3.json) and [source-phase approval record](../experiments/a22-p3/runs/owner-approval-v3-source.json)

The model response is evidence of returned text only. This attempt cannot establish whether the model would have completed the source task, whether a continuation would have been useful, or whether the configured model label was correct for the intended study population. The usage uncertainty also means this report does not claim a precise token debit. The accepted V2 usage and unresolved `q1461` history remain separately reported under the approved V3 accounting boundary.

## Follow-up

Preserve this attempt and its unknown-usage ledger entry. Under the accepted `OBSERVED_NO_RETRY` policy, make no retry or second-turn call for this cell. Any further provider call requires a new owner decision and approval bound to its exact phase and artifacts; this source-only authorization does not extend to route checks or scored campaign work.
