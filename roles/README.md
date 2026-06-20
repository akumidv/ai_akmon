# roles — the cross-project agent role baseline

A **role** is the reusable definition of a development agent: its scope, its
requirements, the pipeline it follows, and the guardrails that bind it. Roles live here
in keystone so every project's agents inherit one standard.

> Role ≠ agent. A role is the *definition*; a project's **agent** (in `_forge/agents/`)
> is the *incarnation* — it inherits a role and adds project specifics. One role may
> have several agents in a project (e.g. two `engineer` agents: backend + data-pipeline).

See the model's three axes in [../README.md](../README.md) §1–3.

## Roles

| Role | Focus | Pipeline | Guardrails |
|---|---|---|---|
| [architect](architect.md) | design, documentation, architecture, requirements, ADRs | [design-flow](../pipelines/design-flow.md) | language `guardrails/` + opted-in `profiles/` |
| [engineer](engineer.md) | code, tests, refactoring | [code-flow](../pipelines/code-flow.md) | language `guardrails/` + opted-in `profiles/` |

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
