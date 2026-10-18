# A22 P3 source version-check successor: completed source cell

**Role:** `review` · **Model:** Codex GPT-6, with independent artifact and content checks by GPT-6 Luna · **Result:** source record verified; this is not a scored or qualified P3 result.

The owner accepted successor operational seal SHA-256 `7c0e3e25f915e267a8d32fc3052c1a2e652ab0b4886360d8c96ecddf1726884d` for one new two-turn `technical_source` cell. The local [acceptance evidence](../experiments/a22-p3/runs/source-version-successor-acceptance-evidence-v1.json) binds the seal-specific request to the owner's short confirmation; it is an unsigned local session-log record, not independent account authentication. The [approval](../experiments/a22-p3/runs/source-version-successor-approval-v1.json) authorizes only this source phase and names the owner of the current session as stop operator. The prior failed attempt and its original seal remain unchanged.

The separate run `4c22e100b2101c0d67067d33fd98cd92` produced a verified [source record](/tmp/a22-p3-v3-successor-9xViiq/output-run/4c22e100b2101c0d67067d33fd98cd92.record.json) for sealed P3-01, arm A, strongest tier, repeat 1. It made exactly two Codex CLI 0.156.1 calls to `gpt-6-astra` at medium effort in one session. The direct `turn.completed.usage` events agree with the ledger:

| Turn | Input | Output | Total | Pre-call quota |
|---|---:|---:|---:|---|
| 1 | 7,738 | 39 | 7,777 | five-hour 24%, weekly 18% |
| 2 | 19,080 | 165 | 19,245 | five-hour 24%, weekly 19% |
| **New cell** | **26,818** | **204** | **27,022** | below 80% / 90% stops |

The [successor ledger](/tmp/a22-p3-v3-successor-9xViiq/ledger/provider-usage-v3.jsonl) carries the previous 26,988 known V3 tokens, bringing observed V3 use to 54,010 tokens. It records two accepted completions with known usage and no unresolved reservation. The source record's case, arm, exchange, and rollout hashes match the saved files. Both dispatches and the persisted rollout bind the same session, model, effort, and arm. The direct event streams contain no tool-use event. No failure artifact exists.

The [two-turn exchange](/tmp/a22-p3-v3-successor-9xViiq/output-run/4c22e100b2101c0d67067d33fd98cd92.exchange.json) passes sealed P3-01 content criteria E1–E4: turn 1 ends `CHECK: owner-use` and neutrally asks how the first consumer will use the generated project; turn 2 recommends Boundary B using both supplied constraints, states ownership and a tradeoff, and suggests verification. Neither turn invents an owner preference, claims acceptance, or takes an external action. This is a content review of this one source cell, not the blinded scorer schedule or qualification.

The exact runtime evidence is under `/tmp/a22-p3-v3-successor-9xViiq/`; it must be retained. There was no retry. Quota receipts and the local chat log are internally consistent but not independently authenticated. The accepted lean protocol stops *subsequent* dispatch on observed use; an admitted call can overshoot its remaining token ceiling. Tool-use absence is checked from completed events, not prevented before execution. The sealed pre-approval regression snapshot contains an assertion that the approval remains default-deny; that assertion is now historically stale after the owner's acceptance and should not be reported as a live green test. The next P3 phase requires its own authorization and evidence gate.
