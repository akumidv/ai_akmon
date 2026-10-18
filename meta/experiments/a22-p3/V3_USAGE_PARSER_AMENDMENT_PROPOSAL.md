# A22 P3 V3 usage parser amendment proposal

**Status: prospective amendment evidence. This note does not change an accepted seal or grant dispatch authority.**

The current runner selects a maximum among nested legacy `token_count` counters. The observed completed-turn event exposes a direct `turn.completed.usage` object, so counting nested telemetry adds parsing work and can obscure ambiguity.

The proposed parser accepts exactly one direct `turn.completed` event with a direct `usage` object containing positive integer `input_tokens` and nonnegative integer `output_tokens`; booleans are invalid. When no direct event exists, legacy `token_count.info.last_token_usage` snapshots retain the previous cumulative-counter behavior and the greatest total is used. If both forms are present, exactly one valid legacy record must agree with the direct record. Duplicate direct events, or ambiguous cross-format records, fail closed.

This amendment is prospective. It does not reinterpret or repair any prior attempt, ledger entry, provider event, transcript, or seal. It grants no authority for a provider call, retry, repair, or phase transition. Any future dispatch requires the owner’s separate explicit authorization against the then-current accepted proposal and seals.

The accompanying chained seal records hashes of this proposal, the changed runner and regression, and the preserved V3 operative and source-phase seals. It is evidence of the proposed parser bytes only; it is not an accepted operational seal.

This historical parser proposal retains the policy it originally recorded. The successor [lean source protocol proposal](V3_LEAN_SOURCE_PROTOCOL_PROPOSAL.md) supersedes its legacy fallback and cross-source reconciliation rules; the old proposal and seal remain unchanged as prior evidence.
