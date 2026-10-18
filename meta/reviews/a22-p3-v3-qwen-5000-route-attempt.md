# A22 P3 V3 Qwen 5,000-token route attempt — Codex GPT-6 review

**Verdict:** one separately sealed, unscored Qwen route call stopped on DNS
resolution before a model response. The 5,000-token setting and default-thinking
configuration passed offline preflight, but scorer mechanics did not pass. The
one-shot call is terminal. No qualification call, scorer reading, or comparison
was added by this successor.

The [proposal](../experiments/a22-p3/V3_QWEN_5000_ROUTE_PROPOSAL.md),
[operational seal](../experiments/a22-p3/runs/v3-qwen-5000-route-seal-v1.json),
[offline preflight](../experiments/a22-p3/runs/v3-qwen-5000-route-preflight-v1.json),
and [phase approval](../experiments/a22-p3/runs/v3-qwen-5000-route-approval-v1.json)
bind the one-call route. Their SHA-256 values are respectively recorded in the
seal, `a8403cf0a9a8b233574c16f13725d094652441535f2f9b3867256b6561b2c012`,
`df4f623646f6b02c9455dcf0cbd21abdbb14b452ca83e77d714cc82c9b35e38a`,
and `e275eb83ce7c18db9ebb6265e36e12ad0f1e4edc0f7222a0ca3d9e1192ee4ff3`.
The same frozen, unscored P3-01 route packet and scoring prompt were
re-rendered before dispatch; Qwen CLI 0.24.7, `qwen3.8-27b`, provider-default
thinking, `maxRetries: 0`, no tool allowance, and an output setting of 5,000
were checked. Four targeted offline regression tests, ruff check and format
check passed. The old qualification source and ledger stayed unchanged.

The private runtime is `/tmp/a22-p3-v3-qwen-5000-route-runtime`. Its
reservation binds call `geb6c462b053e4a579aed9f7842bd8903`, the sealed
request, the phase approval and one Qwen session. The one CLI process returned
an `error_during_execution` event with `getaddrinfo EAI_AGAIN litellm.local`;
the event reports zero API duration and zero token usage. The local correlated
Qwen usage file has no record for that session, so the accepted usage status is
**unknown**, not a confirmed zero provider debit. The runner wrote a terminal
failed outcome with `retry_authorized: false`; it made no second provider
call. The raw stdout SHA-256 is
`33133f9fd59e51fcc3b556eecbe475aa9665d8e8148df4f162cb76c4ce4c5e94`,
the outcome SHA-256 is
`70d3f971337eb9056c0de27d7bacd969516e1da49c5bdcf1f97c0a7192e3a975`,
and the reservation SHA-256 is
`0c2fc5b5da0a54a763e87c623fdc3f10e7b2ae06f89466516319aad35e543dd8`.
The observed failure is DNS/network reachability, not a scorer judgment or
evidence that 5,000 output tokens suffice or fail.

The prior qualification ledger remains terminal with six accepted calls and
one failed Qwen call; V3 charged Codex usage remains 273,286 of 5,000,000
tokens. The next provider step requires a **new** sealed route attempt in an
environment that can resolve the gateway, with this terminal network event
retained and its unknown Qwen usage reported. The current seal cannot be
reused. A successful mechanics route would still require a separately sealed
fresh qualification package and its own dispatch authorization.
