# A22 P3 V3 A — bounded transport recovery

## Accepted policy and remaining execution gate

ADR 0019 D05 accepts at most eight objectively transport-invalid Codex calls eligible for technical replacement across the A chain. The first three have already occurred: two scorers and the first subject turn of cell 25. This proposal specifies that standing policy; it is not a seal or dispatch approval. A reviewed immutable successor packet and live preflight still gate its first call. This successor stops on any further failed call. A later qualifying HTTP 503 may be replaced under D05 without asking the owner again, up to the chain limit, by preparing a distinct reviewed and sealed successor that preserves the terminal ledger.

## Current successor

Carry forward 96 accepted calls and 24 complete cells. Keep all three failed calls charged and unscored. Replace only the failed first subject turn at global position 97 with a fresh Codex turn 1, new call ID and fresh session, using the same frozen prompt, model, case and arm. Its turn 2 resumes only that new session. Then run the 31 unchanged scheduled calls. The expected successful remainder is 32 calls; at most five additional 503 failures can be eligible for substitution. Every Codex call checks fresh interpretable quota below 80% five-hour and 90% weekly and conservative headroom under the V3-only 5,000,000-token ceiling. Qwen retains provider-default thinking and the 16,000-token local output setting.

## Subsequent transport failure

A failed scorer or first subject turn may be replaced only when sealed event/stderr evidence identifies exactly one WebSocket HTTP 503, its usage correlates, and the frozen runner recorded a terminal failure. A new generation hash-binds its predecessor ledger and failed artifacts, keeps the failed attempt charged, and changes only that slot's call ID. The replacement uses identical request bytes and a fresh blind session. Its result is accepted only through the unchanged validator. A failed second subject turn, any other error marker, ambiguous usage, altered packet, exhausted failure allowance, quota stop or aggregate ceiling stop blocks further dispatch. Do not inspect a failed answer to choose whether to substitute.

Primary reduction uses exactly one accepted subject pair and two accepted scorer readings per cell. Historical invalid replies never enter that reduction. Sensitivity calculations, if any, are separately labelled and cannot promote failed calls. B/C remains unauthorized.

## Alternatives and revisit condition

A fully fresh 128-call A run avoids carryover complexity but repeats accepted work and still faces the observed CLI transport errors. Retrospectively accepting answers that arrived with 503 markers breaks the frozen `OBSERVED_NO_RETRY` rule. Direct API transport would change the account and cost boundary and needs a separately accepted design. Revisit the bounded replacement policy if a non-503 failure appears, the subject turn 2 fails, or the eighth transport-invalid event occurs before A completion.
