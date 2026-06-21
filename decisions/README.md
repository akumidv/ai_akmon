# Decisions — keystone ADRs

Architecture Decision Records for the **keystone standard itself** (SHARED — they travel with
the submodule into every consuming project). This is the standard's analogue of a project's
`docs/dev/decisions/`: a consuming project records its *own* domain/architecture ADRs there, and
inherits keystone's ADRs here.

Conventions ([design-flow](../pipelines/design-flow.md) · [tasks](../pipelines/tasks.md) §No dates):

- One ADR = one decision: the context, the locked choice, the consequences. Options/rationale may
  live in a [`design/`](../design/) concept the ADR references.
- **Numbered, not dated** — `NNNN-kebab-title.md`; the commit history is the timeline.
- Write an ADR only for a **locked, non-trivial** decision (the architect role gate). In-progress
  thinking stays in `design/` until it locks.

## Index

- [0001 — Release/versioning standard and the release/learn roles](0001-release-and-roles-model.md)
  — release as a subject-parameterized DEVELOP role, `learn` extracted as a sibling, two-mode
  release cycle, `v0.x.y`, and subject relativity of the Layer axis. Resolves ROADMAP O2.
