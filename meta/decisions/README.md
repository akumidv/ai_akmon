# Decisions — keystone ADRs

Architecture Decision Records for the **keystone standard itself** (SHARED — they travel with
the submodule into every consuming project). This is the standard's analogue of a project's
`docs/dev/decisions/`: a consuming project records its *own* domain/architecture ADRs there, and
inherits keystone's ADRs here.

Conventions ([design-flow](../../pipelines/design-flow.md) · [tasks](../../pipelines/tasks.md) §No dates):

- One ADR = one cohesive topic. Independently replaceable choices inside it are addressable
  decision blocks with a stable `Decision-ID: ADR-NNNN/DNN`.
- **Numbered, not dated** — `NNNN-kebab-title.md`; the commit history is the timeline.
- Write an ADR only for a **locked, non-trivial** decision (the architect role gate). In-progress
  thinking stays in `design/` until the owner accepts a clearly bounded semantic scope.
- ADR status is `Accepted` or `Superseded`. Implementation progress and versioned evidence live in
  tasks and reviews/measurements, not in ADR status.
- A material change creates a new replacing block or ADR and names what it supersedes. Editorial
  correction does not manufacture another acceptance event.
- `Legacy-ID: D2-N` is a unique compatibility alias for pre-cutover lookup, not a status field.

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
- [0006 — Transcript-driven orchestrator detection, corridor warning, context pressure](0006-orchestrator-detection-corridor-context-pressure.md)
  — orchestrator detected from the session transcript (never chosen), subagents follow a
  mid-session `/model` switch; generated `k-*` defs gitignored + regenerated (revises 0004);
  floor warning becomes a named-floor corridor (`opus ≤ orchestrator < top`, silent collapse
  when the ladder tops out at the floor); owner-facing warnings dual-channel
  (`systemMessage` + context); context-pressure detection from transcript `usage`.
  Extends 0004/0005.
- [0007 — D2 ledger: mechanical tracking of owner-verification points](0007-d2-ledger.md)
  — **Superseded historical record** of the former ledger, reminder, counter and
  `pending → approved → verified` lifecycle; replaced by 0016.
