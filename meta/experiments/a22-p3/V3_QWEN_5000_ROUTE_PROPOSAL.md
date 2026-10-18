# A22 P3 V3 Qwen 5,000-token scorer route successor

**Status: offline candidate; no provider dispatch is authorized by this proposal.**

The first qualification attempt stopped terminally after its seventh provider
call. The second Qwen scorer consumed exactly its local 2,000-token output
allowance in default thinking and emitted no final TSV. Its failed call and
the six preceding accepted calls remain in the original ledger; none is
replayed, repaired, or promoted to a qualification result. The Codex V3 charge
after that attempt is 273,286 of 5,000,000 tokens. V2 history remains separate.

The owner previously allowed raising Qwen's local output setting to 5,000 if
needed. This observed exhaustion supplies that need. This successor checks one
unscored Qwen scorer route with the same frozen P3-01 mechanics packet and
scoring prompt used by the earlier route check, retaining default thinking,
`maxRetries: 0`, one session, no tools, the first-nonempty-line TSV rule, a
20,000 observed input limit and a 5,000 observed output limit. The overlay
and environment both set 5,000. The route check establishes configuration,
request, response, usage correlation and parser mechanics only; it cannot
guarantee that every later qualification answer fits 5,000 tokens.

The one-shot route has its own private ledger and evidence root. It binds the
prior qualification seal and terminal ledger hash, the prior route packet,
prompt and source, this proposal and runner, the exact Qwen CLI/model pins, and
an offline preflight. A default-deny approval bound to the new seal is required
before one provider process. A failed attempt is terminal. Record complete
usage even on a failed response when the CLI exposes it. `OBSERVED_NO_RETRY`
describes visible CLI/session evidence only; hidden transport behavior is not
claimed. This route call is unscored and does not authorize qualification,
comparison, repair or retry.

If the route passes, separately prepare a fresh 32-cell qualification schedule
with new IDs and a new ledger, charge the spent 273,286 Codex tokens, and bind
the new route evidence in a successor qualification seal. Preserve the original
terminal attempt. The original two-scorer same-repeat predicate, balanced B/C
comparison rule, Codex 80% five-hour and 90% weekly stops, and 5,000,000-token
ceiling remain. Any new qualification provider call requires acceptance of its
own concrete operational package.
