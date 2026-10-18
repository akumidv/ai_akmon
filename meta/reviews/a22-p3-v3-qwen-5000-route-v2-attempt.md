# A22 P3 V3 Qwen 5,000-token route successor — Codex GPT-6 review

**Verdict:** the second isolated Qwen route reached the model and produced a
complete, correlated response within the 5,000-token setting, but the frozen
TSV parser rejected it. The model placed explanatory prose before the TSV
header. This one-shot route is terminal and does not establish accepted scorer
mechanics, qualification data or a comparison result.

The [successor proposal](../experiments/a22-p3/V3_QWEN_5000_ROUTE_V2_PROPOSAL.md),
[seal](../experiments/a22-p3/runs/v3-qwen-5000-route-seal-v2.json),
[offline preflight](../experiments/a22-p3/runs/v3-qwen-5000-route-preflight-v2.json)
and [phase approval](../experiments/a22-p3/runs/v3-qwen-5000-route-approval-v2.json)
bind a new runtime, the preceding terminal DNS attempt, the frozen P3-01 blind
packet and scoring prompt, Qwen CLI 0.24.7 / `qwen3.8-27b`, default thinking,
`maxRetries: 0` and a local 5,000-token output setting. Their seal, preflight
and approval SHA-256 values are respectively
`4264c87b2003316bf7bb8981b00df5ad0e4826c889e696eeab353c4455036bc0`,
`246e6ffafb31a0d7e2de3e8ff452aad86b8c58b0347e46a931af8fc592dae391`
and `469dbd95939938adf26970de54eacb5eccc597b76fe9d1b8b9adecedc93942ca`.
Five targeted offline regression tests, Ruff check and format check passed.

The private runtime `/tmp/a22-p3-v3-qwen-5000-route-v2-runtime` contains one
reserved call `g955fbe25df9a40d4b633e6b9f37a1026`, one CLI process and one
terminal outcome. DNS was verified reachable outside the restricted network
sandbox before dispatch. The Qwen result reports success, one request, zero
tool calls and 12,710 input + 437 output tokens, directly correlated to its
single session in the local usage record. A thinking block was observed, and
no CLI-visible tool or retry/error marker appeared. Hidden transport retry
behavior is not independently observable.

The complete final text begins with explanatory prose and only later has the
required `run_id\telement\tverdict\treason` header. The frozen parser raises
`ValueError: scorer TSV header mismatch` because that header is not the first
nonempty line. An offline diagnostic showed that the suffix starting at the
header parses as four E1–E4 rows, but the suffix is **not** an accepted scorer
reply under this route's sealed rule; no row is entered into qualification.
The raw stdout SHA-256 is
`d9855d3a467a5c4e4746e6180726a08600817abc29980b5454311db961f57958`,
the reply SHA-256 is
`44977704bd96206c4053a4defc09da229a2603fa45bdd781b88e75b77b7e4da4`,
the correlated usage record SHA-256 is
`a38819e67ee4a4cf3cf0a72b5239bdaf133de79f6148c494ac4653d204809d2d`,
and the failed outcome SHA-256 is
`21e077940049c8f4832406af171cfe25113bd9cb9f08a837c129c3791dcd81c3`.
`retry_authorized` is false; no second call was made under this seal.

The earlier DNS attempt still has unknown Qwen usage and remains separate.
V3 charged Codex use remains 273,286 of 5,000,000 tokens. This response shows
that 5,000 output tokens were sufficient for this *route packet*; it does not
establish sufficiency for all qualification cases. Before any next call, choose
and freeze a scorer-format remedy in a distinct proposal: either strengthen
the model instruction while retaining the strict parser, or explicitly accept
a bounded preamble extractor and recheck it offline against adversarial output.
Such a choice changes the scorer condition and requires its own route check;
the current failed reply cannot be retroactively accepted.
