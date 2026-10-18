# A22 P3 V3 qualification successor proposal

**Status: historical usage direction accepted, four technical mechanics conditions verified (M137, M142), and current-CLI Codex scorer routing verified (M144); qualification operational preparation. This proposal alone does not authorize provider dispatch.**

## Basis and boundary

The verified two-turn `P3-01` / `A` / strongest / repeat-1 source (M137) and the two
terminal, unscored scorer route checks (M138) are mechanics evidence only. The route
seal and approval authorize `route_checks` only. Do not promote the source or either
route check into a scored output, a qualification cell, or an accepted scorer reading.
Preserve their sealed bytes and runtime records. The later V3 ledgers report
66,491 observed Codex tokens after the routes; keep V2's known 153,614 tokens
and unresolved `q1461` separately reported under the accepted V3-only
5,000,000-token boundary. The first V3 source attempt also has a terminal
`UNKNOWN_USAGE` entry in its own ledger. Its event stream exposes 7,766 tokens,
but that number was not accepted as a correlated ledger debit. Before any new
provider call, bind the exact disposition of this **V3** uncertainty to the
qualification accounting gate; do not silently treat the later ledger balance
as all V3 exposure or turn the unknown into zero. A fresh read-only audit found
one direct `turn.completed.usage` event, but it contains only `type` and `usage`:
no call, turn or session ID. The paired rollout has session/turn IDs but no
provider-call ID shared with that event. The execution envelope supports a
likely association, not the unique direct correlation required by the lean
protocol. The ledger's `UNKNOWN_USAGE` classification therefore stands.

The verified A/strongest source supplies one mechanics condition (M137), and
the three fresh, unscored A/mid, C/strongest and C/mid controls passed on Codex
CLI 0.162.1 under a separately accepted seal (M142). Their six calls have known
usage, verified two-turn sessions, frozen case/arm hashes and no visible tools
or retries. They are not qualification cells. Across the three earlier source
attempts and these three controls, six of 24 technical/defect subject attempts
are used; at most 18 remain, subject to the next cross-ledger check. The
earlier scorer route checks are scorer calls, not subject attempts, and used
Codex CLI 0.156.1. A separately authorized, unscored Codex scorer mechanics
check on CLI 0.162.1 subsequently passed (M144). Qualification is the next
proposed executable scope; it is not authorized by either route approval.

The unresolved first V3 usage was an **admission blocker under the previous
accounting rule**. The owner accepted the narrow historical process-envelope
exception described below. Its [separate decision and receipt](V3_HISTORICAL_USAGE_RECONCILIATION.md)
preserve the original `UNKNOWN_USAGE` ledger and charge the observation to
future V3 admissions. This decision did not itself authorize a control or qualification provider
call. The controls have since run under their own exact seal and approval;
qualification still needs a new operational seal, preflight and approval.

A narrow historical-correlation rule applies **only** to
the first V3 technical attempt's reserved call
`b56635eca40db627519d47d4717d379f` in subject attempt
`95e85fab70b5464fd4b520d321088003`. The captured direct usage event has
SHA-256 `6d88be4f6e70f0b19a3656e8dfaffddb227e495359af41e7c81645171324e31b`;
the paired rollout has SHA-256
`97d12028aedcae2eea8622022a223ac20e119d08df7a5e9cb15f854cddef6480`.
The validator requires a unique reserved call and a unique completed event in that isolated
process capture, the same 7,737 input / 29 output values in the rollout, and
no competing attempt in the runtime envelope. The original
`UNKNOWN_USAGE` ledger entry remains; the separately hashed reconciliation
receipt charges 7,766 tokens as *historical, envelope-correlated usage*
to every later V3 admission check. The checked post-route V3 opening balance was 74,257 tokens, rather than the
previously reported 66,491 known tokens. The accepted controls added 127,963
tokens, yielding 202,220 charged V3 Codex tokens before the current-CLI route
check (M142). That check added 12,453 tokens, yielding 214,673 charged V3 Codex
tokens before qualification (M144).
This does not claim direct event-to-call correlation or apply the weaker rule
to future calls. If any receipt or source condition fails on revalidation,
the stop remains in force.

After an accepted qualification seal and fresh quota evidence, start A with fresh
IDs: eight frozen cards ×
two subject tiers × two repeats = 32 two-turn subject outputs. Score each eligible
output once with each of the two fixed, independent routes. The qualification
phase stops with 32 complete Codex readings and 32 complete Qwen readings, or
earlier on a protocol stop. Seal the qualified-stratum map only from both complete
scorer datasets: a card × tier qualifies when both scorers fail the same A
repeat. Require at least four qualifying strata and at least one in each of the
four pairs before proposing B/C comparison. No B/C call is authorized here.

All subject prompts, cards, arms, rubric and scoring prompt come from the
existing sealed P3 packet. Do not adapt cards, trim the baseline, disclose the
arm/tier/model/qualification identity to scorers, or score clause wording,
verbosity or citations. Freeze the exact 32-cell order, IDs, packet/arm hashes,
turn-2 replies and both scorer schedules in an operational seal before calls.
Retain complete failures and discarded outputs; a defective cell gets no
replacement under this approval. The fixed ceiling remains 96 scored subject
runs, at most 24 technical/defect attempts, 120 total subject attempts, and 240
scorer passes including route checks and failures. The 40,000-token subject
input limit remains, with only the predeclared C-only 50,000-token exception.

