# AGENTS.md

Guidance for agents developing the akmon standard itself.

## Active Role

Declare the active DEVELOP role before project work and on every switch:
`🧭 agent: <review|architect|engineer> — <focus>`.

- `review`: assess the existing standard and report evidence-backed findings.
- `architect`: design changes to contracts, roles, pipelines, and ADRs.
- `engineer`: implement a recorded task with tests.
- `learn` and `release` are cross-cutting roles defined under `roles/`.

## Delegation

**Delegation is the default.** For every non-trivial task, before the first repository sweep,
edit, or test run, decompose the work and delegate every independent mechanical sub-step to
available subagents without waiting for an owner prompt. The orchestrator retains decomposition,
routing, synthesis, and owner dialogue. Skip only when the task is atomic or the harness exposes
no subagents; state the reason.

## Project Contract

- Start with `README.md`, `MODEL.md`, and `meta/TASKS.md`; architecture decisions live in
  `meta/decisions/` and living designs in `meta/design/`.
- Follow `pipelines/review-flow.md`, `pipelines/design-flow.md`, or
  `pipelines/code-flow.md` for the declared role.
- Record non-trivial implementation work in `meta/TASKS.md` before code.
- Architecture changes require an entry in `meta/D2_LEDGER.md` and explicit owner verification.
- The owner owns commits, tags, pushes, publishing, and consumer pin bumps.
- Never put secrets in code, docs, tests, or commits. Project files are English.
- Do not edit consuming-project materializations as the source of truth; change this repository,
  release it, then realign consumers.

## Verification

Run:

```bash
uv run pytest
uv run ruff check .
python3 meta/self_ci.py
uv build
```

Do not claim Codex/Claude/Gemini capability parity without a live harness probe and a regression
test for the exact payload and enforcement behavior.
