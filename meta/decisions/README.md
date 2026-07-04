# Decisions — keystone ADRs

Architecture Decision Records for the **keystone standard itself** (SHARED — they travel with
the submodule into every consuming project). This is the standard's analogue of a project's
`docs/dev/decisions/`: a consuming project records its *own* domain/architecture ADRs there, and
inherits keystone's ADRs here.

Conventions ([design-flow](../../pipelines/design-flow.md) · [tasks](../../pipelines/tasks.md) §No dates):

- One ADR = one decision: the context, the locked choice, the consequences. Options/rationale may
  live in a [`design/`](../design/) concept the ADR references.
- **Numbered, not dated** — `NNNN-kebab-title.md`; the commit history is the timeline.
- Write an ADR only for a **locked, non-trivial** decision (the architect role gate). In-progress
  thinking stays in `design/` until it locks.

## Index

- [0001 — Release/versioning standard and the release/learn roles](0001-release-and-roles-model.md)
  — release as a subject-parameterized DEVELOP role, `learn` extracted as a sibling, two-mode
  release cycle, `v0.x.y`, and subject relativity of the Layer axis. Resolves ROADMAP O2.
- [0002 — Typed task-id convention](0002-task-id-convention.md) — task ids carry a type letter
  (A architecture/design · C code · L learning · V release) + number, role derived; optional
  `[#issue]` GitHub link; legacy `T#` grandfathered.
- [0003 — Role triad and develop/use separation](0003-role-triad-and-develop-use-separation.md)
  — review/architect/engineer as analysis/synthesis/implementation; keystone DEVELOP vs USE
  separation; adds task letter N (analysis/review), amending 0002.
- [0004 — Model routing: capability tiers, task-kind matrix, ladder binding](0004-model-routing-capability-tiers.md)
  — vendor-neutral tiers; task-kind→tier matrix as registry data (delegation by default,
  escalate-on-signal); ranked alias ladder with binding computed from the orchestrating model;
  init tool + SessionStart/delegation-log hooks; orchestrator display + weak-orchestrator
  warning; second-opinion advisory, never replacing owner verification.
- [0005 — Synthesizer gate audit, dynamic reasoner, plan-draft, role routing rights](0005-synthesizer-gate-audit-and-role-routing.md)
  — pinned-max `synthesizer` tier + `k-synthesizer` (clean-context whole-material audit at
  gates, level verdict); reasoner goes dynamic (orchestrator rung + per-kind floors);
  second-opinion = model diversity ladder; `plan-draft` row + pre-fan-out plan check;
  gate-pack protocol; `role_task_kinds` routing rights; owner-attention budget. Extends 0004.
