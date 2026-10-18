# A22 P3 V3 successor scorer routes: outcome

**Role:** `review` · **Model:** Codex GPT-6; independent evidence check by GPT-6 Luna · **Status:** two unscored route checks passed; qualification not authorized.

The owner accepted the exact route seal `b42d0a8a6962f800b71e2cfe526bad27ee0e84359def3845aa4a0f40abd01f79` for `route_checks` only, with the owner as the current-session stop operator. The [acceptance evidence](../experiments/a22-p3/runs/successor-route-check-acceptance-evidence-v6.json) retains the raw user message and identifies the single extra space removed after `SHA-256` for the sealed exact-text gate. It binds the local session-log request and reply records; this log is not independently signed. The [approval](../experiments/a22-p3/runs/successor-route-check-approval-v6.json) is limited to this phase.

Both one-shot scorer routes passed. The private runtime is `/tmp/a22-p3-v3-successor-route-runtime/`; its append-only `route-events.jsonl` has exactly one reservation and completion for each route. Both prepared records bind packet SHA-256 `5cce39ac1d12dcb99ab5623e0c44e541df4f471e07f8c972626d574adfcf450c` and identical request SHA-256 `10ab28aec13107ef555d22c5f742866c236acdfa82a0a84092653c92f98cc2d3`. The model-visible packet was blinded; private source identity stayed in the evaluator manifest.

| Route | Observed usage | Evidence outcome |
| --- | ---: | --- |
| Codex CLI 0.156.1, `gpt-6-astra`, medium | 12,305 input + 176 output = 12,481 | Passed exact E1–E4 TSV and correlated CLI/session usage |
| Qwen CLI 0.24.7, `qwen3.8-27b`, default thinking | 12,700 input + 1,024 output = 13,724 | Passed the frozen TSV parser and correlated session usage; see format caveat below |

Independent evidence review found two blank lines before the Qwen TSV header. The frozen parser discards blank lines, then verifies the exact header and four E1–E4 rows, so it recorded a pass. A literal requirement that the header occupy byte zero would fail. The qualification proposal must resolve that interpretation explicitly; neither retroactively edit this terminal reply nor make a replacement route call.

The fresh Codex pre-call quota snapshot reported 72% five-hour and 26% weekly use, below the approved 80% and 90% stops. The V3-only observed Codex balance is 66,491 tokens, including the 54,010 source-phase balance. No accepted scored reading or qualification result was created. The checks support `OBSERVED_NO_RETRY` only for visible CLI/session events; they cannot rule out hidden transport retries.

The prior [readiness review](a22-p3-v3-successor-route-readiness.md) describes the state before these calls. Next, prepare and review a separate qualification proposal and seal. This route approval does not permit qualification, comparison, repair, retry, or additional provider calls.
