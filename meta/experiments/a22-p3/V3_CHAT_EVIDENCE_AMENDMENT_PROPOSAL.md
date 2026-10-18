# A22 P3 V3 chat-evidence amendment

**Status: additive evidence binding for `technical_source`; it preserves the prior amendment and seal.**

The retained Codex session log contains the owner's original quoted approval and a later
explicit override. This amendment records those source messages as they appear in the log and
adds a deterministic normalization for the wrapped Markdown quote. It does not claim that the
local JSONL log is signed or independently authenticated.

## Source messages

The evidence artifact lives outside the repository at
`/tmp/a22-p3-v3-chat-evidence-2.json`. It binds hashes of the selected source-log records and keeps
each raw text, message ID, turn ID, ordinal, timestamp, and raw-text hash. The source is
`/home/ai/.codex/sessions/2026/09/23/rollout-2026-09-23T09-16-25-01a0cd8d-4d82-7ac0-8b96-ce11eb0ff664.jsonl`
with session ID `01a0cd8d-4d82-7ac0-8b96-ce11eb0ff664`.

The quoted approval is message `msg_01a13fac-74fc-7c53-b0e8-3ccd0cab5518` at ordinal
23009. Its raw Markdown text is preserved in the external artifact. The later override is
message `msg_01a13fd2-60d4-76c1-9534-789886872230` at ordinal 23313. Its exact text is
`запусти все, я утверждаю без этой повторной отправки с коррекцией символов.` The override
is recorded as permission to proceed without resending corrected symbols, scoped only to
`technical_source`. It does not authorize scorer routes, qualification, comparison, repair,
retry, or another provider call.

## Quote normalization

The canonical approval quote is the plain-text sentence below. Markdown backticks in the
older proposal are presentation only; they are omitted from this canonical form.

> I accept the V3-only 5,000,000-token Codex accounting ceiling, including its exclusion of the known 153,614-token V2 debit and unresolved q1461 usage from that ceiling while preserving both as separately reported V2 history. I accept the frozen technical-source conditions, the OBSERVED_NO_RETRY evidence limit, the 80% five-hour and 90% weekly stop thresholds, the requirement for fresh interpretable quota telemetry, and the named human stop operator recorded in the amended approval. I authorize only the technical_source phase for the exact amended proposal and seal. This does not authorize route checks, qualification, comparison, repair, retry, or any other provider call.

Normalization ID `blockquote-soft-wrap-dehyphen-v1` requires every physical line to begin
with optional whitespace and `>`, removes that quote marker and at most one following ASCII
space, joins non-empty wrapped lines with one ASCII space, joins a word split at a line-final
ASCII hyphen to its next lowercase ASCII word fragment, then collapses whitespace runs and
trims. The validator compares the result to the canonical quote and separately retains the
raw string. Therefore raw text is not represented as byte-for-byte equal to the canonical
quote.

## Binding and limits

The new seal binds this proposal, the prior source-phase seal by hash, the current source gate
and evidence validator, and the external evidence artifact and source-log hashes. The prior
proposal and seal remain unchanged. This is an additive provenance binding; it is not a
cryptographic signature, account-identity proof, or guarantee that the retained log cannot be
edited by its owner. A reviewer can reproduce the extraction and normalization from the
recorded local log and artifact.

The extractor scans by the two recorded message IDs. Malformed unrelated JSONL rows are
skipped; a malformed row containing either selected ID fails closed. The evidence hash covers
the session-metadata row and the two selected message rows, so later append-only events do not
change this binding. It does not claim integrity or completeness for unrelated log rows.
