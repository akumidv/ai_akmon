# roles — the cross-project role baseline

A **role** is the reusable definition of a mode an agent works in: its scope, its
requirements, the pipeline it follows, and the guardrails that bind it. Roles live here
in akmon so every project's agents inherit one standard.

> Role ≠ agent. An **agent** is a unit of responsibility with a repertoire, state and skills; a
> **role** is a mode it works in, selected by operation. The **development agent** works in `review`,
> `architect` and `engineer` — the files in this folder. The learning and release agents work in one
> mode each, `learn` and `release`, defined in their agent definitions ([agents/](../agents/README.md));
> both names stay valid in the role declaration. A project defines an agent in its **charter**,
> `_aitna/agents/<agent>/README.md` — one directory per agent, with one section per role the agent
> works in (`_aitna/agents/development/README.md` → `review`, `architect`, `engineer`). A project's
> own agents each get a charter beside it.

See the model's four axes in [MODEL.md](../MODEL.md) §1–3.

## Roles

The three roles of the development agent are the **analysis → synthesis → realization** triad —
split by cognitive operation, because each mode has its own definition of good and one bar cannot
optimise all three (a reviewer bent on a fix stops analysing; an architect re-deriving the
as-is wastes its budget). The agent that works in them is defined in
[agents/development.md](../agents/development.md); the `learn` and `release` modes belong to the
learning and release agents ([agents/README.md](../agents/README.md)).

| Role | Focus | Pipeline | Guardrails |
|---|---|---|---|
| [review](review.md) | **analysis** — assess what *is*: state/quality/conformance, problems, bottlenecks; output is a report | [review-flow](../pipelines/review-flow.md) | `guardrails/` + language/environment `profiles/` + opted-in domain profiles |
| [architect](architect.md) | **synthesis** — design what *should be*: options, trade-offs, contracts, ADRs | [design-flow](../pipelines/design-flow.md) | `guardrails/` + language/environment `profiles/` + opted-in domain profiles |
| [engineer](engineer.md) | **realization** — code, tests, refactoring | [code-flow](../pipelines/code-flow.md) | `guardrails/` + language/environment `profiles/` + opted-in domain profiles |

## A role file states

1. **Mission** — one sentence: what this role is responsible for.
2. **Scope** — what it acts on (which artifacts) and, explicitly, what it does **not**.
3. **Inputs / outputs** — what it consumes, what it produces.
4. **Pipeline** — the ordered cycle it follows (link a file in `../pipelines/`).
5. **Requirements** — the standards it must meet (verification, ownership, etc.).
6. **Guardrails** — hard constraints; what it must never do.
7. **Done** — the definition of done for its output.

## Role declaration (announce the active role)

The active role is **chosen per task**, not at session start — so each session opens with
no role declared. Before doing project work, the assistant **declares which role it is
operating in**, and **restates it on every switch** (e.g. handing a locked design from
`architect` to `engineer`). This keeps the role — and the pipeline/guardrails it pulls in —
explicit rather than implicit.

- **Format:** put `🧭 role: <name> — <focus>` on the first non-blank line of its own assistant
  turn (e.g. `🧭 role: engineer — code/tests`). `🧭 agent: <name> — <focus>` is still read as an
  alias for one release; write `role:`. Canonical role names are lowercase; the
  Claude-side advisory case-normalizes the name only as input tolerance. Later inline examples and
  Markdown-prefixed quotations are not declarations; a first-position marker is one by definition.
- **If the task is ambiguous** about which role it calls for, ask before proceeding.
- **Executable side:** the [`session-start-agent`](../hooks/README.md) SessionStart hook
  injects this reminder + the project's scanned agent roster each session, so the
  convention survives a long session and does not depend on the doc staying in context (the
  same rule-plus-hook split as the commit guardrail).

### Routing mixed tasks

Some tasks touch both the **model** (what the process should be) and an **executable
mechanism** (a hook, sync script, validator, or local tool). Route them by the decision
being made, and restate the role on every switch.