## Scorer and output interpretation

The new [offline candidate schedule](runs/v3-qualification-schedule-v1.json) fixes
32 fresh A run IDs, one subject attempt and two subject call IDs per cell, one
opaque packet ID shared by the two scorer routes, 64 scorer call IDs, shuffled
cell order, and alternating scorer order. Its [generator and verifier](v3_qualification_schedule.py)
recheck the original packet seal and reject missing/duplicate cells and IDs.
The [packet renderer](v3_qualification_packet.py) uses the frozen renderer and
scoring prompt, checks the exchange against the exact first turn and resolved
second-turn reply, and yields the same blinded request bytes for both routes.
The [offline reducer](v3_qualification_reduce.py) requires all 64 complete
readings, retains element disagreements, and applies the same-repeat floor;
it never authorizes comparison on its own.
The [one-call-at-a-time dispatch runner](v3_qualification_dispatch.py) binds these
artifacts to a dedicated qualification ledger and output root. Its offline preflight
and operational seal must pass before it can use the owner's phase approval; each
call is independently reserved and terminal. The evidence importer reduces only
all 128 accepted scheduled calls, binding each scorer reply to its call ID, raw
reply and request evidence. These are still preparation artifacts until the seal,
preflight and approval are recorded; no accepted scored result exists. The earlier
`runs/qual-sealed-map.json` remains a sealed historical map; it cannot supply
fresh V3 qualification IDs or be silently reused by the legacy builder.

For the qualification predicate, each scorer marks a **run** failed if any
applicable E element fails. A card × tier stratum qualifies when both scorers
mark at least one **same repeat/run** failed; they need not select the same E
element. B and C then each run both repeats within every selected stratum, so
their matched comparison remains balanced even if qualification selects uneven
numbers of strata across cards or tiers. Publish that coverage; do not imply
the four-stratum floor is representative of all eight cards or both tiers.

Use Codex CLI 0.162.1 / `gpt-6-astra` medium under the fresh scorer route
check that validated this version (M144). Keep Qwen CLI 0.24.7 / `qwen3.8-27b` **with default
thinking retained** under its recorded route condition. The Qwen overlay
must omit a thinking-disable override, reject an existing disable setting,
retain `maxRetries: 0`, set the local output setting to 2,000 tokens and
correlate one usage record to the one session. The earlier controlled Qwen
canary (M125) observed a thinking block; the route check verifies configuration and
response mechanics, not a guarantee that every reply exposes a thinking block.
Stop if the configured or reported model, observable thinking configuration,
usage correlation, or observed retry/tool controls differ. An absent thinking
block in a particular answer is not by itself evidence that thinking was
disabled. Codex keeps the observed 20,000-input /
1,000-output scorer limits; Qwen keeps 20,000 observed input and its 2,000
output setting, which is not a hard provider cap.

For TSV acceptance, **the exact header must be the first nonempty line**, and
the only following nonempty lines must be one valid row for each expected
element. Whitespace-only lines before, between or after these lines are ignored.
This is the already frozen `validate_tsv()` behavior; it does not reinterpret or
alter M138's Qwen reply. A byte-zero-header rule would reject that reply and
would require a new, separately reviewed scorer condition and route check.
Preserve raw output as well as parsed rows so either reading is auditable.

## Accounting, stops, and evidence gate

Use `OBSERVED_NO_RETRY` only for visible CLI/session events; hidden transport
retries cannot be excluded. One direct correlated usage debit is required for
every Codex call, including failed calls. Unknown Codex usage locks all later
V3 dispatch unless an exact separately accepted disposition resolves that
lineage. Qwen has no aggregate token ceiling, but each call needs complete
correlated usage. Fetch fresh, interpretable Codex subscription telemetry
immediately before each Codex call; stop at 80% five-hour or 90% weekly usage.
The current human stop operator is the owner of this chat session. A completed
call may exceed an observed per-call limit before the next stop; record it and
stop rather than treating the setting as a provider-enforced hard cap.

The operational package must have a new V3 qualification ledger and output root, exact
source/route evidence bindings, a default-deny phase approval, negative gates
for stale hashes/duplicate IDs/unknown usage/partial readings, and offline
regression tests. The qualification preflight must bind the completed four control conditions,
new-version Codex scorer-route evidence, packet blinding, score schedule, model
pins, stop controls, write isolation, historical usage receipt and current
214,673-token V3 accounting before requesting a separate owner
acceptance for qualification. Each accepted phase
needs fresh quota evidence before dispatch; the route approval does not carry
over. No comparison, repair, retry, adjudication or other provider calls are
included.

## Why this boundary

The alternative of immediately counting the verified technical source or
route checks as A data would save calls but violates the predeclared grid and
scorer blinding. Requiring a header at byte zero would invalidate the passed
Qwen route on formatting alone and change the frozen parser condition after
seeing its output. Keeping the first-nonempty-line rule preserves the observed
mechanics condition while leaving the raw bytes available to independent audit.
If Qwen's thinking mode cannot be verified under the same configuration during
implementation, stop and review a new scorer condition before dispatch.
