# A22 P3 V3 qualification successor attempt — Codex GPT-6 review

**Verdict:** the owner-authorized qualification successor stopped terminally on
scheduled call 31 of 128. Thirty calls were accepted; seven of 32 A cells have
both scorer readings, and the eighth has two accepted subject turns but no
accepted scorer reading. No qualification map or B/C comparison is established.
The failed call is not eligible for retry or replacement under this seal.

The [proposal](../experiments/a22-p3/V3_QUALIFICATION_SUCCESSOR_PROPOSAL.md),
[operational seal](../experiments/a22-p3/runs/v3-qualification-successor-seal-v1.json),
[offline preflight](../experiments/a22-p3/runs/v3-qualification-successor-preflight-v1.json)
and [owner approval](../experiments/a22-p3/runs/v3-qualification-successor-approval-v1.json)
bind the 32-cell schedule and qualification-only dispatch. The seal SHA-256 is
`0966558a7fcc575ed2d24400f802f02481003d821f2970d8ebac8531fe6d3206`.
Execution was in the detached `/tmp/a22-p3-v3-qualification-checkout` worktree.
The private raw runtime remains at
`/tmp/a22-p3-v3-qualification-successor-runtime`; it was not copied into the
repository because it contains provider credentials and CLI state. Its
SHA-256-chained `qualification-events.jsonl` has one header and 31
reservation/completion pairs, ending with a failed completion. The ledger
SHA-256 is
`77310abd1045e5c5f7357f5f6378d4f9fd22681e9c2261a610db735ad77113e1`.

The 31st call was the Qwen scorer for `P3-01`, A/mid, repeat 1, run
`g538b058fa21a3e23e5886e0860a3da44`, call
`g225a6ea21aeb6b0df81a151977b43f20`. A single correlated Qwen usage
record shows one request, 12,779 input and 558 output tokens, and zero tool
calls on `qwen3.8-27b` with default thinking and a 5,000-token output setting.
The reply had the required header as its first nonempty line and four E rows,
but all four data rows used `gf04a4422bf50dd1`, omitting the final `f` from
the packet's `gf04a4422bf50dd1f`. No row had a quote-prefixed ID. The
frozen parser requires the first TSV column to equal that ID byte for byte;
an offline replay of `validate_tsv` on the saved reply raises `ValueError:
scorer TSV row is malformed`. The reply SHA-256 is
`25a2704f6f6b186ea926083f4c101c24bad8444bd7d5b5387a320554182ba4d8`.
This is observed format drift, not output exhaustion or an E-element verdict.
No CLI-visible tool or retry/error marker appeared; hidden transport retries
are not independently observable. The failure record has SHA-256
`7c5e0daf13166f43e6a5cd3fd9b9e2d40ddc455ac8c32cc284cfb7f09d95b9d9`
and states `retry_authorized: false`. The scheduled Codex scorer for that
eighth cell was not sent.

Twenty-three accepted Codex calls in this successor added 274,053 directly
recorded tokens. Charged V3-only Codex usage is **559,835 / 5,000,000**,
including its 285,782-token opening. The separate V2 known 153,614-token
debit and unresolved q1461 usage remain historical and outside that ceiling.
Each dispatched Codex call had a fresh pre-call quota checkpoint; the terminal
stop was the Qwen format failure, not a Codex quota or aggregate-budget stop.
Eight Qwen scorer calls were made here: seven accepted and this one failed.

The one-packet Qwen and Codex format-route passes (M148–M149) did not predict
every qualification output. A future attempt needs a distinct sealed design,
fresh schedule and explicit phase authorization. An offline design review
should choose whether to tighten exact-ID copying instructions or redesign
the scorer response so packet identity is bound by the runner rather than
copied by the model, then recheck route mechanics before any fresh qualification.
Normalizing the missing ID character would silently change packet identity.
Neither option repairs or reclassifies this terminal call.
