# A22 P3 V3 header-optional route V8 — Codex GPT-6 review

**Result:** the owner-authorized V8 mechanics route completed all four unscored calls on two distinct blind packets. The ledger has one header and four reservation/completion pairs in sealed plan order; each outcome is `passed_unscored`, with `scored_p3=false`, `qualification_data=false`, no failure, no actual tool marker and no visible retry/error marker. This demonstrates that the prospective header-optional parser and the two scorer CLI routes can produce and validate packet-bound E1–E4 TSV on these two packets. It does not establish scorer agreement, A qualification, B/C effects, or a provider-level zero-retry guarantee.

| Blind packet | Route | Input / output tokens | Header handling | Outcome SHA-256 |
| --- | --- | ---: | --- | --- |
| prior route | Qwen `qwen3.8-27b` | 12,783 / 891 | fixed header inserted | `8acf61fb93a7ab61573775bfa0f2dc5fd8b4aeba243bb821010b97342e2a8918` |
| prior route | Codex `gpt-6-astra` | 15,538 / 131 | exact header | `a97e0fcb802e23a516230ec306ac7efc93ababf128eece25e915d231ee4a8666` |
| identity bound | Qwen `qwen3.8-27b` | 12,713 / 939 | exact header | `f5ed8da440d4c359ef2e88dbc3539ffe3fb5749ee22d3695fd3a6f02f71171bc` |
| identity bound | Codex `gpt-6-astra` | 15,470 / 97 | exact header | `d77156e2c411776f486f82eca38c84b267ffc78333df40761cc26d1e2d4752a5` |

Both Qwen calls used CLI 0.24.7, provider-default thinking, a 5,000-token local output setting, and one correlated request with zero tool calls. Both Codex calls used CLI 0.162.1 at medium effort, one correlated session each, and fresh subscription readings before dispatch: five-hour use 20% then 22% (stop at 80%); weekly use 3% in both (stop at 90%). Codex added 31,236 tokens, moving the V3-only charge from 636,645 to **667,881 / 5,000,000**. Qwen added 25,496 input and 1,830 output tokens; it has no aggregate cost ceiling in this protocol.

The sealed [plan](../experiments/a22-p3/runs/v3-header-optional-route-plan-v8.json), [seal](../experiments/a22-p3/runs/v3-header-optional-route-seal-v8.json), [live preflight](../experiments/a22-p3/runs/v3-header-optional-route-live-preflight-v8.json), and [owner approval](../experiments/a22-p3/runs/v3-header-optional-route-approval-v8.json) identify this attempt. The private runtime is `/tmp/a22-p3-v3-header-optional-route-v8-runtime`; its ledger SHA-256 is `c3693f9d54078175548a7a7f8d538ad50918346595d077a5212d4401bae2ce85`. The two Codex quota-receipt SHA-256 values are `aa99a5b190fdd3b999e3ce39a6b97bcdc42ae92c60214b531dc88ba9636e824c` and `3c8bc786f35bab2c657b17b9ff1c9306ac4767a0475ec9b772408c97c50da0fd`. Raw packets, responses and private usage evidence remain in that runtime; no old terminal call was retried.

**Next gate:** prepare a fresh A-qualification schedule, runner/seal, tests and preflight that bind this passing V8 route and keep the old failed attempts terminal. Review that concrete package before any separate qualification authorization or provider call. No qualification or comparison dispatch follows from this route approval.
