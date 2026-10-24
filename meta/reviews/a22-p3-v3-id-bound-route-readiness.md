# A22 P3 V3 identity-bound scorer routes — Codex GPT-6 review

**Verdict:** the prospective three-column scorer contract is implemented
offline and the two-call, unscored Qwen-then-Codex route package is sealed,
preflighted and default-deny. No provider call was made. The fresh A
qualification candidate cannot be sealed or dispatched until both new route
checks pass and their evidence is bound to its own seal and approval.

The terminal qualification successor remains closed at call 31 (M152). Its
hash-verified reply omitted the final `f` from the packet ID on every E row;
the prior report and M152 have been corrected. The saved packet is reused only
as an unscored mechanics fixture. No failed reading is repaired, reclassified
or carried into the new 32-cell dataset.

[ADR 0019 D03](../decisions/0019-collaboration-guidance-from-a22.md#d03--prospective-p3-scorer-packet-identity-binding)
records the accepted prospective format. The [identity proposal](../experiments/a22-p3/V3_SCORER_ID_BINDING_PROPOSAL.md)
explains the alternatives. The [new parser](../experiments/a22-p3/v3_scorer_id_binding.py)
requires exactly E1–E4 with PASS/FAIL and nonblank reasons, rejects extra
columns/text, and creates a four-column canonical TSV using only the scheduled
packet ID. The [qualification candidate](../experiments/a22-p3/v3_qualification_id_bound.py)
stores raw and canonical replies separately and checks their packet/request,
call and evidence binding on ledger replay. Its [fresh schedule](../experiments/a22-p3/runs/v3-qualification-id-bound-schedule-v1.json)
excludes IDs from both terminal qualification schedules; SHA-256
`d8084e398dfa07ae3ce8e0047ce2aed24ae526ebbe201fa1c13986dbc08f8625`.
No qualification seal, preflight or approval exists yet.

The [route proposal](../experiments/a22-p3/V3_ID_BOUND_ROUTE_PROPOSAL.md),
[runner](../experiments/a22-p3/v3_id_bound_route_check.py),
[plan](../experiments/a22-p3/runs/v3-id-bound-route-plan-v1.json),
[seal](../experiments/a22-p3/runs/v3-id-bound-route-seal-v1.json),
[offline preflight](../experiments/a22-p3/runs/v3-id-bound-route-preflight-v1.json)
and [approval template](../experiments/a22-p3/runs/v3-id-bound-route-approval-v1.json)
bind two fresh call IDs, the same blind packet and prompt, model/CLI pins,
private runtime, resource stops, predecessor failure, exact code and tests.
The plan SHA-256 is `4907fe21f504391cfd52c39832c147f1306b33a55db40890ae6a655a0ac4e0f3`;
seal SHA-256 is `834c7d135a793be7b22c0d02d299a59fff3c38a3496aba343b9110eb6d76c61f`;
preflight SHA-256 is `3fcaf928bca1b46c30e413c2e4ff2563417ab946ecc59b802cc985d9a214011e`.
The approval template has `owner_accepted=false`, `dispatch_allowed=false`
and no authorized phase. The route runtime path does not exist.

The independent static review found missing Qwen credential preflight, a
runtime recheck gap and incomplete replay assertions. These were fixed before
the final seal: preflight checks credential presence, dispatch rejects a
precreated/linked/nonprivate runtime, and replay verifies outcome semantics,
usage, request and raw/canonical evidence hashes. Twenty-two targeted tests
pass; changed Python files pass Ruff check and format. `uv build`,
`meta/self_ci.py`, npm install, JS typecheck, oxlint and oxfmt pass. The full
Python suite reported 2,591 passed and 10 failed in other A22/profile tests;
repository-wide Ruff reported 11 findings in existing test files. The
standalone Node test process emitted no result before interruption; the same
JS unit leg passed inside `meta/self_ci.py`. These broader failures are not
presented as a pass for the repository.

**Next gate:** separate owner authorization for only these two route checks.
The runner advances one terminal call at a time, Qwen first. Codex requires a
fresh interpretable pre-call subscription quota below the accepted 80%/90%
stops; the V3-only opening is 559,835 / 5,000,000. A failed or uncorrelated
call stops this seal without retry or repair. Passing routes establish only
mechanics for one packet; qualification needs its own complete sealed schedule,
offline preflight and separate phase authorization.
