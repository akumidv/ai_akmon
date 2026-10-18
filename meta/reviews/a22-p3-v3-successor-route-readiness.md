# A22 P3 V3 successor scorer routes: offline readiness

**Role:** `review` · **Model:** Codex GPT-6; independent file review by GPT-6 Luna · **Status:** offline candidate, dispatch denied.

The verified M137 technical source produced one blinded `P3-01` packet with opaque ID
`g286aa508b7bdeefe`. The model-visible file is
`/tmp/a22-p3-v3-successor-route-packet/visible/packet.md`; the private manifest is
under its sibling `evaluator/`. The packet SHA-256 is
`5cce39ac1d12dcb99ab5623e0c44e541df4f471e07f8c972626d574adfcf450c`.
The Codex and Qwen route checks are designed to use those same exact packet and
scorer-prompt bytes. No source run ID, arm, tier, model, or qualification label
appears in the model-visible packet. Source identity and exact hashes remain
evaluator-only. Both checks are unscored and cannot count toward qualification.

The [proposal](../experiments/a22-p3/V3_SUCCESSOR_ROUTE_CHECK_PROPOSAL.md),
[V3 packet builder](../experiments/a22-p3/v3_successor_route_packet.py), and
[route gate](../experiments/a22-p3/v3_successor_route_check.py) are bound by the
candidate [seal](../experiments/a22-p3/runs/successor-route-check-seal-v6.json),
SHA-256 `b42d0a8a6962f800b71e2cfe526bad27ee0e84359def3845aa4a0f40abd01f79`.
It carries the successful source record, exchange, source ledger, packet,
frozen prompt, helper sources, and regression hash. The
[offline preflight](../experiments/a22-p3/runs/successor-route-check-preflight-v6.json)
passed with zero provider calls and 54,010 prior observed V3 Codex tokens.
Seven focused synthetic tests passed; Ruff check and format check passed. The
default-deny dispatch probe returned `DISPATCH_BLOCKED` before creating a
runtime directory. Both pinned CLIs report the expected local versions,
Codex 0.156.1 and Qwen 0.24.7. The configured Qwen endpoint uses HTTPS and
has no URL userinfo, query, or fragment; this is a local configuration check,
not a gateway response.

The independent review found that an existing shared `/tmp` runtime could
expose credentials and transcripts, that sensitive Qwen URL components could
reach process arguments, and that the source-use check did not enforce distinct
turn-1/turn-2 calls. The current code rejects shared or linked runtime and
lock paths, rejects those URL components, and checks unique call IDs, both
reservations and completions, turn IDs, subject-attempt ID, route, outcome,
and usage. The append-only route journal binds the candidate seal and prior
V3 source ledger; a failed or usage-unknown attempt blocks the other route.

The [route approval](../experiments/a22-p3/runs/successor-route-check-approval-v6.json)
is still default-deny: no authorized phase, no owner acceptance, and no
provider dispatch. The earlier technical-source approval permits only its
completed source cell. The user's request to start the next phase preceded
the exact route seal and therefore does not accept its hash. A fresh owner
acceptance naming this exact seal and `route_checks` phase is required by the
accepted phase protocol before either scorer call. The same current-session
owner remains the human stop operator. Fresh quota telemetry is a separate
immediate pre-call gate for Codex; the Qwen route retains its one-call
correlated-usage and default-thinking checks. No route result or P3 score
exists yet.

The earlier unapproved candidate seals `successor-route-check-seal-v1.json`
through `-v5.json` were superseded during offline corrections and authorized
no call. They are retained as preparation history and must not be used for
dispatch.
