# A22 P3 V3 historical usage reconciliation

**Owner direction accepted:** apply the narrow process-envelope exception to the
first V3 technical attempt only. The owner's current-chat confirmation was
“Подтверждаю. Запускай”. This direction accepts the exception described in the
[qualification draft](V3_QUALIFICATION_PROPOSAL.md); it does not accept an
unbuilt phase seal or authorize an unprepared provider call.

The original ledger remains immutable with `UNKNOWN_USAGE`. The separate
[receipt](runs/v3-historical-usage-reconciliation-v1.json) binds the one
reserved call `b56635eca40db627519d47d4717d379f`, the one terminal source
attempt, direct event and paired rollout by exact hashes. The offline
[validator](reconcile_v3_usage.py) requires one reservation, one completion,
one direct `turn.completed.usage` event, one rollout session and turn, matching
7,737 input and 29 output tokens, and no competing attempt in the captured
runtime envelope. The event itself has no call or turn ID, so this is an
explicit **historical envelope-correlated debit**, not a claim of direct
correlation. It creates no precedent for a later call. A separate external
process cannot be ruled out by these local files.

The [opening accounting record](runs/v3-qualification-opening-accounting-v1.json)
rechecks all three source lineages and both scorer routes. It carries the
known 66,491 Codex tokens plus this 7,766-token historical debit, for 74,257
charged V3 tokens before the next phase. Three technical subject attempts have
used the 24-attempt allowance; the two scorer route checks are separate. V2's
known 153,614 tokens and `q1461` unknown usage remain separately reported
under the accepted V3-only 5,000,000-token ceiling.

Every later V3 admission must revalidate and bind the exact receipt and opening
record, carry the 74,257-token floor into its mutable ledger, and reject any
duplicate, changed, absent or unknown usage. Future provider calls still need
direct per-call usage, fresh interpretable quota below 80% five-hour and 90%
weekly stops, no observed retry, exact phase-specific seal and approval, and
the current-chat owner as stop operator. A technical-control approval may cover
only the three missing unscored A/C-by-tier mechanics cells. Qualification
requires another approval after those controls pass. Neither the route-check
approval nor this reconciliation alone authorizes either phase.
