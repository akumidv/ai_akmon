# 0006 — Transcript-driven orchestrator detection, corridor warning, context pressure

- **Status:** Accepted (extends [0004](0004-model-routing-capability-tiers.md)/[0005](0005-synthesizer-gate-audit-and-role-routing.md);
  revises 0004's committed-agents point; implementation C22–C23). C22 is owner-verified at D2-37 and
  landed in `7312972`, Claude only (Codex pending); the D2-38 amendment below follows an owner-directed choice,
  owner-approved as its ledger row and awaiting the landing commit.
- **Owner:** akuminov@gmail.com
- **References:** design source [`meta/design/model-routing.md` §1 (req 9–12), §3, §4.3, §12](../design/model-routing.md) ·
  C22 landed ([archive](../TASKS_ARCHIVE.md)); C23 in the [backlog](../TASKS.md).

## Context

ADR 0004 bound subagent tiers to the orchestrating model but had no mechanism to *know*
that model: init recorded it once, a mid-session `/model` switch silently left the `k-*`
`model:` frontmatter bound to a stale orchestrator. Its floor warning was also inverted
in practice: with `orchestrator_floor: "highest"`, running on the healthy target (`opus`)
warned, while running the orchestrator on the synthesizer's reserved top rung (`fable`)
— the actually wasteful case — stayed silent. Two further gaps surfaced in live use:
hook warnings went out only as `additionalContext`, which the host UI never shows the
owner (the model saw warnings the owner did not); and the second runtime weakness axis —
the context window filling up — had no detector at all, although the transcript the hook
already reads records per-turn `usage`.

## Decision

1. **The orchestrator is detected, never chosen, by the hook** — from the session
   transcript (`transcript_path`): the last main-chain assistant `message.model`
   (sidechain/subagent turns skipped), mapped to a local alias. Runs at SessionStart and
   every UserPromptSubmit; when the detected alias differs from the recorded one, the
   binding is recomputed and the `k-*` defs regenerated, so **subagent models follow a
   mid-session `/model` switch** with one-turn lag. Only the one-time `init.py` setup
   (the `available` ladder + second-opinion opt-in) stays explicit.
2. **Generated `k-*` agent defs are gitignored + regenerated, not committed** — *revising
   ADR 0004 §8 decision 3*: the `model:` frontmatter now tracks the local orchestrator,
   making the files per-user by construction; committing them churns across users and
   models. The committed source is the registry + project overlay.
3. **The floor warning becomes a corridor:** healthy is `floor ≤ orchestrator < top`,
   with `orchestrator_floor` a *named* alias (anthropic: `opus`). Below the floor → warn
   (too weak, `/model` up); on the top rung while the floor sits lower → warn (the
   synthesizer's reserved tier, wasteful, `/model` down). When the local ladder tops out
   at the floor (no `fable`), `floor == top` and everything collapses to the floor
   silently — the accepted degraded mode. A floor alias absent from the ladder disables
   the corridor; a relative `"highest"` floor (openai keeps it) reproduces the old
   below-top warning. Both warnings stay advisory — the owner's choice stands, and the
   synthesizer's level verdict (ADR 0005) remains the authoritative intelligence check.
4. **Owner-facing hook output goes out on two channels:** everything addressed to the
   owner — init instruction, corridor warning, rebind notice, context-pressure warning —
   is returned as `systemMessage` (UI-visible) *in addition to* `additionalContext`
   (model-visible). The steady-state status line stays context-only. A warning only the
   model sees is a defect.
5. **Context pressure is detected** (design §12): the same transcript pass reads the last
   main-chain `usage`; `fill = input + cache_read + cache_creation` against the model's
   window (registry data: `window_default`/`windows`/`warn_ratios`). Banded warnings
   (0.85 plan / 0.95 critical), throttled by band via a per-session marker, reset when a
   compaction drops the fill back below the lowest band. The hook informs; compaction
   and checkpointing stay the owner's move.

## Consequences

- `routing.py` gains detection (`detect_orchestrator`/`resolve_alias`), shared artifact
  generation + rebind (`binding_artifacts`/`write_artifacts`/`rebind_to`), the corridor
  warning in `compute_binding`, and the context-pressure detector; the model-routing hook
  runs on SessionStart **and** UserPromptSubmit (wired by `sync.py`); consumers gitignore
  `.claude/agents/k-*.md` (BOOTSTRAP §D).
- Registry deltas: `orchestrator_floor: "opus"` (anthropic) + the `context_pressure`
  block — both change the registry hash, so existing local configs go stale once and
  re-init.
- Implementation: C22 (detection + corridor + two-channel delivery) landed in `7312972` and is
  archived after owner verification at D2-37; C23 (context pressure) stays in the backlog until
  D2-38 lands. D2 owner-verify applies to both (hook behaviour is architecture).

## Amendment — context pressure is a share of a recommended maximum (D2-38)

Decision 5 measured the fill against "the model's window". That number is not in the transcript,
so it had to be registry data — and the data was already wrong when checked: main-chain
`claude-opus-5` turns on this machine reach 411,203 tokens with no compaction, while the block
assumed a 200k window. Each model release would make it wrong again, and a larger limit does not
move the point where quality degrades.

The bands are therefore shares of a **recommended maximum context**, not of the model's limit
(owner-directed; the exact contract is the D2-38 row, owner-approved). The registry block's `window_default`/`windows` become `recommended_max`
(default 200000) and `recommended_max_by_alias` (alias-substring exceptions, longest match — e.g.
a model whose hard limit sits below the default); `warn_ratios` is unchanged. A share above 100%
is reported as such. The rename changes the registry hash, so local routing configs go stale once
and re-init; an overlay still using the old keys is ignored. Carrier:
`tools/model_routing/routing.py::recommended_max_context`; the operative contract is
[D2-38](../D2_LEDGER.md) and [design §12.2](../design/model-routing.md).

## Amendment — a one-task context budget, bands 0.85 and 1.0 (D2-42)

The recommended maximum is the recommended active-context budget for a session intended to carry
one task: a session carries the task it is solving, not its history — fewer tokens, less drift
from the task, less forgetting — and the warning is that reminder (owner-directed). The hook knows
neither the task nor what it needs; it sees only the fill, so it is a pressure sensor, and the
boundary between tasks is A21's. 200000 stays — a configurable owner policy set from a typical
one-task development session, not an empirical optimum (C80). The bands become 0.85 (checkpoint;
prepare a focused compact if the task continues) and 1.0 (budget reached — same task: checkpoint
and a task-focused `/compact`; new task: `/clear` or a new session). Every band at or above 1.0 is
one max state whose warning fires once per pressure episode; going on past it is the developer's
call. A fill below the lowest band ends the episode whatever lowered it — decision 5's "a
compaction drops the fill" names one cause, not the mechanism. `AKMON_CONTEXT_RECOMMENDED_MAX`
overrides the budget per user or project. The operative contract is [D2-42](../D2_LEDGER.md) and
[design §12.2](../design/model-routing.md).
