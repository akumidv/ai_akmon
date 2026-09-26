# AGENTS.md

Guidance for agents developing the akmon standard itself.

akmon develops on its own layer. The shipped guardrail and profiles are **imported, not
restated** — they are the single owner of every rule they carry, the same requirement akmon
places on the projects it attaches to. A rule that belongs to them is added there, not here;
this file carries only what is true of akmon and of nothing else.

@guardrails/_common.md
@profiles/python.md
@profiles/python-stdlib.md

## Roles

[`roles/README.md`](roles/README.md) — `review`, `architect` and `engineer` for project work,
`learn` and `release` cross-cutting. Declaring the active role and restating it on every switch
is the guardrail's rule; this file only says where the roles live.

## Delegation

**Delegation is the default.** For every non-trivial task, before the first repository sweep,
edit, or test run, decompose the work and delegate every independent mechanical sub-step to
available subagents without waiting for an owner prompt. The orchestrator retains decomposition,
routing, synthesis, and owner dialogue. Skip only when the task is atomic or the harness exposes
no subagents; state the reason. This clause is direct rather than imported for the same reason
the shipped block states it directly: Codex does not expand nested `@` imports in `AGENTS.md`.

## akmon runs on itself

- **Hooks:** [`.claude/settings.json`](.claude/settings.json) wires this repository's own
  `hooks/` — the same scripts on the same events that `akmon sync` writes for a consumer, with
  in-tree paths instead of a materialized mount. A change to the shipped wiring lands here too;
  `meta/tests/test_self_wiring.py` pins the two together so they cannot drift.
- **Skills:** [`skills/`](skills/) are used here, not only shipped.
- **Pipelines:** follow the one the declared role names —
  [review-flow](pipelines/review-flow.md), [design-flow](pipelines/design-flow.md),
  [code-flow](pipelines/code-flow.md) — over [pre-commit](pipelines/pre-commit.md), with
  [tasks](pipelines/tasks.md) for the backlog format.

## Project contract

- Start with `README.md`, `MODEL.md`, and `meta/TASKS.md`; architecture decisions live in
  `meta/decisions/` and living designs in `meta/design/`.
- Record non-trivial implementation work in `meta/TASKS.md` before code.
- Significant architecture choices require explicit owner acceptance and a stable decision
  block in a thematic ADR under `meta/decisions/`. Open choices stay in design/tasks;
  implementation evidence and remaining verification stay with the implementing task.
- Harness and vendor facts that took an experiment — not what vendor docs state plainly — live in
  `meta/MEASUREMENTS.md` with the version they were verified on. Grep it before a probe, cite a
  row that covers the version in use, and add a row after a new probe, replay or source reading.
- **Commits — the one place akmon is narrower than the guardrail it ships.** The owner owns
  merges into the default branch, tags, pushes, publishing, and consumer pin bumps. An agent
  **may** commit on a local non-default branch to keep its work safe; it never pushes, merges
  or tags. Everything else in § Commits & ownership stands as written.
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
