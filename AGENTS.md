# AGENTS.md

Guidance for agents developing the akmon standard itself. **Archetype:** `agent-tooling`
([ARCHETYPES.md](ARCHETYPES.md)): akmon builds what AI coding agents run with, for several harnesses.

akmon develops on its own layer. The shipped guardrail and profiles are **imported, not
restated** — they are the single owner of every rule they carry, the same requirement akmon
places on the projects it attaches to. A rule that belongs to them is added there, not here;
this file carries only what is true of akmon and of nothing else.

<!-- akmon:imports -->
@guardrails/_common.md
@rules/code.md
<!-- /akmon:imports -->
@profiles/python.md
@profiles/js.md
@profiles/python-stdlib.md
@profiles/agent-harness.md

## Who reads what

If an owner reads your replies and the owner-dialogue rules are not in your context, read
[rules/collaboration.md](rules/collaboration.md) and [rules/templates.md](rules/templates.md);
otherwise read [rules/unattended.md](rules/unattended.md). A hook delivers the right one at start.

## Roles

[`roles/README.md`](roles/README.md) — `review`, `architect` and `engineer`, the modes of the
development agent; [`agents/README.md`](agents/README.md) — the development, learning and release
agents, the last two working in `learn` and `release`. Declaring the active role and restating it on every switch
is the head session's rule ([rules/collaboration.md](rules/collaboration.md)); this file only says where
the roles live.

## Delegation

**Delegation is the default:** for every non-trivial task, before the first repository sweep,
edit, or test run, decompose the work and delegate every independent mechanical sub-step to
available subagents without waiting for an owner prompt, keeping only decomposition, routing,
synthesis and owner dialogue; skip only when the task is atomic or the harness exposes no subagents,
and state the reason. **The work style** sets the rest
([ADR 0031/D06](docs/adr/0031-work-styles-delegating-and-controlling.md#d06--the-delegation-rule-reads-the-style)):
*delegating* also hands whole athla and higher-tier calls to delegates; *controlling* leaves stages to
sessions the developer starts and recommends which higher-tier call, for what and why, with a
delegate's brief in the developer's language. This clause is direct, not imported: Codex does not
expand nested `@` imports.

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
  row that covers the version in use, and add a row after a new probe, replay or source reading. How a harness
  fact is used — one interface, an adapter per harness, no claimed parity without a probe — is the
  [agent-harness](profiles/agent-harness.md) profile.
- **Commits** follow the guardrail § Commits & ownership, narrowed in one place: the owner owns
  merges into the default branch, tags, pushes, publishing and consumer pin bumps, and **the main
  checkout is the owner's** — an agent changes no history there, on any branch, even when asked to
  commit; it commits only inside a worktree, its own or the one the harness made for its athlos
  ([ADR 0029/D09](docs/adr/0029-ergon-athlos-step-one-method-of-work.md#d09--an-agent-commits-only-inside-a-worktree)).
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

The gates are the record's own: `[test].runner` and `[check]` in `meta/.akmon.toml` — run the checks
with `akmon check` and the tests with the runner, as the [pre-commit](pipelines/pre-commit.md)
pipeline says. `meta/self_ci.py` is one of those checks: it builds and installs the wheel and runs
the JavaScript legs (`tsc`, `node --test`, `oxlint`, `oxfmt`), and its finding names a missing
prerequisite (`node` and `npm`, registry reach, a git credential helper outside the checkout)
instead of a bare exit status. It takes its change set from git itself — staged, unstaged and
untracked paths, `meta/` included — and runs only the legs those paths can affect
(`meta/self_ci_legs.json`; an unknown path runs them all), so the pre-commit run is partial. A clean
tree, `--full` and CI (`--full`, explicit) run every leg; `fuzz` and the node corpus (`full_only` in
the table) run only in a full run and are named as deferred otherwise.
