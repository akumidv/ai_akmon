# AGENTS.md

Guidance for agents developing the akmon standard itself.

akmon develops on its own layer. The shipped guardrail and profiles are **imported, not
restated** — they are the single owner of every rule they carry, the same requirement akmon
places on the projects it attaches to. A rule that belongs to them is added there, not here;
this file carries only what is true of akmon and of nothing else.

@guardrails/_common.md
@profiles/python.md
@profiles/js.md
@profiles/python-stdlib.md

## Roles

[`roles/README.md`](roles/README.md) — `review`, `architect` and `engineer`, the modes of the
development agent; [`agents/README.md`](agents/README.md) — the development, learning and release
agents, the last two working in `learn` and `release`. Declaring the active role and restating it on every switch
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

## The method's words

Work is tracked in `meta/.ergon/` (`<DEV>/.ergon/`): an *ergon* is a piece of work (what a user may
call an epic, a kit or a work package); an *athlos* is a bounded unit of it (a job); a *step* is one
line of an athlos, checked off when done; to *park* an athlos is to stop it for another session (a
handoff, a checkpoint). A *task* is a backlog row an ergon serves; a user who says "task" may mean an
ergon or an athlos, so read which from the id. The gloss and its readings are
[ADR 0029/D10](docs/adr/0029-ergon-athlos-step-one-method-of-work.md#d10--the-words-are-glossed-in-the-entry-file-with-the-words-a-user-may-say);
the format of a note or a plan line and its place stay with the code.

## Project contract

- Start with `README.md`, `MODEL.md`, and `meta/TASKS.md`; architecture decisions live in
  `docs/adr/` and living designs in `docs/design/`
  ([ADR 0023](docs/adr/0023-project-documents-layout.md)); reviews, measurements, experiments and the
  backlog stay in `meta/`.
- Record non-trivial implementation work in `meta/TASKS.md` before code.
- **`<DEV>` is `meta/`.** akmon has no `_aitna/`; its `.aitna-root` file declares `meta`, so its local
  layer is `meta/.local/` and its development skills would live in `meta/skills/`
  ([ADR 0022](docs/adr/0022-local-layer-index-and-plans.md)).
- To look for alternatives to a design choice, or to check a decision against how other projects
  solved it, open [`meta/reviews/alternatives/`](meta/reviews/alternatives/README.md). It is
  material for akmon's own development, not part of what a consumer receives.
- Significant architecture choices require explicit owner acceptance and a stable decision
  block in a thematic ADR under `docs/adr/`. Open choices stay in design/tasks;
  implementation evidence and remaining verification stay with the implementing task.
- **Experiments:** before designing one, read [`meta/experiments/README.md`](meta/experiments/README.md),
  the index of what was tested and with what verdict, negative ones included, and grep
  `meta/MEASUREMENTS.md`. An experiment leaves a results document and its index line there; its
  fixtures, runners and raw runs stay in its ergon's `materials/`
  ([ADR 0023/D07](docs/adr/0023-project-documents-layout.md#d07--an-experiment-leaves-its-results-in-the-tree-and-its-materials-in-its-ergon)).
- Harness and vendor facts that took an experiment — not what vendor docs state plainly — live in
  `meta/MEASUREMENTS.md` with the version they were verified on. Grep it before a probe, cite a
  row that covers the version in use, and add a row after a new probe, replay or source reading.
- **Commits — the one place akmon is narrower than the guardrail it ships.** The owner owns
  merges into the default branch, tags, pushes, publishing, and consumer pin bumps. **The main
  checkout is the owner's:** an agent changes no history there, on any branch. An agent commits
  only inside a worktree — its own or the one the harness made for its athlos — on that worktree's
  branch, and may bring other branches into it, never carry it out; carrying a worktree's branch
  into the branch the owner is on is started by the owner only. **When the work in a worktree is ready
  the agent prints the carry as commands, always a squash:** `git merge --squash <branch>` in the
  owner's checkout, then `git commit -m "<message>"` with the message the agent proposes, so every
  commit of the worktree becomes one commit on the owner's branch; the cleanup (`git worktree remove`,
  `git branch -D`) follows. The owner runs them, or asks the agent to run them ([ADR 0029/D09](docs/adr/0029-ergon-athlos-step-one-method-of-work.md#d09--an-agent-commits-only-inside-a-worktree);
  the guard and the shipped carve-out follow in C190). Everything else in § Commits & ownership
  stands as written.
- **No dates, and never a date as an index.** Git history is the timeline. This applies to the
  text and file names of every tracked document: `meta/` (tasks, ADRs, designs, reviews,
  evidence) and the shipped prose. Name a file by its task id and a short subject
  (`c110-evidence.md`); name a repeated output by its task id and an ordinal
  (`c110-second-opinion-2.md`). Cite a measured fact by its `M<n>` id. Exceptions apply only
  when time order is really needed. Prefer a month and year (`2026-07`). Use a full date only
  as a last resort, where the day itself serves a purpose: an external deadline, or the date
  field of a `MEASUREMENTS.md` row. Sealed experiment inputs (files hashed in a `seal*.json`)
  keep their bytes and names. Consumer projects are not bound by this; `pipelines/tasks.md`
  keeps its own rule for their backlog.
- Do not edit consuming-project materializations as the source of truth; change this repository,
  release it, then realign consumers.

## Verification

Run:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
python3 meta/self_ci.py
uv build
npm ci --ignore-scripts
npx --no-install tsc --checkJs --noEmit -p .
node --test "js/**/*.test.mjs"
npx --no-install oxlint .
npx --no-install oxfmt --check .
```

The node toolchain's legs (from C103) need `node` (>= 22) and `npm` on PATH, and `npm ci`
needs registry reach; the JS self-CI legs follow the wheel-smoke stance — a leg that fails on
a prerequisite says so in its finding rather than reporting a bare exit status.

`meta/self_ci.py`'s installed-wheel leg runs `akmon init --mode package`, which resolves the pin
from the akmon repository's **release tags over the network**. It therefore needs network reach
and a git credential helper that works *outside* this checkout — verify with
`git ls-remote --tags <repo>` from a directory that is not a git repository, and wire it with
`gh auth login` then `gh auth setup-git`. Without that the leg fails on the prerequisite, not on
anything akmon ships; the finding says so rather than reporting a bare exit status.

Do not claim Codex/Claude/Gemini capability parity without a live harness probe and a regression
test for the exact payload and enforcement behavior.
