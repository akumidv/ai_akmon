# A22 P3 V3 successor scorer route checks

**Status: preparation only; no route-check dispatch under this proposal.**

The verified technical source is run `4c22e100b2101c0d67067d33fd98cd92`,
`P3-01` / A / strongest / repeat 1, from the separate successor attempt. Its
record and exchange remain outside the repository under
`/tmp/a22-p3-v3-successor-9xViiq/output-run/`. M137 records 27,022 known tokens
for its two calls and 54,010 observed V3 Codex tokens including the prior
terminal technical attempt. This source is evaluator-only, unscored, and cannot
fill an A qualification cell. The earlier failed source lineages are not inputs.

The next phase is exactly two unscored route checks, one Codex CLI 0.156.1 /
`gpt-6-astra` at medium effort and one Qwen CLI 0.24.7 / `qwen3.8-27b` with
default thinking. Generate one fresh opaque packet from the verified source and
the sealed `P3-01` scoring elements. Both routes receive byte-identical packet
and scorer prompt content. The model-visible request carries no source run ID,
arm, tier, model, or qualification label; the private evaluator manifest binds
those facts and the source hashes. A route gets one provider process, one
correlated usage record, no observed tool use or retry/error marker, and a
complete exact-header E1–E4 TSV. The criterion is `OBSERVED_NO_RETRY` at the
observable CLI/session layer; it cannot prove the absence of hidden transport
retries. Any failure is terminal, without a replacement call. Neither check
is an accepted scored reading or a qualification result.

The V3-only 5,000,000-token observed Codex ceiling carries all four known V3
source-turn debits (54,010 tokens) into route admission. V2's 153,614 known
tokens and `q1461` unknown usage remain separately reported V2 history. Qwen
has no aggregate token ceiling. Apply the accepted 80% five-hour and 90%
weekly Codex stops using a fresh interpretable quota snapshot immediately
before its call. Preserve one direct correlated usage debit per Codex call,
the observed 20,000-input / 1,000-output Codex scorer limits, and Qwen's
2,000-output setting and 20,000 observed-input limit. A completed call can
exceed an observed limit before the next stop. Unknown Codex usage locks all
later V3 dispatch; missing Qwen usage fails its route.

Implementation must use a new V3 route ledger/output root and must neither
append to V2 artifacts nor rewrite prior V3 source ledgers. Bind exact source
record, exchange, rollout, packet, scorer prompt, route runner, approval,
and this proposal in a new operational seal. Offline preflight must verify
those hashes, source identity and correlated two-turn usage, packet blinding,
identical packet/prompt bytes for both routes, model/CLI pins, one-shot route
accounting, no-score classification, negative gates, and write isolation.
The phase approval starts default-deny. Before any provider call, the owner
must accept the exact resulting seal, authorize `route_checks` only, name the
current human stop operator, and the phase gate must pass with fresh quota
evidence. The prior `technical_source` approval does not authorize this phase.

If both route checks pass, retain their unscored evidence and prepare a
separate qualification proposal and approval. The current request does not
authorize qualification, comparison, repair, retry, or other provider calls.
