# 0003 — Role triad (analysis/synthesis/implementation) + keystone develop/use separation

**Status:** Accepted (owner-agreed in a design session; records the locked decision).

## Context

Two coupled problems surfaced while reviewing keystone's own dev layer.

1. **The `architect` role conflated two different cognitive operations.** It owned both
   *assessing what exists* (finding problems, bottlenecks, mismatches against goal/vision/
   requirements) **and** *constructing what should be* (options, trade-offs, contracts).
   These are different activities with different outputs and different quality bars. With no
   role for the first, a pure review/analysis task had no home and was routed to `architect`
   by default — observed concretely when a keystone dev-layer review was mislabelled
   `architect` because the model offered nothing else.

2. **keystone's mounted tree mixes its USE surface with its own DEVELOP artifacts.** The
   submodule ships, into every consuming project, both the *standard a consumer follows*
   (roles/pipelines/guardrails) and *keystone's own development* (the vision in `README.md`,
   ADRs, `ROADMAP.md`, `design/`, `TASKS.md`, `tests/`). Worse, operative docs **cite** those
   dev artifacts ("Locked in ADR 0001", "see ROADMAP O4"), coupling the standard to
   keystone's development history and dragging keystone's vision into the consumer's context.

## Decision

### 1. A role triad on the DEVELOP branch

`review` (analysis) → `architect` (synthesis) → `engineer` (implementation), with `learn` and
`release` cross-cutting. The discriminating axis is the **cognitive operation**, not the
temporal target:

| | **review** | **architect** | **engineer** |
|---|---|---|---|
| Operation | **analysis** — decompose an existing whole to understand and measure it | **synthesis** — compose a new whole that did not exist | **realization** — turn a decided structure into code |
| Object | what already exists | what should exist | the decided design |
| Measured against | goal, vision, requirements, environment, user expectations | the same, applied to a *proposed* structure | the agreed design + tests |
| Output | a **report** (findings + the criteria a fix must satisfy) | a **design concept + ADR** | **code + tests** |
| Answers | *what is* | *how it should be* | *make it* |

### 2. The seam (where analysis hands off to synthesis)

Three rules keep the boundary workable rather than naive:

- **Operations nest; the role is fixed by *primary* stance and output.** Synthesis analyses
  its own candidates; analysis imagines a little to frame criteria. `review` exists to
  *understand what is*; `architect` to *produce a constructed proposal*. The rule is not
  "review never thinks about a solution" — it is "review does not *construct* the solution."
- **Criteria are the hand-off artifact.** `review` may state the problem and the **criteria**
  a fix must satisfy (the yardstick), but constructing the structure — a new module seam, a
  contract — is synthesis (`architect`). "What good looks like" crosses into `architect` only
  when expressed as built structure rather than as a criterion.
- **If the yardstick itself is wrong** (a mis-stated requirement/goal), `review` surfaces it
  as a finding; *re-deciding* the requirement is synthesis (`architect`), escalating to
  product/vision if needed.

Directions of work (top-down / bottom-up / horizontal across interfaces) are directions of
*analysis* and belong to `review` regardless of direction; synthesis is also bidirectional,
so direction is not the discriminator — **decompose-to-understand vs compose-to-create** is.

### 3. Why separate modes — the quality rationale

Roles are split because **each mode has its own definition of good, and one undifferentiated
bar cannot optimise all three.** This rationale is recorded so the split is understood as a
quality mechanism, not bureaucracy.

| Failure when fused | Quality gained by separating |
|---|---|
| **Premature synthesis** — the mind jumps to a fix before understanding the problem, anchoring on the first plausible solution | A review pass that *may not propose a solution* protects problem-understanding (institutionalises the existing *analysis-before-mutation* guardrail) |
| **Analysis bent by advocacy** — a pet solution warps the findings (motivated reasoning) | `review`'s success is *fidelity to what-is* (did it find the real problems?), not "did my solution win" — cleaner incentives |
| **Synthesis re-deriving the problem** — design budget wasted rediscovering as-is | Entering with a solid report, `architect` spends its budget on construction and trade-offs |
| **One contradictory stance** — analysis is divergent/critical, synthesis is convergent/constructive | Naming the modes lets the agent deliberately switch stance; a declared role primes the right behaviour (review → critical scan; design → constructive trade-off) |

### 4. Routing discriminator

> A task that **decomposes** an existing thing to understand/measure it → `review` · that
> **constructs** a new structure/decision → `architect` · that **realises** a decided
> structure in code → `engineer`.

This is the operative one-liner; it is also the text fed into the SessionStart role hint.

### 5. keystone meta/use separation

keystone applied to itself: relative to a consumer keystone is USAGE; keystone's own DEVELOP
must not bleed into the consumer's surface. Cordon keystone's development artifacts under
`_forge/keystone/meta/` ("keystone about itself"). The directory is named **`meta/`**, not
`develop/`, so it never collides with the **DEVELOP** *role/mode* of the operative model — the
mode is a relation a consumer reasons about; the directory is keystone's private workspace.

