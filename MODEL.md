# akmon — the operative model

What a consuming project applies to follow the standard. The full vision and rationale live in
akmon's own development layer, which a consumer never loads; this file is the **USE surface** —
the rules, not the why. Self-contained by design.

## 1. Three orthogonal axes (do not conflate)

| Axis | Answers | Values |
|---|---|---|
| **Layer** | *where* an artifact lives + *whom it serves* | SHARED / LOCAL / USAGE |
| **Role** | *who performs* the work + by which pipeline | review / architect / engineer / learn / release |
| **Archetype** | *what* the project exposes outward | package / service / mcp / frontend / job / platform / custom |

Each is a type dimension (a kind, not a thing). An **agent is not an axis value** — it is a
concrete point where a role is applied in a project on a layer; a role is the reusable
definition (here), an agent its incarnation in a project (`_aitna/agents/`).

## 2. Layer — a decision tree

```
Does this artifact help DEVELOP this project — or USE it from outside?
├─ DEVELOP ─► common to all my projects, or specific to this one?
│            ├─ common       → SHARED → _aitna/akmon/   (this submodule)
│            └─ this project  → LOCAL  → _aitna/{skills,tools,memory,agents}/
└─ USE from outside ► USAGE → root skills/ (+ tools/ where applicable)
```

| Layer | Job | Consumer | Lives in |
|---|---|---|---|
| **SHARED** | assist development in general | any of my projects | `_aitna/akmon/` |
| **LOCAL** | assist development of *this* project | this repo's developer | `_aitna/{skills,tools,memory,agents}/` |
| **USAGE** | assist *using* what the project exposes | a downstream project | root `skills/` (+ `tools/`) |

SHARED+LOCAL point inward (building this repo); USAGE points outward.

`_aitna/` is the **default** dev-layer root, not a hard-coded literal: a project may relocate it
by declaring `AITNA_ROOT` (a project-root-relative path, e.g. `tools/ai`); akmon then mounts at
`<AITNA_ROOT>/akmon` and the tooling derives every path from it. Unset → `_aitna`.

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

`CAPTURE` (one fact → `_aitna/memory/`) → `DISTILL` (recurring facts → a LOCAL skill/tool/agent
or a refined requirement/ADR) → `PROMOTE` (general + proven → akmon via PR) → `PROPAGATE`
(every project on `git submodule update`). Flow is one-way **up**. Two memories kept distinct:
shared project memory (`_aitna/memory/`, in git) vs each assistant's provider-private memory
(distilled *into* the shared one, never the reverse).

## 7. Inheritance contract (agent → role)

A project agent charter (`_aitna/agents/<role>/README.md`) **links** its akmon role as the
source of requirements + pipeline and **adds only project specifics** — it does not restate the
role, so a change here propagates to every project after `git submodule update`.

## 8. Secrets

From the project `.env` only (`*.env` gitignored; `*.env.example` carries empty placeholders).
Never in code, markdown, or commits.

## 9. Tooling

`bin/sync.py` writes the thin generated vendor pointers (CLAUDE.md, GEMINI.md, …) and hook
wiring from one source; `bin/verify.py` validates the project contract (it reports, never
modifies). Both are stdlib-only and run in-tree.

## 10. Capability tiers — model routing

Roles say *who* performs an operation; tiers say *which model rung* runs it. Delegation is
**by task kind, as a subagent**: the main session (the **orchestrator**) decomposes, routes,
integrates results, and talks to the owner — those are never delegated.

The routing gradient embodies one **leverage principle: quality investment ∝ artifact
leverage** (an artifact's error cost plus the operation/evolution cost everything downstream
inherits from it). The higher the leverage, the stronger the model, the fresher the context,
and the closer to the owner the check — so the strongest rung concentrates at a few
low-token, high-leverage points (a design fork, the pre-fan-out plan check, the whole-gate
audit) while fan-out execution stays cheap. The goal function is quality per unit of **tokens
+ owner attention**; the tiers are how tokens buy quality where leverage is highest.