- [0008 — Mythological naming: `_aitna` / `akmon` / Kyklōpes](0008-mythological-naming-aitna-akmon-kyklopes.md)
  — seats the whole system in one myth cluster (Hephaestus's forge beneath Etna): the workspace
  `_aitna/` → `_aitna/` (the volcano-forge, begins with **ai**), the standard `keystone` → `akmon`
  (the anvil, mounted `_aitna/akmon/`), the `k-*` subagents re-read as *Kyklōpes* (prefix kept, no
  migration). Containment (anvil inside volcano = `akmon/` inside `_aitna/`) fixes the mapping;
  reservoir for future entities (keraunos, Hephaistos, …). Supersedes V1's English `anvil`; execution
  in V1. Grandfathers older ADRs.
- [0009 — Packaging: the `akmon` package as carrier, four mount modes incl. `package`](0009-packaging-package-carrier-and-mount-modes.md)
  — one distribution (thin CLI + full tree as package data, hatchling, zero runtime deps, floor
  Python 3.11 as amended by [ADR 0009 D04](0009-packaging-package-carrier-and-mount-modes.md#d04--python-floor-and-manifest-pin-semantics),
  PyPI name `akmon`); mount modes `submodule|vendored|subtree|package`; `package` = dev-group pin,
  no tree in the repo, no skew by construction; as amended by C77 it runs the hooks out of the
  installed package via `akmon hook` and materializes only the guardrails `AGENTS.md` imports;
  init pins the latest tag (`--ref` to override); V1 sweep before first
  publish. Pilot: alphavar.
- [0011 — Agent name notation: `k_*`, one notation for every vendor](0011-agent-name-notation-k-underscore.md)
  — A12 lock: the six generated delegates rename `k-*` → `k_*`, forced by codex's `agent_name` rule
  (lowercase, digits, underscores only) and verified legal on Claude Code before deciding; the ADR 0008
  prefix and its *Kyklōpes* reading survive. Historical records keep the hyphen. Migration ships with it
  (`obsolete_agent_files` prunes stale generated defs on init/rebind); C46 still owns the general
  mechanism — this removes one instance, not the class.
- [0012 — Stage 1 contracts and vocabulary](0012-stage1-contracts-and-vocabulary.md) — the stable
  half of the A12 stage-1 lock: one shared finding envelope (`severity · code · message · target ·
  fix`, no `level` alias, one canonical serializer, public JSON only at `akmon status`, retired
  codes recorded so they cannot be reused), stable
  dotted **policy IDs** joining guardrail prose to `hook_core.*_result` docstrings in both
  directions with the initial seven-callable table pinned as callable↔ID pairs; explicit generated
  ownership modes; two-scope always-loaded caps; a top-level six-axis capability matrix; one
  versioned owner for vendor tool and matcher names; one versioned dispatch-request ledger contract;
  read-only actual-state status composition through the existing verify→sync providers, with the
  transcript-owned active role left explicit as unavailable to the separate status process;
  and the stage's acceptance yardstick — the
  seeding unit is the **independently violable rule**, split rather than waived, with no exemption
  class. **Accepted** in [ADR 0012 D06](0012-stage1-contracts-and-vocabulary.md#d06--stage-1-accepted-scope).
- [0013 — Hook survivability and crash posture](0013-hook-survivability-and-crash-posture.md) — the
  measurement-amendable half: top-level guard in all eight spawned entry points with **crash-open**
  posture including deny-class hooks (fail-closed gated on a live probe + test + tested recovery),
  **probe-gated** Codex timeout support where parse acceptance is not support, timeout budgets
  derived by hook class from measured worst cases, and a **bounded input envelope** whose oversize
  path degrades fail-open with exactly one safe diagnostic. Caps are compatibility boundaries, not
  tuning constants. **Accepted** in [ADR 0013 D02](0013-hook-survivability-and-crash-posture.md#d02--bounded-input-and-timeout-evidence-sequence);
  N6 owns the still-open timeout evidence and literals.
- [0014 — Code rules: principles, standard ruff configuration, and profiles](0014-code-rules-catalog-and-language-profiles.md)
  — universal principles, standard linter configuration, language/environment profiles and the
  `akmon check` wrapper over project-owned checks.
- [0015 — Mission and effective resource allocation](0015-mission-and-resource-allocation.md)
  — human attention, joint decision quality and model work optimized for total outcome, bounded
  by truthfulness and product-goal fit.
- [0016 — Thematic decision records and owner acceptance](0016-decision-records-and-owner-acceptance.md)
  — separates open design, accepted blocks, implementation state and evidence; supersedes the D2
  lifecycle and defines stable block IDs plus legacy lookup.
- [0017 — Skill discovery and delivery](0017-skill-discovery-and-delivery.md)
  — one result-first selector description and compatible Claude/Codex delivery.
- [0018 — Release alignment and update lifecycle](0018-release-alignment-and-update-lifecycle.md)
  — version consistency, hand-owned alignment boundaries, explicit update and rollback.
- [0019 — Collaboration guidance changes from the A22 evaluation](0019-collaboration-guidance-from-a22.md)
  — A22's accepted outcomes with the evidence in plain terms; D01: no new claim-calibration rule,
  since neither the clause nor the worked examples improved on the standard in context on two vendors.
- [0020 — Node.js consumers: a JavaScript implementation, an npm carrier, one behavioral spec](0020-node-consumers-js-implementation.md)
  — two permanent implementations (Python, JavaScript) bound by a normative process-level
  conformance corpus; Python-free only in Node `package` mode; JS + JSDoc, Node ≥22, vendored
  smol-toml; npm carrier with one version line and file list; `node` hook wiring; all tools ported
  behind `akmon tool` and exported for JS projects; Node checks per ADR 0014. Narrows ADR 0009
  D01/D02 for executable code.
