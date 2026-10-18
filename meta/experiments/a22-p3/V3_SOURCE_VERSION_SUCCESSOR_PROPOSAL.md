# A22 P3 V3 source version-check successor

**Status: implementation candidate; no provider dispatch under this document.**

The preceding two-turn technical-source attempt is terminal. Its direct usage and raw
events remain evidence, but it did not create a verified source record because Codex
persisted `session_meta.cli_version` as `0.156.1` while the sealed validator required
`codex-cli 0.156.1`. The scratch path matched. Do not resume, repair, or reclassify that
attempt.

For a distinct one-cell successor, keep the pinned executable banner check exact at
`codex-cli 0.156.1`. In persisted rollout metadata, accept exactly the two observed
spellings `0.156.1` and `codex-cli 0.156.1`; reject every other version and leave the
cwd, session, instructions, model, effort, tool-use, quota, usage, and no-retry checks
unchanged. The source case, arm, tier, and two-turn sequence are unchanged.

The successor requires a new exact seal over this proposal, its executable validator,
the authorization gate and regressions, plus a fresh offline preflight. Its approval
must name the exact seal hash, this one `technical_source` cell, and the current human
stop operator. The accepted prior seal and approval remain historical evidence only;
neither authorizes the successor. The new approval must be recorded before any provider
call. A new attempt is also terminal on any failure under `OBSERVED_NO_RETRY`.

The existing 5,000,000-token V3-only accounting ceiling, 80% five-hour and 90% weekly
stop thresholds, one fresh quota snapshot per call, direct `turn.completed.usage`
debits, and 40,000-token per-turn input cap remain in force. The known 26,988 tokens
from the prior lean attempt must be carried into the observed V3 usage history before
the next reservation; no old ledger is rewritten.