**The discriminator (the one question that routes any task):** does it **decompose** an
existing thing to understand/measure it → `review` · **construct** a new structure/decision →
`architect` · **realize** a decided structure in code → `engineer`?

| Work | Role |
|---|---|
| Review state/quality/conformance (product / component / element); find problems, bottlenecks, mismatches vs goal/vision/requirements | `review` |
| Produce a findings report / an as-is assessment | `review` |
| akmon model, role boundaries, guardrails, pipeline semantics, roadmap, bootstrap/sync contract | `architect` |
| Project architecture, requirements, ADRs, design docs | `architect` |
| Production code, tests, build config | `engineer` |
| Executable dev tooling (`_aitna/akmon/{bin,tools,hooks}/`, `_aitna/tools/`, validators, sync scripts) | `engineer` |
| Generated pointer output produced by an existing tool | no new role; report what the tool changed |

For a mixed design + tool task: start as `architect`, lock the behaviour/contract, switch
to `engineer` before editing executable code, then switch back to `architect` only for
model or contract documentation. A documentation edit that merely records implemented tool
behaviour can stay in the current role; a documentation edit that changes the contract is
architect work.

### Switching from design to build — the hand-off gate

Moving from a **design** role (`architect`) to a **build** role (`engineer`) — from *deciding
structure* to *writing code* — is a **gate**, not a relabel. It is the seam where
[design-flow](../pipelines/design-flow.md) step 9 (Hand off) meets [code-flow](../pipelines/code-flow.md)
step 1 (Take). **Before the first code edit**, in order:

1. **Record the task** — the accepted decision scope is recorded as an implementation task in
   `_aitna/TASKS.md`, **as a one-line index entry linked to its design and ADR blocks** (design-flow step 9,
   format: [tasks](../pipelines/tasks.md) — detail by reference, not inlined). A **cold engineer
   session must be able to pick the work from `_aitna/TASKS.md` + the linked doc alone** — do not
   carry it only in the current session's head.
2. **Re-read the backlog** — re-read `_aitna/TASKS.md` to **sequence** the task against other
   in-flight / planned work and note its dependencies (what it sits on, what it touches) — code-flow
   step 1 Take.
3. **Declare the build role** — announce `🧭 role: engineer — <focus>` and pull in its pipeline /
   guardrails.

Skipping 1–2 (jumping straight from a design discussion into editing code) is the failure this gate
prevents: the work becomes un-resumable and unsequenced. **Executable side:** the
[`role-on-code`](../hooks/README.md) PreToolUse hook fires on the first code edit of a session and
injects this same checklist — the rule-plus-hook split, as with role declaration and the commit guard.

## Inheritance contract (agent → role)

A project agent charter (`_aitna/agents/<agent>/README.md`) must:

- **Link** the agent's shipped definition ([agents/](../agents/README.md)) and the role file here for
  each role it works in, as that role's source of requirements and pipeline — one section per role (`## review`, `## architect`, `## engineer` in the development
  charter), so a mode's project specifics sit under its own heading.
- **Add only project specifics**: which modules/docs/tests it touches, which
  `profiles/` are opted in, project-local skills/tools it uses.
- **Not restate** the role's requirements — link them, so a change here propagates to
  every project after `git submodule update`.

**Migration (one release).** A directory named for a development role (`_aitna/agents/architect/`,
`engineer/`, `review/`) or for the learn role (`learn/`, now `learning/`) is the pre-0027 layout:
`akmon verify` still passes it, with a `charters.legacy-role-dir` warning. Move its content into the matching section of
`_aitna/agents/development/README.md` (or `learn/` into `learning/`) and delete the directory;
`akmon init` writes the new layout when `development/`, `learning/` or `release/` is absent.

## Adding / changing a role

- New role or changed requirements → here, via PR into akmon (shared for all
  projects). Introduce a **new role** only when the pipeline is *materially* different
  (a distinct ordered cycle and output), not when a profile or a skill would do.
- A project-only way of working → keep it in the agent charter (under its role) or a local skill; promote
  to a role here only once it proves reusable across projects.
