# roles — the cross-project agent role baseline

A **role** is the reusable definition of a development agent: its scope, its
requirements, the pipeline it follows, and the guardrails that bind it. Roles live here
in keystone so every project's agents inherit one standard.

> Role ≠ agent. A role is the *definition*; a project's **agent** (in `_forge/agents/`)
> is the *incarnation* — it inherits a role and adds project specifics. One role may
> have several agents in a project (e.g. two `engineer` agents: backend + data-pipeline).

See the model's three axes in [MODEL.md](../MODEL.md) §1–3.

## Roles

The three DEVELOP roles are the **analysis → synthesis → realization** triad — split by
cognitive operation, because each mode has its own definition of good and one bar cannot
optimise all three (a reviewer bent on a fix stops analysing; an architect re-deriving the
as-is wastes its budget). `learn` and `release` are cross-cutting.

| Role | Focus | Pipeline | Guardrails |
|---|---|---|---|
| [review](review.md) | **analysis** — assess what *is*: state/quality/conformance, problems, bottlenecks; output is a report | [review-flow](../pipelines/review-flow.md) | language `guardrails/` + opted-in `profiles/` |
| [architect](architect.md) | **synthesis** — design what *should be*: options, trade-offs, contracts, ADRs | [design-flow](../pipelines/design-flow.md) | language `guardrails/` + opted-in `profiles/` |
| [engineer](engineer.md) | **realization** — code, tests, refactoring | [code-flow](../pipelines/code-flow.md) | language `guardrails/` + opted-in `profiles/` |
| [learn](learn.md) | the learn loop — memory, distillation, LOCAL→SHARED promotion | [memory-distill](../pipelines/memory-distill.md) + [learning](../pipelines/learning.md) | promotion test (general + proven); one-way-up; PR-only at SHARED boundary |
| [release](release.md) | release cycle for a subject (package / keystone tag / pin bump) | [release](../pipelines/release.md) | D5 (owner executes landing); coordinator-not-super-role; propose/prepare |

`release` is parameterized by a **subject**. DEVELOP / USAGE / OPERATE are relations to the
chosen subject, not global session modes: a keystone pin bump is a release subject inside the
consuming project's DEVELOP work, while runtime consumption remains OPERATE and out of scope.

## A role file states

1. **Mission** — one sentence: what this role is responsible for.
2. **Scope** — what it acts on (which artifacts) and, explicitly, what it does **not**.
3. **Inputs / outputs** — what it consumes, what it produces.
4. **Pipeline** — the ordered cycle it follows (link a file in `../pipelines/`).
5. **Requirements** — the standards it must meet (verification, ownership, etc.).
6. **Guardrails** — hard constraints; what it must never do.
7. **Done** — the definition of done for its output.

## Role declaration (announce the active agent)

The active agent is **chosen per task**, not at session start — so each session opens with
no agent active. Before doing project work, the assistant **declares which agent it is
operating as**, and **restates it on every switch** (e.g. handing a locked design from
`architect` to `engineer`). This keeps the role — and the pipeline/guardrails it pulls in —
explicit rather than implicit.

- **Format:** `🧭 agent: <name> — <focus>` (e.g. `🧭 agent: engineer — code/tests`).
- **If the task is ambiguous** about which role it calls for, ask before proceeding.
- **Executable side:** the [`session-start-agent`](../hooks/README.md) SessionStart hook
  injects this reminder + the project's scanned agent roster each session, so the
  convention survives a long session and does not depend on the doc staying in context (the
  same rule-plus-hook split as the commit guardrail).

### Routing mixed tasks

Some tasks touch both the **model** (what the process should be) and an **executable
mechanism** (a hook, sync script, validator, or local tool). Route them by the decision
being made, and restate the agent on every switch.

**The discriminator (the one question that routes any task):** does it **decompose** an
existing thing to understand/measure it → `review` · **construct** a new structure/decision →
`architect` · **realize** a decided structure in code → `engineer`?

| Work | Agent |
|---|---|
| Review state/quality/conformance (product / component / element); find problems, bottlenecks, mismatches vs goal/vision/requirements | `review` |
| Produce a findings report / an as-is assessment | `review` |
| Keystone model, role boundaries, guardrails, pipeline semantics, roadmap, bootstrap/sync contract | `architect` |
| Project architecture, requirements, ADRs, design docs | `architect` |
| Production code, tests, build config | `engineer` |
| Executable dev tooling (`_forge/keystone/{bin,tools,hooks}/`, `_forge/tools/`, validators, sync scripts) | `engineer` |
| Generated pointer output produced by an existing tool | no new role; report what the tool changed |

For a mixed design + tool task: start as `architect`, lock the behaviour/contract, switch
to `engineer` before editing executable code, then switch back to `architect` only for
model or contract documentation. A documentation edit that merely records implemented tool
behaviour can stay in the current role; a documentation edit that changes the contract is
architect work.

### Switching from design to build — the hand-off gate

Moving from a **design** role (`architect`) to a **build** role (`engineer`) — from *deciding
structure* to *writing code* — is a **gate**, not a relabel. It is the seam where
[design-flow](../pipelines/design-flow.md) step 8 (Hand off) meets [code-flow](../pipelines/code-flow.md)
step 1 (Take). **Before the first code edit**, in order:

1. **Land the task** — the locked design is recorded as an implementation task in
   `_forge/TASKS.md`, **as a one-line index entry linked to its design doc** (design-flow step 8,
   format: [tasks](../pipelines/tasks.md) — detail by reference, not inlined). A **cold engineer
   session must be able to pick the work from `_forge/TASKS.md` + the linked doc alone** — do not
   carry it only in the current session's head.
2. **Re-read the backlog** — re-read `_forge/TASKS.md` to **sequence** the task against other
   in-flight / planned work and note its dependencies (what it sits on, what it touches) — code-flow
   step 1 Take.
3. **Declare the build role** — announce `🧭 agent: engineer — <focus>` and pull in its pipeline /
   guardrails.

Skipping 1–2 (jumping straight from a design discussion into editing code) is the failure this gate
prevents: the work becomes un-resumable and unsequenced. **Executable side:** the
[`role-on-code`](../hooks/README.md) PreToolUse hook fires on the first code edit of a session and
injects this same checklist — the rule-plus-hook split, as with role declaration and the commit guard.

## Inheritance contract (agent → role)

A project agent charter (`_forge/agents/<role>/README.md`) must:

- **Link** the role file here as its source of requirements and pipeline.
- **Add only project specifics**: which modules/docs/tests it touches, which
  `profiles/` are opted in, project-local skills/tools it uses.
- **Not restate** the role's requirements — link them, so a change here propagates to
  every project after `git submodule update`.

## Adding / changing a role

- New role or changed requirements → here, via PR into keystone (shared for all
  projects). Introduce a **new role** only when the pipeline is *materially* different
  (a distinct ordered cycle and output), not when a profile or a skill would do.
- A project-only way of working → keep it in the agent charter or a local skill; promote
  to a role here only once it proves reusable across projects.
