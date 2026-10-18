# A22 P3 V3 qualification attempt — Codex GPT-6 review

**Verdict:** the owner-authorized qualification attempt stopped at its seventh
provider call. It cannot be resumed or retried under this operational seal.
One of 32 A cells has two accepted scorer readings; the next has two accepted
subject turns but no accepted scorer reading. No qualification map or B/C
comparison is established.

The [operational seal](../experiments/a22-p3/runs/v3-qualification-operational-seal-v1.json),
[offline preflight](../experiments/a22-p3/runs/v3-qualification-preflight-v1.json)
and [phase approval](../experiments/a22-p3/runs/v3-qualification-approval-v1.json)
bind the 128-call schedule, 214,673-token V3 Codex opening, exact inputs and
owner's qualification-only authorization. Dispatch occurred in the detached
`/tmp/a22-p3-v3-qualification-checkout` worktree. The private runtime is
`/tmp/a22-p3-v3-qualification-runtime`; its ledger SHA-256 is
`ab0408ec2b373839b94fcb0fab5b2c08185032f97ac2ca71fa09237e76945b8e`.
The ledger has one header and seven reservation/completion pairs: six accepted
and one failed. No provider process remained active when the ledger was audited.

The first cell (`P3-06`, A/mid, run `gaa0508d171da94ed1c979e83b0eaa77e`)
completed two Codex subject calls and one reading from each scorer. The Codex
and Qwen scorers received the same blinded packet and request. These are
individual accepted readings, not a qualified stratum: the predeclared
predicate requires both complete 32-cell scorer datasets and the same-repeat
floor. The second cell's two subject calls were accepted. Its first scorer,
Qwen call `ga8200254248a05bf5e54c35f831b305e`, returned a successful CLI
result with correlated usage of 12,591 input and exactly 2,000 output tokens,
but no final text. The raw event contains an unfinished thinking block; the
local 2,000-token output setting was exhausted before an E1–E3 TSV could be
emitted. The runner recorded a terminal `ValueError` from TSV validation,
`retry_authorized: false`, and a failed completion. The failed raw stdout has
SHA-256 `9a8eb1642424a511f98282c7bbe6a5328137b92bb699a0a409fb0a55abb431f0`;
its terminal failure record has SHA-256
`6fee7e7c421d44cff997c112fc66940cafd8935997b036ca63db796731b3fff1`.
`status` now returns `QUALIFICATION_STOP`; the missing Codex scorer call for
that cell was not dispatched. This is an observed output-cap failure, not an
E-element FAIL or a model-quality result. No hidden transport retry claim is
made.

Five Codex calls in this attempt used 58,613 directly recorded tokens. The
charged V3 Codex total is **273,286 / 5,000,000**; the separate known V2
153,614-token debit and unresolved q1461 history remain outside that V3 ceiling.
The two Qwen calls used 12,591 input + 1,696 output and 12,591 input + 2,000
output respectively. Fresh pre-call quota records exist for each Codex call;
the stop came from the Qwen response, not a subscription threshold.

The next step is an **offline** successor design: decide and freeze a Qwen
output allowance large enough for default thinking and the requested TSV,
recheck scorer-route mechanics under that allowance, and construct a distinct
seal, preflight, schedule and approval. The earlier 2,000-token setting was an
owner-accepted starting point, with up to 5,000 discussed if needed; this
failure supplies the need, but does not authorize changing a sealed condition
or replaying this failed call. Keep the full terminal evidence and account for
the spent calls in the successor. Any successor must preserve a comparable
scoring task, the two-scorer same-repeat rule, Codex ceiling and quota stops,
and `OBSERVED_NO_RETRY`. No provider call is authorized by this review.
