# A22 P3 V3 qualification successor

**Scope:** a fresh 32-cell A qualification only. This document, seal and offline
preflight do not themselves authorize provider dispatch. The terminal seven-call
attempt remains closed; none of its output becomes a cell in this dataset.

The previous qualification stopped when Qwen spent its 2,000-token output setting
in thinking and returned no final TSV. Subsequent one-shot Qwen and Codex route
checks passed on the same format-only prompt (M148–M149). The successor retains
Qwen `qwen3.8-27b` with provider-default thinking, sets its local output allowance
to 5,000 tokens, and uses `scorer-prompt-format-v2.txt` for both scorers. That
prompt adds final TSV formatting instructions to the original sealed rubric;
the E1–E4 criteria and strict first-nonempty-line parser remain unchanged. The
route checks cover one packet and do not guarantee that every qualification
packet will fit or pass.

Generate new run, subject, packet and scorer call IDs with no overlap with the
terminal schedule. Freeze the complete order before dispatch. Each of eight
frozen cases has two tiers and two repeats: 32 two-turn A subject sessions,
followed by one reading from each scorer on identical blinded request bytes,
for 128 scheduled provider calls. A failure, missing usage, malformed TSV,
changed model, tool/retry marker or exhausted output setting stops the phase;
there is no automatic or same-seal retry, replacement or repair. Each call is
reserved and terminal. Preserve raw evidence, including failed calls.

Codex subject models remain `gpt-6-astra` strongest and `gpt-5.6-luna` mid at
medium effort; the Codex scorer remains `gpt-6-astra` medium on CLI 0.162.1.
The Qwen scorer remains CLI 0.24.7, default thinking, `maxRetries: 0`, 20,000
observed input and 5,000 local output tokens. Codex scorer limits remain
20,000 observed input and 1,000 observed output; subject input remains 40,000.
The accepted Qwen route verifies the altered allowance and final-format
mechanics, not a provider-enforced hard output cap. Record actual usage for
every call.

The V3-only Codex opening is 285,782 of 5,000,000 charged tokens: 202,220
through the technical controls, 12,453 for the prior Codex scorer route,
58,613 in the terminal qualification, and 12,496 in the format-route check.
Keep V2's known 153,614-token debit and unresolved q1461 separate. Before
each Codex call, require fresh interpretable subscription telemetry for the
pinned account/executable; stop at 80% five-hour or 90% weekly usage. Unknown
Codex usage locks further calls. `OBSERVED_NO_RETRY` covers visible CLI events,
not hidden transport behavior. Qwen has no aggregate token ceiling but needs
one correlated usage record per call.

Only two complete 32-reading scorer datasets can establish the qualification
map. A card × tier qualifies when both scorers mark a failure on the same A
repeat, even if they disagree on the E element. Require at least four strata
spanning all four case pairs. Publish coverage and disagreements. This phase
never authorizes B/C comparison. The prior 96 scored-run, 24 technical-attempt,
120 total subject-attempt and 240 scorer-pass ceilings remain; include all
historical failed and route calls in the relevant totals before admission.

The operational seal binds the frozen packet, fresh schedule, exact code and
tests, both passed format-route seals/outcomes, terminal predecessor evidence,
model pins, settings, resource stops and private runtime. The preflight is
offline and default-deny. A separate owner acceptance of this exact successor
package is required before its first provider call. The owner of this chat
session is the stop operator; no repeated name or seal hash is requested.