| Tier | Runs | Bound to |
|---|---|---|
| **orchestrator** | decompose · route · synthesize · owner dialogue | the session's own model — never overridden |
| **reasoner** | load-bearing drafting: deep debugging, design forks, quant derivation, plan drafts | the orchestrator's rung by default; per-kind floors; escalates on signal |
| **auditor** | clean-context audit of a whole gate's material (`audit`) | the **maximal** available rung, always — the highest-leverage check |
| **worker** | delegable realization: exploration, summaries, mechanical edits, gate loops | cheapest adequate rung (`mid` rung for `implement-under-spec`) |
| **second-opinion** | independent review of decisions and code | a *different vendor's* model, opt-in |

The binding surface is the **task-kind matrix** — a finite named list of operations, kept as
data in the routing registry ([`tools/model_routing/registry.json`](tools/model_routing/registry.json)):

| Task kind | Tier |
|---|---|
| `explore-search` · `summarize` · `mech-edit` · `test-scaffold` · `doc-sync` · `validate-loop` | worker |
| `implement-under-spec` | worker (mid rung) |
| `debug-deep` · `design-fork` · `quant-derivation` · `plan-draft` | reasoner |
| `audit` | auditor |
| `independent-review` | second-opinion |
| decompose / route / synthesize / owner dialogue | orchestrator — never delegated |

Which role may route which kind is a second, orthogonal binding — `role_task_kinds` in the
registry — under one invariant: a tier changes who *drafts*, never who *decides*.
**`independent-review` and `audit` are cross-cutting verification kinds**
(`cross_cutting_kinds`): routable from *any* role, because *when* they apply is a structural
trigger (a fan-out touched ≥2 zones, or a findings/options count floor), not the producing
role — the delegation advisory never flags them.

Two policies make the matrix bite: **delegation is the default** (every kind has a named
delegate — the question is "which row is this?", not "is it worth delegating?"), and the
**escalation ladder** (start at the cheapest adequate rung; move up one rung only on failure
signals: gates red twice, the delegate flags uncertainty, a contested fork emerges).

Model names never enter shared process docs or the committed registry as current truth. The
registry records a **semantic selection policy per vendor** (weakest→strongest local discovery
order, worker = lowest, reasoner = the orchestrator's rung, orchestrator floor = highest); concrete model aliases
come from local discovery or an explicit `--available` list and are written only to gitignored
local config / generated harness files. If discovery is unavailable, the binding falls back to
semantic labels and warns instead of pretending those labels are real model ids. A SessionStart
hook displays the binding and a PreToolUse hook logs each delegation at zero token cost. The
static below-floor warning is a **weak prior**, not a gate: with the auditor on, the
whole-gate audit is the authoritative check on whether the session model was strong enough, so a
review/architect-dominant session may deliberately orchestrate below the top rung. Tiers change
who *drafts*, never who *decides* — owner verification stays with the owner, and a second opinion
is advisory input to it, not a sign-off. Cross-vendor review uses the opposite configured provider by default: Claude
sessions ask Codex, Codex sessions ask Claude, unless the project/session explicitly chooses
another provider.

## 11. Principles — the shape in seven lines

The named invariants behind the model, so a proposed change can be tested against them.
Each line is the index entry; the linked artifact owns the full statement.

1. **Leverage** — quality investment ∝ artifact leverage: the strongest model, the freshest
   context, and the closest owner check go where downstream error/evolution cost
   concentrates (§10).
2. **Enforced, not documented** — a rule that must always hold ships with a forcing
   function (a hook), because prose alone decays out of context
   ([README](README.md) — "the smiths are used, not just named"; the commit and analysis
   guards in [guardrails/_common.md](guardrails/_common.md)).
3. **Data over prose** — a binding contract lives as machine-checked data
   ([registry.json](tools/model_routing/registry.json), the sync/verify contracts);
   docs link the owner instead of restating it.
4. **Drafts vs decides** — a tier changes who *drafts*, never who *decides*: owner
   verification stays with the owner; audits and second opinions are advisory input to it
   (§10).
5. **Two budgets** — the goal function is quality per unit of **tokens + owner attention**;
   both are finite, measured, and spent deliberately, not by default (§10).
6. **Isolation by construction** — a delegate's limits are structural, not prompt trust:
   clean context (the auditor receives only a gate-pack) and tool-set rights (audit tiers
   hold no write tools) (§10; worked example: [examples/gate-anatomy.md](examples/gate-anatomy.md)).
7. **One owner per fact** — every table, flow, and rule has exactly one owning artifact;
   everything else links it, so change propagates instead of drifting
   ([guardrails/_common.md](guardrails/_common.md) § Documentation hygiene).
