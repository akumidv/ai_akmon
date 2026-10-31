# Agent: development

**Responsibility.** Turn a task into a reviewed change — analyse what is, design what should be,
realize it in code with tests, and verify it — and hand the finished change to integration
(ADR 0026/D01).

The development agent owns that responsibility, its repertoire and its state; the three roles below
are the modes it works in, selected by operation. Each role keeps its own quality bar, because one
bar cannot optimize analysis, synthesis and realization at once
(ADR 0003). The audit stays a delegate
tier the agent calls ([MODEL.md](../MODEL.md) § Capability tiers), not a role.

---

## Roles

| Role | Mode | Pipeline |
|---|---|---|
| [review](../roles/review.md) | **analysis** — assess what *is*; the output is a report | [review-flow](../pipelines/review-flow.md) |
| [architect](../roles/architect.md) | **synthesis** — design what *should be*: options, contracts, ADRs | [design-flow](../pipelines/design-flow.md) |
| [engineer](../roles/engineer.md) | **realization** — code, tests, refactoring | [code-flow](../pipelines/code-flow.md) |

All three run under [pre-commit](../pipelines/pre-commit.md) before a change is offered, and the
backlog format of [tasks](../pipelines/tasks.md). The role is declared per task
(`🧭 role: <name> — <focus>`, see [roles/README.md](../roles/README.md)), never the agent.

## Hand-off

The development agent delivers a reviewed change and its task record to the **integration** agent
(ADR 0026/D03), which decides the merge. It does not merge its own change, and it does not cut a
release — that is the [release agent](release.md).

## Repertoire

The development agent's repertoire — the actions it may take and under which actor of the run — is
task C173's; this definition names none until it lands.

## Charter

A project defines its development agent in `agents/development/README.md` under its dev-layer root:
one section per role, carrying only the project's specifics.