- **USE surface** (loaded/followed by a consumer): a thin operative `MODEL.md` (layers,
  role/agent, the triad + discriminator, archetypes, inheritance, secrets, sync/verify use),
  `roles/`, `pipelines/`, `guardrails/`, `profiles/`, `skills/`, `tools/`, `hooks/`,
  `bin/{sync,verify}`, `ARCHETYPES.md`, `BOOTSTRAP.md`.
- **`meta/`** (inert for a consumer): `CONCEPT.md` (the vision/constitution — mission, goal,
  why, learn-loop philosophy, distribution, evolving), `decisions/` (ADRs), `design/`,
  `ROADMAP.md`, `TASKS.md`, `TASKS_ARCHIVE.md`, `reviews/`, `tests/`, `self_ci.py`, and the
  dev-layer validator `bin/validate.py`.
- `CHANGELOG.md` stays top-level (a release artifact a consumer wants on a pin bump). A thin
  root `README.md` remains for repo ergonomics; it is the **only** top-level doc that may bridge
  to `meta/` (vision via `meta/CONCEPT.md`), alongside `CHANGELOG.md`.

### 6. The USE surface must not even *name* the development layer

The operative docs (`roles/`, `pipelines/`, `guardrails/`, `profiles/`, `skills/`, `tools/`,
`MODEL.md`, `ARCHETYPES.md`, `BOOTSTRAP.md`) are **self-contained**: they state the rule, not the
rationale, and a deployed external agent should not even learn the development layer exists —
naming it costs tokens and invites the agent to chase inert files. The rule is therefore **"no
mention", not merely "no link"** (the original framing missed inline-code and prose citations).
`bin/verify.py::check_use_surface_isolation` scans the whole USE surface and fails on:

- a **numbered decision-record citation** (`ADR ####`) — the bare word "ADR" as a concept stays
  legal, only a number-pinned citation into a specific record is a leak;
- a **roadmap citation** (`ROADMAP O#` / `ROADMAP.md`) — the generic word "roadmap" stays legal;
- any **path** (markdown link target or inline code) into the dev tree or its artifacts —
  `meta/`, `decisions/`, `reviews/`, `ROADMAP`, `CONCEPT`, `self_ci`.

`README.md` and `CHANGELOG.md` are the deliberate bridges and are not in the scanned surface. The
"why" lives in `meta/`; this is also the token-trim win from the dev-layer review (rule without
inlined rationale is leaner).

### 6a. USE verification is separate from dev verification

The split in §6 is mirrored in the tooling so the USE verifier never reads the dev layer:

- **`bin/verify.py`** validates only the **USE contract** a consuming project must satisfy
  (AGENTS.md, vendor pointers, hooks, skills, memory, layout, the isolation rule). It ships into
  every consumer and is wired into consumer CI. It must **not** require or reference any `meta/`
  artifact.
- **`meta/bin/validate.py`** validates **keystone itself** — that the `meta/` dev layer is whole,
  that the synthetic-fixture self-CI (`meta/self_ci.py`: sync + USE verify) passes, and that the
  unit tests pass. A consumer never runs it.

Rationale: a tool that ships into the consumer and is *named the verifier of the contract* must
not itself carry knowledge of the inert dev tree — otherwise §6's "no mention" leaks back in
through the very tool that enforces it.

### 7. Task-id letter for review

Add **`N`** (aNalysis) for `review` tasks (`R` is reserved for architecture-requirements).
Amends [ADR 0002](0002-task-id-convention.md): `A` architecture/design · `C` code · `L`
learning · `V` release · **`N` analysis/review**; role derived from the letter.

## Consequences

- **Role mislabelling is fixed:** review has a home and a discriminator; the SessionStart hint
  routes by operation.
- **Leaner USE context:** decoupling = the dev-layer review's token-trim; vision no longer
  loads in a consumer.
- **Consumers stop inheriting keystone's ADRs/vision.** They follow `MODEL.md` +
  roles/pipelines/guardrails. This revises [`decisions/README.md`](README.md) (which stated
  ADRs "travel with the submodule into every consuming project") and `README.md §3` ("two
  roles").
- **Physical shipping unchanged:** a git submodule checks out `meta/` regardless; it is
  cordoned and inert, not removed. Sparse-checkout to physically exclude it is a future option
  (revisit-if).
- **Migration is tracked** as `A5–A10` / `C3–C8` in `meta/TASKS.md` (the `develop/`→`meta/`
  rename + the verify split are `C7`).

## Relates to

- Amends [ADR 0002](0002-task-id-convention.md) (adds letter `N`).
- Revises [ADR 0001](0001-release-and-roles-model.md) role roster (review added as a fifth
  role; the analysis/synthesis split refines `architect`).
- Full rationale + the dev-layer review that prompted this lives in
  `meta/reviews/keystone-dev-layer.md`.
