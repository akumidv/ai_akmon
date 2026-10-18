# A22 P3 V3 qualification successor readiness — Codex GPT-6 review

**Verdict:** offline successor package is ready for a qualification-only owner
decision. The default-deny approval remains unset; no successor provider call
has been dispatched and its private runtime does not exist. The terminal
seven-call qualification remains historical evidence only.

The [proposal](../experiments/a22-p3/V3_QUALIFICATION_SUCCESSOR_PROPOSAL.md)
and [fresh schedule](../experiments/a22-p3/runs/v3-qualification-successor-schedule-v1.json)
bind 32 new A cells and 128 sequential provider calls. No run, packet, subject
or scorer call ID overlaps the terminal schedule. Both scorers receive the
same blinded packet/request generated with the format-only prompt that passed
their separate mechanics checks (M148–M149). Qwen retains default thinking
and uses a 5,000-token local output setting; its setting is not a proven hard
provider cap. The strict TSV parser and E1–E4 criteria remain unchanged.

The [operational seal](../experiments/a22-p3/runs/v3-qualification-successor-seal-v1.json)
has SHA-256 `0966558a7fcc575ed2d24400f802f02481003d821f2970d8ebac8531fe6d3206`.
It binds the terminal ledger, both passed format-route seals/outcomes, the
new prompt, packet, schedule, code, tests, model/settings and 285,782-token
Codex opening. The
[preflight](../experiments/a22-p3/runs/v3-qualification-successor-preflight-v1.json)
has SHA-256 `932ad03e8ce97d4bc46649d8c195e5fe6984dfc8caabbe201931a96afb640113`
and reports `PASSED_OFFLINE_QUALIFICATION_SUCCESSOR_PREFLIGHT`,
`provider_calls: 0`, `dispatch_allowed: false`. The
[approval record](../experiments/a22-p3/runs/v3-qualification-successor-approval-v1.json)
is the exact default-deny template. A direct `advance` attempt stopped with
`QualificationError` before creating the runtime.

Focused offline verification: seven successor tests passed; Ruff check and
format check passed. The tests cover the 128-call plan, fresh IDs, blind
format request, opening/limits and denial on missing approval, unresolved
reservation or prior failed call. One P3-01 route packet passed per scorer;
that does not establish that every new case will fit Qwen's 5,000 setting.
The runner stops on the first such failure and never repairs or retries it
under this seal. Fresh Codex quota evidence and usage accounting are still
required before each Codex call.

**Owner action:** accept the exact successor package for `qualification` if
the changed Qwen allowance, new prompt and 128-call plan are intended. That
acceptance authorizes no B/C comparison, repair or retry. After acceptance,
write the affirmative approval record and start at call 1; preserve terminal
evidence and report progress against the full grid.
