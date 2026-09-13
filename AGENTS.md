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
- Measured harness and vendor facts live in `meta/MEASUREMENTS.md`, each with the version it was
  verified on. Grep it before a probe or a documentation lookup and cite a row that covers the
  version in use; add a row after a new measurement.
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

`meta/self_ci.py`'s installed-wheel leg runs `akmon init --mode package`, which resolves the pin
from the akmon repository's **release tags over the network**. It therefore needs network reach
and a git credential helper that works *outside* this checkout — verify with
`git ls-remote --tags <repo>` from a directory that is not a git repository, and wire it with
`gh auth login` then `gh auth setup-git`. Without that the leg fails on the prerequisite, not on
anything akmon ships; the finding says so rather than reporting a bare exit status.

Do not claim Codex/Claude/Gemini capability parity without a live harness probe and a regression
test for the exact payload and enforcement behavior.
