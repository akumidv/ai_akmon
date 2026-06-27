# keystone — the operative model

What a consuming project applies to follow the standard. The full vision and rationale live in
keystone's own development layer, which a consumer never loads; this file is the **USE surface** —
the rules, not the why. Self-contained by design.

## 1. Three orthogonal axes (do not conflate)

| Axis | Answers | Values |
|---|---|---|
| **Layer** | *where* an artifact lives + *whom it serves* | SHARED / LOCAL / USAGE |
| **Role** | *who performs* the work + by which pipeline | review / architect / engineer / learn / release |
| **Archetype** | *what* the project exposes outward | package / service / mcp / frontend / job / platform / custom |

Each is a type dimension (a kind, not a thing). An **agent is not an axis value** — it is a
concrete point where a role is applied in a project on a layer; a role is the reusable
definition (here), an agent its incarnation in a project (`_forge/agents/`).

## 2. Layer — a decision tree

```
Does this artifact help DEVELOP this project — or USE it from outside?
├─ DEVELOP ─► common to all my projects, or specific to this one?
│            ├─ common       → SHARED → _forge/keystone/   (this submodule)
│            └─ this project  → LOCAL  → _forge/{skills,tools,memory,agents}/
└─ USE from outside ► USAGE → root skills/ (+ tools/ where applicable)
```

| Layer | Job | Consumer | Lives in |
|---|---|---|---|
| **SHARED** | assist development in general | any of my projects | `_forge/keystone/` |
| **LOCAL** | assist development of *this* project | this repo's developer | `_forge/{skills,tools,memory,agents}/` |
| **USAGE** | assist *using* what the project exposes | a downstream project | root `skills/` (+ `tools/`) |

SHARED+LOCAL point inward (building this repo); USAGE points outward.

`_forge/` is the **default** dev-layer root, not a hard-coded literal: a project may relocate it
by declaring `FORGE_ROOT` (a project-root-relative path, e.g. `tools/ai`); keystone then mounts at
`<FORGE_ROOT>/keystone` and the tooling derives every path from it. Unset → `_forge`.

## 3. Role vs agent — the DEVELOP triad

A **role** is a definition (pipeline + requirements + guardrails); an **agent** is a role
applied in a project. The three DEVELOP roles split by **cognitive operation** — each mode has
its own definition of good, so one bar cannot optimise all three:

| Role | Operation | Output | Pipeline |
|---|---|---|---|
| [review](roles/review.md) | **analysis** — assess what *is* (state/quality/conformance, problems, bottlenecks) | a findings report | [review-flow](pipelines/review-flow.md) |
| [architect](roles/architect.md) | **synthesis** — design what *should be* (options, trade-offs, contracts, ADRs) | a design + ADR | [design-flow](pipelines/design-flow.md) |
| [engineer](roles/engineer.md) | **realization** — code, tests, refactoring | committed, tested code | [code-flow](pipelines/code-flow.md) |

`learn` ([memory-distill](pipelines/memory-distill.md) + [learning](pipelines/learning.md)) and
`release` ([release](pipelines/release.md)) are cross-cutting. See [roles/README.md](roles/README.md).

**The discriminator (routes any task):** does it **decompose** an existing thing to
understand/measure it → `review` · **construct** a new structure/decision → `architect` ·
**realize** a decided structure in code → `engineer`? Declare the active agent
(`🧭 agent: <name> — <focus>`) and restate it on every switch.

## 4. Archetype

Decides whether USAGE exists and its shape — chosen by the **contract** the project exposes,
not its language. Full taxonomy + per-archetype checklists: [ARCHETYPES.md](ARCHETYPES.md).

## 5. Profiles & guardrails

- **[guardrails/](guardrails/)** — per language/environment, **applied automatically** by the
  project's language (`_common.md` + `python.md`, …).
- **[profiles/](profiles/)** — per domain, **opt-in by need** (`quant.md`, …).

## 6. The learn loop (how the standard evolves)

`CAPTURE` (one fact → `_forge/memory/`) → `DISTILL` (recurring facts → a LOCAL skill/tool/agent
or a refined requirement/ADR) → `PROMOTE` (general + proven → keystone via PR) → `PROPAGATE`
(every project on `git submodule update`). Flow is one-way **up**. Two memories kept distinct:
shared project memory (`_forge/memory/`, in git) vs each assistant's provider-private memory
(distilled *into* the shared one, never the reverse).

## 7. Inheritance contract (agent → role)

A project agent charter (`_forge/agents/<role>/README.md`) **links** its keystone role as the
source of requirements + pipeline and **adds only project specifics** — it does not restate the
role, so a change here propagates to every project after `git submodule update`.

## 8. Secrets

From the project `.env` only (`*.env` gitignored; `*.env.example` carries empty placeholders).
Never in code, markdown, or commits.

## 9. Tooling

`bin/sync.py` writes the thin generated vendor pointers (CLAUDE.md, GEMINI.md, …) and hook
wiring from one source; `bin/verify.py` validates the project contract (it reports, never
modifies). Both are stdlib-only and run in-tree.
