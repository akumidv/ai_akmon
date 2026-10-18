# A22 P3 Codex subscription quota pilot

**Role:** `review` · **Model:** GPT-6 Codex  
**Result:** Five sequential Codex calls succeeded. The live quota counters moved during the run, but they are coarse counters and do not reconcile to the user-reported remaining percentages. This pilot does not qualify A22 P3, and the earlier V2 `q1461` attempt still has unknown usage.

## Run result

The user-reported starting point was **5h remaining: 100%; weekly remaining: 82%**. This is a separate, user-reported measure. The live quota snapshots below are the values observed by the pilot's quota check; they are coarse counter readings, not remaining percentages.

One initial local attempt failed before any call completed: exit code 1 after 0.43 seconds, with no usage events. The recorded error category is `nonzero_exit`; it was not retried. A subsequent run made **five successful calls out of five**, stopping at the predeclared maximum. No sixth call was made.

| Snapshot (UTC) | Observed 5h counter | Observed weekly counter |
|---|---:|---:|
| Before, 07:37:15 | 0 | 0 |
| After call 1, 07:37:24 | 1 | 0 |
| After call 2, 07:37:32 | 2 | 0 |
| After call 3, 07:37:38 | 3 | 0 |
| After call 4, 07:37:46 | 4 | 1 |
| After call 5, 07:37:52 | 4 | 1 |

The before snapshot is not a clean comparison to the user-reported 100% / 82% remaining: it reports zero in both observed counter fields. The underlying quota window may have reset or rolled over, and these snapshots alone cannot establish the reset time or translate the counters into remaining percentages. The last snapshot also did not increment after call 5, showing the counter is too coarse to treat each call as one unit. Therefore the pilot demonstrates that quota-related telemetry changed during the period, but not how many percentage points or subscription units the calls consumed.

## Token usage reported for the five successful calls

| Call | Time (UTC) | Input tokens | Cached input tokens | Output tokens |
|---|---|---:|---:|---:|
| 1 | 07:37:17 | 16,975 | 12,160 | 5 |
| 2 | 07:37:25 | 17,448 | 0 | 5 |
| 3 | 07:37:33 | 17,448 | 12,160 | 5 |
| 4 | 07:37:39 | 17,448 | 12,160 | 5 |
| 5 | 07:37:48 | 17,448 | 12,160 | 5 |
| **Total** | | **86,767** | **48,640** | **25** |

Each successful call reported zero reasoning output tokens. These CLI usage events are per-call token accounting; they do not convert the coarse live quota counters into subscription percentages. The failed local attempt reported no usage event, which is not proof of zero provider-side usage for that failed attempt.

## Relation to V2 and qualification

This quota pilot was not an A22 P3 route check or scorer run. V2 technical attempt `q1461` remains unresolved: its usage is unknown, and this pilot does not reconcile it. **No P3 qualification was performed or obtained.** The five successful calls establish only that these calls completed and that the observed counters changed during the run; they do not establish P3 readiness, route acceptance, a hard subscription cap, or the cost of a future qualification run.

## Evidence and limits

Evidence: the initial failed-attempt record and the five-call run records, including UTC quota snapshots and per-call usage events, were captured in `/tmp/a22-p3-quota-pilot-20261012/first-attempt.results.json` and `/tmp/a22-p3-quota-pilot-20261012/results.json`; the accompanying human-readable summary is `report.txt`. The successful run's recorded policy was a maximum of five sequential calls, stopping at the first failure, with no retries. The failed local attempt preceded the successful five-call run and was retained as a separate attempt.

The quota observations are snapshots, not a continuous usage ledger. Their counter resolution and reset semantics are not established by these artifacts. The user-reported percentages were not independently captured by the pilot, so no before/after percentage delta can be claimed.
